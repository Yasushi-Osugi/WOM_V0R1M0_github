# psi/gui/engine_api.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import re
from functools import lru_cache
# PlanEnv / Config は既存のものを利用
from pysi.psi_planner_mvp.plan_env_main import PlanEnv
from pysi.utils.config import Config
# === UI向けの軽量ノード ===
@dataclass
class UINode:
    id: str
    name: str
    sku: Optional[str] = None
    node_type: str = "node"
    region: str = "NA"
    origin: str = "NA"
    dest: str = "NA"
    attrs: Dict[str, Any] = field(default_factory=dict)
    children: List["UINode"] = field(default_factory=list)
    def add(self, c: "UINode"):
        self.children.append(c)
def _infer_region(name: str) -> str:
    # 例: "CS_JPN" -> "JPN" / "GR_CS_JPN" -> 最後の _ 区切りを採用
    m = re.search(r"_([A-Za-z0-9]+)$", name)
    return m.group(1) if m else "NA"
def _infer_channel(name: str) -> str:
    # 超軽量ヒューリスティック（足りなければ随時拡張）
    if name.startswith("CS_"):  return "Consumer"
    if name.startswith("RT_"):  return "Retail"
    if name.startswith("WS"):   return "Wholesale"
    if name.startswith("DAD"):  return "Distribution"
    if name.startswith("GR"):   return "Government"
    if name == "supply_point":  return "SupplyPoint"
    return "NA"
# PlanEnv をモジュール内でキャッシュ（Streamlit の再実行にも強い）
@lru_cache(maxsize=1)
def _get_env() -> PlanEnv:
    cfg = Config()                      # 既存の Config を利用（DATA_DIRECTORY 等）
    env = PlanEnv(cfg)
    env.load_data_files()               # product_tree_* + cost/price 反映
    env.init_psi_spaces_and_demand()    # sku_S_month_data.csv → 週次/PSI スロット投入
    return env
def _adapt_one_tree(root_plan, product_name: str, inbound: bool) -> UINode:
    """
    PlanNode 木 → UINode 木に変換。
    inbound=True のときは ID に 'IN::' を付与して app の Direction フィルタに対応。
    """
    id_prefix = "IN::" if inbound else ""
    def walk(pn, parent_ui: Optional[UINode]) -> UINode:
        node_id = f"{id_prefix}{pn.name}"
        ui = UINode(
            id=node_id,
            name=pn.name,
            sku=product_name,
            node_type=getattr(pn, "node_type", "node"),
            region=_infer_region(pn.name),
            origin=parent_ui.id if parent_ui else "ROOT",
            dest=node_id,
            attrs={"channel": _infer_channel(pn.name),
                   "direction": "IN" if inbound else "OUT"}
        )
        if parent_ui:
            parent_ui.add(ui)
        for c in getattr(pn, "children", []):
            walk(c, ui)
        return ui
    return walk(root_plan, None)
def _apply_filters(root: UINode, filters: Optional[Dict[str, Any]]) -> UINode:
    """
    UINode 木をフィルタ（sku/region/origin/dest/channel）。
    条件にマッチしないサブツリーを剪定。条件なしは無変更。
    """
    if not filters:
        return root
    def match(n: UINode) -> bool:
        def _in(k: str, v: Any, cand: Any) -> bool:
            # 単一値 or リストのどちらでも受ける
            if isinstance(v, list):
                return cand in v
            return cand == v
        ok = True
        if "sku" in filters:     ok &= _in("sku",     filters["sku"],     n.sku)
        if "region" in filters:  ok &= _in("region",  filters["region"],  n.region)
        if "origin" in filters:  ok &= _in("origin",  filters["origin"],  n.origin)
        if "dest" in filters:    ok &= _in("dest",    filters["dest"],    n.dest)
        if "channel" in filters: ok &= _in("channel", filters["channel"], n.attrs.get("channel"))
        return ok
    def prune(n: UINode) -> Optional[UINode]:
        kids = [prune(c) for c in n.children]
        kids = [k for k in kids if k is not None]
        n.children = kids
        # ルートは無条件で残す。その下は自分 or 子がヒットすれば残す
        if n.origin == "ROOT":
            return n
        if match(n) or n.children:
            return n
        return None
    out = prune(root)
    return out or UINode(id="EMPTY", name="EMPTY")
def count_nodes(root: UINode) -> int:
    cnt = 0
    stack = [root]
    while stack:
        n = stack.pop()
        cnt += 1
        stack.extend(n.children)
    return cnt
def collect_facets(root: UINode) -> Dict[str, List[Any]]:
    sku, region, origin, dest, channel = set(), set(), set(), set(), set()
    st = [root]
    while st:
        n = st.pop()
        if n.sku: sku.add(n.sku)
        if n.region: region.add(n.region)
        if n.origin: origin.add(n.origin)
        if n.dest: dest.add(n.dest)
        ch = n.attrs.get("channel")
        if ch: channel.add(ch)
        st.extend(n.children)
    return {
        "sku": sorted(sku),
        "region": sorted(region),
        "origin": sorted(origin),
        "dest": sorted(dest),
        "channel": sorted(channel),
    }
def build_plan_from_db(scenario_name: str, filters: Optional[Dict[str, Any]] = None) -> Tuple[UINode, Dict[str, Any]]:
    """
    app.py が期待している API。現段階では DB を使わず、
    PlanEnv の CSV ローダを使って OUT/IN の二本を束ねた統合グラフを返す。
    将来 DB 化する際も、この関数の中身だけ差し替えれば app 側は無改造でOK。
    """
    env = _get_env()
    # OUT/IN の両方を束ねるルートを作る
    root_ui = UINode(id="ROOT", name="ROOT", attrs={"direction": "OUT+IN"})
    for prod, root_ot in env.prod_tree_dict_OT.items():
        out_sub = _adapt_one_tree(root_ot, product_name=prod, inbound=False)
        root_ui.add(out_sub)
    for prod, root_in in env.prod_tree_dict_IN.items():
        in_sub = _adapt_one_tree(root_in, product_name=prod, inbound=True)
        root_ui.add(in_sub)
    # フィルタ適用（必要なら剪定）
    root_filtered = _apply_filters(root_ui, filters)
    meta = {
        "built_from": "engine-csv",     # 将来 "db" に切替予定
        "scenario": scenario_name or "(default)",
        "filters": filters or {},
        "node_count": count_nodes(root_filtered),
    }
    return root_filtered, meta
