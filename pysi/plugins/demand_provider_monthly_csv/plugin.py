#pysi/plugins/demand_provider_monthly_csv/plugin.py

from __future__ import annotations

import os
import logging
import pandas as pd

from pysi.core.hooks.core import action
from pysi.plan.demand_generate import (
    _normalize_monthly_demand_df_sku,
    convert_monthly_to_weekly_sku,
)

logger = logging.getLogger(__name__)


def _traverse(root):
    st = [root]
    while st:
        n = st.pop()
        yield n
        st.extend(getattr(n, "children", []) or [])


def _make_lot_size_lookup(env):
    """
    lot_size_lookup(product_name, node_name) -> int
    plan_env_main.py と同じ思想：prod_tree_dict_OT から leaf(node_name) を見つけて lot_size を返す
    """
    def _lot_size_lookup(prod_name: str, node_name: str) -> int:
        root = getattr(env, "prod_tree_dict_OT", {}).get(prod_name)
        if root is None:
            return 1
        fn = getattr(root, "find_node", None)
        if callable(fn):
            nd = fn(lambda n: getattr(n, "name", None) == node_name)
            return int(getattr(nd, "lot_size", 1) or 1) if nd else 1
        for n in _traverse(root):
            if getattr(n, "name", None) == node_name:
                return int(getattr(n, "lot_size", 1) or 1)
        return 1

    return _lot_size_lookup


@action("pipeline:before_planning", priority=10)
def demand_provider_monthly_csv_to_weekly(env=None, root=None, **kwargs):
    """
    正本仕様：
      入力: sku_S_month_data.csv (優先) / S_month_data.csv
      出力: env.weekly_demand (dict[product_name]=df_weekly_sub)
            env.weekly_demand_df (df_weekly all)
            env.plan_range / env.plan_year_st
    週次DFの列は convert_monthly_to_weekly_sku() の正本仕様：
      product_name, node_name, iso_year, iso_week, value, lot_size, S_lot, lot_id_list ...
    """
    if env is None:
        logger.warning("[DemandProvider] env is None -> skip")
        return

    directory = getattr(env, "directory", None) or getattr(env, "load_directory", None)
    if not directory:
        raise RuntimeError("[DemandProvider] env.directory (or load_directory) is not set")

    new_csv = os.path.join(directory, "sku_S_month_data.csv")
    old_csv = os.path.join(directory, "S_month_data.csv")
    month_csv = new_csv if os.path.exists(new_csv) else old_csv

    if not os.path.exists(month_csv):
        logger.info("[DemandProvider] monthly csv not found: %s / %s", new_csv, old_csv)
        env.weekly_demand = {}
        env.weekly_demand_df = pd.DataFrame()
        return

    # 月次読込
    df_month_raw = pd.read_csv(month_csv, encoding="utf-8-sig")

    # sampleを見た限り year が float の場合があるので、ここで確実にint化
    if "year" in df_month_raw.columns:
        df_month_raw["year"] = pd.to_numeric(df_month_raw["year"], errors="coerce").fillna(0).astype(int)

    # 正規化（列名ゆれ吸収）
    df_month = _normalize_monthly_demand_df_sku(df_month_raw)

    lot_size_lookup = _make_lot_size_lookup(env)

    # ★ 正本：df_weekly, plan_range, plan_year_st
    df_weekly, plan_range, plan_year_st = convert_monthly_to_weekly_sku(df_month, lot_size_lookup)

    env.plan_range = int(plan_range)
    env.plan_year_st = int(plan_year_st)

    # dict保持（あなたの方針）
    weekly_dict = {}
    if not df_weekly.empty:
        for prod, g in df_weekly.groupby("product_name"):
            weekly_dict[str(prod)] = g.reset_index(drop=True)

    env.weekly_demand = weekly_dict
    env.weekly_demand_df = df_weekly

    logger.info("[DemandProvider] weekly demand ready: products=%d rows=%d src=%s",
                len(weekly_dict), len(df_weekly), os.path.basename(month_csv))

    # init は「需要生成を剥がした版」にしておく前提
    if hasattr(env, "init_psi_spaces_and_demand") and callable(env.init_psi_spaces_and_demand):
        env.init_psi_spaces_and_demand()

