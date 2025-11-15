# psi/gui/psi_adapter.py
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
from functools import lru_cache
from pysi.psi_planner_mvp.plan_env_main import PlanEnv
from pysi.utils.config import Config
from pysi.network.tree import eval_supply_chain_cost   # 既存の評価関数を再利用
class EngineNotAvailable(Exception):
    pass
@lru_cache(maxsize=1)
def _get_env() -> PlanEnv:
    cfg = Config()
    env = PlanEnv(cfg)
    env.load_data_files()
    env.init_psi_spaces_and_demand()
    return env
def _psi_stats(root) -> Tuple[int, int]:
    """
    ごく軽い KPI 用集計（Pロット数と Iロット数）※ざっくり版
    """
    total_p = 0
    total_i = 0
    stack = [root]
    while stack:
        n = stack.pop()
        psi = getattr(n, "psi4demand", None)
        if isinstance(psi, list):
            for wk in psi:
                # wk = [S, CO, I, P]
                if len(wk) >= 3:
                    total_i += len(wk[2])
                if len(wk) >= 4:
                    total_p += len(wk[3])
        stack.extend(getattr(n, "children", []) or [])
    return total_p, total_i
def run_real_engine(scenario_name: str, params: Dict[str, Any], filters: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """
    Streamlit app から呼ばれる実エンジンの実行口。
    - ここでは「選択SKU（なければ全SKU）」の OUT ツリーを評価し、KPI を返します。
    - 将来、params や filters を PlanEnv/DB に反映する処理を足します。
    """
    env = _get_env()
    # 対象SKU
    skus = filters.get("sku") if isinstance(filters, dict) and "sku" in filters else None
    if skus and not isinstance(skus, list):
        skus = [skus]
    if not skus:
        skus = list(env.prod_tree_dict_OT.keys())
    gross_profit = 0.0
    ship_lots = 0
    inv_lots = 0
    for sku in skus:
        root = env.prod_tree_dict_OT.get(sku)
        if not root:
            continue
        # コストベースの評価（既存関数）
        rev, prof = eval_supply_chain_cost(root)
        gross_profit += float(prof)
        p, i = _psi_stats(root)
        ship_lots += p
        inv_lots += i
    # 在庫回転は簡易指標（将来は在庫金額ベースへ）
    inventory_turns = float(ship_lots) / float(max(1, inv_lots))
    # ひとまず欠品率は 0 に（将来は計画未充足分から算出）
    stockout_rate = 0.0
    return {
        "gross_profit": round(gross_profit, 2),
        "inventory_turns": round(inventory_turns, 3),
        "stockout_rate": round(stockout_rate, 3),
    }
