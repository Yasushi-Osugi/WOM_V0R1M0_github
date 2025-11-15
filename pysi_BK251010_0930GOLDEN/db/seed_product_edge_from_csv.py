# seed_product_edge_from_csv.py
## 例：DB と CSV フォルダを指定して投入（既存を消して入れ直す）
#python pysi\db\seed_product_edge_from_csv.py `
#  --db "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\pysi.sqlite3" `
#  --dir "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2" `
#  --wipe --verbose
from __future__ import annotations
import argparse, csv, os, sqlite3, sys
from typing import Iterable, Tuple
def read_edges_from_csv(path: str, bound: str) -> Iterable[Tuple[str,str,str,str]]:
    """
    CSV 期待列: Product_name, Parent_node, Child_node, [lot_size], [leadtime]
    返り: (product_name, parent_name, child_name, bound)
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            prod = (r.get("Product_name") or "").strip()
            par  = (r.get("Parent_node")  or "").strip()
            chi  = (r.get("Child_node")   or "").strip()
            if not prod or not par or not chi:
                continue
            yield (prod, par, chi, bound)
def ensure_table_exists(con: sqlite3.Connection):
    con.execute("""
    CREATE TABLE IF NOT EXISTS product_edge (
      product_name TEXT NOT NULL,
      parent_name  TEXT NOT NULL,
      child_name   TEXT NOT NULL,
      bound        TEXT NOT NULL CHECK(bound IN ('OUT','IN')),
      UNIQUE(product_name, bound, parent_name, child_name)
    );
    """)
    con.execute("""
    CREATE INDEX IF NOT EXISTS idx_edge_prod_bound
      ON product_edge(product_name, bound);
    """)
def main():
    ap = argparse.ArgumentParser(description="Seed product_edge from product_tree_outbound/inbound.csv")
    ap.add_argument("--db", "-d", required=True, help="path to SQLite db (e.g. data\\pysi.sqlite3)")
    ap.add_argument("--dir", required=True, help="directory containing product_tree_outbound.csv / product_tree_inbound.csv")
    ap.add_argument("--wipe", action="store_true", help="delete existing rows for products seen in CSV (both OUT/IN) before insert")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()
    db = args.db
    datadir = args.dir
    ot_csv = os.path.join(datadir, "product_tree_outbound.csv")
    in_csv = os.path.join(datadir, "product_tree_inbound.csv")
    if not os.path.isfile(db):
        print(f"[ERR ] DB not found: {db}", file=sys.stderr); sys.exit(1)
    if not (os.path.isfile(ot_csv) or os.path.isfile(in_csv)):
        print(f"[ERR ] CSV not found: need at least one of {ot_csv} / {in_csv}", file=sys.stderr); sys.exit(1)
    # 収集
    edges = []
    prods_seen = set()
    if os.path.isfile(ot_csv):
        es = list(read_edges_from_csv(ot_csv, "OUT"))
        edges.extend(es); prods_seen.update(p for p,_,_,_ in es)
        if args.verbose: print(f"[INFO] OUT rows read: {len(es)} from {ot_csv}")
    if os.path.isfile(in_csv):
        es = list(read_edges_from_csv(in_csv, "IN"))
        edges.extend(es); prods_seen.update(p for p,_,_,_ in es)
        if args.verbose: print(f"[INFO] IN  rows read: {len(es)} from {in_csv}")
    if not edges:
        print("[INFO] no edges to insert (csv empty?)"); sys.exit(0)
    con = sqlite3.connect(db)
    try:
        ensure_table_exists(con)
        with con:
            if args.wipe and prods_seen:
                qmarks = ",".join(["?"] * len(prods_seen))
                con.execute(f"DELETE FROM product_edge WHERE product_name IN ({qmarks})", tuple(sorted(prods_seen)))
                if args.verbose: print(f"[INFO] wiped products: {sorted(prods_seen)}")
            con.executemany(
                "INSERT OR IGNORE INTO product_edge(product_name,parent_name,child_name,bound) VALUES (?,?,?,?)",
                edges
            )
        # サマリ
        rows = list(con.execute(
            "SELECT product_name, bound, COUNT(*) FROM product_edge "
            "GROUP BY product_name, bound ORDER BY product_name, bound"))
        print("\n[SUMMARY] product_edge counts:")
        for prod, bnd, cnt in rows:
            print(f"  - {prod:20s} {bnd}: {cnt}")
    finally:
        con.close()
if __name__ == "__main__":
    main()
