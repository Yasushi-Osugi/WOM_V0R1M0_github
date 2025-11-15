# tools/seed_scenario_tobe.py
# python -X utf8 tools\seed_scenario_tobe.py

import sqlite3, datetime as dt

DB = r"var\psi.sqlite"
SCN_CODE1 = "ASIS_BASE"
SCN_CODE2 = "TOBE_S1"

def coltype(conn, table, col):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    for _, name, ctype, *_ in rows:
        if name == col:
            return (ctype or "").upper()
    return ""

con = sqlite3.connect(DB)
now = dt.datetime.now().isoformat(timespec="seconds")

id_type     = coltype(con, "scenario", "id")
tag_id_type = coltype(con, "scenario_price_tag", "scenario_id")

# --- scenario への登録（id が INTEGER の場合は自動採番、TEXTならコードをそのまま入れる）
if "INT" in id_type:
    con.execute("INSERT OR IGNORE INTO scenario(name, plan_year_st, plan_range, created_at) VALUES(?,?,?,?)",
                (SCN_CODE1, 2025, 3, now))
    con.execute("INSERT OR IGNORE INTO scenario(name, plan_year_st, plan_range, created_at) VALUES(?,?,?,?)",
                (SCN_CODE2, 2025, 3, now))
    sid_num = con.execute("SELECT id FROM scenario WHERE name=?", (SCN_CODE2,)).fetchone()[0]
    # scenario_price_tag.scenario_id の型に合わせて値を選ぶ
    sid_for_tags = sid_num if "INT" in tag_id_type else SCN_CODE2
else:
    con.execute("INSERT OR IGNORE INTO scenario(id,name,plan_year_st,plan_range,created_at) VALUES(?,?,?,?,?)",
                (SCN_CODE1, "AS-IS baseline", 2025, 3, now))
    con.execute("INSERT OR IGNORE INTO scenario(id,name,plan_year_st,plan_range,created_at) VALUES(?,?,?,?,?)",
                (SCN_CODE2, "TO-BE sample #1", 2025, 3, now))
    sid_for_tags = SCN_CODE2

# --- TOBE上書き（重複しないように同一キーは消してから挿入）
con.execute("""DELETE FROM scenario_price_tag
               WHERE scenario_id=? AND product_name=? AND node_name=? AND tag=?""",
            (sid_for_tags, "CAL_RICE_1", "supply_point", "TOBE"))
con.execute("""INSERT INTO scenario_price_tag(scenario_id, product_name, node_name, tag, price)
               VALUES(?,?,?,?,?)""",
            (sid_for_tags, "CAL_RICE_1", "supply_point", "TOBE", 36000.0))

con.commit(); con.close()
print(f"[OK] seeded scenario '{SCN_CODE2}' (scenario_id for tags={sid_for_tags!r})")
