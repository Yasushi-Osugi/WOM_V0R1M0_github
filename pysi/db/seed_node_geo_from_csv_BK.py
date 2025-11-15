# seed_node_geo_from_csv.py
# starter
#python seed_node_geo_from_csv.py ^
#  --db "C:\...\data\pysi.sqlite3" ^
#  --csv "C:\...\data\node_geo.csv" --wipe
# "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\pysi.sqlite3"
# "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\node_geo.csv"
# python seed_node_geo_from_csv.py  --db "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\pysi.sqlite3"  --csv "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\node_geo.csv" --wipe
import argparse, csv, sqlite3, sys
from pathlib import Path
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--csv", required=True, help="node_geo.csv (node_name,lat,lon)")
    ap.add_argument("--wipe", action="store_true", help="node_geo を全消ししてから投入")
    args = ap.parse_args()
    db = Path(args.db); csv_path = Path(args.csv)
    conn = sqlite3.connect(str(db)); conn.execute("PRAGMA foreign_keys=ON;")
    try:
        if args.wipe:
            conn.execute("DELETE FROM node_geo;")
        with csv_path.open(encoding="utf-8", newline="") as f:
            rdr = csv.DictReader(f)
            rows = [(r["node_name"].strip(),
                     float(str(r["lat"]).strip()),
                     float(str(r["lon"]).strip())) for r in rdr if r.get("node_name")]
        conn.executemany(
            "INSERT INTO node_geo(node_name,lat,lon) VALUES(?,?,?) "
            "ON CONFLICT(node_name) DO UPDATE SET lat=excluded.lat, lon=excluded.lon",
            rows
        )
        conn.commit()
        print(f"[OK] upsert {len(rows)} rows into node_geo")
        # 存在しない node を検出
        missing = conn.execute("""
          SELECT g.node_name FROM node_geo g
          LEFT JOIN node n ON n.node_name=g.node_name
          WHERE n.node_name IS NULL
        """).fetchall()
        if missing:
            print("[WARN] not found in node table:", [m[0] for m in missing][:20], "...")
    finally:
        conn.close()
if __name__ == "__main__":
    sys.exit(main())
