# psi_consistency_tests.py
# -*- coding: utf-8 -*-
"""
Step 5: Minimum Consistency Tests for Global Weekly PSI Planner
チェック項目
-----------
1) 週数一致（calendar_iso と node の psi 長さ）
2) lot / lot_bucket の重複なし（UNIQUEが効いているか）
3) 保存則（葉ノード：Σ|S| == Σ|P| after S->P）
4) 休暇週に S を置かない（親Sは postorder集約後に検証）
5) 書き戻しの冪等性（同じ書き戻しを2回実行しても増えない）
前提
----
- Step 1〜4 を完了済み（DDL/ETL/I/Oアダプタ）
- PlanNode/Node は既存実装を使用
- Windows の標準 sqlite3 でOK
使い方（最小例）
---------------
python psi_consistency_tests.py --db psi.sqlite --scenario Baseline --product RICE --node TOKYO --leaf
（親ノードの休暇週Sなし検証は --parent オプション）
"""
from __future__ import annotations
import argparse
import sqlite3
from typing import Dict, List, Tuple
# Step4 のI/Oアダプタを利用
from psi_io_adapters import (
    _open, get_scenario_id, get_node_id, get_product_id,
    get_scenario_bounds, calendar_map_for_scenario,
    load_leaf_S_and_compute, write_both_layers
)
# ----------------------------
# DB helpers
# ----------------------------
def calendar_weeks_for_scenario(conn: sqlite3.Connection, scenario_id: int) -> int:
    y0, pr = get_scenario_bounds(conn, scenario_id)
    y1 = y0 + pr - 1
    row = conn.execute(
        "SELECT COUNT(*) FROM calendar_iso WHERE iso_year BETWEEN ? AND ?",
        (y0, y1),
    ).fetchone()
    return int(row[0] or 0)
def count_rows(conn: sqlite3.Connection, sql: str, params=()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])
# ----------------------------
# Checks
# ----------------------------
def check_week_length(conn: sqlite3.Connection, scenario_id: int, node) -> Tuple[bool, str]:
    want = calendar_weeks_for_scenario(conn, scenario_id)
    got_d = len(getattr(node, "psi4demand", []))
    got_s = len(getattr(node, "psi4supply", []))
    ok = (got_d == want) and (got_s == want)
    msg = f"weeks demand={got_d}, supply={got_s}, calendar={want}"
    return ok, msg
def check_no_duplicates_lot(conn: sqlite3.Connection) -> Tuple[bool, str]:
    c_all = count_rows(conn, "SELECT COUNT(*) FROM lot")
    c_dist = count_rows(conn, "SELECT COUNT(DISTINCT lot_id) FROM lot")
    ok = (c_all == c_dist)
    return ok, f"lot rows={c_all}, distinct_lot_id={c_dist}"
def check_no_duplicates_lot_bucket(conn: sqlite3.Connection, scenario_id: int) -> Tuple[bool, str]:
    c_all = count_rows(conn, "SELECT COUNT(*) FROM lot_bucket WHERE scenario_id=?", (scenario_id,))
    c_dist = count_rows(conn, """
        SELECT COUNT(*) FROM (
          SELECT DISTINCT scenario_id, layer, node_id, product_id, week_index, bucket, lot_id
          FROM lot_bucket WHERE scenario_id=?
        )
    """, (scenario_id,))
    ok = (c_all == c_dist)
    return ok, f"lot_bucket rows={c_all}, distinct_key={c_dist}"
def check_leaf_conservation(node) -> Tuple[bool, str]:
    """
    葉ノードで S->P 後に Σ|S| == Σ|P| （同一ノード内の SS/休暇シフトはあっても保存則は成立）
    """
    psi = getattr(node, "psi4demand", [])
    s_sum = sum(len(week[0]) for week in psi)
    p_sum = sum(len(week[3]) for week in psi)
    ok = (s_sum == p_sum)
    return ok, f"leaf conservation: sum(S)={s_sum}, sum(P)={p_sum}"
def check_parent_vacation_no_S(node) -> Tuple[bool, str]:
    """
    親ノードで、long_vacation_weeks に S が置かれていない（postorder集約後前提）
    ※ aggregate_children_P_into_parent_S(..., vacation_policy='shift_to_next_open') を使った場合に成立
    """
    vac = set(int(w) for w in getattr(node, "long_vacation_weeks", []) or [])
    psi = getattr(node, "psi4demand", [])
    bad = []
    for w in vac:
        if 0 <= w < len(psi):
            if len(psi[w][0]) > 0:
                bad.append(w)
    ok = (len(bad) == 0)
    return ok, f"vacation weeks with S placed = {bad}"
def check_db_write_idempotent(conn: sqlite3.Connection, scenario_id: int, node, product_name: str) -> Tuple[bool, str]:
    """
    lot_bucket 書き戻しを2回やっても増えない（replace_slice=True 推奨）
    """
    before = count_rows(conn, """
        SELECT COUNT(*) FROM lot_bucket
        WHERE scenario_id=? AND node_id=? AND product_id=?""",
        (scenario_id, get_node_id(conn, node.name), get_product_id(conn, product_name))
    )
    # 1回目
    write_both_layers(conn, scenario_id=scenario_id, node_obj=node, product_name=product_name, replace_slice=True)
    mid = count_rows(conn, """
        SELECT COUNT(*) FROM lot_bucket
        WHERE scenario_id=? AND node_id=? AND product_id=?""",
        (scenario_id, get_node_id(conn, node.name), get_product_id(conn, product_name))
    )
    # 2回目（冪等）
    write_both_layers(conn, scenario_id=scenario_id, node_obj=node, product_name=product_name, replace_slice=True)
    after = count_rows(conn, """
        SELECT COUNT(*) FROM lot_bucket
        WHERE scenario_id=? AND node_id=? AND product_id=?""",
        (scenario_id, get_node_id(conn, node.name), get_product_id(conn, product_name))
    )
    ok = (mid == after)
    return ok, f"lot_bucket rows before={before}, after1={mid}, after2={after}"
# ----------------------------
# Runner
# ----------------------------
def run_min_checks(
    conn: sqlite3.Connection,
    *,
    scenario_name: str,
    node,
    product_name: str,
    is_leaf: bool,
    check_vacation_on_parent: bool = False
) -> Dict[str, Tuple[bool, str]]:
    """
    まとめて実行。node は既存の PlanNode/Node インスタンス（name が DB の node.name と一致していること）。
    葉の場合は DB→S注入→S->P→コピーまで先に実施。
    """
    scenario_id = get_scenario_id(conn, scenario_name)
    # 葉なら DB から S 注入 → S->P → 需要→供給コピー
    if is_leaf:
        load_leaf_S_and_compute(
            conn, scenario_id=scenario_id,
            node_obj=node, product_name=product_name, layer="demand"
        )
    results: Dict[str, Tuple[bool, str]] = {}
    results["week_length"] = check_week_length(conn, scenario_id, node)
    results["no_dup_lot"] = check_no_duplicates_lot(conn)
    results["no_dup_lot_bucket"] = check_no_duplicates_lot_bucket(conn, scenario_id)
    if is_leaf:
        results["leaf_conservation"] = check_leaf_conservation(node)
    if check_vacation_on_parent:
        results["parent_vacation_no_S"] = check_parent_vacation_no_S(node)
    # 書き戻し冪等性（両レイヤ書く）
    results["write_idempotent"] = check_db_write_idempotent(conn, scenario_id, node, product_name)
    return results
# ----------------------------
# CLI
# ----------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="SQLite file path")
    ap.add_argument("--scenario", required=True, help="scenario name")
    ap.add_argument("--product", required=True, help="product name")
    ap.add_argument("--node", required=True, help="node name (must match PlanNode.name)")
    ap.add_argument("--leaf", action="store_true", help="treat node as leaf (inject S from DB and compute S->P)")
    ap.add_argument("--parent", action="store_true", help="run vacation S-empty check on this node")
    args = ap.parse_args()
    # --- ユーザ環境の PlanNode を作る（最低限 name が一致していればOK）
    # 既にあなたのコードで PlanNode がある前提：
    try:
        from pysi.network.node_base import PlanNode
    except Exception:
        print("[ERR] Could not import PlanNode from your project. Ensure PYTHONPATH is set.")
        return
    node = PlanNode(args.node)
    # 任意：必要なら SS/休暇を手動セット（DBから読みたい場合はここを拡張）
    # node.SS_days = 7
    # node.long_vacation_weeks = []
    conn = _open(args.db)
    results = run_min_checks(
        conn,
        scenario_name=args.scenario,
        node=node,
        product_name=args.product,
        is_leaf=args.leaf,
        check_vacation_on_parent=args.parent
    )
    print("=== Consistency Report ===")
    ok_all = True
    for key, (ok, msg) in results.items():
        print(f"[{key:20}] {'OK' if ok else 'NG'} - {msg}")
        ok_all = ok_all and ok
    print("==========================")
    print("OVERALL:", "PASS ✅" if ok_all else "FAIL ❌")
if __name__ == "__main__":
    main()
#これで確認できること
#
#週数一致：calendar_iso の週数と、psi4demand/psi4supply の配列長が一致。
#
#重複なし：lot と lot_bucket の行数＝DISTINCT 行数。
#
#保存則（葉）：S を SS/休暇で P にシフトしても、総ロット数が保存。
#
#休暇週（親）：postorder集約後、親の休暇週に S が置かれていない（ポリシーどおり）。
#
#冪等性：lot_bucket 書き戻しを2回実行しても 行数が増えない。
#
#実行例
## 葉ノード（TOKYO, RICE）をチェック
#python psi_consistency_tests.py --db psi.sqlite --scenario Baseline --product RICE --node TOKYO --leaf
#
## 親ノード（JAPAN_DC, RICE）：休暇週Sなしの検証も
#python psi_consistency_tests.py --db psi.sqlite --scenario Baseline --product RICE --node JAPAN_DC --parent
#
#必要なら、このチェックに「階層保存則（子P合計 ≒ 親S合計）」の検証も追加できます（LTで範囲外に溢れた分の扱い方だけ決めればOK）。
