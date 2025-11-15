# tools/check_scenario_columns.py

# starter
#python -X utf8 tools\check_scenario_columns.py

import sqlite3
con = sqlite3.connect(r"var/psi.sqlite"); con.row_factory=sqlite3.Row
def cols(t):
    return [r["name"] for r in con.execute(f"PRAGMA table_info({t})")]
for t in ["scenario","scenario_price_tag","scenario_tariff","scenario_param","scenario_node_product"]:
    try:
        print(t, "=>", cols(t))
    except Exception as e:
        print(t, "->", e)
con.close()
