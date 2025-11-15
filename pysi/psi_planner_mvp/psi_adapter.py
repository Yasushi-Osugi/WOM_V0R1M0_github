#psi_adapter.py
from typing import Dict, Any, Optional
from engine_api import run_weekly_psi, RunOptions, DEFAULT_KPIS
class EngineNotAvailable(Exception):
    pass
def run_real_engine(scenario_name: str,
                    params: Dict[str, Any],
                    filters: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    # 実エンジンに接続済みならそのままrun_weekly_psiが内部エンジンを呼びます
    result = run_weekly_psi(
        scenario_name=scenario_name,
        overrides=params,
        kpis=DEFAULT_KPIS,
        options=RunOptions(horizon_weeks=26, return_level="summary", filters=filters)
    )
    return result.summary
