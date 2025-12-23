# pysi/plan/engines.py

# this "annotations" be the top position
from __future__ import annotations

from collections import deque
import inspect
from pysi.network.tree import *

# 既存のNode/PlanNode側にある想定のメソッドを呼び出す薄いラッパ
# - n.aggregate_children_P_into_parent_S(layer=...)
# - n.calcS2P(layer=...)
# - n.calcS2P_4supply()
# - n.calcPS2I4supply()
def _iter_postorder(root):
    st = [(root, False)]
    while st:
        n, done = st.pop()
        if not n:
            continue
        if done:
            yield n
        else:
            st.append((n, True))
            for c in getattr(n, "children", []) or []:
                st.append((c, False))


def _find(root, name: str):
    for n in _iter_postorder(root):
        if getattr(n, "name", None) == name:
            return n
    return None


def outbound_backward_leaf_to_MOM(out_root, in_root, layer="demand"):
    # 子P→親Sの集約 → 各ノードのS→P（SS/LV/休暇はノード実装に委譲）
    for n in _iter_postorder(out_root):
        if hasattr(n, "aggregate_children_P_into_parent_S"):
            n.aggregate_children_P_into_parent_S(layer=layer)
        if hasattr(n, "calcS2P"):
            n.calcS2P()  # .\pysi\network\node_base.py layer="demand" is default
            # n.calcS2P(layer=layer)
    return out_root, in_root


def inbound_MOM_leveling_vs_capacity(out_root, in_root, mom_name="MOM"):
    """
    Inbound (MOM) 側で、leaf から積み上がった P ロットを MOM の capacity で envelope し、
    overflow を前倒し(平準化)する簡易ロジック。

    ※ 従来は mom.nx_capacity (単一cap) のみ参照していたが、
       _wom_env.weekly_capability[...] があれば週次capで envelope する。
       (後方互換: weekly_capability が無ければ従来通り cap=nx_capacity)

    ★対応形式
      1) product階層あり: env.weekly_capability[product][mom_name][w]
      2) 旧形式:          env.weekly_capability[mom_name][w]
      3) どちらも無い:    mom.nx_capacity
    """
    mom = getattr(in_root, "children", {}).get(mom_name)
    if mom is None:
        return out_root, in_root

    psi = getattr(mom, "psi4demand", None)
    if not psi:
        return out_root, in_root

    W = len(psi)
    cap = int(getattr(mom, "nx_capacity", 0) or 0)
    if cap <= 0:
        return out_root, in_root

    # env を inbound 側 or outbound 側の root から拾う（wom_pipeline の実装差を吸収）
    env = getattr(in_root, "_wom_env", None) or getattr(out_root, "_wom_env", None)

    for w in range(W):
        wc = (getattr(env, "weekly_capability", {}) or {}) if env else {}

        # 1) product階層あり: wc[product][mom_name][w]
        # 2) 旧形式: wc[mom_name][w]
        # 3) どちらも無い: cap（nx_capacity）で後方互換
        product = (
            getattr(env, "product", None)
            or getattr(out_root, "product_name", None)
            or getattr(in_root, "product_name", None)
        )

        series = None
        if product and isinstance(wc.get(product, None), dict):
            series = wc.get(product, {}).get(mom_name, None)
        if series is None:
            series = wc.get(mom_name, None)

        cap_w = int(
            (series[w] if (isinstance(series, (list, tuple)) and len(series) > w) else cap)
        )

        lots = mom.psi4demand[w][3]  # Pスロット
        if len(lots) > cap_w:
            overflow = lots[cap_w:]
            mom.psi4demand[w][3] = lots[:cap_w]

            # 前倒しへ平準化
            wp = w - 1
            while overflow and wp >= 0:
                room = max(0, cap_w - len(mom.psi4demand[wp][3]))
                if room:
                    take, overflow = overflow[:room], overflow[room:]
                    mom.psi4demand[wp][3].extend(take)
                wp -= 1

    return out_root, in_root


# =============================================================
def deep_copy_psi(psi):
    # psi[w][k] は lot_id のリスト想定
    return [[lst.copy() for lst in week] for week in psi]


def build_node_psi_dict(node, layer="demand", d=None):
    if d is None:
        d = {}
    psi = node.psi4demand if layer == "demand" else node.psi4supply
    d[node.name] = deep_copy_psi(psi)
    for c in node.children:
        build_node_psi_dict(c, layer, d)
    return d


def deep_copy_psi_dict(d_src):
    return {name: deep_copy_psi(psi) for name, psi in d_src.items()}


def re_connect_suppy_dict2psi(node, node_psi_dict_In4Sp):
    # 供給レイヤの実体を「辞書の配列」に統一（以後 GUI も同じ物を見る）
    node.psi4supply = node_psi_dict_In4Sp[node.name]
    for c in node.children:
        re_connect_suppy_dict2psi(c, node_psi_dict_In4Sp)


def inbound_backward_MOM_to_leaf(out_root, in_root, layer="demand"):
    # 1) OUT→IN の接続（root の demand/supply を一致コピー）
    connect_outbound2inbound(out_root, in_root)
    # 2) PRE-ORDER: inbound の S→P（親） & P→S（子）を伝播（Backward）
    calc_all_psiS2P2childS_preorder(in_root)  # ← 親P→子Sは demand レイヤに入る
    # 3) & 4)  "clone psi4demand to psi4supply"
    def _clone_psi_layer(psi_layer):
        return [[slot[:] for slot in week] for week in psi_layer]

    def copy_demand_to_supply_rec(node):
        node.psi4supply = _clone_psi_layer(node.psi4demand)
        for c in node.children:
            copy_demand_to_supply_rec(c)

    copy_demand_to_supply_rec(in_root)
    # 5) POST-ORDER: supply レイヤの P/S/CO から I を確定生成
    calc_all_psi2i4supply_post(in_root)
    return out_root, in_root


# =============================================================
def inbound_forward_leaf_to_MOM(out_root, in_root, layer="supply"):
    for n in _iter_postorder(in_root):
        if hasattr(n, "calcPS2I4supply"):
            n.calcPS2I4supply()
    return out_root, in_root


# *************************************************
# PUSH and PULL engine
# *************************************************
def copy_S_demand2supply(node):  # TOBE 240926
    # 明示的に.copyする。
    plan_len = 53 * node.plan_range
    for w in range(0, plan_len):
        node.psi4supply[w][0] = node.psi4demand[w][0].copy()


def copy_P_demand2supply(node):  # TOBE 240926
    # 明示的に.copyする。
    plan_len = 53 * node.plan_range
    for w in range(0, plan_len):
        node.psi4supply[w][3] = node.psi4demand[w][3].copy()


def PUSH_process(node):
    node.calcPS2I4supply()  # calc_psi with PULL_S
    print(f"PUSH_process applied to {node.name}")


def PULL_process(node):
    copy_S_demand2supply(node)
    copy_P_demand2supply(node)
    node.calcPS2I4supply()  # calc_psi with PULL_S&P
    print(f"PULL_process applied to {node.name}")


def apply_pull_process(node):
    for child in node.children:
        PULL_process(child)
        apply_pull_process(child)


def push_pull_all_psi2i_decouple4supply5(node, decouple_nodes):
    print("node in supply_proc", node.name)
    if node.name in decouple_nodes:
        node.calcPS2I4supply()  # calc_psi with PULL_S
        copy_S_demand2supply(node)
        PUSH_process(node)
        apply_pull_process(node)
    else:
        PUSH_process(node)
        for child in node.children:
            push_pull_all_psi2i_decouple4supply5(child, decouple_nodes)


# *****************
# helper for make_nodes_decouple_all
# *****************
def find_depth(node):
    if not node.parent:
        return 0
    else:
        return find_depth(node.parent) + 1


def find_all_leaves(node, leaves, depth=0):
    if not node.children:
        leaves.append((node, depth))  # (leafノード, 深さ) のタプルを追加
    else:
        for child in node.children:
            find_all_leaves(child, leaves, depth + 1)


def make_nodes_decouple_all(node):
    leaves = []
    leaves_name = []
    nodes_decouple = []
    find_all_leaves(node, leaves)
    pickup_list = sorted(leaves, key=lambda x: x[1], reverse=True)
    pickup_list = [leaf[0] for leaf in pickup_list]  # 深さ情報を取り除く
    for nd in pickup_list:
        nodes_decouple.append(nd.name)
    nodes_decouple_all = []
    while len(pickup_list) > 0:
        nodes_decouple_all.append(nodes_decouple.copy())
        current_node = pickup_list.pop(0)
        del nodes_decouple[0]
        parent_node = current_node.parent
        if parent_node is None:
            break
        if current_node.parent:
            depth = find_depth(parent_node)
            inserted = False
            for idx, node in enumerate(pickup_list):
                if find_depth(node) <= depth:
                    pickup_list.insert(idx, parent_node)
                    nodes_decouple.insert(idx, parent_node.name)
                    inserted = True
                    break
            if not inserted:
                pickup_list.append(parent_node)
                nodes_decouple.append(parent_node.name)
            for child in parent_node.children:
                if child in pickup_list:
                    pickup_list.remove(child)
                    nodes_decouple.remove(child.name)
        else:
            print("error: node dupplicated", parent_node.name)
    return nodes_decouple_all


# *************************************************
# GPT defined "PUSH and PULL engine"
# *************************************************
from typing import Iterable, Optional


def _normalize_decouple_nodes(decouple_nodes: Optional[Iterable]) -> list[str]:
    if not decouple_nodes:
        return []
    sample = next(iter(decouple_nodes))
    if hasattr(sample, "name"):  # Node の可能性
        return [n.name for n in decouple_nodes]
    return list(decouple_nodes)


def push_pull(out_root, in_root, decouple_nodes=None):
    """
    out_root, in_root を破壊的に更新して返す。
    GUI には一切依存しない（self.* を触らない）。
    """
    names = _normalize_decouple_nodes(decouple_nodes)
    if not names:
        nodes_decouple_all = make_nodes_decouple_all(out_root)
        names = nodes_decouple_all[-2] if len(nodes_decouple_all) >= 2 else nodes_decouple_all[-1]
    push_pull_all_psi2i_decouple4supply5(out_root, names)
    return out_root, in_root


# *************************************************
# end of PUSH and PULL engine
# *************************************************
def outbound_forward_push_DAD_to_buffer(root, layer="supply", dad_name="DAD", buffer_name="BUFFER"):
    dad = _find(root, dad_name)
    buf = _find(root, buffer_name)
    if not dad or not buf:
        return root
    psi = getattr(buf, "psi4supply", None)
    if not psi:
        return root
    W = len(psi)
    for w in range(W):
        buf.psi4supply[w][0] = list(getattr(dad.psi4supply[w], 0, []) or dad.psi4supply[w][0])
    if hasattr(buf, "calcS2P_4supply"):
        buf.calcS2P_4supply()
    if hasattr(buf, "calcPS2I4supply"):
        buf.calcPS2I4supply()
    return root


def outbound_backward_pull_buffer_to_leaf(root, layer="supply", buffer_name="BUFFER"):
    buf = _find(root, buffer_name)
    if not buf:
        return root
    q = deque([buf])
    while q:
        p = q.popleft()
        chs = getattr(p, "children", []) or []
        q.extend(chs)
        if not chs:
            continue
        W = len(getattr(p, "psi4supply", []) or [])
        for w in range(W):
            s_lots = p.psi4supply[w][0]
            if not s_lots:
                continue
            share = max(1, len(s_lots) // len(chs))
            k = 0
            for c in chs:
                take = s_lots[k : k + share]
                if take:
                    c.psi4supply[w][3].extend(take)  # 子のPへ
                k += share
    for n in _iter_postorder(root):
        if hasattr(n, "calcPS2I4supply"):
            n.calcPS2I4supply()
    return root


def run_engine_safenet(out_root, in_root, decouple_nodes, mode: str, layer: str = "demand", **kw):
    import inspect

    def _call(fn, *args, **kwargs):
        params = inspect.signature(fn).parameters
        filt = {k: v for k, v in kwargs.items() if k in params}
        return fn(*args, **filt)

    if mode == "outbound_backward_leaf_to_MOM":
        return outbound_backward_leaf_to_MOM(out_root, in_root, layer=layer)

    if mode == "inbound_MOM_leveling_vs_capacity":
        return _call(inbound_MOM_leveling_vs_capacity, out_root, in_root, **kw)

    if mode == "inbound_backward_MOM_to_leaf":
        return inbound_backward_MOM_to_leaf(out_root, in_root, layer=layer)

    if mode == "inbound_forward_leaf_to_MOM":
        return inbound_forward_leaf_to_MOM(out_root, in_root, layer="supply")

    if mode == "outbound_forward_push_DAD_to_buffer":
        return _call(push_pull, out_root, in_root, decouple_nodes=decouple_nodes, **kw)

    if mode == "outbound_backward_pull_buffer_to_leaf":
        return _call(outbound_backward_pull_buffer_to_leaf, out_root, layer="supply", **kw)

    raise ValueError(f"unknown mode={mode}")


def run_engine(out_root, in_root, decouple_nodes, mode: str, layer: str = "demand", **kw):
    if mode == "outbound_backward_leaf_to_MOM":
        return outbound_backward_leaf_to_MOM(out_root, in_root, layer=layer)

    if mode == "inbound_MOM_leveling_vs_capacity":

        def _only_accepted_kwargs(func, kw: dict) -> dict:
            try:
                params = inspect.signature(func).parameters
                return {k: v for k, v in kw.items() if k in params}
            except Exception:
                return {}

        safe_kw = _only_accepted_kwargs(inbound_MOM_leveling_vs_capacity, kw)
        return inbound_MOM_leveling_vs_capacity(out_root, in_root, **safe_kw)

    if mode == "inbound_backward_MOM_to_leaf":
        return inbound_backward_MOM_to_leaf(out_root, in_root, layer=layer)

    if mode == "inbound_forward_leaf_to_MOM":
        return inbound_forward_leaf_to_MOM(out_root, in_root, layer="supply")

    if mode == "outbound_forward_push_DAD_to_buffer":
        return push_pull(out_root, in_root, decouple_nodes, **kw)

    if mode == "outbound_backward_pull_buffer_to_leaf":
        return outbound_backward_pull_buffer_to_leaf(out_root, in_root, layer="supply", **kw)

    raise ValueError(f"unknown mode={mode}")
