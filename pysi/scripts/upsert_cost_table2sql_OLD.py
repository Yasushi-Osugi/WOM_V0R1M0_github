# .\pysi\scripts\upsert_cost_table2sql.py
# starter
# # 仮にプロジェクト直下に置いた場合
#python .\pysi\scripts\upsert_cost_table2sql.py `
#  --csv ".\data\sku_cost_table_inbound.csv" `
#  --db  ".\var\psi.sqlite"
# python .\pysi\scripts\upsert_cost_table2sql.py --csv ".\data\sku_cost_table_inbound.csv"  --db  ".\var\psi.sqlite"
# python .\pysi\scripts\upsert_cost_table2sql.py --csv ".\data\sku_cost_table_outbound.csv"  --db  ".\var\psi.sqlite"
import sqlite3
import pandas as pd
from typing import Iterable
import argparse
from pathlib import Path
#from upsert_inbound_cost_impl import upsert_inbound_cost_csv_to_sql  # ←関数を置いたモジュール名
# CSV の % → SQL の 0..1 に落とす対象
CS_COLS = [
    "cs_logistics_costs", "cs_warehouse_cost", "cs_fixed_cost", "cs_profit",
    "cs_direct_materials_costs", "cs_tax_portion"
]
def _ensure_master(conn: sqlite3.Connection, products: Iterable[str], nodes: Iterable[str]):
    cur = conn.cursor()
    cur.executemany("INSERT OR IGNORE INTO product(product_name) VALUES (?)",
                    [(p,) for p in set(products)])
    cur.executemany("INSERT OR IGNORE INTO node(node_name) VALUES (?)",
                    [(n,) for n in set(nodes)])
    conn.commit()
def _clamp_and_warn(row, key_sum, cap=0.95):
    if row[key_sum] > cap:
        print(f"[WARN] sum of ratios > {cap}: {row['product_name']} / {row['node_name']} -> {row[key_sum]:.3f} (clamped)")
        row[key_sum] = cap
    return row[key_sum]
def upsert_inbound_cost_csv_to_sql(csv_path: str, db_path: str):
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    # 列名マッピング：CSV 側の列名 → SQL 側の列名
    # ここはあなたの CSV に合わせて調整してください
    rename = {
        "product_name": "product_name",
        "node_name": "node_name",
        # ▼比率（%）で来る列
        "logistics_costs": "cs_logistics_costs",
        "warehouse_cost": "cs_warehouse_cost",
        # 固定費は CSV に SGA_total があればそれを採用、なければ marketing+sales_admin
        "SGA_total": "cs_fixed_cost",
        "profit": "cs_profit",
        "direct_materials_costs": "cs_direct_materials_costs",
        "tax_portion": "cs_tax_portion",
        # 任意：参照用
        "price_sales_shipped": "price_sales_shipped",
        "marketing_promotion": "marketing_promotion",
        "sales_admin_cost": "sales_admin_cost",
    }
    for k in list(rename):
        if k not in df.columns:
            # SGA_total が無いケース → marketing + sales_admin を使うために一時生成
            if k == "SGA_total" and {"marketing_promotion","sales_admin_cost"} <= set(df.columns):
                df["SGA_total"] = (df["marketing_promotion"].fillna(0.0) +
                                   df["sales_admin_cost"].fillna(0.0))
            else:
                # 無ければスキップ（任意列）
                rename.pop(k, None)
    df = df.rename(columns=rename)
    # 未存在列を 0 で補完（% 単位）
    for c in CS_COLS:
        if c not in df.columns:
            df[c] = 0.0
    for c in ["price_sales_shipped","marketing_promotion","sales_admin_cost"]:
        if c not in df.columns:
            df[c] = 0.0
    # % → 0..1 へ変換（SQL 保存形式）
    df_sql = df.copy()
    for c in CS_COLS:
        df_sql[c] = (df_sql[c].fillna(0.0) / 100.0).clip(lower=0.0)
    # 合計比率チェック（材料・関税も“比率”として持つ前提）
    sum_cols = ["cs_logistics_costs","cs_warehouse_cost","cs_fixed_cost",
                "cs_profit","cs_direct_materials_costs","cs_tax_portion"]
    df_sql["sum_r"] = df_sql[sum_cols].sum(axis=1)
    df_sql["sum_r"] = df_sql.apply(lambda r: _clamp_and_warn(r, "sum_r", cap=0.95), axis=1)
    # マスタ挿入
    conn = sqlite3.connect(db_path)
    _ensure_master(conn, df_sql["product_name"], df_sql["node_name"])
    # node_product UPSERT
    upsert_np = """
    INSERT INTO node_product(
      node_name, product_name, lot_size,
      cs_logistics_costs, cs_warehouse_cost, cs_fixed_cost, cs_profit,
      cs_direct_materials_costs, cs_tax_portion
    ) VALUES (?,?,?,?,?,?,?,?,?)
    ON CONFLICT(node_name, product_name) DO UPDATE SET
      cs_logistics_costs=excluded.cs_logistics_costs,
      cs_warehouse_cost=excluded.cs_warehouse_cost,
      cs_fixed_cost=excluded.cs_fixed_cost,
      cs_profit=excluded.cs_profit,
      cs_direct_materials_costs=excluded.cs_direct_materials_costs,
      cs_tax_portion=excluded.cs_tax_portion
    ;
    """
    rows = []
    for _, r in df_sql.iterrows():
        rows.append((
            r["node_name"], r["product_name"], int(1),  # lot_size は評価金額に掛けない方針
            float(r["cs_logistics_costs"]),
            float(r["cs_warehouse_cost"]),
            float(r["cs_fixed_cost"]),
            float(r["cs_profit"]),
            float(r["cs_direct_materials_costs"]),
            float(r["cs_tax_portion"]),
        ))
    conn.executemany(upsert_np, rows)
    conn.commit()
    # （任意）price_tag へ ASIS を入れたい場合
    if "price_sales_shipped" in df.columns:
        upsert_price = """
        INSERT INTO price_tag(node_name, product_name, tag, price)
        VALUES (?,?, 'ASIS', ?)
        ON CONFLICT(node_name, product_name, tag) DO UPDATE SET price=excluded.price;
        """
        rows_p = []
        for _, r in df.iterrows():
            price = float(r.get("price_sales_shipped", 0.0) or 0.0)
            rows_p.append((r["node_name"], r["product_name"], price))
        conn.executemany(upsert_price, rows_p)
        conn.commit()
    conn.close()
    print(f"[OK] inbound CSV → SQL 反映完了: {len(df_sql)} rows")
def main():
    ap = argparse.ArgumentParser(description="Inbound cost CSV -> SQLite UPSERT")
    ap.add_argument("--csv", required=True, help="sku_cost_table_inbound.csv のパス")
    ap.add_argument("--db",  required=True, help="SQLite DB (psi.sqlite) のパス")
    args = ap.parse_args()
    csv_path = Path(args.csv).expanduser().resolve()
    db_path  = Path(args.db).expanduser().resolve()
    print(f"[RUN] CSV: {csv_path}")
    print(f"[RUN] DB : {db_path}")
    upsert_inbound_cost_csv_to_sql(str(csv_path), str(db_path))
if __name__ == "__main__":
    main()
