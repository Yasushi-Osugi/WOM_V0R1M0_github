# pysi/plugins/capacity_provider_monthly_csv/plugin.py
from __future__ import annotations

import calendar
import logging
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from pysi.core.hooks.core import action

logger = logging.getLogger(__name__)


def normalize_mom_name(node_name: str) -> str:
    """Normalize MOM/DAD naming: DADxxx -> MOMxxx (leave others as-is)."""
    if not node_name:
        return node_name
    if node_name.startswith("MOM"):
        return node_name
    if node_name.startswith("DAD"):
        return "MOM" + node_name[3:]
    return node_name


DEFAULT_FILENAME = "sku_P_month_data.csv"


def _weeks_count(year_st: int, year_end: int) -> int:
    # year_st..year_end inclusive → 52 weeks base (WOM側の前提に合わせる)
    return (year_end - year_st + 1) * 52


def _month_to_week_index(year: int, month: int, year_st: int) -> int:
    # 簡易: 1ヶ月=4週換算 + 年オフセット
    # 例: year_stの1月→0, 2月→4, ..., 12月→44
    y_off = (year - year_st) * 52
    m_off = (month - 1) * 4
    return y_off + m_off


@action("pipeline:before_planning", priority=20)
def capacity_provider_monthly_csv(**ctx):
    """
    Build env.weekly_capability from monthly capacity CSV.

    Output:
      - env.weekly_capability[product][MOMxxx] = [cap_lot per week]
      - env.weekly_capability_df (debug)
    """
    # HookBus calls plugins as cb.fn(**ctx). So we accept **ctx and extract fields here.
    env = ctx.get("env", None)
    root = ctx.get("root", None)

    if env is None:
        env = ctx.get("env")
    if env is None:
        raise RuntimeError("capacity_provider_monthly_csv: env is required in ctx")

    data_dir = Path(ctx.get("data_dir") or ctx.get("csv") or ctx.get("csv_dir") or "data")
    filename = ctx.get("capacity_monthly_csv") or DEFAULT_FILENAME
    csv_path = data_dir / filename

    if not csv_path.exists():
        logger.warning("[CapacityProvider] monthly capacity csv not found: %s (skip)", csv_path)
        return

    # year range
    year_st = int(getattr(env, "year_st", 2024))
    year_end = int(getattr(env, "year_end", 2026))
    weeks_count = int(getattr(env, "weeks_count", 0) or 0) or _weeks_count(year_st, year_end)

    # load
    df = pd.read_csv(csv_path)
    required_cols = {"product_name", "node_name", "year", "m1", "m2", "m3", "m4", "m5", "m6",
                     "m7", "m8", "m9", "m10", "m11", "m12"}
    miss = required_cols - set(df.columns)
    if miss:
        raise ValueError(f"capacity_provider_monthly_csv: missing columns in {csv_path}: {sorted(miss)}")

    # normalize types
    df["product_name"] = df["product_name"].astype(str)
    df["node_name"] = df["node_name"].astype(str)
    df["year"] = df["year"].astype(int)

    # melt (m1..m12) -> rows
    mcols = [f"m{i}" for i in range(1, 13)]
    df_long = df.melt(
        id_vars=["product_name", "node_name", "year"],
        value_vars=mcols,
        var_name="month",
        value_name="cap_lot",
    )
    df_long["month"] = df_long["month"].str.replace("m", "", regex=False).astype(int)
    df_long["cap_lot"] = pd.to_numeric(df_long["cap_lot"], errors="coerce").fillna(0).astype(float)

    # weekly allocation: 1ヶ月=4週の等分配（WOMの簡易教材前提）
    weekly_rows = []
    for _, r in df_long.iterrows():
        prod = str(r["product_name"])
        node = str(r["node_name"])
        year = int(r["year"])
        month = int(r["month"])
        cap_m = float(r["cap_lot"])

        # 0はスキップ
        if cap_m == 0:
            continue

        w0 = _month_to_week_index(year, month, year_st)
        # 4週に均等割り（端数は float のまま → 後で int に寄せる）
        cap_w = cap_m / 4.0
        for k in range(4):
            w = w0 + k
            if 0 <= w < weeks_count:
                weekly_rows.append((prod, node, w, cap_w))

    if not weekly_rows:
        logger.info("[CapacityProvider] no capacity rows >0 in %s (skip)", csv_path)
        env.weekly_capability = {}
        env.weekly_capability_df = pd.DataFrame(columns=["product", "node", "week", "cap_lot"])
        return

    dfw = pd.DataFrame(weekly_rows, columns=["product", "node", "week", "cap_lot"])
    # 四捨五入して int 化（lot単位）
    dfw["cap_lot"] = dfw["cap_lot"].round().astype(int)

    # build env.weekly_capability[product][MOMxxx] = [..]
    weekly_cap: Dict[str, Dict[str, list]] = {}
    for (prod, node), g in dfw.groupby(["product", "node"], as_index=False):
        arr = [0] * weeks_count
        for _, row in g.iterrows():
            w = int(row["week"])
            arr[w] += int(row["cap_lot"])  # ★加算（同一週に複数行が来ても潰さない）

        # ★DADで来てもMOMへ寄せる
        mom = normalize_mom_name(str(node))
        weekly_cap.setdefault(str(prod), {}).setdefault(mom, [0] * weeks_count)
        weekly_cap[str(prod)][mom] = arr

    env.weekly_capability = weekly_cap
    env.weekly_capability_df = dfw

    logger.info(
        "[CapacityProvider] weekly capability ready: products=%d src=%s",
        len(weekly_cap),
        csv_path.name,
    )
