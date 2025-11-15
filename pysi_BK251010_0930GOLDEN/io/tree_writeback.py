# pysi/io/tree_writeback.py
from __future__ import annotations
import sqlite3
from typing import Dict, List
from typing import Set, Tuple, Iterable
# 既存 I/O ユーティリティを利用
from pysi.io.psi_io_adapters import (
    load_leaf_S_and_compute,
    write_both_layers,
    calendar_map_for_scenario,
    get_node_id,
    get_product_id,
)
# ******************************************
# 本物の PlanNode を使う
# ******************************************
from pysi.network.node_base import PlanNode
class _NodeShim:
    """
    PlanNode を持たない環境でも I/O を流せる極小の代替。
    - name
    - set_plan_range_by_weeks(weeks, plan_year_st, preserve=False)
    - set_S2psi(pSi): 週ごとの S ロット配列（EX: [['L1','L2'], ...]）
    - calcS2P / calcS2P_4supply: NO-OP（既存API互換のため）
    - copy_demand_to_supply: demand→supply をコピー
    - psi4demand/psi4supply: 週ごとに [S,CO,I,P] の4配列
    """
    __slots__ = ("name", "_weeks", "psi4demand", "psi4supply")
    def __init__(self, name: str):
        self.name = name
        self._weeks = 0
        self.psi4demand: List[List[List[str]]] = []
        self.psi4supply: List[List[List[str]]] = []
    def set_plan_range_by_weeks(self, weeks_count: int, plan_year_st: int, preserve: bool = False):
        self._weeks = int(weeks_count)
        base = [[[], [], [], []] for _ in range(self._weeks)]
        if preserve and self.psi4demand:
            # 必要なら既存をマージ（今回は単純化してリセット）
            pass
        self.psi4demand = [ [list(b[0]), list(b[1]), list(b[2]), list(b[3])] for b in base ]
        self.psi4supply = [ [list(b[0]), list(b[1]), list(b[2]), list(b[3])] for b in base ]
    # 古いAPIで呼ばれる可能性に備えたダミー（未使用でも安全）
    def set_plan_range_lot_counts(self, lot_years: int, plan_year_st: int):
        # 53週×年 で近似（ここは呼ばれない想定。保険で用意）
        weeks = max(1, int(lot_years)) * 53
        self.set_plan_range_by_weeks(weeks, plan_year_st, preserve=False)
    def set_S2psi(self, pSi: List[List[str]]):
        """pSi は週ごとの S ロット配列。psi4demand を [S,CO,I,P] 形に組み直す。"""
        if self._weeks == 0:
            self.set_plan_range_by_weeks(len(pSi), plan_year_st=0, preserve=False)
        if len(pSi) != self._weeks:
            # 長さ相違は短い方に合わせて安全に詰める
            m = min(len(pSi), self._weeks)
        else:
            m = self._weeks
        # Sだけ埋め、CO/I/P は空のまま
        for i in range(m):
            self.psi4demand[i][0] = list(pSi[i])  # S
            self.psi4demand[i][1] = []           # CO
            self.psi4demand[i][2] = []           # I
            self.psi4demand[i][3] = []           # P
    def calcS2P(self):         # エンジンが無くても互換のため用意（NO-OP）
        return
    def calcS2P_4supply(self): # 呼ばれる場合があるので用意（NO-OP）
        return
    def copy_demand_to_supply(self):
        # 深いコピー（lot_id 文字列なので浅くても実害は小さいが、形は分ける）
        self.psi4supply = [ [list(b[0]), list(b[1]), list(b[2]), list(b[3])] for b in self.psi4demand ]
def _build_psibuckets_from_lot(conn: sqlite3.Connection, scenario_id: int,
                               node_name: str, product_name: str) -> _NodeShim:
    """
    lot から週次 S 配列を復元し、_NodeShim に積む（PlanNode 不要の最終フォールバック）。
    """
    week_map, week_seq = calendar_map_for_scenario(conn, scenario_id)
    weeks = len(week_seq)
    node_id = get_node_id(conn, node_name)
    product_id = get_product_id(conn, product_name)
    rows = conn.execute(
        """SELECT iso_year, iso_week, lot_id
             FROM lot
            WHERE scenario_id=? AND node_id=? AND product_id=?
            ORDER BY iso_year, iso_week, lot_id""",
        (scenario_id, node_id, product_id)
    ).fetchall()
    pSi = [[] for _ in range(weeks)]
    missed = 0
    for y, w, lot_id in rows:
        idx = week_map.get((int(y), int(w)))
        if idx is None or not (0 <= idx < weeks):
            missed += 1
            continue
        pSi[idx].append(lot_id)
    if missed:
        print(f"[WARN] lot→PSI: {node_name}/{product_name} シナリオ外 {missed} 件をスキップ")
    shim = _NodeShim(node_name)
    shim.set_plan_range_by_weeks(weeks, plan_year_st=0, preserve=False)
    shim.set_S2psi(pSi)
    shim.copy_demand_to_supply()
    return shim
def write_both_layers_for_pair(conn: sqlite3.Connection,
                               scenario_id: int,
                               node_name: str,
                               product_name: str) -> Dict[str, int]:
    """
    1回で「DB→pSi（S注入）→計算（NO-OPでもOK）→ demand/supply 両レイヤ書戻し」。
    PlanNode が使えない/未初期化でも lot 直読みのフォールバックで確実に書き戻す。
    戻り値: {"d_rows": int, "s_rows": int, "weeks": int}
    """
    # まずは正攻法：DB→pSi（lot→S注入）を使って demand/supply を作る
    node = _NodeShim(node_name)
    try:
        load_leaf_S_and_compute(
            conn,
            scenario_id=scenario_id,
            node_obj=node,
            product_name=product_name,
            layer="demand"
        )
        d_rows, s_rows = write_both_layers(
            conn,
            scenario_id=scenario_id,
            node_obj=node,
            product_name=product_name,
            replace_slice=True
        )
        weeks = len(node.psi4demand) if node.psi4demand else 0
        if (d_rows + s_rows) > 0:
            return {"d_rows": int(d_rows), "s_rows": int(s_rows), "weeks": weeks}
    except Exception as e:
        # 落ちても後段のフォールバックに任せる
        pass
    # フォールバック：lot 直読みで S バケツを構成して書戻し
    fb = _build_psibuckets_from_lot(conn, scenario_id, node_name, product_name)
    d_rows, s_rows = write_both_layers(
        conn,
        scenario_id=scenario_id,
        node_obj=fb,
        product_name=product_name,
        replace_slice=True
    )
    weeks = len(fb.psi4demand) if fb.psi4demand else 0
    return {"d_rows": int(d_rows), "s_rows": int(s_rows), "weeks": weeks}
# --- helpers used by orchestrator (tree mode) --------------------
def pairs_from_weekly_demand(conn: sqlite3.Connection, scenario_id: int) -> Set[Tuple[str, str]]:
    """
    DBの weekly_demand から (node_name, product_name) のユニークペアを返す。
    orchestrator で使う簡易ヘルパ（leafでも流用可）
    """
    rows = conn.execute(
        """
        SELECT n.name, p.name
          FROM weekly_demand wd
          JOIN node n    ON wd.node_id = n.id
          JOIN product p ON wd.product_id = p.id
         WHERE wd.scenario_id = ?
         GROUP BY n.name, p.name
        """, (scenario_id,)
    ).fetchall()
    return {(r[0], r[1]) for r in rows}
def node_names_from_plan_root(root) -> Set[str]:
    """
    PlanNode ルートから .children をたどってノード名集合を返す。
    GUI/計算のクラス差異に耐えるよう、属性が無ければ単体のみ。
    """
    names: Set[str] = set()
    if root is None:
        return names
    stack = [root]
    seen = set()
    while stack:
        cur = stack.pop()
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        name = getattr(cur, "name", None)
        if isinstance(name, str):
            names.add(name)
        # children / childs / get_children のどれかがある想定でゆるく取得
        children = []
        for attr in ("children", "childs"):
            ch = getattr(cur, attr, None)
            if isinstance(ch, Iterable):
                children = list(ch)
                break
        if not children and hasattr(cur, "get_children") and callable(cur.get_children):
            try:
                children = list(cur.get_children())
            except Exception:
                children = []
        stack.extend(children)
    return names
def intersect_pairs_with_network(pairs: Iterable[Tuple[str, str]], node_names: Set[str]) -> Set[Tuple[str, str]]:
    """
    ネットワークに含まれるノード名だけに (node, product) ペアを絞り込む。
    """
    node_names = set(node_names or ())
    return {(n, p) for (n, p) in pairs if n in node_names}
# ******************************************
# 本物の PlanNode を使う
# ******************************************
def _read_node_attrs(conn: sqlite3.Connection, node_name: str, product_name: str) -> Dict:
    """
    node_product から leaf の属性（lot_size, leadtime, ss_days, long_vacation_weeks）を読む。
    見つからない項目は無理に埋めない（PlanNode がデフォルトを持つ前提）。
    """
    row = conn.execute("""
      SELECT np.lot_size, np.leadtime, np.ss_days, np.long_vacation_weeks
      FROM node_product np
      JOIN node n    ON np.node_id = n.id
      JOIN product p ON np.product_id = p.id
      WHERE n.name=? AND p.name=?
    """, (node_name, product_name)).fetchone()
    if not row:
        return {}
    lot_size, leadtime, ss_days, lvw = row
    out = {}
    if lot_size is not None: out["lot_size"] = int(lot_size)
    if leadtime is not None: out["leadtime"] = int(leadtime)
    if ss_days is not None:  out["SS_days"] = int(ss_days)
    if lvw:  # JSON 文字列想定
        try:
            out["long_vacation_weeks"] = json.loads(lvw)
        except Exception:
            pass
    return out
def _build_plan_node(node_name: str, attrs: Dict) -> PlanNode:
    """PlanNode を生成して、取得できた属性だけ安全にセット。"""
    n = PlanNode(node_name)
    for k, v in attrs.items():
        if hasattr(n, k):
            setattr(n, k, v)
    return n
def write_both_layers_for_pair(conn: sqlite3.Connection,
                               scenario_id: int,
                               node_name: str,
                               product_name: str) -> Dict[str, int]:
    """
    1) lot から S を leaf ノードへ注入 → 2) calcS2P() で P/I/CO 計算
    → 3) lot_bucket へ demand/supply 両レイヤ書戻し。
    戻り値: {"d_rows": ..., "s_rows": ..., "weeks": ...}
    """
    # 属性を取得して PlanNode 構築
    attrs = _read_node_attrs(conn, node_name, product_name)
    node  = _build_plan_node(node_name, attrs)
    # Sを注入し、S→P 計算 & demand→supply 同期
    load_leaf_S_and_compute(
        conn,
        scenario_id=scenario_id,
        node_obj=node,
        product_name=product_name,
        layer="demand",
    )
    # demand/supply 両方を書き戻し
    d_rows, s_rows = write_both_layers(
        conn,
        scenario_id=scenario_id,
        node_obj=node,
        product_name=product_name,
        replace_slice=True,
    )
    # 週数は calendar（すでに DB 側が正）に依存：手軽に数える
    weeks = conn.execute("SELECT COUNT(*) FROM calendar_iso").fetchone()[0] or 0
    return {"d_rows": int(d_rows), "s_rows": int(s_rows), "weeks": int(weeks)}
# ******************************************
