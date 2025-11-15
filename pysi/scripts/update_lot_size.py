# pysi/scripts/update_lot_size.py
import argparse
import sqlite3
from pathlib import Path
SQL_HIST = """
SELECT lot_size, COUNT(*)
FROM node_product
GROUP BY lot_size
ORDER BY lot_size;
"""
def histogram(con):
    return con.execute(SQL_HIST).fetchall()
def main():
    ap = argparse.ArgumentParser(description="Update lot_size for all rows in node_product")
    ap.add_argument("--db", required=True, help="SQLite DB path (e.g. var/psi.sqlite)")
    ap.add_argument("--value", type=int, default=1000, help="New lot_size value (default: 1000)")
    args = ap.parse_args()
    db_path = Path(args.db).resolve()
    print(f"DB: {db_path}")
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA foreign_keys=ON;")
    cur = con.cursor()
    exists = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='node_product';"
    ).fetchone()
    if not exists:
        print("[ERR] 'node_product' table not found. Did you apply schema_core_only.sql?")
        con.close()
        return
    before = histogram(con)
    print("before histogram:", before or "(empty)")
    cur.execute("UPDATE node_product SET lot_size = ?;", (args.value,))
    con.commit()
    after = histogram(con)
    print("after  histogram:", after or "(empty)")
    print(f"[OK] node_product.lot_size set to {args.value} for all rows.")
    con.close()
if __name__ == "__main__":
    main()
