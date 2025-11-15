# pysi/app/scenario_runner.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, os, sqlite3, json, re
from typing import Dict, Any, List, Tuple
from datetime import date
from pysi.db.apply_schema import apply_schema
from pysi.db.calendar_sync import sync_calendar_iso
from pysi.etl.etl_monthly_to_lots import run_etl
from pysi.io.psi_io_adapters import (
    _open, get_scenario_id, get_node_id, get_product_id,
    write_both_layers, load_leaf_S_and_compute
)
# 冪等パス（存在しない環境ではフォールバック）
try:
    from pysi.plan.run_pass import run_idempotent_demand_pass
except Exception:
    run_idempotent_demand_pass = None
# レポート
try:
    from pysi.report.psi_report import fetch_weekly_counts, get_scenario_id as _rep_sid, get_node_id as _rep_nid, get_product_id as _rep_pid, plot_weekly
except Exception:
    fetch_weekly_counts = None
LOT_SEP = "-"
def _sanitize_token(s: str) -> str:
    return str(s).replace(LOT_SEP,"").replace(" ","").strip()
def _iso_str_to_year_week(s: str) -> Tuple[int,int]:
    m = re.fullmatch(r"(\d{4})-W(\d{2})", s.strip())
    if not m: raise ValueError(f"bad ISO week: {s}")
    return int(m.group(1)), int(m.group(2))
def _rebuild_lots_from_weekly(conn: sqlite3.Connection, scenario_id: int, node_id: int, product_id: int):
    """
    weekly_demand → lot を再生成（node×product全週）。冪等化のため一度DELETE→INSERT。
    lot_id形式: NODE-PROD-YYYYWWNNNN（週ごとに 0001 リセット）
    """
    cur = conn.execute("""
        SELECT wd.iso_year, wd.iso_week, wd.value,
               coalesce(np.lot_size,1)
        FROM weekly_demand wd
        JOIN node n ON n.id=wd.node_id
        JOIN product p ON p.id=wd.product_id
        LEFT JOIN node_product np ON np.node_id=wd.node_id AND np.product_id=wd.product_id
        WHERE wd.scenario_id=? AND wd.node_id=? AND wd.product_id=?
        ORDER BY wd.iso_year, wd.iso_week
    """, (scenario_id, node_id, product_id))
    rows = cur.fetchall()
    # 既存 lot を削除
    with conn:
        conn.execute("""DELETE FROM lot WHERE scenario_id=? AND node_id=? AND product_id=?""",
                     (scenario_id, node_id, product_id))
    # 週ごとに 0001 リセットで生成
    lots = []
    # 取得しておく（名前 → lot_idベース作成に使用）
    node_name = conn.execute("SELECT name FROM node WHERE id=?", (node_id,)).fetchone()[0]
    product_name = conn.execute("SELECT name FROM product WHERE id=?", (product_id,)).fetchone()[0]
    nn = _sanitize_token(node_name)
    pn = _sanitize_token(product_name)
    for (y, w, val, lot_size) in rows:
        lot_size = max(1, int(lot_size or 1))
        cnt = int((float(val) + lot_size - 1)//lot_size) if float(val)>0 else 0
        base = f"{nn}{LOT_SEP}{pn}{LOT_SEP}{int(y)}{int(w):02d}"
        for i in range(1, cnt+1):
            lots.append((scenario_id, node_id, product_id, int(y), int(w), f"{base}{i:04d}"))
    if lots:
        with conn:
            conn.executemany("""
                INSERT INTO lot(scenario_id,node_id,product_id,iso_year,iso_week,lot_id)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(lot_id) DO UPDATE SET
                  scenario_id=excluded.scenario_id,
                  node_id=excluded.node_id,
                  product_id=excluded.product_id,
                  iso_year=excluded.iso_year,
                  iso_week=excluded.iso_week
            """, lots)
def _apply_action(conn: sqlite3.Connection, sid: int, action: Dict[str,Any]):
    t = action.get("type")
    if t == "demand_scale":
        node = action["node"]; product = action["product"]
        y0,w0 = _iso_str_to_year_week(action["from"])
        y1,w1 = _iso_str_to_year_week(action["to"])
        factor = float(action["factor"])
        nid = get_node_id(conn, node); pid = get_product_id(conn, product)
        with conn:
            conn.execute("""
                UPDATE weekly_demand
                SET value = value * ?
                WHERE scenario_id=? AND node_id=? AND product_id=?
                  AND (iso_year, iso_week) BETWEEN (?, ?) AND (?, ?)
            """, (factor, sid, nid, pid, y0, w0, y1, w1))
        _rebuild_lots_from_weekly(conn, sid, nid, pid)
    elif t == "shutdown_weeks":
        node = action["node"]; weeks = [ _iso_str_to_year_week(w) for w in action["weeks"] ]
        # long_vacation_weeks は week_index で持つのが最適：ここでは iso_week（年内番号）を簡易反映
        # 実運用では calendar_iso とJOINして week_index配列に変換するのが堅牢
        nid = get_node_id(conn, node)
        # node_product 単位に持つ設計の場合、既存行に対し JSON配列を更新するなど実装差あり。
        # デモとして node 単位でメモ: 別テーブルを推奨だが最小例として node.name 属性的に保持できないため省略。
        print(f"[INFO] shutdown weeks requested for {node}: {weeks} (reflect via engine policy using node.long_vacation_weeks)")
    elif t == "leadtime_set":
        node = action["node"]; product = action["product"]; lt = int(action["leadtime"])
        nid = get_node_id(conn, node); pid = get_product_id(conn, product)
        with conn:
            # 無ければINSERT
            conn.execute("""
               INSERT INTO node_product(node_id,product_id,lot_size,leadtime,ss_days,long_vacation_weeks)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(node_id,product_id)
               DO UPDATE SET leadtime=excluded.leadtime
            """, (nid,pid,1,lt,0,None))
    else:
        raise ValueError(f"unknown action: {t}")
def _report(conn: sqlite3.Connection, scenario: str, outdir: str, fmt: str, targets: List[Dict[str,str]]):
    if fetch_weekly_counts is None:
        print("[WARN] report module not available")
        return []
    sid = _rep_sid(conn, scenario)
    imgs = []
    for t in targets:
        nid = _rep_nid(conn, t["node"])
        pid = _rep_pid(conn, t["product"])
        df = fetch_weekly_counts(conn, sid, nid, pid, t.get("layer","demand"))
        os.makedirs(outdir, exist_ok=True)
        base = os.path.join(outdir, f"{scenario}_{t.get('layer','demand')}_{t['node']}_{t['product']}")
        img = plot_weekly(df, f"{scenario}/{t.get('layer','demand')}/{t['node']}/{t['product']}", f"{base}_weekly_chart", fmt=fmt, show=False)
        df.to_csv(f"{base}_weekly_counts.csv", index=False, encoding="utf-8-sig")
        imgs.append(img)
    return imgs
def run_from_yaml(cfg: Dict[str,Any]) -> Dict[str,Any]:
    db = cfg["db"]; scenario = cfg["scenario"]
    conn = _open(db)
    # スキーマは存在前提（必要ならここでapply_schemaを呼んでもOK）
    if "etl" in cfg and cfg["etl"]:
        run_etl(db, cfg["etl"]["csv"], scenario, cfg["etl"].get("default_lot_size"))
    # カレンダ同期（CSV or 明示境界）
    cal = cfg.get("calendar", {})
    weeks = sync_calendar_iso(
        conn,
        scenario_name=scenario,
        csv_path=cal.get("from_csv"),
        plan_year_st=cal.get("plan_year_st"),
        plan_range=cal.get("plan_range"),
        clear_lot_bucket_on_change=True,
    )
    sid = get_scenario_id(conn, scenario)
    # アクション適用（C/V/M）
    for act in (cfg.get("actions") or []):
        _apply_action(conn, sid, act)
    # 計算：葉へS注入→冪等パス→書戻し
    mode = cfg.get("mode","leaf")
    if mode == "leaf":
        # lotから自動検出された (node,product) は orchestrator側で可能。ここは簡易版として全lotを対象にする
        pairs = conn.execute("""
            SELECT DISTINCT n.name, p.name
            FROM lot l
            JOIN node n ON n.id=l.node_id
            JOIN product p ON p.id=l.product_id
            WHERE l.scenario_id=?
            ORDER BY n.name, p.name
        """,(sid,)).fetchall()
        # 葉ノードのPlanNodeを動的生成せず、各pairごとに単ノード計算でも良いが、
        # ここでは既存leaf注入→copy→書戻しの最小ルートを使用
        from pysi.network.node_base import PlanNode
        for node_name, product_name in pairs:
            leaf = PlanNode(node_name)
            load_leaf_S_and_compute(conn, scenario_id=sid, node_obj=leaf, product_name=product_name)
            write_both_layers(conn, scenario_id=sid, node_obj=leaf, product_name=product_name, replace_slice=True)
    else:
        # tree: 既存のファクトリを使用
        spec = cfg.get("network")
        if not spec:
            raise ValueError("tree mode requires 'network' (pkg.module:factory)")
        import importlib
        mod, fn = spec.split(":")
        root = getattr(importlib.import_module(mod), fn)()
        # 既に lot → leaf 注入は orchestrator流儀を踏襲すべきだが、ここは省略
        if run_idempotent_demand_pass:
            run_idempotent_demand_pass(root)
        # root等の書戻しは省略（必要なら追記）
    # レポート
    imgs = []
    rep = cfg.get("report")
    if rep:
        imgs = _report(conn, scenario, rep.get("outdir","var/report"), rep.get("fmt","png"), rep.get("targets",[]))
    out = {"weeks": weeks, "reports": imgs}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="YAML scenario file")
    args = ap.parse_args()
    import yaml
    cfg = yaml.safe_load(open(args.config, "r", encoding="utf-8"))
    run_from_yaml(cfg)
if __name__ == "__main__":
    main()
