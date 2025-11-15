#engine_api.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional, Literal, Dict, List, Union
import pandas as pd
DEFAULT_KPIS = [
    "revenue","cogs","gross_profit","gross_margin",
    "inventory_turns","stockout_rate"
]
@dataclass
class RunOptions:
    horizon_weeks: int = 26
    seed: Optional[int] = None
    return_level: Literal["summary","node","none"] = "summary"
    # 例: {"sku":["RICE-A","RICE-B"], "origin":"VN", "dest":"JP"}
    filters: Optional[Dict[str, Union[str, List[str]]]] = None
@dataclass
class EngineResult:
    summary: Dict[str, float]
    by_node: Optional[pd.DataFrame]
    meta: Dict[str, Any]
class PlanNode:
    def __init__(self, id: str, name: str, node_type: str,
                 sku: str | None = None, region: str | None = None,
                 origin: str | None = None, dest: str | None = None,
                 channel: str | None = None, attrs: Dict[str, Any] | None = None):
        self.id = id
        self.name = name
        self.node_type = node_type
        self.sku = sku; self.region = region
        self.origin = origin; self.dest = dest
        self.channel = channel
        self.attrs = attrs or {}
        self.children: list["PlanNode"] = []
        self.parent: "PlanNode | None" = None
    def add_child(self, child: "PlanNode"):
        child.parent = self
        self.children.append(child)
def run_weekly_psi(
    scenario_name: str,
    overrides: Optional[Dict[str, Any]] = None,
    kpis: Optional[List[str]] = None,
    options: RunOptions = RunOptions(),
) -> EngineResult:
    kpis = kpis or DEFAULT_KPIS
    root, meta = build_plan_from_db(scenario_name, filters=options.filters)
    meta["overrides"] = overrides or {}
    simulate(root, horizon_weeks=options.horizon_weeks, seed=options.seed, overrides=overrides)
    summary, df = evaluate(root, kpis)
    if options.return_level != "node":
        df = None
    return EngineResult(summary=summary, by_node=df, meta={
        **meta, "scenario_name": scenario_name, "filters": options.filters, "kpis": kpis
    })
def build_plan_from_db(scenario_name: str, filters: dict | None = None) -> tuple[PlanNode, Dict[str, Any]]:
    # TODO: 実DBに置換（plan_nodes/plan_lanes から再構成）
    root = _build_sample_graph()
    if filters:
        root = prune_graph(root, filters)
    meta = {"built_from": "db", "node_count": count_nodes(root)}
    return root, meta
def prune_graph(root: PlanNode, filters: Dict[str, Union[str, List[str]]]) -> PlanNode:
    def match(node: PlanNode) -> bool:
        if not filters:
            return True
        for k, v in filters.items():
            node_val = getattr(node, k, None)
            if isinstance(v, list):
                if node_val not in v: return False
            else:
                if node_val != v: return False
        return True
    def dfs(n: PlanNode) -> tuple[bool, PlanNode | None]:
        kept_children: list[PlanNode] = []
        any_child_kept = False
        for c in n.children:
            child_keep, child_new = dfs(c)
            if child_keep and child_new:
                kept_children.append(child_new); any_child_kept = True
        new_node = PlanNode(n.id, n.name, n.node_type, n.sku, n.region, n.origin, n.dest, n.channel, n.attrs.copy())
        for kc in kept_children: new_node.add_child(kc)
        keep_self = match(n) or any_child_kept
        return keep_self, (new_node if keep_self else None)
    keep, new_root = dfs(root)
    if not keep or new_root is None:
        return PlanNode(id=root.id, name=root.name, node_type=root.node_type)
    return new_root
def count_nodes(root: PlanNode) -> int:
    return 1 + sum(count_nodes(c) for c in root.children)
#def simulate(root: PlanNode, horizon_weeks: int, seed: int | None, overrides: dict | None):
#    # ダミー：実エンジン接続時に置換
#    def _walk(n: PlanNode):
#        n.attrs.setdefault("shipped_qty", 100.0)
#        n.attrs.setdefault("price", 250.0)
#        n.attrs.setdefault("cogs", 200.0)
#        for c in n.children: _walk(c)
#    _walk(root)
# engine_api.py
try:
    from real_engine_bridge import run_core as _run_core   # 既存エンジン呼び出し
    _import_err = None
except Exception as e:
    _run_core = None
    _import_err = e
def simulate(root, horizon_weeks, seed, overrides):
    """実エンジンがあれば呼び出し、失敗時はスタブにフォールバック"""
    # 実エンジン
    if _run_core is not None:
        try:
            _run_core(root, horizon_weeks, seed, overrides or {})
            return
        except Exception as e:
            print("[engine_api.simulate] bridge failed, fallback to stub:", e)
    # スタブ
    def _walk(n):
        n.attrs.setdefault("shipped_qty", 100.0)
        n.attrs.setdefault("price", 250.0)
        n.attrs.setdefault("cogs", 200.0)
        for c in n.children:
            _walk(c)
    if _import_err:
        print("[engine_api.simulate] bridge not loaded:", _import_err)
    _walk(root)
def evaluate(root: PlanNode, kpis: List[str]) -> tuple[Dict[str, float], pd.DataFrame]:
    rows: list[dict] = []
    def _collect(n: PlanNode):
        rows.append({
            "node_id": n.id, "node_type": n.node_type, "sku": n.sku, "region": n.region,
            "origin": n.origin, "dest": n.dest, "channel": n.channel,
            "revenue": n.attrs.get("price", 0) * n.attrs.get("shipped_qty", 0),
            "cogs": n.attrs.get("cogs", 0) * 1.0,
            "inventory_turns": 8.0, "stockout_rate": 0.05,
        })
        for c in n.children: _collect(c)
    _collect(root)
    df = pd.DataFrame(rows)
    summary: Dict[str, float] = {}
    if "revenue" in kpis: summary["revenue"] = float(df["revenue"].sum())
    if "cogs" in kpis:    summary["cogs"] = float(df["cogs"].sum())
    if "gross_profit" in kpis: summary["gross_profit"] = summary.get("revenue",0.0)-summary.get("cogs",0.0)
    if "gross_margin" in kpis:
        rv = summary.get("revenue",0.0)
        summary["gross_margin"] = (summary.get("gross_profit",0.0)/rv) if rv else 0.0
    if "inventory_turns" in kpis: summary["inventory_turns"] = float(df["inventory_turns"].mean())
    if "stockout_rate" in kpis:   summary["stockout_rate"]   = float(df["stockout_rate"].mean())
    return summary, df
def _build_sample_graph() -> PlanNode:
    root = PlanNode("root","SupplyChain","root")
    plant = PlanNode("p1","Plant VN","plant", origin="VN")
    dc    = PlanNode("d1","DC JP","dc", origin="VN", dest="JP")
    m1    = PlanNode("m1","Market Kanto EC RICE-A","market",
                     sku="RICE-A", region="Kanto", origin="VN", dest="JP", channel="EC")
    m2    = PlanNode("m2","Market Kanto Retail RICE-A","market",
                     sku="RICE-A", region="Kanto", origin="VN", dest="JP", channel="Retail")
    root.add_child(plant); plant.add_child(dc); dc.add_child(m1); dc.add_child(m2)
    return root
# --- add: facets collector ---
from typing import Dict, List
def collect_facets(root: PlanNode) -> Dict[str, List[str]]:
    """PlanGraph から UI フィルタ候補（sku/region/origin/dest/channel）を抽出。"""
    facets = {k: set() for k in ("sku","region","origin","dest","channel")}
    def walk(n: PlanNode):
        # 追加: inboundなどUI候補に出したくないノードはスキップ
        if isinstance(getattr(n, "attrs", None), dict) and n.attrs.get("facet_exclude"):
            for c in n.children: walk(c)
            return
        for k in facets:
            v = getattr(n, k, None)
            if v:
                facets[k].add(v)
        for c in n.children:
            walk(c)
    walk(root)
    return {k: sorted(list(v)) for k, v in facets.items()}
#@250811 ADD
# --- helpers: attach origin/dest, count, facets -----------------
def attach_commons(root: "PlanNode") -> None:
    """親子関係から origin/dest を自動補完（未設定のみ）。"""
    def walk(n: "PlanNode"):
        for c in n.children:
            if getattr(c, "origin", None) is None:
                c.origin = n.id
            if getattr(c, "dest", None) is None:
                c.dest = c.id
            walk(c)
    walk(root)
def count_nodes(root: "PlanNode") -> int:
    return 1 + sum(count_nodes(c) for c in root.children)
def collect_facets(root: "PlanNode") -> dict[str, list[str]]:
    facets = {k: set() for k in ("sku","region","origin","dest","channel")}
    def walk(n: "PlanNode"):
        for k in facets:
            v = getattr(n, k, None)
            if v:
                facets[k].add(v)
        for c in n.children:
            walk(c)
    walk(root)
    return {k: sorted(list(v)) for k, v in facets.items()}
# 追加
def _bridge():
    try:
        import real_engine_bridge as bridge
        print("[engine_api] using bridge")
        return bridge
    except Exception as e:
        print("[engine_api] bridge unavailable:", e)
        return None
def build_plan_from_db(scenario_name: str, filters: dict | None = None):
    bridge = _bridge()
    if bridge and hasattr(bridge, "build_plan_graph"):
        # filters から SKU を1つ渡す（複数や未指定は super-root に任せる）
        def _first(x):
            return (x[0] if isinstance(x, list) and x else x)
        product = _first(filters.get("sku")) if (filters and "sku" in filters) else None
        root = bridge.build_plan_graph(scenario_name, product=product, filters=filters)
        attach_commons(root)
        if filters:
            root = prune_graph(root, filters)
        meta = {"built_from": "bridge", "node_count": count_nodes(root)}
        return root, meta
    # ←ブリッジが無い/失敗時のみサンプルにフォールバック
    root = _build_sample_graph()
    attach_commons(root)
    if filters:
        root = prune_graph(root, filters)
    meta = {"built_from": "sample", "node_count": count_nodes(root)}
    return root, meta
