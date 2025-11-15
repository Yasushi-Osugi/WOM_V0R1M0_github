# app/entry_sql.py
import argparse
from types import SimpleNamespace
from app.run_once import run_once

def parse_args():
    ap = argparse.ArgumentParser(description="PySI SQL starter")
    ap.add_argument("--dsn", required=True)               # sqlite:///path.sqlite など
    ap.add_argument("--schema", default=None)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--plugins", default="./plugins")
    ap.add_argument("--weeks", type=int, default=5)
    ap.add_argument("--iso-year-start", type=int, default=2025)
    ap.add_argument("--iso-week-start", type=int, default=1)
    return ap.parse_args()

def main():
    a = parse_args()
    cfg = SimpleNamespace(
        scenario_id=a.scenario,
        plugins_dir=a.plugins,
        input=SimpleNamespace(kind="sql", dsn=a.dsn, schema=a.schema),
        calendar=dict(iso_year_start=a.iso_year_start,
                      iso_week_start=a.iso_week_start,
                      weeks=a.weeks),
    )
    run_once(cfg)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
