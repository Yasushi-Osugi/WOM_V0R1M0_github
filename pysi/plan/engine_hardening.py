#1) 新ユーティリティ（冪等S→P / PS→I / 事前クリア）
#2) 親S集約の冪等（replace方式を常用） MEMO attached at end of this code
#
# psi/plan/engine_hardening.py
# -*- coding: utf-8 -*-
"""
Engine hardening: idempotent PSI rebuild helpers
 - 冪等S->P（毎回Pを再構成）
 - PS->Iの差集合計算（FIFO順維持）
 - 事前クリア（CO/I/P）
 - 休暇週(長期休暇)の前倒し・詰めロジック
"""
from __future__ import annotations
from typing import List, Iterable
BUCKET = {"S":0, "CO":1, "I":2, "P":3}
# ---------- LV helpers ----------
def _is_vacation_week(vac_weeks: Iterable[int], w: int) -> bool:
    if not vac_weeks: return False
    try:
        s = {int(x) for x in vac_weeks}
    except Exception:
        s = set()
    return int(w) in s
def _prev_open_week(vac_weeks: Iterable[int], w: int) -> int:
    """後退方向（S->P 用）"""
    wp = int(w)
    if not vac_weeks: return wp
    s = {int(x) for x in vac_weeks}
    while wp in s and wp >= 0:
        wp -= 1
    return max(wp, 0)
# ---------- core: idempotent S->P ----------
def rebuild_P_from_S_idempotent(psi: List[List[List[str]]],
                                shift_week: int,
                                vac_weeks: Iterable[int]) -> None:
    """
    Sを正本とし、Pを毎回ゼロから再構成（冪等）。
    - shift_week = round(SS_days/7) 等
    - 休暇週は「直前の稼働週」へ詰める（backward）
    """
    W = len(psi)
    # P/CO/I は触らない、まずPだけ空に
    for w in range(W):
        psi[w][BUCKET["P"]] = []
    # 後ろから前へ（backward shift）
    for w in range(W-1, -1, -1):
        S = psi[w][BUCKET["S"]]
        if not S:
            continue
        eta_plan = w - int(shift_week)
        if eta_plan < 0:
            # 範囲外は捨てる仕様にするか、w=0へ寄せるかは要件次第（ここでは捨てる）
            continue
        eta_shift = _prev_open_week(vac_weeks, eta_plan)
        psi[eta_shift][BUCKET["P"]].extend(S)
    # 重複は基本発生しない想定だが、保険で順序維持のままユニーク化
    for w in range(W):
        if psi[w][BUCKET["P"]]:
            psi[w][BUCKET["P"]] = list(dict.fromkeys(psi[w][BUCKET["P"]]))
# ---------- core: PS->I (FIFO) ----------
def calc_PS2I_idempotent(psi: List[List[List[str]]]) -> None:
    """
    I(n) = (I(n-1) + P(n)) - S(n)
    FIFO順維持（list順）、毎回Iを再構成（冪等）
    """
    W = len(psi)
    # Iをゼロから再構成
    if W == 0: return
    # w=0 の I は“初期在庫”があれば尊重、なければ空のまま
    for w in range(1, W):
        prev_I = psi[w-1][BUCKET["I"]]
        P      = psi[w][BUCKET["P"]]
        S      = psi[w][BUCKET["S"]]
        # FIFO：結合→Sを消し込み（順序維持）
        inv = (prev_I or []) + (P or [])
        if S:
            sset = set(S)
            inv = [lot for lot in inv if lot not in sset]
        psi[w][BUCKET["I"]] = inv
    # w=0 も念のためユニーク化
    psi[0][BUCKET["I"]] = list(dict.fromkeys(psi[0][BUCKET["I"]])) if psi[0][BUCKET["I"]] else []
# ---------- clear helpers ----------
def clear_buckets(psi: List[List[List[str]]], *, clear_S: bool=False, clear_CO: bool=True, clear_I: bool=True, clear_P: bool=True) -> None:
    """
    冪等再計算の前に派生バケツをクリア
     - 通常 S は“入力の正本”なので clear_S=False
    """
    W = len(psi)
    for w in range(W):
        if clear_S:  psi[w][BUCKET["S"]]  = []
        if clear_CO: psi[w][BUCKET["CO"]] = []
        if clear_I:  psi[w][BUCKET["I"]]  = []
        if clear_P:  psi[w][BUCKET["P"]]  = []
# ---------- high-level one pass ----------
def rebuild_node_demand_idempotent(node) -> None:
    """
    Nodeの demand 面を冪等に再構成
     1) CO/I/P をクリア
     2) S->P（SS/休暇バックシフト）
     3) PS->I（FIFO差集合）
    """
    psi = node.psi4demand
    if not isinstance(psi, list): return
    shift_week = int(round(getattr(node, "SS_days", 0)/7))
    vac = getattr(node, "long_vacation_weeks", []) or []
    clear_buckets(psi, clear_CO=True, clear_I=True, clear_P=True)
    rebuild_P_from_S_idempotent(psi, shift_week, vac)
    calc_PS2I_idempotent(psi)
def rebuild_node_supply_idempotent(node) -> None:
    """
    Nodeの supply 面も同様に再構成（Sは需要コピーが正本）
    """
    psi = node.psi4supply
    if not isinstance(psi, list): return
    shift_week = int(round(getattr(node, "SS_days", 0)/7))
    vac = getattr(node, "long_vacation_weeks", []) or []
    clear_buckets(psi, clear_CO=True, clear_I=True, clear_P=True)
    rebuild_P_from_S_idempotent(psi, shift_week, vac)
    calc_PS2I_idempotent(psi)
#2) 親S集約の冪等（replace方式を常用）
#
#既に提示済みの aggregate_children_P_into_parent_S() を replace_parent_S=True / dedup=True で呼ぶのを“標準”にします。
#（親Sは毎回再構成→calcS2P でP再構成→PS->I 再構成）
#
#もし既存の PlanNode.calcP2S を使うなら、内部で replace する版へ置換します。
#
## 置換推奨：PlanNode.calcP2S = aggregate_children_P_into_parent_S を包む冪等版
#def calcP2S_idempotent(self, *, layer="demand", lt_attr="leadtime", vacation_policy="shift_to_next_open"):
#    from pysi.plan.operations import aggregate_children_P_into_parent_S
#    aggregate_children_P_into_parent_S(
#        self, layer=layer, lt_attr=lt_attr,
#        vacation_policy=vacation_policy,
#        replace_parent_S=True,  # ← 冪等：Sは再構成
#        dedup=True, verbose=False
#    )
## monkey-patch（初回ロード時に一度だけ）
#try:
#    from pysi.network.node_base import PlanNode
#    PlanNode.calcP2S_idempotent = calcP2S_idempotent
#except Exception:
#    pass
