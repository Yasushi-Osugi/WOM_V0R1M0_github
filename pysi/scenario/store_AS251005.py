# pysi/scenario/store.py
from __future__ import annotations
from typing import List, Tuple, Optional
import sqlite3

def get_db_path_from(self_obj) -> str:
    # SQLバックエンドから安全にDBパスを取るヘルパ
    for attr in ("db_path", "dbfile", "db"):
        if hasattr(self_obj, attr):
            v = getattr(self_obj, attr)
            if isinstance(v, str) and v:
                return v
    return r"var/psi.sqlite"

def list_scenarios(db_path: str) -> List[Tuple[str, str]]:
    """
    return [(id, name), ...]  新しい順
    """
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("""
            SELECT id, COALESCE(name,id) AS name
              FROM scenario
             ORDER BY datetime(created_at) DESC, id ASC
        """).fetchall()
    except Exception:
        rows = []
    finally:
        con.close()
    return [(r[0], r[1]) for r in rows]
