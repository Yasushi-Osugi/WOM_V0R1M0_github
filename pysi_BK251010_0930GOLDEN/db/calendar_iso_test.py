# calendar_iso_test.py
import sqlite3
from calendar_iso import ensure_calendar_iso, load_week_index_map, weeks_count
conn = sqlite3.connect("psi.sqlite")
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA synchronous=NORMAL;")
conn.execute("PRAGMA foreign_keys=ON;")
# 例：2025年開始・3カ年（+αの“はみ出し年”は後段で吸収する前提なら plan_range を +1 してもOK）
plan_year_st = 2025
plan_range   = 3
n_weeks = ensure_calendar_iso(conn, plan_year_st, plan_range)
print("weeks in calendar_iso =", n_weeks)  # 例: 156〜159 付近（53週の年数に依存）
wkmap = load_week_index_map(conn)
print("map sample:", list(wkmap.items())[:5])
