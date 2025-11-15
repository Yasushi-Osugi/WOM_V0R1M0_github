import sqlite3
con = sqlite3.connect(r"var\psi.sqlite")
print("scenario_* tables =",
      [r[0] for r in con.execute(
          "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'scenario_%' ORDER BY name"
      )])
for t in ("scenario","scenario_overrides","scenario_run","scenario_result_summary","scenario_result_node"):
    print(t, "exists =", bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)
    ).fetchone()))
con.close()
