#sql_geo_check.py
import sqlite3
DB=r"C:\Users\ohsug\PySI_V0R8_SQL_010\data\pysi.sqlite3"
with sqlite3.connect(DB) as con:
    n = con.execute("select count(*) from node where lat is not null and lon is not null").fetchone()[0]
    print("nodes with geo:", n)
    print(con.execute("select node_name,lat,lon from node order by node_name limit 5").fetchall())
