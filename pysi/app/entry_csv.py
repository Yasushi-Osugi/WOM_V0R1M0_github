# pysi/app/entry_csv.py

#通電チェック（10分で到達）
#
#CSVでスモーク
#python -m pysi.app.entry_csv \
#  --root ./examples/scenarios/edu_csv \
#  --scenario EDU_RICE_5W \
#  --plugins ./plugins \
#  --weeks 3 --iso-year-start 2025 --iso-week-start 1
#
# *************
# starter
# *************
#LOGLEVEL=DEBUG
#python -m pysi.app.entry_csv   --root ./examples/scenarios/edu_csv   --scenario EDU_RICE_5W   --plugins ./plugins   --weeks 3 --iso-year-start 2025 --iso-week-start 1  --out out_u
#
#→ 例外なく終わる（after_scenario_run ログ）。

import argparse
from types import SimpleNamespace
from pysi.app.run_once import run_once

def parse_args():
    ap = argparse.ArgumentParser(description="PySI CSV starter")
    ap.add_argument("--root", required=True)              # CSV置き場
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--plugins", default="./plugins")

    ap.add_argument("--out", default="out")

    ap.add_argument("--weeks", type=int, default=5)
    ap.add_argument("--iso-year-start", type=int, default=2025)
    ap.add_argument("--iso-week-start", type=int, default=1)
    return ap.parse_args()

def main():
    a = parse_args()
    cfg = SimpleNamespace(
        scenario_id=a.scenario,
        plugins_dir=a.plugins,
        input=SimpleNamespace(kind="csv", root=a.root),
        calendar=dict(iso_year_start=a.iso_year_start,
                      iso_week_start=a.iso_week_start,
                      weeks=a.weeks),
                      
        output_dir=a.out,
    )
    run_once(cfg)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
