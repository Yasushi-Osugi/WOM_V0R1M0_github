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
            #n.calcS2P(layer=layer)
    return out_root, in_root

def inbound_MOM_leveling_vs_capacity(out_root, in_root, mom_name="MOM"):
#def inbound_MOM_leveling_vs_capacity(out_root, in_root, layer="demand"):
    mom = _find(in_root, mom_name)
    if not mom:
        return out_root, in_root
    psi = getattr(mom, "psi4demand", None)
    if not psi:
        return out_root, in_root
    W = len(psi)
    cap = int(getattr(mom, "nx_capacity", 0) or 0)
    if cap <= 0:
        return out_root, in_root
    for w in range(W):
        lots = mom.psi4demand[w][3]  # Pスロット
        if len(lots) > cap:
            overflow = lots[cap:]
            mom.psi4demand[w][3] = lots[:cap]
            # 前倒しへ平準化
            wp = w - 1
            while overflow and wp >= 0:
                room = max(0, cap - len(mom.psi4demand[wp][3]))
                if room:
                    take, overflow = overflow[:room], overflow[room:]
                    mom.psi4demand[wp][3].extend(take)
                wp -= 1
            # まだ余るならCO退避（方針に応じて後で変更可）
            if overflow:
                mom.psi4demand[w][1].extend(overflow)
    return out_root, in_root
# =============================================================
def deep_copy_psi(psi):
    # psi[w][k] は lot_id のリスト想定
    return [[lst.copy() for lst in week] for week in psi]
def build_node_psi_dict(node, layer="demand", d=None):
    if d is None: d = {}
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
    #calc_all_psi2i4supply_post(in_root)
    #@STOP
    ## 3) demand → supply を辞書で Deep Copy
    #node_psi_dict_In4Dm = build_node_psi_dict(in_root, layer="demand")  # deep copy 全ノード分
    #node_psi_dict_In4Sp = deep_copy_psi_dict(node_psi_dict_In4Dm)       # さらに別辞書にdeep copy
    #
    ## 4) ノードの psi4supply を「辞書側の配列」へバインドし直す（参照先を辞書に統一）
    #re_connect_suppy_dict2psi(in_root, node_psi_dict_In4Sp)
    # 5) POST-ORDER: supply レイヤの P/S/CO から I を確定生成
    calc_all_psi2i4supply_post(in_root)
    #@STOP
    ## 必要なら返す（GUI 側で self.node_psi_dict_In4Sp に持たせるなら return する）
    #return node_psi_dict_In4Dm, node_psi_dict_In4Sp
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
def copy_S_demand2supply(node): # TOBE 240926
#def update_child_PS(node): # TOBE 240926
    # 明示的に.copyする。
    plan_len = 53 * node.plan_range
    for w in range(0, plan_len):
        node.psi4supply[w][0] = node.psi4demand[w][0].copy()

def copy_P_demand2supply(node): # TOBE 240926
#def update_child_PS(node): # TOBE 240926
    # 明示的に.copyする。
    plan_len = 53 * node.plan_range
    for w in range(0, plan_len):
        node.psi4supply[w][3] = node.psi4demand[w][3].copy()

def PUSH_process(node):
    # ***************
    # decoupl nodeに入って最初にcalcPS2Iで状態を整える
    # ***************
    node.calcPS2I4supply()  # calc_psi with PULL_S
    # STOP STOP
    ##@241002 decoupling nodeのみpullSで確定ship
    ## *******************************************
    ## decouple nodeは、pull_Sで出荷指示する
    ## *******************************************
    ## copy S demand2supply
    #copy_S_demand2supply(node)
    #
    ## 自分のnodeをPS2Iで確定する
    #node.calcPS2I4supply()  # calc_psi with PUSH_S
    print(f"PUSH_process applied to {node.name}")

def PULL_process(node):
    # *******************************************
    # decouple nodeは、pull_Sで出荷指示する
    # *******************************************
    #@241002 childで、親nodeの確定S=確定P=demandのPで計算済み
    # copy S&P demand2supply for PULL
    copy_S_demand2supply(node)
    copy_P_demand2supply(node)
    # 自分のnodeをPS2Iで確定する
    node.calcPS2I4supply()  # calc_psi with PULL_S&P
    print(f"PULL_process applied to {node.name}")

def apply_pull_process(node):
    #@241002 MOVE
    #PULL_process(node)
    for child in node.children:
        PULL_process(child)
        apply_pull_process(child)

def push_pull_all_psi2i_decouple4supply5(node, decouple_nodes):
    print("node in supply_proc", node.name )
    # dump check
    #if  node.name == "DADJPN":
    #    print("DADJPN.psi4demand", node.psi4demand )
    #    print("DADJPN.psi4supply", node.psi4supply )
    if node.name in decouple_nodes:
        # ***************
        # decoupl nodeに入って最初にcalcPS2Iで状態を整える
        # ***************
        node.calcPS2I4supply()  # calc_psi with PULL_S
        #@241002 decoupling nodeのみpullSで確定ship
        # *******************************************
        # decouple nodeは、pull_Sで出荷指示する
        # *******************************************
        copy_S_demand2supply(node)
        PUSH_process(node)         # supply SP2Iしてからの
        apply_pull_process(node)   # demandSに切り替え
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
    #
    #    root_node = build_tree()
    #    set_parent(root_node)
    #    leaves = []
    #    find_all_leaves(root_node, leaves)
    #    pickup_list = leaves[::-1]  # 階層の深い順に並べる
    leaves = []
    leaves_name = []
    nodes_decouple = []
    find_all_leaves(node, leaves)
    # find_all_leaves(root_node, leaves)
    pickup_list = sorted(leaves, key=lambda x: x[1], reverse=True)
    pickup_list = [leaf[0] for leaf in pickup_list]  # 深さ情報を取り除く
    # こうすることで、leaf nodeを階層の深い順に並べ替えた pickup_list が得られます。
    # 先に深さ情報を含めて並べ替え、最後に深さ情報を取り除くという流れになります。
    # 初期処理として、pickup_listをnodes_decoupleにcopy
    # pickup_listは使いまわしで、pop / insert or append / removeを繰り返す
    for nd in pickup_list:
        nodes_decouple.append(nd.name)
    nodes_decouple_all = []
    while len(pickup_list) > 0:
        # listのcopyを要素として追加
        nodes_decouple_all.append(nodes_decouple.copy())
        current_node = pickup_list.pop(0)
        del nodes_decouple[0]  # 並走するnode.nameの処理
        parent_node = current_node.parent
        if parent_node is None:
            break
        # 親ノードをpick up対象としてpickup_listに追加
        if current_node.parent:
            #    pickup_list.append(current_node.parent)
            #    nodes_decouple.append(current_node.parent.name)
            # if parent_node not in pickup_list:  # 重複追加を防ぐ
            # 親ノードの深さを見て、ソート順にpickup_listに追加
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
            # 親ノードから見た子ノードをpickup_listから削除
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
# names でも Node でも受け取れるように薄い正規化
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
    # 1) decouple の決定（未指定なら自動選定）
    names = _normalize_decouple_nodes(decouple_nodes)
    if not names:
        nodes_decouple_all = make_nodes_decouple_all(out_root)  # 既存ヘルパー
        names = nodes_decouple_all[-2] if len(nodes_decouple_all) >= 2 else nodes_decouple_all[-1]
    # 2) 実処理（既存ロジック流用）
    push_pull_all_psi2i_decouple4supply5(out_root, names)
    # 3) できる限り「結果だけ」返す（GUI の更新は呼び出し側で）
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
        # DADのSをbufferのSへコピー（PUSHの需要信号）
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
                take = s_lots[k:k+share]
                if take:
                    c.psi4supply[w][3].extend(take)  # 子のPへ
                k += share
    # 配分後にPS→I更新
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
        # 定義が (root, layer="supply", buffer_name="BUFFER") なら out_root のみ渡す
        return _call(outbound_backward_pull_buffer_to_leaf, out_root, layer="supply", **kw)

    raise ValueError(f"unknown mode={mode}")





def run_engine(out_root, in_root,  decouple_nodes, mode: str, layer: str = "demand", **kw):
#def run_engine(out_root, in_root,  *, mode: str, layer: str = "demand", **kw):
#def run_engine(root, *, mode: str, layer: str = "demand", **kw):
    if mode == "outbound_backward_leaf_to_MOM":
        return outbound_backward_leaf_to_MOM(out_root, in_root, layer=layer)
    
    if mode == "inbound_MOM_leveling_vs_capacity":
        #return inbound_MOM_leveling_vs_capacity(out_root, in_root, layer=layer, **kw)
    
        def _only_accepted_kwargs(func, kw: dict) -> dict:
            try:
                params = inspect.signature(func).parameters
                return {k: v for k, v in kw.items() if k in params}
            except Exception:
                return {}

        # ...run_engine内の該当ブロックだけ差し替え...
        # 旧: return inbound_MOM_leveling_vs_capacity(out_root, in_root, layer=layer, **kw)
        safe_kw = _only_accepted_kwargs(inbound_MOM_leveling_vs_capacity, kw)
        return inbound_MOM_leveling_vs_capacity(out_root, in_root, **safe_kw)

    if mode == "inbound_backward_MOM_to_leaf":
        return inbound_backward_MOM_to_leaf(out_root, in_root, layer=layer)
    
    if mode == "inbound_forward_leaf_to_MOM":
        return inbound_forward_leaf_to_MOM(out_root, in_root, layer="supply")
    
    if mode == "outbound_forward_push_DAD_to_buffer":
        return push_pull(out_root, in_root, decouple_nodes, **kw)
        #return push_pull(out_root, in_root, layer="supply", **kw)
        #return outbound_forward_push_DAD_to_buffer(out_root, in_root, layer="supply", **kw)
        #def push_pull(out_root, decouple_nodes): # self.decouple_node_selected
    
    if mode == "outbound_backward_pull_buffer_to_leaf":
        return outbound_backward_pull_buffer_to_leaf(out_root, in_root, layer="supply", **kw)
    
    raise ValueError(f"unknown mode={mode}")
