# pysi/io/sql_bridge.py
from __future__ import annotations
import os
from typing import Dict, Iterable
from pysi.db.sqlite_bridge import (
    connect, init_schema,
    upsert_node, upsert_node_product, upsert_tariff,
    persist_node_psi, set_price_tag
)
# ---- ざっくり最小スキーマ（存在しなければ作成） -----------------
SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS product(
  product_name TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS node(
  node_name TEXT PRIMARY KEY,
  parent_name TEXT,
  leadtime INTEGER,
  ss_days INTEGER,
  long_vacation_weeks TEXT
);
CREATE TABLE IF NOT EXISTS node_product(
  node_name TEXT,
  product_name TEXT,
  lot_size INTEGER DEFAULT 1,
  cs_logistics_costs REAL DEFAULT 0,
  cs_warehouse_cost REAL DEFAULT 0,
  cs_fixed_cost REAL DEFAULT 0,
  cs_profit REAL DEFAULT 0,
  cs_direct_materials_costs REAL DEFAULT 0,
  cs_tax_portion REAL DEFAULT 0,
  PRIMARY KEY(node_name, product_name)
);
CREATE TABLE IF NOT EXISTS price_money_per_lot(
  node_name TEXT,
  product_name TEXT,
  direct_materials_costs REAL DEFAULT 0,
  tariff_cost REAL DEFAULT 0,
  PRIMARY KEY(node_name, product_name)
);
CREATE TABLE IF NOT EXISTS tariff(
  product_name TEXT,
  from_node TEXT,
  to_node TEXT,
  tariff_rate REAL DEFAULT 0,
  PRIMARY KEY(product_name, from_node, to_node)
);
CREATE TABLE IF NOT EXISTS calendar445(
  iso_index INTEGER PRIMARY KEY,
  iso_year INTEGER,
  iso_week INTEGER,
  week_label TEXT
);
CREATE TABLE IF NOT EXISTS weekly_demand(
  node_name TEXT,
  product_name TEXT,
  iso_year INTEGER,
  iso_week INTEGER,
  s_lot INTEGER,
  lot_id_list TEXT,
  PRIMARY KEY(node_name, product_name, iso_year, iso_week)
);
CREATE TABLE IF NOT EXISTS psi(
  node_name TEXT,
  product_name TEXT,
  iso_index INTEGER,
  bucket TEXT,
  lot_id TEXT
);
CREATE TABLE IF NOT EXISTS price_tag(
  node_name TEXT,
  product_name TEXT,
  tag TEXT CHECK(tag IN ('ASIS','TOBE')),
  price REAL,
  PRIMARY KEY(node_name, product_name, tag)
);
"""
# ---- ユーティリティ -----------------------------------------------------
def _iter_nodes(root):
    stack = [root]
    while stack:
        n = stack.pop()
        yield n
        for c in getattr(n, "children", []) or []:
            stack.append(c)
def _node_attrs(n):
    """sqliteのupsert_nodeに渡す属性を安全に抽出"""
    return {
        "node_name": getattr(n, "name", ""),
        "parent_name": getattr(getattr(n, "parent", None), "name", None),
        "leadtime": int(getattr(n, "leadtime", 0) or 0),
        "ss_days": int(getattr(n, "SS_days", 0) or 0),
        "long_vacation_weeks": getattr(n, "long_vacation_weeks", []) or []
    }
def _sku_attrs(n, product_name: str):
    """node_productの cs_* と lot_size を安全に拾う（無ければ0/1）"""
    lot_size = 1
    cs = dict(
        cs_logistics_costs=0.0,
        cs_warehouse_cost=0.0,
        cs_fixed_cost=0.0,
        cs_profit=0.0,
        cs_direct_materials_costs=0.0,
        cs_tax_portion=0.0,
    )
    # Node.sku_dict があれば優先
    try:
        sku = (getattr(n, "sku_dict", {}) or {}).get(product_name)
        if sku:
            lot_size = int(getattr(sku, "lot_size", lot_size) or lot_size)
            for k in cs:
                cs[k] = float(getattr(sku, k, cs[k]) or cs[k])
        else:
            # フラット属性に持っている場合の救済
            lot_size = int(getattr(n, "lot_size", lot_size) or lot_size)
            for k in cs:
                cs[k] = float(getattr(n, k, cs[k]) or cs[k])
    except Exception:
        pass
    return lot_size, cs
# ---- 公開API ------------------------------------------------------------
def persist_all_psi(psi_env, db_path: str):
    """
    現在の計画結果（COPY版）を DB（psi / price_tag / node / node_product）へ保存。
    - psi_env.prod_tree_dict_OT: {product_name: root_node}
    - root/leaf の price タグもあれば保存（ASIS=root, TOBE=leaf）
    """
    # DBディレクトリが無ければ作成
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with connect(db_path) as con:
        init_schema(con, schema_sql=SCHEMA_SQL)
        # 製品ごとにツリーを走査
        prod_roots: Dict[str, object] = getattr(psi_env, "prod_tree_dict_OT", {}) or {}
        for product_name, root in prod_roots.items():
            # まず node / node_product をupsert（メタ）
            for n in _iter_nodes(root):
                na = _node_attrs(n)
                upsert_node(con, **na)
                lot_size, cs = _sku_attrs(n, product_name)
                upsert_node_product(
                    con, na["node_name"], product_name, lot_size=lot_size, **cs
                )
            # PSI（demand面）を保存
            for n in _iter_nodes(root):
                persist_node_psi(con, n, product_name, source="demand")
            # price tags（存在すれば）
            # ルートの ASIS
            root_price = getattr(root, "offering_price_ASIS", None)
            if root_price is not None:
                set_price_tag(con, root.name, product_name, "ASIS", float(root_price))
            # 葉の TOBE
            for n in _iter_nodes(root):
                if not getattr(n, "children", []):
                    p = getattr(n, "offering_price_TOBE", None)
                    if p is not None:
                        set_price_tag(con, n.name, product_name, "TOBE", float(p))
def persist_tariff_table(db_path: str, tariff_table: Dict[tuple, float] | Iterable[tuple]):
    """
    tariff_table: {(product_name, from_node, to_node): rate} もしくは
                  iterable of (product_name, from_node, to_node, rate)
    """
    with connect(db_path) as con:
        init_schema(con, schema_sql=SCHEMA_SQL)
        if isinstance(tariff_table, dict):
            items = [(k[0], k[1], k[2], v) for k, v in tariff_table.items()]
        else:
            items = list(tariff_table)
        for product_name, from_node, to_node, rate in items:
            upsert_tariff(con, str(product_name), str(from_node), str(to_node), float(rate))
#@250823 ADD
# --- geo migration & import helpers ---------------------------------
import sqlite3, csv
def ensure_node_latlon_columns(con: sqlite3.Connection):
    cols = [r[1] for r in con.execute("PRAGMA table_info(node)").fetchall()]
    if "lat" not in cols:
        con.execute("ALTER TABLE node ADD COLUMN lat REAL")
    if "lon" not in cols:
        con.execute("ALTER TABLE node ADD COLUMN lon REAL")
def upsert_node_geo(con: sqlite3.Connection, node_name: str, lat: float, lon: float):
    cur = con.execute("UPDATE node SET lat=?, lon=? WHERE node_name=?", (lat, lon, node_name))
    if cur.rowcount == 0:
        # node行がまだ無いDBの場合は警告（通常はnodeは先に存在）
        print(f"[GEO][WARN] node not found: {node_name}")
def import_node_geo_csv(db_path: str, csv_path: str, encoding="utf-8-sig"):
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        ensure_node_latlon_columns(con)
        with open(csv_path, newline="", encoding=encoding) as f:
            rdr = csv.DictReader(f)
            for row in rdr:
                try:
                    nm  = (row.get("node_name") or "").strip()
                    lat = float(row.get("lat") or row.get("latitude") or 0.0)
                    lon = float(row.get("lon") or row.get("longitude") or 0.0)
                except Exception as e:
                    print(f"[GEO][SKIP] bad row {row}: {e}"); continue
                if nm:
                    upsert_node_geo(con, nm, lat, lon)
        con.commit()
        print(f"[GEO] imported lat/lon from {csv_path}")
# --- geo export helpers ---------------------------------
#import sqlite3, csv
from typing import Iterable
def export_node_geo_csv(db_path: str, csv_path: str,
                        include_current: bool = True,
                        encoding: str = "utf-8-sig") -> None:
    """
    node表の node_name, lat, lon をCSVに書き出す。
    include_current=True なら既存のlat/lonをそのまま出力（未設定は空欄）。
    Falseなら lat/lon を空欄でテンプレ化。
    """
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        # 列が無いDBでも安全に動くよう保証
        cols = [r[1] for r in con.execute("PRAGMA table_info(node)").fetchall()]
        if "lat" not in cols:
            con.execute("ALTER TABLE node ADD COLUMN lat REAL")
        if "lon" not in cols:
            con.execute("ALTER TABLE node ADD COLUMN lon REAL")
        rows: Iterable[sqlite3.Row] = con.execute(
            "SELECT node_name, lat, lon FROM node ORDER BY node_name"
        ).fetchall()
    with open(csv_path, "w", newline="", encoding=encoding) as f:
        w = csv.writer(f)
        w.writerow(["node_name", "lat", "lon"])
        for r in rows:
            nm = r["node_name"]
            if include_current:
                lat = "" if r["lat"] is None else float(r["lat"])
                lon = "" if r["lon"] is None else float(r["lon"])
            else:
                lat = ""
                lon = ""
            w.writerow([nm, lat, lon])
    print(f"[GEO] exported node_geo.csv to {csv_path}")
