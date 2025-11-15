
# ******************************
# PSI_plan/planning_operation.py
# ******************************
from __future__ import annotations
from typing import Iterable, List, Optional
# --- ADD: ISO week → internal index helpers -------------------------------
from datetime import date
import ast
def _build_iso_week_index_map(plan_year_st: int, plan_range: int) -> tuple[dict[tuple[int,str], int], int]:
    """
    (iso_year, 'WW') → 0-based index の写像を作る。
    年度跨ぎ/存在しない週(53週が無い年)を自然にスキップして詰める。
    返り値: (mapping, weeks_count)
    """
    mapping: dict[tuple[int,str], int] = {}
    idx = 0
    year_end = plan_year_st + int(plan_range)  # ハミ出し分は plan_range 側が面倒を見る前提
    for y in range(plan_year_st, year_end):
        for w in range(1, 54):  # ISO週は1..53
            try:
                # ISO週の月曜が存在する週のみ採用
                date.fromisocalendar(y, w, 1)
            except ValueError:
                continue
            mapping[(y, f"{w:02d}")] = idx
            idx += 1
    return mapping, idx
def _make_lot_id_list_slots_iso(df_weekly, node_name: str,
                                week_index_map: dict[tuple[int,str], int],
                                weeks_count: int) -> list[list[str]]:
    """
    df_weekly の (iso_year, iso_week, lot_id_list) を、
    内部インデックス 0..weeks_count-1 のスロット配列 pSi に割り当てる。
    """
    pSi: list[list[str]] = [[] for _ in range(weeks_count)]
    df_node = df_weekly[df_weekly["node_name"] == node_name]
    for _, r in df_node.iterrows():
        key = (int(r["iso_year"]), str(r["iso_week"]).zfill(2))
        idx = week_index_map.get(key, None)
        if idx is None or idx < 0 or idx >= weeks_count:
            print(f"[WARN] {node_name}: ISO week {key} → idx={idx} is out of range(0..{weeks_count-1}); skipped.")
            continue
        lots = r.get("lot_id_list", [])
        # 万一、文字列で入ってきた場合に復元（例: "[ 'A', 'B' ]"）
        if not isinstance(lots, list):
            if isinstance(lots, str):
                try:
                    lots = ast.literal_eval(lots)
                except Exception:
                    print(f"[WARN] {node_name}: lot_id_list not list-like -> {lots!r}; treated as empty.")
                    lots = []
            else:
                lots = []
        pSi[idx].extend(lots)
    return pSi
def _validate_pSi_vs_df(df_weekly, node_name: str, pSi: list[list[str]]):
    """投入検証：期待Lot数（S_lot合計）と実Lot数（pSi合計）を照合。"""
    df_node = df_weekly[df_weekly["node_name"] == node_name]
    exp = int(df_node["S_lot"].sum()) if "S_lot" in df_node.columns else None
    act = sum(len(x) for x in pSi)
    if exp is not None and exp != act:
        print(f"[WARN] {node_name}: expected S_lot={exp}, placed lots={act} (mismatch).")
# ****************************
# PSI planning operation on tree
# ****************************
def set_S2psi_stop(node, pSi):
    # S_lots_listが辞書で、node.psiにセットする
    # print("len(node.psi4demand) = ", len(node.psi4demand) )
    # print("len(pSi) = ", len(pSi) )
    for w in range(len(pSi)):  # Sのリスト
        node.psi4demand[w][0].extend(pSi[w])
def calcS2P(node): # backward planning
    # **************************
    # Safety Stock as LT shift
    # **************************
    # leadtimeとsafety_stock_weekは、ここでは同じ
    # 同一node内なので、ssのみで良い
    shift_week = int(round(node.SS_days / 7))
    ## stop 同一node内でのLT shiftは無し
    ## SS is rounded_int_num
    # shift_week = node.leadtime +  int(round(node.SS_days / 7))
    # **************************
    # long vacation weeks
    # **************************
    lv_week = node.long_vacation_weeks
    # 同じnode内でのS to P の計算処理 # backward planning
    node.psi4demand = shiftS2P_LV(node.psi4demand, shift_week, lv_week)
    pass
def get_set_childrenP2S2psi_STOP(node, plan_range):
    for child in node.children:
        for w in range(node.leadtime, 53 * plan_range):
            # ******************
            # logistics LT switch
            # ******************
            # 物流をnodeとして定義する場合の表現 STOP
            # 子node childのP [3]のweek positionを親node nodeのS [0]にset
            # node.psi4demand[w][0].extend(child.psi4demand[w][3])
            # 物流をLT_shiftで定義する場合の表現 GO
            # childのPのweek positionをLT_shiftして、親nodeのS [0]にset
            ws = w - node.leadtime
            node.psi4demand[ws][0].extend(child.psi4demand[w][3])
# ******************************
# PSI_plan.demand_processing.py
# ******************************
# *******************
# 生産平準化の前処理　ロット・カウント
# *******************
def count_lots_yyyy(psi_list, yyyy_str):
    matrix = psi_list
    # 共通の文字列をカウントするための変数を初期化
    count_common_string = 0
    # Step 1: マトリクス内の各要素の文字列をループで調べる
    for row in matrix:
        for element in row:
            # Step 2: 各要素内の文字列が "2023" を含むかどうかを判定
            if yyyy_str in element:
                # Step 3: 含む場合はカウンターを増やす
                count_common_string += 1
    return count_common_string
# sliced df をcopyに変更
def make_lot_id_list_list(df_weekly, node_name):
    # 指定されたnode_nameがdf_weeklyに存在するか確認
    if node_name not in df_weekly["node_name"].values:
        return "Error: The specified node_name does not exist in df_weekly."
    # node_nameに基づいてデータを抽出
    df_node = df_weekly[df_weekly["node_name"] == node_name].copy()
    # 'iso_year'列と'iso_week'列を結合して新しいキーを作成
    df_node.loc[:, "iso_year_week"] = df_node["iso_year"].astype(str) + df_node[
        "iso_week"
    ].astype(str)
    # iso_year_weekでソート
    df_node = df_node.sort_values("iso_year_week")
    # lot_id_listのリストを生成
    pSi = [lot_id_list for lot_id_list in df_node["lot_id_list"]]
    return pSi
# dfを渡す
# **********************************
# make and set weekly demand lots on LEAF2ROOT
# **********************************
#了解！「方法A＝Node側を weeks_count（実週長）に合わせる」に統一する前提で、
#set_df_Slots2psi4demand は下のように置き換えてください。ポイントは：
#余計な短尺 pSi 生成（make_lot_id_list_list）を完全にやめる
#Node に既に確保されている psi4demand の**長さ（=weeks_count）**に合わせて pSi を作る
#週インデックスは _build_iso_week_index_map(plan_year_st, plan_range) で作り、
#_make_lot_id_list_slots_iso(..., weeks_count) でフル長の pSi を作る
#その pSi を **node.set_S2psi(pSi)（Nodeメソッドの正本）**で投入
#親側の P→S 集約は 実配列長で回る実装に（※後述のヘルパ差し替え）
def set_df_Slots2psi4demand(node, df_weekly):
    """
    LEAF→ROOT の後行順で PSI を構築。
    - LEAF: df_weekly から (iso_year, iso_week) → 内部 index にマップし、フル長 pSi を生成→S投入→S→P
    - 非LEAF: 子の P を LT 分だけ早めて自分の S に集約→S→P
    最後に S を供給側へ初期転写（node.copy_demand_to_supply）
    """
    # 1) まず子を処理（後行順）
    for child in node.children:
        set_df_Slots2psi4demand(child, df_weekly)
    # 2) 自ノードの週数（実長）
    weeks_count = len(getattr(node, "psi4demand", []))
    if weeks_count == 0:
        # もし未初期化なら、df から最小限の初期化（保険）
        # ただし通常は build 時に set_plan_range_by_weeks(...) 済みのはず
        uniq = df_weekly[["iso_year","iso_week"]].drop_duplicates()
        weeks_count = len(uniq)
        plan_year_st = int(uniq["iso_year"].min()) if len(uniq) else 2025
        node.set_plan_range_by_weeks(weeks_count, plan_year_st)
    if not node.children:
        # === LEAF：需要の投入 ===
        # Nodeに付いていればそれを使い、無ければ df からフォールバック
        plan_year_st = int(getattr(node, "plan_year_st", df_weekly["iso_year"].min()))
        plan_range   = int(getattr(node, "plan_range", max(1, (weeks_count + 52) // 53)))
        # ISO週→内部 index 写像（年を跨ぐ欠番は自然にスキップ）
        week_index_map, _ = _build_iso_week_index_map(plan_year_st, plan_range)
        # 実長 weeks_count に合わせて pSi（各週の lot_id 配列）を作る
        pSi = _make_lot_id_list_slots_iso(df_weekly, node.name, week_index_map, weeks_count)
        # 期待 lot 数と実 lot 数の簡易照合（警告のみ）
        _validate_pSi_vs_df(df_weekly, node.name, pSi)
        # 厳密チェック（Node.set_S2psi 側にも assert を入れておくと二重で安全）
        if len(pSi) != weeks_count:
            raise RuntimeError(
                f"[{node.name}] len(pSi)={len(pSi)} != weeks_count={weeks_count} "
                f"(plan_year_st={plan_year_st}, plan_range={plan_range})"
            )
        # S 投入 → S→P（安全在庫/休暇週を考慮）
        node.set_S2psi(pSi)
        node.calcS2P()
    else:
        # === 非LEAF：子の P → 自分の S に集約（LT前倒し）→ S→P ===
        # ※ 実配列長で回る実装の get_set_childrenP2S2psi に差し替えておくこと
        node.get_set_childrenP2S2psi()   # 引数 plan_range は使用しない版にしておく
        node.calcS2P()
    # 3) 需要側を供給側へ初期転写（実長で）
    node.copy_demand_to_supply()
    # （必要ならデバッグ）
    # print("psi4demand", node.name, node.psi4demand)
    # print("psi4supply", node.name, node.psi4supply)
# 同一node内のS2Pの処理
def shiftS2P_LV(psiS, shift_week, lv_week):  # LV:long vacations
    # ss = safety_stock_week
    sw = shift_week
    plan_len = len(psiS) - 1  # -1 for week list position
    for w in range(plan_len, sw, -1):  # backward planningで需要を降順でシフト
        # my_list = [1, 2, 3, 4, 5]
        # for i in range(2, len(my_list)):
        #    my_list[i] = my_list[i-1] + my_list[i-2]
        # 0:S
        # 1:CO
        # 2:I
        # 3:P
        eta_plan = w - sw  # sw:shift week (includung safty stock)
        eta_shift = check_lv_week_bw(lv_week, eta_plan)  # ETA:Estimate Time Arrival
        # リスト追加 extend
        # 安全在庫とカレンダ制約を考慮した着荷予定週Pに、w週Sからoffsetする
        psiS[eta_shift][3].extend(psiS[w][0])  # P made by shifting S with
    return psiS
# ************************************
# checking constraint to inactive week , that is "Long Vacation"
# ************************************
def check_lv_week_bw(const_lst, check_week):
    num = check_week
    if const_lst == []:
        pass
    else:
        while num in const_lst:
            num -= 1
    return num
def check_lv_week_fw(const_lst, check_week):
    num = check_week
    if const_lst == []:
        pass
    else:
        while num in const_lst:
            num += 1
    return num
# ************************************************
#呼び出し方（置き換え例）
#
# 旧：
#root.get_set_childrenP2S2psi()
#root.calcS2P()
#root.copy_demand_to_supply()
#
#を、木全体の post-order 版に置き換え：
# 新（推奨）：
#propagate_postorder_with_calcP2S(root, layer="demand",
#                                 parent_before_child=True, dedup=True)
#※ もちろん 1段だけ上げたいフェーズであれば、親ノード個別に
#
#parent.calcP2S(layer="demand", parent_before_child=True)
#parent.calcS2P()
#parent.copy_demand_to_supply()
# ************************************************
# ちょいデバッグ（合計確認）
#def _count_S(psi): return sum(len(psi[w][0]) for w in range(len(psi)))
#def _count_P(psi): return sum(len(psi[w][3]) for w in range(len(psi)))
#
## 例：実行後、root と 直下の子でざっくり確認
#print("root S sum =", _count_S(root.psi4demand))
#for ch in getattr(root, "children", []):
#    print("child P sum =", _count_P(ch.psi4demand))
# ************************************************
def _postorder_nodes(root):
    out = []
    def dfs(n):
        for c in getattr(n, "children", []) or []:
            dfs(c)
        out.append(n)
    dfs(root)
    return out
# === pysi/plan/operations.py に追記 ======================================
from typing import List, Set
BUCKET = {"S":0, "CO":1, "I":2, "P":3}
def _iter_postorder(root):
    stack = [(root, False)]
    while stack:
        n, done = stack.pop()
        if n is None:
            continue
        if done:
            yield n
        else:
            stack.append((n, True))
            for c in getattr(n, "children", []) or []:
                stack.append((c, False))
def _psi(node, layer:str):
    return node.psi4demand if layer=="demand" else node.psi4supply
def _is_vacation_week(node, w:int) -> bool:
    weeks = getattr(node, "long_vacation_weeks", None) or getattr(node, "vacation_weeks", None) or []
    try:
        s = {int(x) for x in weeks}
    except Exception:
        s = set()
    return int(w) in s
def _next_open_week(node, w:int, W:int) -> int:
    wp = w
    while wp < W and _is_vacation_week(node, wp):
        wp += 1
    return wp  # W 以上ならオーバーフロー
def aggregate_children_P_into_parent_S(
    parent,
    *,
    layer:str="demand",
    lt_attr:str="leadtime",
    replace_parent_S:bool=True,
    vacation_policy:str="shift_to_next_open",   # or "spill_to_CO"
    spill_bucket:str="CO",                      # when vacation_policy == spill_to_CO
    dedup:bool=True
):
    """
    親ノード1個に対し、子PをLTオフセットして親Sへ集約する“ローカル集約”。
    - 休暇週: デフォルトは「次の稼働週へシフト」。CO にこぼす方針も選択可。
    - replace_parent_S=True だと親Sを再構成（冪等）。
      False だと既存Sへ追記（重複は dedup=True で吸収）。
    """
    psi_p = _psi(parent, layer)
    W     = len(psi_p)
    # 作業用の新S（replace時は丸ごと入れ替え）
    new_S: List[List[str]] = [[] for _ in range(W)]
    for child in getattr(parent, "children", []) or []:
        psi_c = _psi(child, layer)
        if len(psi_c) != W:
            # 長さ不一致はスキップ（上位で検証関数が拾える）
            continue
        LT = int(getattr(child, lt_attr, 0) or 0)
        # 子の各週Pをたどってオフセット
        for wc in range(W):
            lots = psi_c[wc][BUCKET["P"]]
            if not lots:
                continue
            wp = wc - LT  # 親Sは子PよりLTだけ前倒し（需要面の定義）
            if wp < 0:
                # レンジ外に出る（将来に向けて押し出す仕様ならここで方針追加）
                continue
            # 休暇週処理
            if _is_vacation_week(parent, wp):
                if vacation_policy == "shift_to_next_open":
                    wp2 = _next_open_week(parent, wp, W)
                    if wp2 < W:
                        new_S[wp2].extend(lots)
                    else:
                        # レンジ外に溢れた。必要なら最後の週のCO/Iに退避する選択肢もあり。
                        pass
                elif vacation_policy == "spill_to_CO":
                    psi_p[wp][BUCKET[spill_bucket]].extend(lots)
                else:
                    # 未知ポリシーはそのままSに積む（後段のcalcS2Pに任せる）
                    new_S[wp].extend(lots)
            else:
                new_S[wp].extend(lots)
    # 親Sへ反映（replace or merge）
    if replace_parent_S:
        if dedup:
            for w in range(W):
                if new_S[w]:
                    psi_p[w][BUCKET["S"]] = list(dict.fromkeys(new_S[w]))  # 順序保った重複除去
                else:
                    psi_p[w][BUCKET["S"]] = []
        else:
            for w in range(W):
                psi_p[w][BUCKET["S"]] = new_S[w][:]
    else:
        for w in range(W):
            if not new_S[w]:
                continue
            if dedup:
                # 既存+新規 を set で冪等化（順序保持したいなら OrderedDict 等でも可）
                merged = psi_p[w][BUCKET["S"]] + new_S[w]
                psi_p[w][BUCKET["S"]] = list(dict.fromkeys(merged))
            else:
                psi_p[w][BUCKET["S"]].extend(new_S[w])
#呼び出し方（旧 → 新）
## 旧:
## root.get_set_childrenP2S2psi()
## root.calcS2P()
## root.copy_demand_to_supply()
#
## 新（親Sを“休暇週対応で”構成してから、親S->P）:
#from pysi.plan.operations import propagate_postorder_with_calcP2S
#
#propagate_postorder_with_calcP2S(
#    root,
#    layer="demand",
#    lt_attr="leadtime",
#    vacation_policy="shift_to_next_open",  # or "spill_to_CO"
#    replace_parent_S=True                  # 冪等にしたいなら True 推奨
#)
#
#
#ポイント
#
#休暇週ロジックは aggregate_children_P_into_parent_S に実装しており、
#propagate_postorder_with_calcP2S は順序制御と calcS2P 呼びに専念しています。
#
#親の calcS2P は、安全在庫(SS)や休暇週の生産/入荷側の調整を担当。
#一方で 出荷（S）の休暇週はローカル集約側で先に扱うため、二重でぶつかりません。
#
#replace_parent_S=True で再実行しても積み増しが起きない冪等性を確保。
#
# 新しい定義
def propagate_postorder_with_calcP2S(
    root,
    *,
    layer:str="demand",
    lt_attr:str="leadtime",
    vacation_policy:str="shift_to_next_open",
    replace_parent_S:bool=True
):
    """
    多段ツリーで “葉S→P → 子P→親S → 親S→P …” を post-order で完走させる。
    - 休暇週やCOこぼしのローカル集約は aggregate_children_P_into_parent_S に実装。
    """
    # 1) 葉で S->P（既に他所で済んでいれば冪等なので再実行可）
    for n in _iter_postorder(root):
        if getattr(n, "children", []) :
            continue
        if hasattr(n, "calcS2P"):
            n.calcS2P()
        elif hasattr(n, "calcS2P_4supply"):
            n.calcS2P_4supply()
        if hasattr(n, "copy_demand_to_supply"):
            n.copy_demand_to_supply()
    # 2) 内部ノードで 子P→親S（休暇週/CO/冪等 対応）→ 親S->P
    for n in _iter_postorder(root):
        if not getattr(n, "children", []):
            continue
        aggregate_children_P_into_parent_S(
            n,
            layer=layer,
            lt_attr=lt_attr,
            vacation_policy=vacation_policy,
            replace_parent_S=replace_parent_S,
            dedup=True
        )
        # 親でも S->P
        if hasattr(n, "calcS2P"):
            n.calcS2P()
        elif hasattr(n, "calcS2P_4supply"):
            n.calcS2P_4supply()
        if hasattr(n, "copy_demand_to_supply"):
            n.copy_demand_to_supply()
# pysi/plan/propagate_postorder_with_calcP2S.py
# --------------------------------------------------
# Post-order PSI propagation utilities
#  - leaf S->P
#  - children P -> parent S  (LT & vacation aware)
#  - parent S->P
# Designed to work with your Node/PlanNode that has:
#   - attributes: name, children, psi4demand, psi4supply, leadtime, long_vacation_weeks
#   - methods   : calcS2P() or calcS2P_4supply(), copy_demand_to_supply()
# PSI bucket layout per week: [S, CO, I, P]
# --------------------------------------------------
#from __future__ import annotations
#from typing import Iterable, List, Optional
BUCKET = {"S": 0, "CO": 1, "I": 2, "P": 3}
__all__ = [
    "aggregate_children_P_into_parent_S",
    "propagate_postorder_with_calcP2S",
]
# ----------------------------
# small helpers
# ----------------------------
def _iter_postorder(root):
    """yield nodes in post-order (children before parent)"""
    stack = [(root, False)]
    while stack:
        n, done = stack.pop()
        if n is None:
            continue
        if done:
            yield n
        else:
            stack.append((n, True))
            for c in getattr(n, "children", []) or []:
                stack.append((c, False))
def _psi(node, layer: str):
    if layer == "supply":
        return getattr(node, "psi4supply", None)
    return getattr(node, "psi4demand", None)
def _vacation_set(node) -> set[int]:
    weeks = (
        getattr(node, "long_vacation_weeks", None)
        or getattr(node, "vacation_weeks", None)
        or []
    )
    try:
        return {int(w) for w in weeks}
    except Exception:
        return set()
def _is_vacation_week(node, w: int) -> bool:
    return int(w) in _vacation_set(node)
def _next_open_week(node, w: int, W: int) -> int:
    """forward-scan to the next non-vacation week; may return W (overflow)"""
    wp = int(w)
    while wp < W and _is_vacation_week(node, wp):
        wp += 1
    return wp
def _calc_S2P(node):
    """call whichever S->P exists, then sync demand->supply if available"""
    if hasattr(node, "calcS2P"):
        node.calcS2P()
    elif hasattr(node, "calcS2P_4supply"):
        node.calcS2P_4supply()
    if hasattr(node, "copy_demand_to_supply"):
        node.copy_demand_to_supply()
# ----------------------------
# core: children P -> parent S
# ----------------------------
def aggregate_children_P_into_parent_S(
    parent,
    *,
    layer: str = "demand",
    lt_attr: str = "leadtime",
    vacation_policy: str = "shift_to_next_open",  # or "spill_to_CO"
    spill_bucket: str = "CO",
    replace_parent_S: bool = True,
    dedup: bool = True,
    verbose: bool = False,
):
    """
    Aggregate each child's P-lots into the parent's S-lots with LT offset.
    Parameters
    ----------
    parent : Node
        Parent node that receives S from its children P.
    layer : {"demand","supply"}
        Which PSI space to use.
    lt_attr : str
        Attribute name on *child* that carries leadtime (weeks).
    vacation_policy : {"shift_to_next_open","spill_to_CO"}
        How to handle parent vacation weeks when placing S.
    spill_bucket : {"CO","I","P"}
        Bucket to receive lots when vacation_policy == "spill_to_CO".
    replace_parent_S : bool
        If True, rebuild parent's S from scratch (idempotent). If False, append into existing S.
    dedup : bool
        If True, remove duplicates while preserving order.
    verbose : bool
        Print assignment/overflow summary.
    Notes
    -----
    - If child's PSI length differs from parent's, the overlapping min length is used.
    - LT < 0 is treated as 0.
    """
    psi_p = _psi(parent, layer)
    if not isinstance(psi_p, list):
        return
    W = len(psi_p)
    new_S: List[List[str]] = [[] for _ in range(W)]
    assigned = 0
    overflow = 0
    children = getattr(parent, "children", []) or []
    for child in children:
        psi_c = _psi(child, layer)
        if not isinstance(psi_c, list):
            continue
        Wc = min(W, len(psi_c))
        LT = max(0, int(getattr(child, lt_attr, 0) or 0))
        for wc in range(Wc):
            clots = psi_c[wc][BUCKET["P"]]
            if not clots:
                continue
            # demand-side definition: parent S must occur LT weeks BEFORE child P
            wp = wc - LT
            if wp < 0:
                # would place before range -> drop (or accumulate elsewhere if needed)
                overflow += len(clots)
                continue
            # handle parent's vacation week
            if vacation_policy == "shift_to_next_open" and _is_vacation_week(parent, wp):
                wp2 = _next_open_week(parent, wp, W)
                if wp2 < W:
                    new_S[wp2].extend(clots)
                    assigned += len(clots)
                else:
                    overflow += len(clots)
            elif vacation_policy == "spill_to_CO" and _is_vacation_week(parent, wp):
                psi_p[wp][BUCKET.get(spill_bucket, 1)].extend(clots)
                assigned += len(clots)
            else:
                if 0 <= wp < W:
                    new_S[wp].extend(clots)
                    assigned += len(clots)
                else:
                    overflow += len(clots)
    # write back to parent's S
    if replace_parent_S:
        for w in range(W):
            lots = new_S[w]
            if dedup and lots:
                psi_p[w][BUCKET["S"]] = list(dict.fromkeys(lots))
            else:
                psi_p[w][BUCKET["S"]] = lots[:]
    else:
        for w in range(W):
            if not new_S[w]:
                continue
            if dedup:
                merged = psi_p[w][BUCKET["S"]] + new_S[w]
                psi_p[w][BUCKET["S"]] = list(dict.fromkeys(merged))
            else:
                psi_p[w][BUCKET["S"]].extend(new_S[w])
    if verbose:
        print(
            f"[aggregate P->S] parent={getattr(parent,'name',None)} "
            f"children={len(children)} assigned={assigned} overflow={overflow}"
        )
# ----------------------------
# pipeline: full post-order walk
# ----------------------------
def propagate_postorder_with_calcP2S(
    root,
    *,
    layer: str = "demand",
    lt_attr: str = "leadtime",
    vacation_policy: str = "shift_to_next_open",
    replace_parent_S: bool = True,
    dedup: bool = True,
    verbose: bool = False,
):
    """
    Walk the whole tree in post-order and perform:
      1) Leaf:   S->P (then demand->supply sync if available)
      2) Parent: children P -> parent S (LT & vacation aware)
      3) Parent: S->P (then sync)
    Safe to call multiple times when replace_parent_S=True (idempotent on parent S).
    """
    # 1) ensure every leaf has P from its own S
    for n in _iter_postorder(root):
        if not getattr(n, "children", []):  # leaf
            _calc_S2P(n)
    # 2) internal nodes: aggregate & calc
    for n in _iter_postorder(root):
        if getattr(n, "children", []):
            aggregate_children_P_into_parent_S(
                n,
                layer=layer,
                lt_attr=lt_attr,
                vacation_policy=vacation_policy,
                replace_parent_S=replace_parent_S,
                dedup=dedup,
                verbose=verbose,
            )
            _calc_S2P(n)
