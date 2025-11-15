
import sqlite3
DB_PATH = r"C:\Users\ohsug\PySI_V0R8_SQL_010\data\pysi.sqlite3"
with sqlite3.connect(DB_PATH) as con:
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM node WHERE parent_name IS NULL").fetchall()
    if not rows:
        print("[WARN] No root nodes found. parent_name is NULL for none.")
    else:
        print("[INFO] Root candidates:")
        for r in rows:
            print(dict(r))
