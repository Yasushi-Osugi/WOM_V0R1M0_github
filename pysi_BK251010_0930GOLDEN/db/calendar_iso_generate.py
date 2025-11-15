# calendar_iso_generate.py
import sqlite3
from calendar_iso import ensure_calendar_iso, load_week_index_map, weeks_count
conn = sqlite3.connect("psi.sqlite")
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("PRAGMA synchronous=NORMAL;")
conn.execute("PRAGMA foreign_keys=ON;")
# 📌 DDL（最初に必ず1回だけ実行する）
conn.execute("""
CREATE TABLE IF NOT EXISTS calendar_iso (
  week_index INTEGER PRIMARY KEY,
  iso_year   INTEGER NOT NULL,
  iso_week   INTEGER NOT NULL,
  week_start TEXT    NOT NULL,
  week_end   TEXT    NOT NULL,
  UNIQUE (iso_year, iso_week)
);
""")
# ✅ カレンダ構築
#plan_year_st = 2025
#plan_range   = 3
plan_year_st = 2024
plan_range   = 20
n_weeks = ensure_calendar_iso(conn, plan_year_st, plan_range)
print("weeks in calendar_iso =", n_weeks)
wkmap = load_week_index_map(conn)
print("map sample:", list(wkmap.items())[:5])
