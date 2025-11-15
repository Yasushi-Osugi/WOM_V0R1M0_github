# iso_calendar_sync_on_scenario.py
# python -m pysi.scripts.iso_calendar_sync_on_scenario --db var\psi.sqlite --scenario Baseline
r"""
Sync calendar_iso to match (plan_year_st, plan_range) of a scenario.
Usage:
  python -m pysi.scripts.iso_calendar_sync_on_scenario --db var\psi.sqlite --scenario Baseline
"""
import argparse
import sqlite3
from pysi.db.calendar_iso import ensure_calendar_iso
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--scenario", required=True)
    args = ap.parse_args()
    con = sqlite3.connect(args.db)
    con.execute("PRAGMA foreign_keys=ON")
    row = con.execute(
        "SELECT plan_year_st, plan_range FROM scenario WHERE name=?",
        (args.scenario,)
    ).fetchone()
    if not row:
        raise SystemExit(f"[ERR] scenario '{args.scenario}' not found. Run ETL first.")
    y0, pr = map(int, row)
    n = ensure_calendar_iso(con, y0, pr)
    print(f"[OK] calendar_iso synced: weeks={n}, plan_year_st={y0}, plan_range={pr}")
    con.close()
if __name__ == "__main__":
    main()
