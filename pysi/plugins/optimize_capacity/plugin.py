# pysi/plugins/optimize_capacity.py
"""
Optimize capacity plugin
- 読み込むCSV: data/node_geo.csv (capacity列があれば読取)
- Runner から渡される ctx に対し、'env' 内の global_nodes の capacity を更新する。
- pulp が入っていれば LP、無ければシンプル補正を行う。
"""

from typing import Any, Dict
import logging
import csv
from pathlib import Path

try:
    import pulp
    HAS_PULP = True
except Exception:
    HAS_PULP = False

logger = logging.getLogger(__name__)

CSV_FILES = {
    "node_geo": "node_geo.csv",
    "p_month": "sku_P_month_data.csv",
    "s_month": "sku_S_month_data.csv",
    "S_month": "S_month_data.csv",
}

def register(bus):
    
    bus.add_action("pipeline:before_planning", on_pre_plan, priority=10)
    # またはもっと早めにしたいなら
    # bus.add_action("pipeline:after_build", on_pre_plan, priority=90)

    #bus.register("pre_plan", on_pre_plan)

    logger.info("[plugin] optimize_capacity registered for pre_plan")

def _read_csv_dicts(data_dir: Path, name: str):
    p = data_dir / name
    if not p.exists():
        return []
    rows = []
    with p.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows

def on_pre_plan(ctx: Dict[str, Any]) -> None:
    logger.info("[optimize_capacity] start")
    # 1) data_dir を探す（ctx から優先的に取り出す）
    data_dir = None
    if "data_dir" in ctx:
        data_dir = Path(ctx["data_dir"])
    else:
        # try to derive from env if present
        env = ctx.get("env")
        if env and hasattr(env, "data_dir"):
            data_dir = Path(getattr(env, "data_dir"))
    if not data_dir:
        # fallback to repo/data
        repo_root = Path(__file__).resolve().parents[2]
        data_dir = repo_root / "data"
    # 2) read CSVs
    p_rows = _read_csv_dicts(data_dir, CSV_FILES["p_month"])
    s_rows = _read_csv_dicts(data_dir, CSV_FILES["s_month"])
    nodes_rows = _read_csv_dicts(data_dir, CSV_FILES["node_geo"])

    # 3) aggregate total demand by sku (simple)
    total_demand = 0
    for r in p_rows:
        q = r.get("plan_qty") or r.get("qty") or r.get("plan_qty_month") or r.get("plan")
        try:
            total_demand += int(float(q))
        except Exception:
            continue

    # 4) current total capacity from nodes_rows or env.global_nodes
    env = ctx.get("env")
    node_caps = {}
    if env and hasattr(env, "global_nodes") and env.global_nodes:
        for n, node_obj in env.global_nodes.items():
            cap = getattr(node_obj, "capacity", None)
            node_caps[n] = int(cap) if cap is not None else 0
    else:
        for r in nodes_rows:
            node = r.get("node") or r.get("node_id") or r.get("name")
            cap = r.get("capacity") or r.get("cap") or 0
            try:
                node_caps[node] = int(float(cap))
            except Exception:
                node_caps[node] = 0

    cur_total = sum(node_caps.values())
    logger.info("[optimize_capacity] total_demand=%d cur_total_capacity=%d", total_demand, cur_total)

    if cur_total >= total_demand:
        logger.info("[optimize_capacity] capacity sufficient, no change")
        return

    deficit = total_demand - cur_total
    logger.info("[optimize_capacity] deficit=%d -> applying optimization", deficit)

    # 5) Solve: try pulp
    if HAS_PULP and node_caps:
        logger.info("[optimize_capacity] solving LP via pulp")
        prob = pulp.LpProblem("cap_opt", pulp.LpMinimize)
        x = {n: pulp.LpVariable(f"cap_{n}", lowBound=node_caps[n]) for n in node_caps}
        capex_unit = 1.0  # 単位投資コストの仮値。将来的にCSV/設定から取得する
        prob += pulp.lpSum([(x[n] - node_caps[n]) * capex_unit for n in node_caps])
        prob += pulp.lpSum([x[n] for n in node_caps]) >= total_demand
        prob.solve(pulp.PULP_CBC_CMD(msg=False))
        for n in node_caps:
            v = pulp.value(x[n])
            if v is None:
                continue
            node_caps[n] = int(round(v))
    else:
        # fallback greedy: evenly distribute deficit
        logger.info("[optimize_capacity] pulp not available, applying greedy distribution")
        keys = list(node_caps.keys())
        if not keys:
            logger.warning("[optimize_capacity] no node capacity info available, aborting")
            return
        add_per = max(1, int(deficit / len(keys)))
        for i, k in enumerate(keys):
            node_caps[k] += add_per
        # if rounding left-over
        rem = total_demand - sum(node_caps.values())
        i = 0
        while rem > 0:
            node_caps[keys[i % len(keys)]] += 1
            rem -= 1
            i += 1

    # 6) apply back to env.global_nodes if present
    if env and hasattr(env, "global_nodes") and env.global_nodes:
        for n, newcap in node_caps.items():
            node_obj = env.global_nodes.get(n)
            if node_obj and hasattr(node_obj, "capacity"):
                try:
                    setattr(node_obj, "capacity", int(newcap))
                except Exception:
                    pass
    else:
        # else write back to node_geo.csv as a convenience (not overwriting original, write debug file)
        outp = data_dir / "_node_geo_after_opt.csv"
        try:
            with outp.open("w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["node", "capacity"])
                for n, c in node_caps.items():
                    w.writerow([n, c])
            logger.info("[optimize_capacity] wrote node capacity to %s", outp)
        except Exception as e:
            logger.exception("failed to write debug node csv: %s", e)

    # push back context
    ctx["env"] = env
    logger.info("[optimize_capacity] done")
