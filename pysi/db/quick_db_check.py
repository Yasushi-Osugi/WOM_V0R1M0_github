# quick_db_check.py
import sqlite3, os, sys
DB = r"C:\Users\ohsug\PySI_V0R8_SQL_010\data\pysi.sqlite3"
q = lambda con, sql, p=(): con.execute(sql, p).fetchall()
with sqlite3.connect(DB) as con:
    con.row_factory = sqlite3.Row
    print("[nodes]   ", q(con, "SELECT COUNT(*) AS c FROM node")[0]["c"])
    print("[products]", q(con, "SELECT COUNT(*) AS c FROM product")[0]["c"])
    print("[psi rows]", q(con, "SELECT COUNT(*) AS c FROM psi")[0]["c"])
    print("\n-- psi rows by product & bucket --")
    for r in q(con, """
        SELECT product_name, bucket, COUNT(*) AS c
        FROM psi
        GROUP BY product_name, bucket
        ORDER BY product_name, bucket"""):
        print(dict(r))
    print("\n-- price tags --")
    for r in q(con, """
        SELECT product_name, tag, COUNT(*) AS c
        FROM price_tag
        GROUP BY product_name, tag
        ORDER BY product_name, tag"""):
        print(dict(r))
    print("\n-- sample few PSI lots (root S) --")
    for r in q(con, """
        SELECT node_name, product_name, iso_index, bucket, lot_id
        FROM psi
        WHERE bucket='S'
        ORDER BY iso_index
        LIMIT 10"""):
        print(dict(r))
