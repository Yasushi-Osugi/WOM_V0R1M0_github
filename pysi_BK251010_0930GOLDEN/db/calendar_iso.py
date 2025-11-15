# calendar_iso.py
from __future__ import annotations
import sqlite3
from datetime import date
from typing import Dict, Tuple, List
def _generate_calendar_rows(plan_year_st: int, plan_range: int) -> List[tuple]:
    """
    ISO週 (iso_year, iso_week) を連続列挙し、存在しない週はスキップ。
    week_index は 0..N-1 の連番。
    戻り値の各要素: (week_index, iso_year, iso_week, week_start, week_end)
    """
    rows = []
    idx = 0
    year_end = int(plan_year_st) + int(plan_range)
    for y in range(int(plan_year_st), year_end):
        for w in range(1, 54):  # ISO週は 1..53
            try:
                week_start = date.fromisocalendar(y, w, 1)  # Monday
                week_end   = date.fromisocalendar(y, w, 7)  # Sunday
            except ValueError:
                continue  # 存在しない週を自然にスキップ
            rows.append((idx, y, w, week_start.isoformat(), week_end.isoformat()))
            idx += 1
    return rows
def rebuild_calendar_iso(conn: sqlite3.Connection, plan_year_st: int, plan_range: int) -> int:
    """
    calendar_iso を指定レンジで再構築（原子的に入替え）。
    返り値: 生成した週数（= rows 件数）
    """
    rows = _generate_calendar_rows(plan_year_st, plan_range)
    with conn:  # トランザクション
        conn.execute("DELETE FROM calendar_iso;")
        conn.executemany(
            """
            INSERT INTO calendar_iso(week_index, iso_year, iso_week, week_start, week_end)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
    return len(rows)
def ensure_calendar_iso(conn: sqlite3.Connection, plan_year_st: int, plan_range: int) -> int:
    """
    既存件数が期待レンジと異なる場合は再構築、同じなら何もしない（冪等）。
    """
    cur = conn.execute("SELECT COUNT(*) FROM calendar_iso;")
    cnt = int(cur.fetchone()[0] or 0)
    exp = len(_generate_calendar_rows(plan_year_st, plan_range))
    if cnt != exp:
        return rebuild_calendar_iso(conn, plan_year_st, plan_range)
    return cnt
def load_week_index_map(conn: sqlite3.Connection) -> Dict[Tuple[int, str], int]:
    """
    DBから (iso_year,'WW') -> week_index のマップを作る。
    """
    cur = conn.execute(
        "SELECT iso_year, iso_week, week_index FROM calendar_iso ORDER BY week_index"
    )
    return {(row[0], f"{int(row[1]):02d}"): int(row[2]) for row in cur.fetchall()}
def weeks_count(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT COUNT(*) FROM calendar_iso;")
    return int(cur.fetchone()[0] or 0)
# おまけ：逆写像（week_index -> (iso_year, 'WW')）
def load_index_to_iso_map(conn: sqlite3.Connection) -> List[Tuple[int, str]]:
    cur = conn.execute(
        "SELECT iso_year, iso_week FROM calendar_iso ORDER BY week_index"
    )
    return [(r[0], f"{int(r[1]):02d}") for r in cur.fetchall()]
