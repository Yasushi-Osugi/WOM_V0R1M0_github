# psi_io_adapters.py
"""
Step 4: Engine I/O Adapters for Global Weekly PSI Planner (SQLite × PlanNode)
提供する機能
-----------
1) DB → pSi（葉のSを注入して PlanNode を初期化＆計算）
   - calendar_iso を正本とする週長に合わせて node を初期化
   - lot テーブルから週ごとに lot_id 配列を復元して node.set_S2psi(...)
   - node.calcS2P()（SS/休暇はエンジン側ロジック）→ node.copy_demand_to_supply()
2) pSi → DB（計算結果の書き戻し）
   - lot_bucket テーブルへ S/CO/I/P を冪等UPSERT
   - 需要層・供給層どちらでもOK
前提スキーマ（抜粋）
-------------------
- calendar_iso(week_index PK, iso_year, iso_week, UNIQUE(iso_year, iso_week))
- scenario(id PK, name, plan_year_st, plan_range)
- node(id PK, name UNIQUE)
- product(id PK, name UNIQUE)
- lot(scenario_id, node_id, product_id, iso_year, iso_week, lot_id, UNIQUE(lot_id))
- lot_bucket(scenario_id, layer CHECK IN ('demand','supply'),
             node_id, product_id, week_index, bucket CHECK IN ('S','CO','I','P'),
             lot_id, UNIQUE(...))
使い方の最小例は本ファイル末尾参照。
"""
from __future__ import annotations
import ast
import json
import sqlite3
from typing import Dict, List, Tuple, Optional
# PSIバケツの並び（週ごとに [S, CO, I, P]）
BUCKETS = ("S", "CO", "I", "P")
BMAP = {"S": 0, "CO": 1, "I": 2, "P": 3}
# ----------------------------
# SQLite helpers
# ----------------------------
#def _open(db_path: str) -> sqlite3.Connection:
#    conn = sqlite3.connect(db_path)
#    conn.execute("PRAGMA journal_mode=WAL;")
#    conn.execute("PRAGMA synchronous=NORMAL;")
#    conn.execute("PRAGMA foreign_keys=ON;")
#    return conn
def _open(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # ← これを追加
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn
def _one(conn: sqlite3.Connection, sql: str, args=()) -> Optional[tuple]:
    cur = conn.execute(sql, args)
    return cur.fetchone()
def get_scenario_id(conn: sqlite3.Connection, scenario_name: str) -> int:
    row = _one(conn, "SELECT id FROM scenario WHERE name=?", (scenario_name,))
    if not row:
        raise ValueError(f"scenario not found: {scenario_name}")
    return int(row[0])
def get_node_id(conn: sqlite3.Connection, node_name: str) -> int:
    row = _one(conn, "SELECT id FROM node WHERE name=?", (node_name,))
    if not row:
        raise ValueError(f"node not found: {node_name}")
    return int(row[0])
def get_product_id(conn: sqlite3.Connection, product_name: str) -> int:
    row = _one(conn, "SELECT id FROM product WHERE name=?", (product_name,))
    if not row:
        raise ValueError(f"product not found: {product_name}")
    return int(row[0])
def get_scenario_bounds(conn: sqlite3.Connection, scenario_id: int) -> Tuple[int, int]:
    row = _one(conn, "SELECT plan_year_st, plan_range FROM scenario WHERE id=?", (scenario_id,))
    if not row:
        raise ValueError(f"scenario id not found: {scenario_id}")
    return int(row[0]), int(row[1])
def calendar_map_for_scenario(conn: sqlite3.Connection, scenario_id: int) -> Tuple[Dict[Tuple[int,int], int], List[Tuple[int,int]]]:
    """
    (iso_year, iso_week) → week_index の写像と、シナリオに含まれる週の並びを返す。
    """
    plan_year_st, plan_range = get_scenario_bounds(conn, scenario_id)
    y0 = plan_year_st
    y1 = plan_year_st + plan_range - 1
    rows = conn.execute(
        """SELECT week_index, iso_year, iso_week
           FROM calendar_iso
           WHERE iso_year BETWEEN ? AND ?
           ORDER BY week_index""",
        (y0, y1),
    ).fetchall()
    if not rows:
        # calendar_iso が全期間で作られている場合は全件採用
        rows = conn.execute(
            "SELECT week_index, iso_year, iso_week FROM calendar_iso ORDER BY week_index"
        ).fetchall()
    mapping: Dict[Tuple[int,int], int] = {}
    seq: List[Tuple[int,int]] = []
    for wi, y, w in rows:
        mapping[(int(y), int(w))] = int(wi)
        seq.append((int(y), int(w)))
    return mapping, seq
# ----------------------------
# DB → pSi : 葉S注入＋計算
# ----------------------------
def load_leaf_S_and_compute(
    conn: sqlite3.Connection,
    *,
    scenario_id: int,
    node_obj,               # PlanNode / Node （既存クラス）
    product_name: str,      # 製品名（lotは製品単位）
    layer: str = "demand",  # 通常は "demand"
) -> None:
    """
    calendar_iso に合わせて node を初期化し、lot から S を注入 → S->P → demand->supply 同期。
    """
    if layer not in ("demand", "supply"):
        raise ValueError("layer must be 'demand' or 'supply'")
    node_name = node_obj.name
    plan_year_st, plan_range = get_scenario_bounds(conn, scenario_id)
    week_map, week_seq = calendar_map_for_scenario(conn, scenario_id)
    weeks_count = len(week_seq)
    # node 側の週長を calendar に合わせる（既存データ保持は不要なら preserve=False）
    if hasattr(node_obj, "set_plan_range_by_weeks"):
        node_obj.set_plan_range_by_weeks(weeks_count, plan_year_st, preserve=False)
    else:
        # 古いAPIのフォールバック（53*range 型の場合）
        node_obj.set_plan_range_lot_counts(max(1, (weeks_count + 52) // 53), plan_year_st)
    # 週ごとの S 配列（lot_idのlist）を復元
    node_id = get_node_id(conn, node_name)
    product_id = get_product_id(conn, product_name)
    # 決定的順序：iso_year, iso_week, lot_id
    rows = conn.execute(
        """SELECT l.iso_year, l.iso_week, l.lot_id
           FROM lot l
           WHERE l.scenario_id=? AND l.node_id=? AND l.product_id=?
           ORDER BY l.iso_year, l.iso_week, l.lot_id""",
        (scenario_id, node_id, product_id),
    ).fetchall()
    pSi: List[List[str]] = [[] for _ in range(weeks_count)]
    missing = 0
    for y, w, lot_id in rows:
        idx = week_map.get((int(y), int(w)))
        if idx is None or not (0 <= idx < weeks_count):
            missing += 1
            continue
        pSi[idx].append(lot_id)
    if missing:
        print(f"[WARN] {node_name}/{product_name}: {missing} lots were outside scenario calendar; skipped.")
    # S を投入（Node.set_S2psi は assert で長さ整合を検査する実装）
    node_obj.set_S2psi(pSi)
    # 葉で S->P → demand→supply 同期
    if hasattr(node_obj, "calcS2P"):
        node_obj.calcS2P()
    elif hasattr(node_obj, "calcS2P_4supply"):
        node_obj.calcS2P_4supply()
    if hasattr(node_obj, "copy_demand_to_supply"):
        node_obj.copy_demand_to_supply()
# ----------------------------
# pSi → DB : 計算結果の書き戻し
# ----------------------------
def write_layer_to_lot_bucket(
    conn: sqlite3.Connection,
    *,
    scenario_id: int,
    node_obj,
    product_name: str,
    layer: str = "demand",
    replace_slice: bool = True,  # Trueなら対象スライスをDELETEしてから挿入（冪等・再現性◎）
) -> int:
    """
    指定ノード/製品/層の pSi（バケツ S/CO/I/P）を lot_bucket に書き戻す。
    戻り値：挿入した行数
    """
    if layer not in ("demand", "supply"):
        raise ValueError("layer must be 'demand' or 'supply'")
    node_name = node_obj.name
    node_id = get_node_id(conn, node_name)
    product_id = get_product_id(conn, product_name)
    psi = node_obj.psi4demand if layer == "demand" else node_obj.psi4supply
    if not isinstance(psi, list):
        raise ValueError(f"{layer} PSI not initialized on node '{node_name}'")
    # --- 安全パッチ：calendar 週数に合わせて週配列を正規化し、
    #                 各週の [S,CO,I,P] を 4 バケツにパディングする ---
    weeks = conn.execute("SELECT COUNT(*) FROM calendar_iso").fetchone()[0] or 0
    def _normalize_psi(seq, weeks: int) -> List[List[List[str]]]:
        """
        外側：週配列の長さを calendar に合わせる
        内側：各週のバケツ配列を [S,CO,I,P] の 4 要素にそろえ、要素は list として扱う
        """
        base = list(seq or [])
        if len(base) < weeks:
            base += [None] * (weeks - len(base))
        elif len(base) > weeks:
            base = base[:weeks]
        out: List[List[List[str]]] = []
        for w in range(weeks):
            wk = base[w]
            if not isinstance(wk, (list, tuple)):
                out.append([[], [], [], []])
                continue
            # 0..3 を見る。足りなければ [] でパディング、タプル等は list に変換
            week_buckets: List[List[str]] = []
            for i in range(4):
                if i < len(wk) and isinstance(wk[i], (list, tuple)):
                    week_buckets.append(list(wk[i]))
                elif i < len(wk) and wk[i] is None:
                    week_buckets.append([])
                else:
                    week_buckets.append([])
            out.append(week_buckets)
        return out
    psi_norm = _normalize_psi(psi, weeks)
    # --- 安全パッチ ここまで ---
    # 対象スライスを丸ごと置換（冪等・決定性のため推奨）
    if replace_slice:
        with conn:
            conn.execute(
                """DELETE FROM lot_bucket
                   WHERE scenario_id=? AND layer=? AND node_id=? AND product_id=?""",
                (scenario_id, layer, node_id, product_id),
            )
    # INSERT（ON CONFLICT DO NOTHING）
    rows = []
    for w, buckets in enumerate(psi_norm):
        for key, idx in BMAP.items():
            lots = buckets[idx]  # ← ここで IndexError は起きない（必ず4要素）
            if not lots:
                continue
            for lot in lots:
                rows.append((scenario_id, layer, node_id, product_id, int(w), key, lot))
    with conn:
        conn.executemany(
            """INSERT INTO lot_bucket
               (scenario_id, layer, node_id, product_id, week_index, bucket, lot_id)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(scenario_id, layer, node_id, product_id, week_index, bucket, lot_id)
               DO NOTHING""",
            rows,
        )
    return len(rows)
def write_both_layers(
    conn: sqlite3.Connection,
    *,
    scenario_id: int,
    node_obj,
    product_name: str,
    replace_slice: bool = True,
) -> Tuple[int, int]:
    """
    demand/supply 両レイヤを書き戻すユーティリティ。
    戻り値：(demand_rows, supply_rows)
    """
    d = write_layer_to_lot_bucket(
        conn, scenario_id=scenario_id, node_obj=node_obj, product_name=product_name,
        layer="demand", replace_slice=replace_slice
    )
    s = write_layer_to_lot_bucket(
        conn, scenario_id=scenario_id, node_obj=node_obj, product_name=product_name,
        layer="supply", replace_slice=replace_slice
    )
    return d, s
# ----------------------------
# 便利：葉～親まで一気に（任意）
# ----------------------------
def run_engine_postorder_and_write(
    conn: sqlite3.Connection,
    *,
    scenario_id: int,
    root_node,
    product_name: str,
    # 休暇シフト・SSは各 Node.calcS2P / 既存 propagate 関数に委譲
    propagate_fn=None,   # 例: pysi.plan.operations.propagate_postorder_with_calcP2S
    write_layers=("demand","supply"),
) -> Dict[str, int]:
    """
    既に各 leaf に S を注入済み（load_leaf_S_and_computeを別途呼んだ）という前提で、
    ツリー全体の post-order 伝播 → 書き戻しを行う簡易ランナー。
    """
    if propagate_fn:
        propagate_fn(root_node, layer="demand", replace_parent_S=True)
    out = {}
    for layer in write_layers:
        n = write_layer_to_lot_bucket(
            conn, scenario_id=scenario_id, node_obj=root_node,
            product_name=product_name, layer=layer, replace_slice=True
        )
        out[layer] = n
    return out
# ----------------------------
# 最小使用例（参考）
# ----------------------------
"""
from psi_io_adapters import (
    _open, get_scenario_id, load_leaf_S_and_compute,
    write_both_layers,
)
from pysi.network.node_base import PlanNode  # or your Node
# 1) DB接続とシナリオ取得
conn = _open("psi.sqlite")
scenario_id = get_scenario_id(conn, "Baseline")
# 2) 葉ノードを用意（既存の PlanNode を使う：SS_days/long_vacation_weeks 等は適宜セット）
leaf = PlanNode("TOKYO")
leaf.SS_days = 7
leaf.long_vacation_weeks = []  # 例
# 3) DB→pSi（S注入→S->P→需要→供給コピー）
load_leaf_S_and_compute(conn, scenario_id=scenario_id, node_obj=leaf, product_name="RICE", layer="demand")
# 4) 書き戻し（demand/supply 両方）
d_rows, s_rows = write_both_layers(conn, scenario_id=scenario_id, node_obj=leaf, product_name="RICE")
print("wrote:", d_rows, s_rows, "rows")
# 5) 親子ツリー全体でやるなら：
#   - 先に全leafに対して load_leaf_S_and_compute を行う
#   - その後、propagate_postorder_with_calcP2S(root) を呼ぶ
#   - 最後に write_layer_to_lot_bucket(...) を root/各ノードで呼ぶ
"""
#要点
#
#週長は calendar_iso に合わせて Node を初期化（set_plan_range_by_weeks）。
#
#lot→S の復元は決定的順序（ORDER BY iso_year, iso_week, lot_id）。
#
#書き戻しは スライスDELETE→INSERT で冪等・再実行安全。
#
#休暇週・安全在庫の扱いは、既存の calcS2P() / propagate_postorder_with_calcP2S() に委譲。
