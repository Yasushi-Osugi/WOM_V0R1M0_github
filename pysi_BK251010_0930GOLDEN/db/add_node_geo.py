# add_node_geo.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-
# "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\pysi.sqlite3"
# "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\node_geo.csv"
# starter
# python add_node_geo.py --db "C:\path\to\pysi.sqlite3" --print-sql --verbose
# python add_node_geo.py --db "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\pysi.sqlite3" --print-sql --verbose
"""
SQLite に add_node_geo テーブルを追加する単体マイグレーション。
- 冪等（既にあれば何もしない）
- 事前に .bak_YYYYmmdd_HHMMSS を自動バックアップ
- 検証して結果を表示
使い方:
  python add_node_geo.py --db "C:\path\to\pysi.sqlite3" --print-sql --verbose
"""
# add_product_edge.py
from __future__ import annotations
import argparse, os, shutil, sqlite3, sys
from datetime import datetime
from textwrap import dedent
MIGRATION_SQL = dedent("""
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS node_geo (
    node_name TEXT PRIMARY KEY
                REFERENCES node(node_name) ON DELETE CASCADE,
    lat REAL NOT NULL,
    lon REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_node_geo_latlon ON node_geo(lat, lon);
""").strip()
def backup_db(db_path: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = f"{db_path}.bak_{ts}"
    shutil.copy2(db_path, dst)
    return dst
def run_migration(db_path: str, print_sql: bool=False, verbose: bool=False) -> None:
    if not os.path.isfile(db_path):
        print(f"[ERR ] DB not found: {db_path}", file=sys.stderr); sys.exit(1)
    backup = backup_db(db_path)
    print(f"[INFO] Backup created: {backup}")
    if print_sql:
        print("----- SQL to execute -----")
        print(MIGRATION_SQL)
        print("--------------------------")
    try:
        con = sqlite3.connect(db_path, timeout=5.0)  # ← デフォルトのトランザクション管理を使用
        if verbose: print("[INFO] applying DDL in a single transaction ...")
        with con:  # ここで自動的に BEGIN/COMMIT（失敗時は自動 ROLLBACK）
            con.executescript(MIGRATION_SQL)
    except Exception as e:
        print(f"[ERR ] Migration failed: {e}", file=sys.stderr); sys.exit(2)
    finally:
        try: con.close()
        except: pass
    # 検証
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='node_geo';")
    table = cur.fetchone()
    cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_node_geo_latlon';")
    index = cur.fetchone()
    con.close()
    if table: print("[OK  ] table node_geo ✓")
    else:     print("[NG  ] node_geo not found", file=sys.stderr) or sys.exit(3)
    if index: print("[OK  ] index idx_node_geo_latlon ✓")
    else:     print("[WARN] idx_node_geo_latlon not found")
    print("[DONE] Schema migration finished.")
def main():
    ap = argparse.ArgumentParser(description="Add node_geo table to an existing SQLite DB (idempotent).")
    ap.add_argument("--db", "-d", required=True, help="Path to SQLite database file")
    ap.add_argument("--print-sql", action="store_true")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()
    run_migration(args.db, print_sql=args.print_sql, verbose=args.verbose)
if __name__ == "__main__":
    main()
