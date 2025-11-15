# pysi/db/calendar_sync.py
from __future__ import annotations
import sqlite3
from typing import Optional, Tuple
from pysi.db.calendar_iso import ensure_calendar_iso
def _bounds_for_scenario(conn: sqlite3.Connection, scenario_id: int) -> Tuple[int, int]:
    row = conn.execute(
        "SELECT plan_year_st, plan_range FROM scenario WHERE id=?",
        (int(scenario_id),)
    ).fetchone()
    if not row:
        raise ValueError(f"scenario id not found: {scenario_id}")
    return int(row[0]), int(row[1])
def sync_calendar_iso(
    conn: sqlite3.Connection,
    scenario_id: Optional[int] = None,
    plan_year_st: Optional[int] = None,
    plan_range: Optional[int] = None,
) -> int:
    """
    calendar_iso を冪等に同期。
    - scenario_id を渡せばシナリオの境界から同期
    - plan_year_st/plan_range を渡せばそれで同期
    - どちらも無ければ最初のシナリオから同期
    戻り値: 週数
    """
    if scenario_id is not None:
        pys, pr = _bounds_for_scenario(conn, int(scenario_id))
    elif plan_year_st is not None and plan_range is not None:
        pys, pr = int(plan_year_st), int(plan_range)
    else:
        row = conn.execute(
            "SELECT plan_year_st, plan_range FROM scenario ORDER BY id LIMIT 1"
        ).fetchone()
        if not row:
            raise ValueError(
                "No scenario found and no (plan_year_st, plan_range) provided."
            )
        pys, pr = int(row[0]), int(row[1])
    return ensure_calendar_iso(conn, pys, pr)
__all__ = ["sync_calendar_iso"]
