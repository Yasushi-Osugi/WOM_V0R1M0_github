# pysi/scripts/quick_pair_check.py
# 起動方法の例
#cd C:\Users\ohsug\PySI_V0R8_SQL_031
#python -m pysi.scripts.quick_pair_check ^
#  --db var\psi.sqlite ^
#  --scenario Baseline ^
#  --node CS_JPN ^
#  --product prod-A
import sqlite3
import argparse
from pathlib import Path
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="var/psi.sqlite")
    ap.add_argument("--scenario", default="Baseline")
    ap.add_argument("--node", required=True)
    ap.add_argument("--product", required=True)
    args = ap.parse_args()
    # dbパスを安定解決：相対なら「リポジトリ直下」を起点に解決
    here = Path(__file__).resolve()
    repo_root = here.parents[2]     # .../pysi/scripts/ -> repo root
    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = (repo_root / args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"[ERR] DB not found: {db_path}")
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    sid_row = con.execute("SELECT id FROM scenario WHERE name=?", (args.scenario,)).fetchone()
    if not sid_row:
        raise SystemExit(f"[ERR] scenario not found: {args.scenario}")
    sid = sid_row["id"]
    nid_row = con.execute("SELECT id FROM node WHERE name=?", (args.node,)).fetchone()
    if not nid_row:
        raise SystemExit(f"[ERR] node not found: {args.node}")
    nid = nid_row["id"]
    pid_row = con.execute("SELECT id FROM product WHERE name=?", (args.product,)).fetchone()
    if not pid_row:
        raise SystemExit(f"[ERR] product not found: {args.product}")
    pid = pid_row["id"]
    buckets = con.execute("""
        SELECT bucket, COUNT(*)
        FROM lot_bucket
        WHERE scenario_id=? AND node_id=? AND product_id=?
        GROUP BY bucket ORDER BY bucket
    """, (sid, nid, pid)).fetchall()
    topweeks = con.execute("""
        SELECT week_index, COUNT(*) AS lots
        FROM lot_bucket
        WHERE scenario_id=? AND node_id=? AND product_id=? AND bucket='S'
        GROUP BY week_index ORDER BY lots DESC, week_index LIMIT 5
    """, (sid, nid, pid)).fetchall()
    print({
        "db": str(db_path),
        "scenario": args.scenario,
        "node": args.node,
        "product": args.product,
        "buckets": [(r["bucket"], r[1]) for r in buckets],
        "top_weeks_S": [(r["week_index"], r[1]) for r in topweeks],
    })
    con.close()
if __name__ == "__main__":
    main()
