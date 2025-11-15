# tools/migrate_add_label_note.py

#starter
#python -X utf8 tools\migrate_add_label_note.py

#chacker
#python -c "import sqlite3; con=sqlite3.connect(r'var\\psi.sqlite'); print([r[1] for r in con.execute('PRAGMA table_info(scenario_run)').fetchall()]); con.close()"


import sqlite3, sys

DB = r"var\psi.sqlite"

con = sqlite3.connect(DB)
cols = [r[1] for r in con.execute("PRAGMA table_info(scenario_run)").fetchall()]

if "label" not in cols:
    con.execute("ALTER TABLE scenario_run ADD COLUMN label TEXT")
if "note" not in cols:
    con.execute("ALTER TABLE scenario_run ADD COLUMN note  TEXT")

con.commit(); con.close()
print("[OK] scenario_run altered (label/note)")
