
#### ** "psi.plan.demand_generate.py" **
import math
import pandas as pd
import numpy as np
# *********************************
# for Lot_ID generate
# *********************************
# === lot-id formatting (shared) ===
LOT_SEP = "-"  # node・product には使わない安全な記号を選ぶ
def _sanitize_token(s: str) -> str:
    """区切り記号や空白を除去してロットIDのプレフィクスに安全なトークンにする"""
    return str(s).replace(LOT_SEP, "").replace(" ", "").strip()
# *********************************
# check_plan_range
# *********************************
def check_plan_range(df):  # df is dataframe
    #
    # getting start_year and end_year
    #
    start_year = node_data_min = df["year"].min()
    end_year = node_data_max = df["year"].max()
    # *********************************
    # plan initial setting
    # *********************************
    plan_year_st = int(start_year)  # 2024  # plan開始年
    # 3ヵ年または5ヵ年計画分のS計画を想定
    plan_range = int(end_year) - int(start_year) + 1 + 1  # +1はハミ出す期間
    plan_year_end = plan_year_st + plan_range
    return plan_range, plan_year_st
#@250813 ADD
def _normalize_monthly_demand_df_sku(df: pd.DataFrame) -> pd.DataFrame:
    """
    入力DFを `product_name,node_name,year,m1..m12` に正規化。
    大文字小文字や別名 (Product_name, Node, Year, M1..M12) も吸収。
    """
    # トリム＋小文字化した暫定名で揃える
    rename = {c: c.strip() for c in df.columns}
    df = df.rename(columns=rename)
    # 代表名へ寄せる
    aliases = {
        "Product_name": "product_name",
        "PRODUCT_NAME": "product_name",
        "Node": "node_name",
        "Node_name": "node_name",
        "NODE_NAME": "node_name",
        "Year": "year",
        "YEAR": "year",
    }
    # 月列も一括で吸収
    for m in range(1, 13):
        aliases[f"M{m}"] = f"m{m}"
        aliases[f"m{m}"] = f"m{m}"
    df = df.rename(columns=aliases)
    # 必須列チェック
    required = ["product_name", "node_name", "year"] + [f"m{i}" for i in range(1, 12+1)]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"[ERR] monthly csv missing columns: {missing}")
    # 型と欠損処理
    df["product_name"] = df["product_name"].astype(str).str.strip()
    df["node_name"]    = df["node_name"].astype(str).str.strip()
    df["year"]         = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    for m in range(1, 13):
        col = f"m{m}"
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    # year 欠損は除外
    df = df.dropna(subset=["year"]).copy()
    df["year"] = df["year"].astype(int)
    return df[required]
def convert_monthly_to_weekly_sku(df: pd.DataFrame, lot_size_lookup) -> tuple[pd.DataFrame, int, int]:
    """
    月次を週次に変換。行ごとの lot_size は lot_size_lookup(product_name, node_name) で解決。
    戻り値: (df_weekly, plan_range, plan_year_st)
    """
    # 計画レンジ
    plan_range, plan_year_st = check_plan_range(df.rename(columns={"year":"year"}))
    # 縦持ち化
    df_melt = df.melt(
        id_vars=["product_name", "node_name", "year"],
        var_name="month", value_name="value"
    )
    # 'm1'→1
    df_melt["month"] = df_melt["month"].str[1:].astype(int)
    # 日次にばらし → 週番号で集計
    frames = []
    for _, r in df_melt.iterrows():
        y = int(r["year"]); m = int(r["month"]); v = float(r["value"])
        if v == 0:
            continue
        try:
            days = pd.Timestamp(y, m, 1).days_in_month
        except Exception:
            continue
        dates = pd.date_range(f"{y}-{m:02d}-01", periods=days, freq="D")
        frames.append(pd.DataFrame({
            "product_name": r["product_name"],
            "node_name":    r["node_name"],
            "date":         dates,
            "value":        v
        }))
    if frames:
        df_daily = pd.concat(frames, ignore_index=True)
    else:
        df_daily = pd.DataFrame(columns=["product_name","node_name","date","value"])
    if df_daily.empty:
        # 空でも落ちないように最低限の列を返す
        return (pd.DataFrame(columns=["product_name","node_name","iso_year","iso_week","value","S_lot","lot_id_list"]),
                plan_range, plan_year_st)
    iso = df_daily["date"].dt.isocalendar()
    df_daily["iso_year"] = iso.year.astype(int)
    df_daily["iso_week"] = iso.week.astype(int)
    df_weekly = (
        df_daily.groupby(["product_name","node_name","iso_year","iso_week"], as_index=False)["value"]
        .sum()
    )
    # lot_size を行ごとに解決して S_lot と lot_id を作成
    def _row_lot_size(row):
        try:
            return max(1, int(lot_size_lookup(row["product_name"], row["node_name"])))
        except Exception:
            return 1
    df_weekly["lot_size"] = df_weekly.apply(_row_lot_size, axis=1)
    df_weekly["S_lot"]    = (df_weekly["value"] / df_weekly["lot_size"]).apply(np.ceil).astype(int)
    # 既存: df_weekly["S_lot"] = ...
    # ここから lot_id 生成の関数を差し替え
    def _mk_lots(row):
        y   = int(row["iso_year"])
        w   = int(row["iso_week"])
        nn  = _sanitize_token(row["node_name"])
        pn  = _sanitize_token(row["product_name"])
        cnt = int(row["S_lot"])
        if cnt <= 0:
            return []
        # 形式: NODE-PRODUCT-YYYYWWNNNN
        return [f"{nn}{LOT_SEP}{pn}{LOT_SEP}{y}{w:02d}{i+1:04d}" for i in range(cnt)]
    df_weekly["lot_id_list"] = df_weekly.apply(_mk_lots, axis=1)
    # 互換のため: iso_week は "02" 文字列
    df_weekly["iso_week"] = df_weekly["iso_week"].astype(str).str.zfill(2)
    return df_weekly, plan_range, plan_year_st
def generate_lot_ids(row):
    """
    Generate lot IDs based on the row's data.
    Parameters:
        row (pd.Series): A row from the DataFrame.
    Returns:
        list: List of generated lot IDs.
    """
    lot_count = row["S_lot"]
    # "_" を削除した形式で生成
    return [f"{row['node_name']}{row['iso_year']}{str(row['iso_week']).zfill(2)}{i+1:04d}" for i in range(lot_count)]
def convert_monthly_to_weekly(df: pd.DataFrame, lot_size: int):
    """
    Convert monthly demand data to weekly ISO format with lot IDs and return additional metadata.
    Parameters:
        df (pd.DataFrame): Monthly demand data.
        lot_size (int): Lot size for allocation.
    Returns:
        Tuple[pd.DataFrame, int, int]: Weekly demand data, planning range, and starting year.
    """
    # デバッグ出力
    print("DataFrame type:", type(df))
    print("DataFrame columns:", df.columns if isinstance(df, pd.DataFrame) else "Not a DataFrame")
    print("DataFrame head:", df.head() if isinstance(df, pd.DataFrame) else "Not a DataFrame")
    # ** Check and extract plan range and starting year **
    plan_range, plan_year_st = check_plan_range(df)
    # ** Reshape data for processing **
    df = df.melt(
        id_vars=["product_name", "node_name", "year"],
        var_name="month",
        value_name="value",
    )
    df["month"] = df["month"].str[1:].astype(int)
    # ** Handle potential NaNs in 'year' **
    if df["year"].isna().any():
        print("Warning: 'year' column contains NaN values. These rows will be dropped.")
        df = df.dropna(subset=["year"])
    try:
        df["year"] = df["year"].astype(int)
    except Exception as e:
        print(f"Error during 'year' conversion: {e}")
        raise
    # ** Convert monthly data to daily data **
    df_daily = pd.DataFrame()
    for _, row in df.iterrows():
        year = int(row["year"])
        month = int(row["month"])
        try:
            days_in_month = pd.Timestamp(year, month, 1).days_in_month
        except Exception as e:
            print(f"Timestamp error at year={year}, month={month}: {e}")
            continue  # skip this row
        daily_values = np.full(days_in_month, row["value"])
        dates = pd.date_range(
            start=f"{year}-{month}-01", periods=len(daily_values)
        )
        df_temp = pd.DataFrame(
            {
                "product_name": row["product_name"],
                "node_name": row["node_name"],
                "date": dates,
                "value": daily_values,
            }
        )
        df_daily = pd.concat([df_daily, df_temp])
    # ** Aggregate data by ISO week **
    df_daily["iso_year"] = df_daily["date"].dt.isocalendar().year
    df_daily["iso_week"] = df_daily["date"].dt.isocalendar().week.astype(str).str.zfill(2)
    df_weekly = (
        df_daily.groupby(["product_name", "node_name", "iso_year", "iso_week"])["value"]
        .sum()
        .reset_index()
    )
    # ** Add lot-based calculations **
    df_weekly["S_lot"] = df_weekly["value"].apply(lambda x: math.ceil(x / lot_size))
    df_weekly["lot_id_list"] = df_weekly.apply(generate_lot_ids, axis=1)
    return df_weekly, plan_range, plan_year_st
def generate_lot_ids(row):
    """
    Generate lot IDs based on the row's data.
    Parameters:
        row (pd.Series): A row from the DataFrame.
    Returns:
        list: List of generated lot IDs.
    """
    lot_count = row["S_lot"]
    # "_" を削除した形式で生成
    return [f"{row['node_name']}{row['iso_year']}{str(row['iso_week']).zfill(2)}{i+1:04d}" for i in range(lot_count)]
