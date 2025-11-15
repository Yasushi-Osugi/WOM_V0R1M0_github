# verify_geo_in_db.py
# starter
# python verify_geo_in_db.py "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\pysi.sqlite3"
import sqlite3, sys
db = sys.argv[1]
con = sqlite3.connect(db)
nodes = {r[0] for r in con.execute("SELECT node_name FROM node")}
geo   = {r[0] for r in con.execute("SELECT node_name FROM node_geo")}
missing = sorted(geo - nodes)
print(f"nodes in DB: {len(nodes)}, geo entries: {len(geo)}, missing in node: {len(missing)}")
for n in missing[:50]:
    print("  -", n)
con.close()
