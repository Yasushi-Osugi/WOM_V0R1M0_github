# psi_runner.py
from typing import Dict
import math
# 想定KPI: gross_profit, inventory_turns, stockout_rate
def run_simulation(scenario_name: str, params: Dict[str, str]) -> Dict[str, float]:
    lead = float(params.get("lead_time_days", 30))
    markup = float(params.get("price_markup", 1.2))
    service = float(params.get("service_level", 0.95))
    # デモ用のダミー式（単調性と直感の整合を重視）
    demand = 1000 * (1.0 - 0.8*(markup-1.0))              # 高価格→需要減
    demand = max(demand, 10)
    cogs = 200
    price = cogs * markup
    gross_profit = (price - cogs) * demand * 0.1           # 0.1は週次販路係数
    # 在庫回転：LT長いと悪化、サービス上げると在庫増で悪化
    inventory_turns = max(0.1, 12.0 / (1.0 + lead/60.0 + (service-0.9)*3))
    # 欠品率：サービス上げると低下、LT長いと上昇
    stockout_rate = min(0.5, max(0.0, 0.3 + lead/300.0 - (service-0.8)))
    return {
        "gross_profit": round(gross_profit, 2),
        "inventory_turns": round(inventory_turns, 2),
        "stockout_rate": round(stockout_rate, 3)
    }