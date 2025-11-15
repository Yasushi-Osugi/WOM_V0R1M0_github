# pysi/scripts/add_perf_indexes.py
import sqlite3, argparse, pathlib
DDL = [
    # 週次需要クエリの主キー
    "CREATE INDEX IF NOT EXISTS idx_weekly_demand_q1 ON weekly_demand (scenario_id, node_id, product_id, iso_year, iso_week)",
    # lot 検索（使っていれば）
    "CREATE INDEX IF NOT EXISTS idx_lot_q1 ON lot (scenario_id, node_id, product_id, iso_year, iso_week)",
    # 集計・描画で多用する条件
    "CREATE INDEX IF NOT EXISTS idx_lot_bucket_q1 ON lot_bucket (scenario_id, layer, node_id, product_id, week_index, bucket)"
    # ※ UNIQUE(lot_id, …) だけだと prefix は効くものの、最後に lot_id が付いているため
    #   この“短いキーの索引”を別途持つと実測で効きます。
]
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    args = ap.parse_args()
    p = pathlib.Path(args.db).resolve()
    con = sqlite3.connect(str(p))
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    for sql in DDL:
        con.execute(sql)
    con.commit()
    con.execute("PRAGMA optimize;")
    print("[OK] perf indexes added to:", p)
if __name__ == "__main__":
    main()
