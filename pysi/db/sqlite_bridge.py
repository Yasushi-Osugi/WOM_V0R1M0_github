#pysi.db.sqlite_bridge.py
from __future__ import annotations
import sqlite3
import json
from contextlib import contextmanager
from typing import Iterable, Optional
# ---------------------------------
# 基本接続
# ---------------------------------
@contextmanager
def connect(db_path: str):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    # 軽量同時実行のため
    con.execute("PRAGMA foreign_keys=ON;")
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    try:
        yield con
        con.commit()
    finally:
        con.close()
def init_schema(con: sqlite3.Connection, schema_sql: str | None = None, schema_path: str | None = None):
    """
    schema_sql または schema_path のどちらかで初期化。
    """
    if schema_sql is None and schema_path is None:
        raise ValueError("schema_sql or schema_path is required")
    if schema_sql is None:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()
    con.executescript(schema_sql)
# ---------------------------------
# Upsert helpers (master)
# ---------------------------------
def upsert_product(con: sqlite3.Connection, product_name: str):
    con.execute("INSERT OR IGNORE INTO product(product_name) VALUES (?)", (product_name,))
def upsert_node(
    con: sqlite3.Connection,
    node_name: str,
    parent_name: Optional[str] = None,
    leadtime: int = 1,
    ss_days: int = 7,
    long_vacation_weeks: Iterable[int] | str | None = None,
):
    if long_vacation_weeks is None:
        lv = "[]"
    elif isinstance(long_vacation_weeks, str):
        lv = long_vacation_weeks
    else:
        lv = json.dumps(list(long_vacation_weeks))
    con.execute("""
        INSERT INTO node(node_name, parent_name, leadtime, ss_days, long_vacation_weeks)
        VALUES (?,?,?,?,?)
        ON CONFLICT(node_name) DO UPDATE SET
          parent_name=excluded.parent_name,
          leadtime=excluded.leadtime,
          ss_days=excluded.ss_days,
          long_vacation_weeks=excluded.long_vacation_weeks
    """, (node_name, parent_name, int(leadtime), int(ss_days), lv))
def upsert_node_product(
    con: sqlite3.Connection,
    node_name: str, product_name: str, lot_size: int = 1,
    cs_logistics_costs: float = 0.0, cs_warehouse_cost: float = 0.0,
    cs_fixed_cost: float = 0.0, cs_profit: float = 0.0,
    cs_direct_materials_costs: float = 0.0, cs_tax_portion: float = 0.0,
):
    upsert_product(con, product_name)
    con.execute("""
      INSERT INTO node_product(
        node_name, product_name, lot_size,
        cs_logistics_costs, cs_warehouse_cost, cs_fixed_cost, cs_profit,
        cs_direct_materials_costs, cs_tax_portion
      )
      VALUES (?,?,?,?,?,?,?,?,?)
      ON CONFLICT(node_name, product_name) DO UPDATE SET
        lot_size=excluded.lot_size,
        cs_logistics_costs=excluded.cs_logistics_costs,
        cs_warehouse_cost=excluded.cs_warehouse_cost,
        cs_fixed_cost=excluded.cs_fixed_cost,
        cs_profit=excluded.cs_profit,
        cs_direct_materials_costs=excluded.cs_direct_materials_costs,
        cs_tax_portion=excluded.cs_tax_portion
    """, (node_name, product_name, int(lot_size),
          float(cs_logistics_costs), float(cs_warehouse_cost), float(cs_fixed_cost), float(cs_profit),
          float(cs_direct_materials_costs), float(cs_tax_portion)))
def upsert_money_per_lot(
    con: sqlite3.Connection,
    node_name: str, product_name: str,
    direct_materials_costs: float = 0.0, tariff_cost: float = 0.0
):
    upsert_product(con, product_name)
    con.execute("""
      INSERT INTO price_money_per_lot(node_name, product_name, direct_materials_costs, tariff_cost)
      VALUES (?,?,?,?)
      ON CONFLICT(node_name, product_name) DO UPDATE SET
        direct_materials_costs=excluded.direct_materials_costs,
        tariff_cost=excluded.tariff_cost
    """, (node_name, product_name, float(direct_materials_costs), float(tariff_cost)))
def upsert_tariff(con: sqlite3.Connection, product_name: str, from_node: str, to_node: str, tariff_rate: float):
    upsert_product(con, product_name)
    con.execute("""
      INSERT INTO tariff(product_name, from_node, to_node, tariff_rate)
      VALUES (?,?,?,?)
      ON CONFLICT(product_name, from_node, to_node) DO UPDATE SET
        tariff_rate=excluded.tariff_rate
    """, (product_name, from_node, to_node, float(tariff_rate)))
def fetch_tariff_rate(con: sqlite3.Connection, product_name: str, from_node: str, to_node: str) -> float:
    cur = con.execute("""
      SELECT tariff_rate FROM tariff WHERE product_name=? AND from_node=? AND to_node=?
    """, (product_name, from_node, to_node))
    row = cur.fetchone()
    return float(row["tariff_rate"]) if row else 0.0
# ---------------------------------
# Calendar445
# ---------------------------------
def seed_calendar445(con: sqlite3.Connection, rows: Iterable[tuple[int,int,int,str]]):
    """
    rows: iterable of (iso_index, iso_year, iso_week, week_label)
    """
    con.executemany("""
      INSERT OR REPLACE INTO calendar445(iso_index, iso_year, iso_week, week_label)
      VALUES (?,?,?,?)
    """, ((int(i), int(y), int(w), str(lbl)) for (i,y,w,lbl) in rows))
# ---------------------------------
# Weekly demand (df → DB)
# ---------------------------------
def upsert_weekly_demand(con: sqlite3.Connection, df_weekly):
    """
    df_weekly columns: product_name,node_name,iso_year,iso_week,S_lot,lot_id_list(list or JSON-string)
    """
    cur = con.cursor()
    for _, r in df_weekly.iterrows():
        lots = r["lot_id_list"]
        if not isinstance(lots, (list, tuple)):
            try:
                lots = json.loads(lots)
            except Exception:
                lots = []
        cur.execute("""
          INSERT INTO weekly_demand(node_name,product_name,iso_year,iso_week,s_lot,lot_id_list)
          VALUES (?,?,?,?,?,?)
          ON CONFLICT(node_name,product_name,iso_year,iso_week) DO UPDATE SET
            s_lot=excluded.s_lot, lot_id_list=excluded.lot_id_list
        """, (r["node_name"], r["product_name"], int(r["iso_year"]), int(r["iso_week"]),
              int(r["S_lot"]), json.dumps(list(lots))))
# Node 用 lot 配列（pSi[w]）を DB の weekly_demand から生成
def load_lots_for_node(
    con: sqlite3.Connection,
    node_name: str, product_name: str,
    week_index_map: dict[tuple[int,str], int], weeks_count: int
):
    pSi = [[] for _ in range(weeks_count)]
    cur = con.execute("""
      SELECT iso_year, iso_week, lot_id_list
      FROM weekly_demand
      WHERE node_name=? AND product_name=?
    """, (node_name, product_name))
    for row in cur.fetchall():
        key = (int(row["iso_year"]), f"{int(row['iso_week']):02d}")
        idx = week_index_map.get(key)
        if idx is None or idx < 0 or idx >= weeks_count:
            continue
        lots = json.loads(row["lot_id_list"]) if row["lot_id_list"] else []
        pSi[idx].extend(lots)
    return pSi
# ---------------------------------
# PSI persist/load
# ---------------------------------
def persist_node_psi(con: sqlite3.Connection, node, product_name: str, source: str = "demand"):
    """
    node.psi4demand / node.psi4supply を psi テーブルへ保存。
    source: "demand" or "supply"
    """
    assert source in ("demand", "supply")
    data = node.psi4demand if source == "demand" else node.psi4supply
    weeks = len(data)
    # 一旦該当ノード・製品の PSI 全消し→挿入（最小実装）
    con.execute("DELETE FROM psi WHERE node_name=? AND product_name=?", (node.name, product_name))
    cur = con.cursor()
    for w in range(weeks):
        S, CO, I, P = data[w]
        for lot in S:
            cur.execute("INSERT INTO psi(node_name,product_name,iso_index,bucket,lot_id) VALUES (?,?,?,?,?)",
                        (node.name, product_name, w, "S", lot))
        for lot in CO:
            cur.execute("INSERT INTO psi(node_name,product_name,iso_index,bucket,lot_id) VALUES (?,?,?,?,?)",
                        (node.name, product_name, w, "CO", lot))
        for lot in I:
            cur.execute("INSERT INTO psi(node_name,product_name,iso_index,bucket,lot_id) VALUES (?,?,?,?,?)",
                        (node.name, product_name, w, "I", lot))
        for lot in P:
            cur.execute("INSERT INTO psi(node_name,product_name,iso_index,bucket,lot_id) VALUES (?,?,?,?,?)",
                        (node.name, product_name, w, "P", lot))
def load_node_psi(con: sqlite3.Connection, node_name: str, product_name: str, weeks_count: int):
    p = [[[],[],[],[]] for _ in range(weeks_count)]
    idx = {"S":0, "CO":1, "I":2, "P":3}
    cur = con.execute("""
      SELECT iso_index, bucket, lot_id FROM psi
      WHERE node_name=? AND product_name=?
      ORDER BY iso_index
    """, (node_name, product_name))
    for r in cur.fetchall():
        bi = idx.get(r["bucket"])
        if bi is None: continue
        i = int(r["iso_index"])
        if 0 <= i < weeks_count:
            p[i][bi].append(r["lot_id"])
    return p
# ---------------------------------
# Price tags (ASIS/TOBE)
# ---------------------------------
def set_price_tag(con: sqlite3.Connection, node_name: str, product_name: str, tag: str, price: float):
    assert tag in ("ASIS","TOBE")
    con.execute("""
      INSERT INTO price_tag(node_name,product_name,tag,price)
      VALUES (?,?,?,?)
      ON CONFLICT(node_name,product_name,tag) DO UPDATE SET
        price=excluded.price
    """, (node_name, product_name, tag, float(price)))
def get_price_tag(con: sqlite3.Connection, node_name: str, product_name: str, tag: str) -> float | None:
    cur = con.execute("""
      SELECT price FROM price_tag WHERE node_name=? AND product_name=? AND tag=?
    """, (node_name, product_name, tag))
    row = cur.fetchone()
    return float(row["price"]) if row else None
# ---------------------------------
# Fetch helpers for cost calc
# ---------------------------------
def fetch_node_product_cs(con: sqlite3.Connection, node_name: str, product_name: str) -> dict:
    cur = con.execute("""
      SELECT * FROM node_product WHERE node_name=? AND product_name=?
    """, (node_name, product_name))
    row = cur.fetchone()
    return dict(row) if row else {}
def fetch_money_per_lot(con: sqlite3.Connection, node_name: str, product_name: str) -> dict:
    cur = con.execute("""
      SELECT * FROM price_money_per_lot WHERE node_name=? AND product_name=?
    """, (node_name, product_name))
    row = cur.fetchone()
    return dict(row) if row else {}
# ---------------------------------
# 簡易バリデーション（任意）
# ---------------------------------
def validate_cs_sum(con: sqlite3.Connection, atol: float = 1e-6) -> list[tuple[str,str,float]]:
    """
    cs_* 合計が 1 からズレている (|sum-1| > atol) レコードを返す。
    """
    cur = con.execute("SELECT * FROM node_product")
    bad = []
    for r in cur.fetchall():
        s = (r["cs_logistics_costs"] + r["cs_warehouse_cost"] + r["cs_fixed_cost"] +
             r["cs_profit"] + r["cs_direct_materials_costs"] + r["cs_tax_portion"])
        if abs(s - 1.0) > atol:
            bad.append((r["node_name"], r["product_name"], s))
    return bad
# ---------------------------------
# Weekly vs PSI(S) consistency check
# ---------------------------------
def _count_weekly_lots(con: sqlite3.Connection, node_name: str, product_name: str) -> int:
    """
    weekly_demand の lot_id_list を合計した期待ロット数（S）を返す
    """
    cur = con.execute("""
        SELECT lot_id_list FROM weekly_demand
        WHERE node_name=? AND product_name=?
    """, (node_name, product_name))
    total = 0
    for (payload,) in cur.fetchall():
        if not payload:
            continue
        try:
            lots = json.loads(payload) if isinstance(payload, str) else (payload or [])
        except Exception:
            lots = []
        total += len(lots)
    return total
def _count_psi_S_lots(con: sqlite3.Connection, node_name: str, product_name: str) -> int:
    """
    psi テーブルの S バケツに保存されたロット数を返す
    """
    cur = con.execute("""
        SELECT COUNT(*) AS c
        FROM psi
        WHERE node_name=? AND product_name=? AND bucket='S'
    """, (node_name, product_name))
    row = cur.fetchone()
    return int(row["c"] if row else 0)
def sanity_check_weekly_vs_psi(con: sqlite3.Connection, node_name: str, product_name: str, verbose: bool = True) -> dict:
    """
    weekly_demand のロット総数 と psi(S) のロット総数の一致を検証
    """
    expected = _count_weekly_lots(con, node_name, product_name)
    actual   = _count_psi_S_lots(con, node_name, product_name)
    ok = (expected == actual)
    if verbose:
        print(f"[CHECK] {node_name}/{product_name}: weekly S lots={expected}, psi S lots={actual} -> {'OK' if ok else 'NG'}")
    return {
        "node_name": node_name,
        "product_name": product_name,
        "weekly_S": expected,
        "psi_S": actual,
        "ok": ok,
    }
