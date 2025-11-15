# add_product_edge.py
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SQLite に product_edge テーブルを追加する単体マイグレーション。
- 冪等（既にあれば何もしない）
- 事前に .bak_YYYYmmdd_HHMMSS を自動バックアップ
- 検証して結果を表示
使い方:
  python add_product_edge.py --db "C:\path\to\pysi.sqlite3" --print-sql --verbose
"""
# add_product_edge.py
from __future__ import annotations
import argparse, os, shutil, sqlite3, sys
from datetime import datetime
from textwrap import dedent
MIGRATION_SQL = dedent("""
    PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS product_edge (
      product_name TEXT NOT NULL,
      parent_name  TEXT NOT NULL,
      child_name   TEXT NOT NULL,
      bound        TEXT NOT NULL CHECK(bound IN ('OUT','IN')),
      UNIQUE(product_name, bound, parent_name, child_name)
    );
    CREATE INDEX IF NOT EXISTS idx_edge_prod_bound
      ON product_edge(product_name, bound);
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
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='product_edge';")
    table = cur.fetchone()
    cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_edge_prod_bound';")
    index = cur.fetchone()
    con.close()
    if table: print("[OK  ] table product_edge ✓")
    else:     print("[NG  ] product_edge not found", file=sys.stderr) or sys.exit(3)
    if index: print("[OK  ] index idx_edge_prod_bound ✓")
    else:     print("[WARN] idx_edge_prod_bound not found")
    print("[DONE] Schema migration finished.")
def main():
    ap = argparse.ArgumentParser(description="Add product_edge table to an existing SQLite DB (idempotent).")
    ap.add_argument("--db", "-d", required=True, help="Path to SQLite database file")
    ap.add_argument("--print-sql", action="store_true")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()
    run_migration(args.db, print_sql=args.print_sql, verbose=args.verbose)
if __name__ == "__main__":
    main()
