# pysi/evaluate/cost_df_loader.py
# cost_df_loader.py ー cost_df 構築ロジック（比率はnode_product、金額はprice_money_per_lot）
import os
import sqlite3
import numpy as np
import pandas as pd
# =========================
# 定数/ユーティリティ
# =========================
# node_product における「比率カラム」だけを定義（DBに保持するのも比率のみ）
RATIO_COLS = [
    "cs_logistics_costs",
    "cs_warehouse_cost",
    "cs_fixed_cost",
    "cs_profit",
    "cs_direct_materials_costs",
    "cs_tax_portion",
    "cs_prod_indirect_labor",
    "cs_prod_indirect_others",
    "cs_direct_labor_costs",
    "cs_depreciation_others",
    "cs_mfg_overhead",
]
# 購買系（money で扱う）に相当する「比率カラム」
# ー price推定の分母からは除外（purchase_costに含めるため）
PURCHASE_RATIO_COLS = [
    "cs_direct_materials_costs",  # ← moneyは PMPL.direct_materials_costs
    "cs_tax_portion",             # ← moneyは PMPL.tariff_cost
]
# 分母に入れるべき比率（= 合計から購買系を除いた分）
# 物流、倉庫、SGA、利益、各種労務・OH・償却など
CORE_RATIO_COLS = [c for c in RATIO_COLS if c not in PURCHASE_RATIO_COLS]
MAX_PRICE_MULT = 20.0  # 子価格の上限（親価格の n 倍）だけは安全弁として残す
def _validate_sum_r(df: pd.DataFrame, ratio_cols=RATIO_COLS, policy: str = "warn") -> pd.DataFrame:
    """
    sum_r 検証ユーティリティ
    policy:
      - 'error' : sum_r > 1.0 を例外で止める（従来）
      - 'warn'  : Warning を出して継続（推奨、デフォルト）
      - 'scale' : >1.0 行は比率列を合計で割って 1.0 に正規化して継続
    """
    sum_r = df[ratio_cols].sum(axis=1).astype(float)
    mask = sum_r > 1.0 + 1e-9
    if not mask.any():
        return df  # OK
    bad_pairs = df.loc[mask, ["product_name", "node_name"]].astype(str).agg(" / ".join, axis=1).tolist()
    msg = f"[sum_r check] >1.0 at {mask.sum()} rows: {bad_pairs}"
    if policy == "error":
        raise ValueError(msg)
    elif policy == "scale":
        # 合計が1.0を超えている行だけ、比率列を合計で割って 1.0 に正規化
        over = df.loc[mask, ratio_cols]
        s = over.sum(axis=1).replace(0, np.nan)
        df.loc[mask, ratio_cols] = over.div(s, axis=0).fillna(0.0)
        print(f"[FIXED] {mask.sum()} rows were scaled to sum_r==1.0. {msg}", flush=True)
    else:
        # 'warn'
        print(f"[WARNING] {msg}", flush=True)
    return df
# =========================
# メイン：DB -> cost_df
# =========================
def build_cost_df_from_sql(db_path: str) -> pd.DataFrame:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    # node_product（比率）・price_tag（ASIS）・price_money_per_lot（money）・product_edge/tariff を束ねる
    q = """
    WITH node_rows AS (
      SELECT
        np.product_name,
        np.node_name,
        COALESCE(pt.price, 0) AS node_price_asis,
        -- ========= 比率（node_product 全面取得）=========
        COALESCE(np.cs_logistics_costs,         0) AS r_logistics,
        COALESCE(np.cs_warehouse_cost,          0) AS r_warehouse,
        COALESCE(np.cs_fixed_cost,              0) AS r_fixed,
        COALESCE(np.cs_profit,                  0) AS r_profit,
        COALESCE(np.cs_direct_materials_costs,  0) AS r_dm_ratio,
        COALESCE(np.cs_tax_portion,             0) AS r_tariff_ratio,
        COALESCE(np.cs_prod_indirect_labor,     0) AS r_prod_indirect_labor,
        COALESCE(np.cs_prod_indirect_others,    0) AS r_prod_indirect_others,
        COALESCE(np.cs_direct_labor_costs,      0) AS r_direct_labor_costs,
        COALESCE(np.cs_depreciation_others,     0) AS r_depreciation_others,
        COALESCE(np.cs_mfg_overhead,            0) AS r_mfg_overhead,
        -- ========= 金額（price_money_per_lot）=========
        COALESCE(pml.direct_materials_costs, 0) AS dm_money_existing,
        COALESCE(pml.tariff_cost,            0) AS tariff_money_existing
      FROM node_product np
      LEFT JOIN price_tag pt
        ON pt.product_name = np.product_name
       AND pt.node_name    = np.node_name
       AND pt.tag          = 'ASIS'
      LEFT JOIN price_money_per_lot pml
        ON pml.product_name = np.product_name
       AND pml.node_name    = np.node_name
    ),
    parent_ref AS (
      SELECT pe.product_name, pe.child_name AS node_name, pe.parent_name
      FROM product_edge pe
      WHERE pe.bound = 'OUT'
    ),
    parent_price AS (
      SELECT pr.product_name, pr.node_name, pr.parent_name,
             COALESCE(ptp.price, 0) AS parent_price_asis
      FROM parent_ref pr
      LEFT JOIN price_tag ptp
        ON ptp.product_name = pr.product_name
       AND ptp.node_name    = pr.parent_name
       AND ptp.tag          = 'ASIS'
    ),
    tariff_edge AS (
      SELECT t.product_name, t.from_node AS parent_name, t.to_node AS node_name, t.tariff_rate
      FROM tariff t
    )
    SELECT
      nr.product_name, nr.node_name, nr.node_price_asis,
      -- 比率列
      nr.r_logistics, nr.r_warehouse, nr.r_fixed, nr.r_profit,
      nr.r_dm_ratio, nr.r_tariff_ratio,
      nr.r_prod_indirect_labor, nr.r_prod_indirect_others,
      nr.r_direct_labor_costs, nr.r_depreciation_others, nr.r_mfg_overhead,
      -- 金額列
      nr.dm_money_existing, nr.tariff_money_existing,
      -- 親価格/関税レート
      pp.parent_name, COALESCE(pp.parent_price_asis, 0) AS parent_price_asis,
      COALESCE(tf.tariff_rate, 0) AS tariff_rate
    FROM node_rows nr
    LEFT JOIN parent_price pp
      ON pp.product_name = nr.product_name AND pp.node_name = nr.node_name
    LEFT JOIN tariff_edge tf
      ON tf.product_name = nr.product_name
     AND tf.node_name    = nr.node_name
     AND tf.parent_name  = pp.parent_name
    ;
    """
    df = pd.read_sql_query(q, con)
    # ルート（supply_point）の ASIS を取得：分母補完用
    q_root = """
    SELECT product_name,
           MAX(CASE WHEN tag='ASIS' THEN price END) AS asis,
           MAX(CASE WHEN tag='TOBE' THEN price END) AS tobe
    FROM price_tag
    WHERE node_name='supply_point'
    GROUP BY product_name;
    """
    root_price = pd.read_sql_query(q_root, con).set_index("product_name")
    con.close()
    def get_root_price(prod: str) -> float:
        if prod in root_price.index:
            row = root_price.loc[prod]
            val = row["asis"] if pd.notna(row["asis"]) else row["tobe"]
            return float(val) if pd.notna(val) else 0.0
        return 0.0
    # 正規化
    df["product_name"] = df["product_name"].astype(str).str.strip()
    df["node_name"]    = df["node_name"].astype(str).str.strip()
    df["parent_name"]  = df["parent_name"].astype(object).where(~df["parent_name"].isna(), None)
    is_root = df["parent_name"].isna() | (df["node_name"] == "supply_point")
    parent_price = pd.to_numeric(df["parent_price_asis"], errors="coerce").fillna(0.0)
    parent_price = parent_price.where(parent_price > 0.0,
                                      df["product_name"].map(get_root_price))
    # 比率列（%混在も許容 → 0..1 に揃える）
    def as_ratio(s: pd.Series) -> pd.Series:
        x = pd.to_numeric(s, errors="coerce").fillna(0.0)
        x = np.where(x <= 1.0, x, x / 100.0)  # 1超なら%とみなす
        x = np.clip(x, 0.0, 1.0)
        return pd.Series(x, index=s.index)
    # すべての比率列を整形
    ratio_map = {
        "cs_logistics_costs":        "r_logistics",
        "cs_warehouse_cost":         "r_warehouse",
        "cs_fixed_cost":             "r_fixed",
        "cs_profit":                 "r_profit",
        "cs_direct_materials_costs": "r_dm_ratio",
        "cs_tax_portion":            "r_tariff_ratio",
        "cs_prod_indirect_labor":    "r_prod_indirect_labor",
        "cs_prod_indirect_others":   "r_prod_indirect_others",
        "cs_direct_labor_costs":     "r_direct_labor_costs",
        "cs_depreciation_others":    "r_depreciation_others",
        "cs_mfg_overhead":           "r_mfg_overhead",
    }
    for k, v in ratio_map.items():
        if v not in df.columns:
            df[v] = 0.0  # 念のため
        df[v] = as_ratio(df[v])
    # 検証用：sum_r は「比率すべての合計」でチェック
    df_for_check = pd.DataFrame({k: df[v] for k, v in ratio_map.items()})
    sum_policy = os.environ.get("PSI_COST_SUM_POLICY", "warn")  # 'warn' / 'scale' / 'error'
    #そのまま：warn（既定） → 警告を出しつつ続行
    #正規化：scale → sum_r が 1.0 を超えた行のみ 自動スケール
    #厳格停止：error → 例外で停止
    df_checked = df.copy()
    for k, v in ratio_map.items():
        df_checked[k] = df[v]
    df_checked = _validate_sum_r(df_checked, ratio_cols=list(ratio_map.keys()), policy=sum_policy)
    # price推定の分母は「購買系を除いた比率の合計」
    # ＝ logistics/warehouse/fixed/profit/労務/間接/償却/OH 等は分母に入れる
    # ＝ direct_materials/tax は purchase_cost 側でmoneyとして扱う
    sum_r_core = df_for_check[[c for c in df_for_check.columns
                               if c not in PURCHASE_RATIO_COLS]].sum(axis=1).astype(float)
    sum_r_core = np.clip(sum_r_core, 0.0, 0.999999)  # 0割防止のため、1に張り付かないように微小マージン
    # ============ money（PMPL） ============
    tariff_rate = pd.to_numeric(df["tariff_rate"], errors="coerce").fillna(0.0).clip(0.0)
    purchase_cost = parent_price * (1.0 + tariff_rate)
    dm_money = pd.to_numeric(df["dm_money_existing"], errors="coerce").fillna(0.0)
    dm_money = np.where(is_root, 0.0, np.where(dm_money > 0.0, dm_money, parent_price))
    tariff_money = pd.to_numeric(df["tariff_money_existing"], errors="coerce").fillna(0.0)
    tariff_money = np.where(is_root, 0.0,
                            np.where(tariff_money > 0.0, tariff_money, parent_price * tariff_rate))
    # 価格推定：非rootは分母 (1 - sum_r_core)
    root_price_map = df["product_name"].map(get_root_price).astype(float)
    price_est = np.where(is_root, root_price_map,
                         purchase_cost / np.maximum(1e-6, (1.0 - sum_r_core)))
    # 子価格の上限のみ適用（クランプではない安全弁）
    price_cap = np.where(is_root, np.inf, parent_price * MAX_PRICE_MULT)
    price = np.minimum(price_est, np.where(np.isfinite(price_cap), price_cap, price_est))
    # ============ 出力DF（円グラフ・評価用） ============
    out = pd.DataFrame({
        "product_name": df["product_name"],
        "node_name":    df["node_name"],
        "price_sales_shipped": price.astype(float),
        # money化（比率×価格）
        "logistics_costs":         (df["r_logistics"] * price).astype(float),
        "warehouse_cost":          (df["r_warehouse"] * price).astype(float),
        "manufacturing_overhead":  (df["r_mfg_overhead"] * price).astype(float),
        "prod_indirect_labor":     (df["r_prod_indirect_labor"] * price).astype(float),
        "prod_indirect_others":    (df["r_prod_indirect_others"] * price).astype(float),
        "direct_labor_costs":      (df["r_direct_labor_costs"] * price).astype(float),
        "depreciation_others":     (df["r_depreciation_others"] * price).astype(float),
        "fixed_cost":              (df["r_fixed"] * price).astype(float),
        "profit":                  (df["r_profit"] * price).astype(float),
        # money（PMPLそのまま）
        "direct_materials_costs":  dm_money.astype(float),
        "tax_portion":             tariff_money.astype(float),
        # 表示上は 0（SGA内訳は必要に応じて今後拡張）
        "marketing_promotion": 0.0,
        "sales_admin_cost":    0.0,
    })
    # 参考：上限にかかった行は警告だけ出す
    over_cap = (~is_root) & (price_est > price_cap)
    if bool(np.any(over_cap)):
        warn2 = df.loc[over_cap, ["product_name","node_name"]].astype(str).agg(" / ".join, axis=1)
        print(f"[WARN] price capped to {MAX_PRICE_MULT}x parent:", list(warn2))
    return out
