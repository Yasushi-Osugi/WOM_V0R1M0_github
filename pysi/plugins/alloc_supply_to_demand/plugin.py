
# pysi/plugins/alloc_supply_to_demand.py
"""
Alloc supply to demand plugin
- data/sku_P_month_data.csv (plan側)
- data/sku_S_month_data.csv or data/S_month_data.csv (supply側)
- 出力: ctx['pre_allocations'] = list of dicts with keys:
    month, sku, supply_node, demand_node, qty
"""

from typing import Any, Dict, List
import logging
import csv
from pathlib import Path

logger = logging.getLogger(__name__)

P_FILE = "sku_P_month_data.csv"
S_FILE_CANDIDATES = ["sku_S_month_data.csv", "S_month_data.csv"]

def register(bus):
    bus.register("pre_plan", on_pre_plan)
    logger.info("[plugin] alloc_supply_to_demand registered for pre_plan")

def _read_csv_rows(path: Path):
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows

def on_pre_plan(ctx: Dict[str, Any]) -> None:
    logger.info("[alloc_supply_to_demand] start")
    # find data_dir
    data_dir = None
    if "data_dir" in ctx:
        data_dir = Path(ctx["data_dir"])
    else:
        # try env
        env = ctx.get("env")
        if env and hasattr(env, "data_dir"):
            data_dir = Path(getattr(env, "data_dir"))
    if not data_dir:
        repo_root = Path(__file__).resolve().parents[2]
        data_dir = repo_root / "data"

    p_path = data_dir / P_FILE
    s_path = None
    for cand in S_FILE_CANDIDATES:
        t = data_dir / cand
        if t.exists():
            s_path = t
            break

    p_rows = _read_csv_rows(p_path)
    s_rows = _read_csv_rows(s_path) if s_path else []

    # normalize numeric fields and keys
    def safe_int(val):
        try:
            return int(float(val))
        except Exception:
            return 0

    # index supplies by (month, sku)
    supply_idx = {}
    for r in s_rows:
        month = r.get("month") or r.get("period") or r.get("ym")
        sku = r.get("sku") or r.get("product") or r.get("product_id")
        try:
            avail = safe_int(r.get("supply_qty") or r.get("qty") or r.get("supply"))
        except Exception:
            avail = 0
        node = r.get("node") or r.get("snode") or r.get("site")
        key = (month, sku)
        supply_idx.setdefault(key, []).append({
            "node": node,
            "avail": avail,
            "raw": r
        })

    allocations: List[Dict[str,Any]] = []
    for r in p_rows:
        month = r.get("month") or r.get("period") or r.get("ym")
        sku = r.get("sku") or r.get("product") or r.get("product_id")
        demand_node = r.get("node") or r.get("dnode") or r.get("site")
        req = safe_int(r.get("plan_qty") or r.get("qty") or r.get("demand"))
        if req <= 0:
            continue
        key = (month, sku)
        supplies = supply_idx.get(key, [])
        # simple: iterate supplies and take as much as possible
        for s in supplies:
            if req <= 0:
                break
            take = min(req, s["avail"])
            if take <= 0:
                continue
            allocations.append({
                "month": month,
                "sku": sku,
                "supply_node": s["node"],
                "demand_node": demand_node,
                "qty": take
            })
            s["avail"] -= take
            req -= take
        # if remaining req > 0, record as unmet demand
        if req > 0:
            allocations.append({
                "month": month,
                "sku": sku,
                "supply_node": None,
                "demand_node": demand_node,
                "qty": -req  # negative qty denotes unmet
            })

    ctx["pre_allocations"] = allocations
    logger.info("[alloc_supply_to_demand] allocations computed: %d", len(allocations))
