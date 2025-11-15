# engine_api.py
from dataclasses import dataclass
from typing import Any, Literal, Dict, List, Optional
import pandas as pd
DEFAULT_KPIS = ["revenue","cogs","gross_profit","gross_margin",
                "inventory_turns","stockout_rate"]
@dataclass
class RunOptions:
    horizon_weeks: int = 26
    seed: Optional[int] = None
    return_level: Literal["summary","node","none"] = "summary"  # nodeは明細返却
@dataclass
class EngineResult:
    summary: Dict[str, float]
    by_node: Optional[pd.DataFrame]
    meta: Dict[str, Any]  # run_id, scenario_name, resolved_params など
def run_weekly_psi(
    scenario_name: str,
    overrides: Optional[Dict[str, Any]] = None,
    kpis: Optional[List[str]] = None,
    options: RunOptions = RunOptions(),
) -> EngineResult:
    """
    1) DBから PlanGraph を build
    2) overrides を適用（resolveで優先順位を解決）
    3) Planning Engine を実行（週次シミュレーション）
    4) evaluate()でKPIを算出（summary & by_node）
    5) EngineResult を返す
    """
# --- add: facets collector ---
from typing import Dict, List
def collect_facets(root: "PlanNode") -> Dict[str, List[str]]:
    """PlanGraph から UI フィルタ候補（sku/region/origin/dest/channel）を抽出。"""
    facets = {k: set() for k in ("sku","region","origin","dest","channel")}
    def walk(n: "PlanNode"):
        # 1) ノードの軽量属性から収集
        for k in facets:
            v = getattr(n, k, None)
            if v:
                facets[k].add(v)
        # 2) 将来のための拡張（在庫や出荷のレコードからSKUを収集）
        inv = (n.attrs.get("inventory_by_sku") or {})
        facets["sku"].update(inv.keys())
        for rec in n.attrs.get("shipments", []):
            sku = rec.get("sku")
            if sku:
                facets["sku"].add(sku)
        for c in n.children:
            walk(c)
    walk(root)
    return {k: sorted(list(v)) for k, v in facets.items()}
