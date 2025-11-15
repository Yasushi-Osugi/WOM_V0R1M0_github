# .\pysi\scripts\upsert_cost_table2sql.py
# starter
# # 仮にプロジェクト直下に置いた場合
#python .\pysi\scripts\upsert_cost_table2sql.py `
#  --csv ".\data\sku_cost_table_inbound.csv" `
#  --db  ".\var\psi.sqlite"
# python .\pysi\scripts\upsert_cost_table2sql.py --csv ".\data\sku_cost_table_inbound.csv"  --db  ".\var\psi.sqlite"
# python .\pysi\scripts\upsert_cost_table2sql.py --csv ".\data\sku_cost_table_outbound.csv"  --db  ".\var\psi.sqlite"
# pysi/scripts/upsert_cost_table2sql.py  （IN/OUT 共通）
import sqlite3, sys, os, argparse
import pandas as pd
CS_COLS = [
    "cs_logistics_costs","cs_warehouse_cost","cs_fixed_cost","cs_profit",
    "cs_direct_materials_costs","cs_tax_portion"
]
def upsert_cost_csv_to_sql(csv_path: str, db_path: str):
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    rename = {
        "product_name":"product_name",
        "node_name":"node_name",
        "logistics_costs":"cs_logistics_costs",
        "warehouse_cost":"cs_warehouse_cost",
        "SGA_total":"cs_fixed_cost",
        "profit":"cs_profit",
        "direct_materials_costs":"cs_direct_materials_costs",
        "tax_portion":"cs_tax_portion",
        "price_sales_shipped":"price_sales_shipped",
        "marketing_promotion":"marketing_promotion",
        "sales_admin_cost":"sales_admin_cost",
    }
    # SGA_total 無ければ marketing + sales_admin を仮生成
    if "SGA_total" not in df.columns and {"marketing_promotion","sales_admin_cost"} <= set(df.columns):
        df["SGA_total"] = (df["marketing_promotion"].fillna(0.0) + df["sales_admin_cost"].fillna(0.0))
    df = df.rename(columns={k:v for k,v in rename.items() if k in df.columns})
    # 不足列は 0 補完（CSVは%）
    for c in CS_COLS:
        if c not in df.columns:
            df[c] = 0.0
    # % → 0..1
    for c in CS_COLS:
        x = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        df[c] = (x.where(x <= 1.0, x/100.0)).clip(0.0, 1.0)
    # Strict: 合計比率チェック（>1.0 は即エラー）
    sum_r = (df["cs_logistics_costs"] + df["cs_warehouse_cost"] + df["cs_fixed_cost"] +
             df["cs_profit"] + df["cs_direct_materials_costs"] + df["cs_tax_portion"])
    bad = df.loc[sum_r > 1.0 + 1e-9, ["product_name","node_name"]]
    if not bad.empty:
        rows = bad.astype(str).agg(" / ".join, axis=1).tolist()
        print(f"[ERROR] sum_r > 1.0 rows: {rows}", flush=True)
        sys.exit(1)
    # UPSERT
    conn = sqlite3.connect(db_path)
    conn.executemany("INSERT OR IGNORE INTO product(product_name) VALUES (?)",
                     [(p,) for p in set(df["product_name"].astype(str))])
    conn.executemany("INSERT OR IGNORE INTO node(node_name) VALUES (?)",
                     [(n,) for n in set(df["node_name"].astype(str))])
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
    for _, r in df.iterrows():
        rows.append((
            r["node_name"], r["product_name"], 1,
            float(r["cs_logistics_costs"]), float(r["cs_warehouse_cost"]),
            float(r["cs_fixed_cost"]), float(r["cs_profit"]),
            float(r["cs_direct_materials_costs"]), float(r["cs_tax_portion"]),
        ))
    conn.executemany(upsert_np, rows)
    conn.commit()
    # 任意：ASIS 価格をそのまま入れる（あれば）
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
    print(f"[OK] CSV → SQL 反映: {len(df)} rows", flush=True)
def _parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", required=True, help="inbound/outbound cost CSV path")
    p.add_argument("--db",  required=True, help="SQLite DB path (psi.sqlite)")
    return p.parse_args()
if __name__ == "__main__":
    args = _parse_args()
    print(f"[RUN] CSV: {os.path.abspath(args.csv)}", flush=True)
    print(f"[RUN] DB : {os.path.abspath(args.db)}", flush=True)
    upsert_cost_csv_to_sql(args.csv, args.db)
