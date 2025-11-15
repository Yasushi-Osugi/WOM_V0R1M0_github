# etl_monthly_to_lots.py
# -*- coding: utf-8 -*-
"""
ETL (Step 3): monthly_demand_stg → weekly_demand → lot
- 入力: 月次CSV (product_name, node_name, year, m1..m12)
- 動作: 正規化 → 週次集計（ISO週）→ lot_id生成（NODE-PROD-YYYYWWNNNN, 週ごとに0001リセット）
- 出力: SQLite (weekly_demand, lot) に冪等UPSERT
"""
import argparse
import ast
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Tuple
import numpy as np
import pandas as pd
# -------------------------
# 共有仕様（lot_id 形式など）
# -------------------------
LOT_SEP = "-"  # NODE-PRODUCT-YYYYWWNNNN の区切り
def _sanitize_token(s: str) -> str:
    """区切り記号や空白を除去してlot_idに安全なトークンにする"""
    return str(s).replace(LOT_SEP, "").replace(" ", "").strip()
# -------------------------
# DB helpers（冪等UPSERT）
# -------------------------
def _open(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn
def ensure_node(conn: sqlite3.Connection, name: str) -> int:
    cur = conn.execute("SELECT id FROM node WHERE name=?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO node(name) VALUES(?)", (name,))
    return cur.lastrowid
def ensure_product(conn: sqlite3.Connection, name: str) -> int:
    cur = conn.execute("SELECT id FROM product WHERE name=?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO product(name) VALUES(?)", (name,))
    return cur.lastrowid
def ensure_scenario(conn: sqlite3.Connection, name: str, plan_year_st: int, plan_range: int) -> int:
    cur = conn.execute("SELECT id FROM scenario WHERE name=?", (name,))
    row = cur.fetchone()
    if row:
        # 既存でも plan_year_st/plan_range を更新（冪等）
        conn.execute(
            "UPDATE scenario SET plan_year_st=?, plan_range=? WHERE id=?",
            (int(plan_year_st), int(plan_range), row[0])
        )
        return row[0]
    cur = conn.execute(
        "INSERT INTO scenario(name, plan_year_st, plan_range) VALUES(?,?,?)",
        (name, int(plan_year_st), int(plan_range))
    )
    return cur.lastrowid
def upsert_node_product_params(
    conn: sqlite3.Connection,
    node_id: int,
    product_id: int,
    *,
    lot_size: int = None,
    leadtime: int = None,
    ss_days: int = None,
    long_vacation_weeks: str | None = None,
):
    # 既存有無チェック
    cur = conn.execute(
        "SELECT node_id FROM node_product WHERE node_id=? AND product_id=?",
        (node_id, product_id)
    )
    exists = cur.fetchone() is not None
    if not exists:
        conn.execute(
            """INSERT INTO node_product(node_id, product_id, lot_size, leadtime, ss_days, long_vacation_weeks)
               VALUES(?,?,?,?,?,?)""",
            (
                node_id,
                product_id,
                int(lot_size or 1),
                int(leadtime or 0),
                int(ss_days or 0),
                long_vacation_weeks,
            ),
        )
    else:
        # 与えられた値だけ更新
        sets, vals = [], []
        if lot_size is not None:
            sets.append("lot_size=?"); vals.append(int(lot_size))
        if leadtime is not None:
            sets.append("leadtime=?"); vals.append(int(leadtime))
        if ss_days is not None:
            sets.append("ss_days=?"); vals.append(int(ss_days))
        if long_vacation_weeks is not None:
            sets.append("long_vacation_weeks=?"); vals.append(long_vacation_weeks)
        if sets:
            sql = f"UPDATE node_product SET {', '.join(sets)} WHERE node_id=? AND product_id=?"
            vals.extend([node_id, product_id])
            conn.execute(sql, tuple(vals))
def lot_size_lookup_factory(conn: sqlite3.Connection) -> Callable[[str, str], int]:
    """
    DBの node_product.lot_size を参照する lookup を返す。
    未設定は 1 を返す（ロット化は ceil(value/lot_size) なので 1 は安全）。
    """
    def f(product_name: str, node_name: str) -> int:
        cur = conn.execute(
            """SELECT np.lot_size
               FROM node_product np
               JOIN node n ON n.id=np.node_id
               JOIN product p ON p.id=np.product_id
               WHERE n.name=? AND p.name=?""",
            (node_name, product_name),
        )
        row = cur.fetchone()
        try:
            return max(1, int(row[0])) if row else 1
        except Exception:
            return 1
    return f
# -------------------------
# CSV 正規化（列ゆれ吸収）
# -------------------------
REQUIRED_COLS = ["product_name", "node_name", "year"] + [f"m{i}" for i in range(1, 13)]
def normalize_monthly_csv(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    # 列名トリム
    df = df.rename(columns={c: c.strip() for c in df.columns})
    # 別名吸収
    aliases: Dict[str, str] = {
        "Product_name": "product_name",
        "PRODUCT_NAME": "product_name",
        "Node": "node_name",
        "Node_name": "node_name",
        "NODE_NAME": "node_name",
        "Year": "year",
        "YEAR": "year",
    }
    for m in range(1, 13):
        aliases[f"M{m}"] = f"m{m}"
        aliases[f"m{m}"] = f"m{m}"
    df = df.rename(columns=aliases)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")
    # 型
    df["product_name"] = df["product_name"].astype(str).str.strip()
    df["node_name"]    = df["node_name"].astype(str).str.strip()
    df["year"]         = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    for m in range(1, 13):
        df[f"m{m}"] = pd.to_numeric(df[f"m{m}"], errors="coerce").fillna(0.0)
    df = df.dropna(subset=["year"]).copy()
    df["year"] = df["year"].astype(int)
    return df[REQUIRED_COLS]
# -------------------------
# 月次 → 週次 → lot_id 生成
# -------------------------
@dataclass
class PlanBounds:
    plan_year_st: int
    plan_range: int
def compute_plan_bounds(df_monthly: pd.DataFrame) -> PlanBounds:
    y0 = int(df_monthly["year"].min())
    y1 = int(df_monthly["year"].max())
    # +1 は下期の“はみ出し”保険（仕様通り）
    return PlanBounds(plan_year_st=y0, plan_range=(y1 - y0 + 1 + 1))
def monthly_to_weekly_with_lots(
    df_monthly: pd.DataFrame,
    lot_size_lookup: Callable[[str, str], int]
) -> Tuple[pd.DataFrame, PlanBounds]:
    """
    - 月次を縦持ち→日次→ISO週集計
    - S_lot = ceil(value / lot_size_lookup(prod,node))
    - lot_id を NODE-PROD-YYYYWWNNNN で生成（週単位で 0001 リセット）
    戻り: df_weekly（iso_year, iso_week, value, S_lot, lot_id_list）, PlanBounds
    """
    bounds = compute_plan_bounds(df_monthly)
    # 縦持ち
    melt = df_monthly.melt(
        id_vars=["product_name", "node_name", "year"],
        var_name="month", value_name="value"
    )
    melt["month"] = melt["month"].str[1:].astype(int)
    # 月→日→ISO週
    frames = []
    for _, r in melt.iterrows():
        y, m, v = int(r["year"]), int(r["month"]), float(r["value"])
        if v == 0:
            continue
        days = pd.Timestamp(y, m, 1).days_in_month
        dates = pd.date_range(f"{y}-{m:02d}-01", periods=days, freq="D")
        frames.append(pd.DataFrame({
            "product_name": r["product_name"],
            "node_name":    r["node_name"],
            "date":         dates,
            "value":        v
        }))
    if frames:
        daily = pd.concat(frames, ignore_index=True)
    else:
        daily = pd.DataFrame(columns=["product_name","node_name","date","value"])
    if daily.empty:
        cols = ["product_name","node_name","iso_year","iso_week","value","S_lot","lot_id_list"]
        return pd.DataFrame(columns=cols), bounds
    iso = daily["date"].dt.isocalendar()
    daily["iso_year"] = iso.year.astype(int)
    daily["iso_week"] = iso.week.astype(int)
    weekly = (
        daily.groupby(["product_name","node_name","iso_year","iso_week"], as_index=False)["value"]
        .sum()
    )
    # lot_size と S_lot
    def _row_lot_size(row):
        try:
            return max(1, int(lot_size_lookup(row["product_name"], row["node_name"])))
        except Exception:
            return 1
    weekly["lot_size"] = weekly.apply(_row_lot_size, axis=1)
    weekly["S_lot"]    = (weekly["value"] / weekly["lot_size"]).apply(np.ceil).astype(int)
    # lot_id 生成（週単位 0001 リセット）
    def _mk_lots(row):
        y   = int(row["iso_year"])
        w   = int(row["iso_week"])
        nn  = _sanitize_token(row["node_name"])
        pn  = _sanitize_token(row["product_name"])
        cnt = int(row["S_lot"])
        if cnt <= 0:
            return []
        base = f"{nn}{LOT_SEP}{pn}{LOT_SEP}{y}{w:02d}"
        return [f"{base}{i:04d}" for i in range(1, cnt+1)]
    weekly["lot_id_list"] = weekly.apply(_mk_lots, axis=1)
    return weekly, bounds
# -------------------------
# DB 書き込み（冪等）
# -------------------------
def upsert_monthly_stg(conn: sqlite3.Connection, scenario_id: int, df_monthly: pd.DataFrame):
    """
    monthly_demand_stg へ冪等 UPSERT。
    事前に node/product を ensure し、node_product 行も最小作成（lot_sizeが未登録なら1）。
    """
    with conn:
        for _, r in df_monthly.iterrows():
            node_id = ensure_node(conn, r["node_name"])
            product_id = ensure_product(conn, r["product_name"])
            # node_product の骨だけ作る（lot_size未設定は 1）
            upsert_node_product_params(conn, node_id, product_id)
            vals = (
                scenario_id, node_id, product_id, int(r["year"]),
                float(r["m1"]),  float(r["m2"]),  float(r["m3"]),
                float(r["m4"]),  float(r["m5"]),  float(r["m6"]),
                float(r["m7"]),  float(r["m8"]),  float(r["m9"]),
                float(r["m10"]), float(r["m11"]), float(r["m12"]),
            )
            conn.execute(
                """INSERT INTO monthly_demand_stg
                   (scenario_id,node_id,product_id,year,
                    m1,m2,m3,m4,m5,m6,m7,m8,m9,m10,m11,m12)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(scenario_id,node_id,product_id,year)
                   DO UPDATE SET
                     m1=excluded.m1, m2=excluded.m2, m3=excluded.m3, m4=excluded.m4,
                     m5=excluded.m5, m6=excluded.m6, m7=excluded.m7, m8=excluded.m8,
                     m9=excluded.m9, m10=excluded.m10, m11=excluded.m11, m12=excluded.m12
                """,
                vals,
            )
def upsert_weekly_and_lot(conn: sqlite3.Connection, scenario_id: int, df_weekly: pd.DataFrame):
    """
    weekly_demand と lot を冪等UPSERT
    """
    with conn:
        # weekly_demand
        w_rows = [
            (
                scenario_id,
                ensure_node(conn, r["node_name"]),
                ensure_product(conn, r["product_name"]),
                int(r["iso_year"]), int(r["iso_week"]),
                float(r["value"]),
            )
            for _, r in df_weekly.iterrows()
        ]
        conn.executemany(
            """INSERT INTO weekly_demand
               (scenario_id,node_id,product_id,iso_year,iso_week,value)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(scenario_id,node_id,product_id,iso_year,iso_week)
               DO UPDATE SET value=excluded.value
            """,
            w_rows,
        )
        # lot（lot_id は UNIQUE 一意）
        lot_rows = []
        for _, r in df_weekly.iterrows():
            node_id = ensure_node(conn, r["node_name"])
            product_id = ensure_product(conn, r["product_name"])
            iso_year = int(r["iso_year"])
            iso_week = int(r["iso_week"])
            lots = r["lot_id_list"]
            if not isinstance(lots, list):
                if isinstance(lots, str):
                    try:
                        lots = ast.literal_eval(lots)
                    except Exception:
                        lots = []
                else:
                    lots = []
            for lot_id in lots:
                lot_rows.append((scenario_id, node_id, product_id, iso_year, iso_week, lot_id))
        if lot_rows:
            conn.executemany(
                """INSERT INTO lot(scenario_id,node_id,product_id,iso_year,iso_week,lot_id)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(lot_id) DO UPDATE SET
                     scenario_id=excluded.scenario_id,
                     node_id=excluded.node_id,
                     product_id=excluded.product_id,
                     iso_year=excluded.iso_year,
                     iso_week=excluded.iso_week
                """,
                lot_rows,
            )
# -------------------------
# メイン：CSV → STG → 週次 → lot
# -------------------------
def run_etl(db_path: str, csv_path: str, scenario_name: str, default_lot_size: int | None = None):
    df_monthly = normalize_monthly_csv(csv_path)
    # 計画レンジ
    bounds = compute_plan_bounds(df_monthly)
    with _open(db_path) as conn:
        scenario_id = ensure_scenario(conn, scenario_name, bounds.plan_year_st, bounds.plan_range)
        # オプションで node_product.lot_size を一括上書き
        if default_lot_size is not None:
            # 先に node/product を作っておく
            for _, r in df_monthly.iterrows():
                nid = ensure_node(conn, r["node_name"])
                pid = ensure_product(conn, r["product_name"])
                upsert_node_product_params(conn, nid, pid, lot_size=int(default_lot_size))
        # STG へ冪等投入
        upsert_monthly_stg(conn, scenario_id, df_monthly)
        # 週次化＋lot_id生成（DBの lot_size を参照）
        ls_lookup = lot_size_lookup_factory(conn)
        df_weekly, _ = monthly_to_weekly_with_lots(df_monthly, ls_lookup)
        # weekly_demand / lot へ冪等UPSERT
        upsert_weekly_and_lot(conn, scenario_id, df_weekly)
    print(f"[OK] ETL complete. scenario='{scenario_name}', rows_weekly={len(df_weekly)}")
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="SQLite path (e.g., psi.sqlite)")
    ap.add_argument("--csv", required=True, help="Monthly demand CSV path")
    ap.add_argument("--scenario", required=True, help="Scenario name (e.g., 'Baseline')")
    ap.add_argument("--default-lot-size", type=int, help="Optional: set node_product.lot_size for all rows")
    args = ap.parse_args()
    run_etl(args.db, args.csv, args.scenario, args.default_lot_size)
#使い方（手順）
#
#先に Step 2 の DDL を適用（schema.sql）。
#
#月次CSVを用意（列：product_name,node_name,year,m1..m12）。
#別名（Node, Product_name, M1..M12 等）でもOK。内部で正規化します。
#
#実行：
#python etl_monthly_to_lots.py --db psi.sqlite --csv demand.csv --scenario Baseline
## すべての lot_size を仮に 50 で固定したい場合
#python etl_monthly_to_lots.py --db psi.sqlite --csv demand.csv --scenario Baseline --default-lot-size 50
#
#ここまででできること
#monthly_demand_stg に冪等で投入（名前ゆれ吸収）。
#月→日→ISO週で集計して weekly_demand を更新。
#node_product.lot_size を参照して S_lot を計算し、週単位で 0001 リセットの lot_id を生成して lot にUPSERT。
#何度流しても同じ状態（冪等）になります。
