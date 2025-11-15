# seed_node_geo_from_csv.py
# starter
#python seed_node_geo_from_csv.py ^
#  --db "C:\...\data\pysi.sqlite3" ^
#  --csv "C:\...\data\node_geo.csv" --wipe
# "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\pysi.sqlite3"
# "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\node_geo.csv"
# 1.不足ノードを知りたいだけ（作らない）
#python seed_node_geo_from_csv.py --db "<path>\pysi.sqlite3" --csv "<path>\node_geo.csv" --wipe
# python seed_node_geo_from_csv.py  --db "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\pysi.sqlite3"  --csv "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\node_geo.csv" --wipe
# 2.不足ノードを自動作成してから地理座標を入れたい
#python seed_node_geo_from_csv.py --db "<path>\pysi.sqlite3" --csv "<path>\node_geo.csv" --wipe --create-missing
# python seed_node_geo_from_csv.py  --db "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\pysi.sqlite3"  --csv "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\node_geo.csv" --wipe --create-missing
# seed_node_geo_from_csv.py
#
# 1) 不足ノードを知りたいだけ（作らない）
#    python seed_node_geo_from_csv.py --db "<path>\pysi.sqlite3" --csv "<path>\node_geo.csv" --wipe
#
# 2) 不足ノードを自動作成してから地理座標を入れたい
#    python seed_node_geo_from_csv.py --db "<path>\pysi.sqlite3" --csv "<path>\node_geo.csv" --wipe --create-missing
#
# 例）
# python seed_node_geo_from_csv.py ^
#   --db "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\pysi.sqlite3" ^
#   --csv "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\node_geo.csv" ^
#   --wipe --create-missing
import argparse, csv, sqlite3, sys
from pathlib import Path
def _read_csv_rows(csv_path: Path):
    """CSVを読み込み、(node_name, lat, lon) のリストを返す。軽いバリデーション付き。"""
    rows = []
    bad = 0
    with csv_path.open(encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        # 必須カラムチェック（緩め）
        missing_cols = [c for c in ("node_name", "lat", "lon") if c not in (rdr.fieldnames or [])]
        if missing_cols:
            raise ValueError(f"CSV header missing columns: {missing_cols} (found={rdr.fieldnames})")
        for i, r in enumerate(rdr, start=2):  # 2行目=データ行の先頭
            nm = (r.get("node_name") or "").strip()
            if not nm:
                bad += 1
                continue
            try:
                lat = float(str(r["lat"]).strip())
                lon = float(str(r["lon"]).strip())
            except Exception:
                bad += 1
                continue
            rows.append((nm, lat, lon))
    if bad:
        print(f"[WARN] skipped {bad} bad row(s) in CSV (empty node_name or invalid lat/lon).")
    return rows
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="SQLite DB file path")
    ap.add_argument("--csv", required=True, help="node_geo.csv (node_name,lat,lon)")
    ap.add_argument("--wipe", action="store_true", help="node_geo を全消ししてから投入")
    ap.add_argument("--create-missing", dest="create_missing", action="store_true",
                    help="node テーブルに無い node_name を自動追加してから upsert する")
    args = ap.parse_args()
    db = Path(args.db)
    csv_path = Path(args.csv)
    if not db.exists():
        print(f"[ERR ] DB not found: {db}", file=sys.stderr)
        return 2
    if not csv_path.exists():
        print(f"[ERR ] CSV not found: {csv_path}", file=sys.stderr)
        return 2
    # 接続
    conn = sqlite3.connect(str(db))
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        # 既存 node 名セットを取得
        existing = {row[0] for row in conn.execute("SELECT node_name FROM node").fetchall()}
        # CSV 読み込み
        rows = _read_csv_rows(csv_path)
        if not rows:
            print("[WARN] no valid rows in CSV; nothing to do.")
            return 0
        # 不足ノードの洗い出し
        missing = sorted({nm for (nm, _, _) in rows if nm not in existing})
        if missing:
            print(f"[WARN] {len(missing)} node(s) not found in node table: {missing}")
            if not args.create_missing:
                print("[HINT] node に先に追加するか、--create-missing を付けて自動作成してください。")
                return 2  # 非0で終了
            # 自動作成（デフォルト値で node へ追加）
            # schema: node(node_name PK, parent_name, leadtime, ss_days, long_vacation_weeks)
            conn.executemany(
                "INSERT OR IGNORE INTO node(node_name, parent_name, leadtime, ss_days, long_vacation_weeks) "
                "VALUES(?, NULL, 1, 7, '[]')",
                [(nm,) for nm in missing]
            )
            conn.commit()
            print(f"[INFO] created {len(missing)} missing node(s) in node table.")
        # wipe 要求があれば先に削除
        if args.wipe:
            conn.execute("DELETE FROM node_geo;")
            conn.commit()
            print("[INFO] wiped node_geo.")
        # upsert 実行（外部キーはここで満たされているはず）
        conn.executemany(
            "INSERT INTO node_geo(node_name,lat,lon) VALUES(?,?,?) "
            "ON CONFLICT(node_name) DO UPDATE SET lat=excluded.lat, lon=excluded.lon",
            rows
        )
        conn.commit()
        print(f"[OK] upsert {len(rows)} rows into node_geo")
        # 最終確認：node_geo にあって node に無いもの（通常は 0）
        dangling = conn.execute("""
          SELECT g.node_name FROM node_geo g
          LEFT JOIN node n ON n.node_name=g.node_name
          WHERE n.node_name IS NULL
        """).fetchall()
        if dangling:
            names = [d[0] for d in dangling]
            print(f"[WARN] geo rows without node: {names[:20]}{' ...' if len(names) > 20 else ''}")
        else:
            print("[OK] all geo rows have matching node.")
        return 0
    finally:
        conn.close()
if __name__ == "__main__":
    sys.exit(main())
