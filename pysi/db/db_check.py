
import sqlite3
DB_PATH = r"C:\Users\ohsug\PySI_V0R8_SQL_010\data\pysi.sqlite3"
with sqlite3.connect(DB_PATH) as con:
    cursor = con.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in cursor.fetchall()]
    print("Tables in DB:", tables)
    if "node" in tables:
        cursor.execute("PRAGMA table_info('node');")
        cols = cursor.fetchall()
        print("Schema for 'node':")
        for col in cols:
            print(col)
