# pysi/scripts/check_lot_size.py
import argparse
import sqlite3
from pathlib import Path
SQL_HIST = """
SELECT lot_size, COUNT(*)
FROM node_product
GROUP BY lot_size
ORDER BY lot_size;
"""
SQL_SAMPLE = """
SELECT n.name AS node, p.name AS product, np.lot_size
FROM node_product np
JOIN node n    ON np.node_id = n.id
JOIN product p ON np.product_id = p.id
ORDER BY n.name, p.name
LIMIT 20;
"""
def main():
    ap = argparse.ArgumentParser(description="Show lot_size histogram and sample pairs")
    ap.add_argument("--db", required=True, help="SQLite DB path (e.g. var/psi.sqlite)")
    args = ap.parse_args()
    db_path = Path(args.db).resolve()
    print(f"DB: {db_path}")
    try:
        con = sqlite3.connect(str(db_path))
        con.execute("PRAGMA foreign_keys=ON;")
    except Exception as e:
        print("[ERR] failed to open DB:", e)
        return
    cur = con.cursor()
    # テーブル存在チェック
    exists = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='node_product';"
    ).fetchone()
    if not exists:
        print("[ERR] 'node_product' table not found. Did you apply schema_core_only.sql?")
        con.close()
        return
    print("lot_size histogram (node_product):")
    rows = cur.execute(SQL_HIST).fetchall()
    if not rows:
        print("  (no rows)")
    else:
        for lot_size, cnt in rows:
            print(f"  lot_size = {lot_size:<6} rows = {cnt}")
    print("\nsample pairs:")
    rows = cur.execute(SQL_SAMPLE).fetchall()
    if not rows:
        print("  (no rows)")
    else:
        for node, product, lot_size in rows:
            print(f"  ({node}, {product}) lot_size={lot_size}")
    con.close()
if __name__ == "__main__":
    main()
