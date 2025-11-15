# apply_schema.py
import sqlite3, pathlib
def apply_schema(db_path: str, schema_sql_path: str):
    sql = pathlib.Path(schema_sql_path).read_text(encoding="utf-8")
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.executescript(sql)
    print("DDL applied:", db_path)
# 使い方
# apply_schema("psi.sqlite", "schema.sql")
