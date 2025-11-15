#check_scenario.py
import sqlite3
db = "var/psi.sqlite"
scenario = "Baseline"
con = sqlite3.connect(db)
sid = con.execute("SELECT id FROM scenario WHERE name=?", (scenario,)).fetchone()[0]
print("scenario_id=", sid)
rows = con.execute("""
  SELECT n.name, p.name, COUNT(*)
  FROM weekly_demand w
  JOIN node n ON n.id = w.node_id
  JOIN product p ON p.id = w.product_id
  WHERE w.scenario_id = ?
  GROUP BY n.name, p.name
  ORDER BY p.name, n.name
""", (sid,)).fetchall()
for r in rows[:50]:
    print(r)
con.close()
