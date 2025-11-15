
# pysi/plan/lot_validators.py
from __future__ import annotations
from typing import Iterable, Dict, List, Tuple, Set, Optional
BUCKET_IDX = {"S":0, "CO":1, "I":2, "P":3}
def _iter_nodes(root):
    stack=[root]
    while stack:
        n=stack.pop()
        yield n
        stack.extend(getattr(n,"children",[]) or [])
def _psi_layer(node, layer:str):
    return node.psi4demand if layer=="demand" else node.psi4supply
def _weekly_sets(psi:List[List[list]], bucket:str)->List[Set[str]]:
    """週ごとに set 化（重複確認に便利）"""
    b = BUCKET_IDX[bucket]
    W = len(psi)
    return [set(psi[w][b]) for w in range(W)]
def _weekly_lists(psi:List[List[list]], bucket:str)->List[List[str]]:
    b = BUCKET_IDX[bucket]
    return [psi[w][b] for w in range(len(psi))]
def _count_bucket(psi, bucket:str)->int:
    return sum(len(psi[w][BUCKET_IDX[bucket]]) for w in range(len(psi)))
# ============= 1) 親S = Σ(子PをLTオフセット) を検証 ===================
def validate_parent_S_equals_children_P(root, *,
    layer:str="demand",
    parent_before_child:bool=True,
    lt_attr:str="leadtime",
    stop_on_first:bool=False,
) -> Dict:
    """
    木の全エッジ（親<-子）に対し、
      actual_parent_S[w] == union_over_children(P_child[w + sign*LT(child)])
    を検証する。sign = -1 (既定: 親S=子P-LT)
    戻り: dict(summary, per_node_mismatches)
    """
    sign = -1 if parent_before_child else +1
    all_ok = True
    per_node = []
    for parent in _iter_nodes(root):
        chs = getattr(parent,"children",[]) or []
        if not chs:
            continue  # 葉は親にならない
        psi_p = _psi_layer(parent, layer)
        W = len(psi_p)
        actual_S = _weekly_sets(psi_p, "S")
        # 期待Sを子Pから合成
        expected_S = [set() for _ in range(W)]
        for ch in chs:
            psi_c = _psi_layer(ch, layer)
            if len(psi_c)!=W:
                per_node.append({
                    "node": parent.name, "type":"length_mismatch",
                    "detail": f"parent W={W} child({ch.name}) W={len(psi_c)}"
                })
                all_ok=False
                continue
            LT = int(getattr(ch, lt_attr, 0) or 0)
            for wc in range(W):
                wp = wc + sign*LT
                if 0<=wp<W:
                    expected_S[wp].update(psi_c[wc][BUCKET_IDX["P"]])
        # 週ごと一致判定
        mismatches = []
        for w in range(W):
            a, e = actual_S[w], expected_S[w]
            if a!=e:
                # どれが足りない/余分か
                missing = list(e - a)    # あるべきなのに親Sに無い
                extra   = list(a - e)    # 親Sにあるが計算上いらない
                if missing or extra:
                    mismatches.append((w, missing[:20], extra[:20]))  # 表示は上限
        if mismatches:
            all_ok=False
            per_node.append({
                "node": parent.name,
                "type": "parentS_childrenP_mismatch",
                "count": len(mismatches),
                "samples": mismatches[:5],
            })
