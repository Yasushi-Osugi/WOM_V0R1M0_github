# pysi/plugins/diagnostics.py
from __future__ import annotations
import os
from typing import Any
from pysi.core.hooks.core import action, filter

_DIAG = os.getenv("HOOKS_DIAG", "0") not in ("", "0", "false", "False")

@action("before_scenario_run", priority=10)
def _log_before(gui=None, db_path:str|None=None, scenario_id:str|None=None, **_:Any):
    if _DIAG:
        print(f"[diag] before_scenario_run sid={scenario_id} db={db_path}")

@action("after_scenario_run", priority=90)
def _log_after(run_id:str|None=None, **_:Any):
    if _DIAG:
        print(f"[diag] after_scenario_run run_id={run_id}")

@filter("offering_price_df", priority=50)
def _peek_price(df, **ctx):
    # 何もしない（壊さない）— DIAG時だけ行数をログ
    if _DIAG:
        print(f"[diag] offering_price_df rows={len(df)} ctx={_short_ctx(ctx)}")
    return df

@filter("cost_df", priority=50)
def _peek_cost(df, **ctx):
    if _DIAG:
        print(f"[diag] cost_df rows={len(df)} ctx={_short_ctx(ctx)}")
    return df

def _short_ctx(ctx:dict) -> dict:
    keys = ("scenario_id","source")
    return {k: ctx.get(k) for k in keys}
