# pysi/plugins/capacity_provider_monthly_csv/plugin.py
from __future__ import annotations

import os
import logging
from typing import Any, Dict

import pandas as pd

from pysi.core.hooks.core import action
from pysi.plan.demand_generate import (
    _normalize_monthly_demand_df_sku,
    convert_monthly_to_weekly_sku,
)
from pysi.plan.operations import _build_iso_week_index_map

logger = logging.getLogger(__name__)

DEFAULT_CAPA_CSV_CANDIDATES = [
    "sku_P_month_data.csv",
    "sku_P_month.csv",
    "sku_P_data.csv",
]

def _pick_first_existing(data_dir: str, candidates: list[str]) -> str | None:
    for fn in candidates:
        p = os.path.join(data_dir, fn)
        if os.path.exists(p):
            return p
    return None


def normalize_mom_name(node_name: str) -> str:
    """
    Normalize capacity node_name to MOMxxx.
    - If already MOMxxx, keep.
    - If DADxxx appears by legacy data definition, convert to MOMxxx.
    """
    if node_name is None:
        return node_name
    s = str(node_name)
    if s.startswith("MOM"):
        return s
    if s.startswith("DAD"):
        return "MOM" + s[3:]
    return s


@action("pipeline:before_planning", priority=20)
def capacity_provider_monthly_csv(ctx: Dict[str, Any], root: Any = None, env: Any = None):
    """
    Build env.weekly_capability from monthly capacity CSV.
    Output:
      - env.weekly_capability[product][node_name] = [cap_lot per week]
      - env.weekly_capability_df (debug)
    """
    if env is None:
        env = ctx.get("env")
    if env is None:
        logger.warning("[CapacityProvider] env not found in ctx")
        return

    data_dir = getattr(env, "directory", None) or ctx.get("data_dir")
    if not data_dir:
        logger.warning("[CapacityProvider] data_dir not found")
        return

    csv_path = _pick_first_existing(data_dir, DEFAULT_CAPA_CSV_CANDIDATES)
    if not csv_path:
        logger.info("[CapacityProvider] no capacity monthly csv found (skip)")
        return

    # --- read monthly CSV
    df_m = pd.read_csv(csv_path)

    # monthly schema normalize (same as demand)
    df_m_norm = _normalize_monthly_demand_df_sku(df_m)

    # lot_size lookup: env has variant funcs; use the most recent "lot_size_lookup" if present
    lot_size_lookup = getattr(env, "lot_size_lookup", None)
    if not callable(lot_size_lookup):
        # fallback: some versions have _lot_size_lookup
        lot_size_lookup = getattr(env, "_lot_size_lookup", None)
    if not callable(lot_size_lookup):
        raise RuntimeError("lot_size_lookup function not found on env")

    # plan year range: use env authoritative settings
    plan_year_st = int(getattr(env, "plan_year_st"))
    plan_range   = int(getattr(env, "plan_range"))
    year_st = plan_year_st
    year_end = plan_year_st + plan_range - 1

    # --- monthly -> weekly (reuse demand converter)
    # returns weekly df with columns including: iso_year, iso_week, value, lot_size, S_lot, lot_id_list ...
    df_w = convert_monthly_to_weekly_sku(
        df_m_norm,
        lot_size_lookup=lot_size_lookup,
        year_st=year_st,
        year_end=year_end,
    )

    # Rename to "capability" semantics
    df_w = df_w.rename(columns={
        "value": "cap_qty",
        "S_lot": "cap_lot",
    })

    # week index map: authoritative "real ISO weeks"
    week_index_map, weeks_count = _build_iso_week_index_map(year_st, year_end)

    # attach week_index
    df_w["week_index"] = df_w.apply(
        lambda r: week_index_map.get((int(r["iso_year"]), int(r["iso_week"])), None),
        axis=1
    )
    df_w = df_w[df_w["week_index"].notna()].copy()
    df_w["week_index"] = df_w["week_index"].astype(int)

    # ensure int
    df_w["cap_lot"] = df_w["cap_lot"].fillna(0).astype(int)

    # --- Normalize node_name to MOMxxx (IMPORTANT)
    if "node_name" in df_w.columns:
        df_w["node_name"] = df_w["node_name"].apply(normalize_mom_name)

    # --- build env.weekly_capability dict
    weekly_cap: dict[str, dict[str, list[int]]] = {}

    # NOTE: node_name is already normalized to MOMxxx here
    for (prod, node), g in df_w.groupby(["product_name", "node_name"], dropna=False):
        arr = [0] * weeks_count
        for _, row in g.iterrows():
            w = int(row["week_index"])
            # 週のcapは「代入」ではなく「加算」の方が安全（複数行が同週に乗る可能性）
            arr[w] += int(row["cap_lot"])
        weekly_cap.setdefault(str(prod), {})[str(node)] = arr

    setattr(env, "weekly_capability", weekly_cap)
    setattr(env, "weekly_capability_df", df_w)

    logger.info(
        "[CapacityProvider] loaded monthly capacity -> weekly_capability: file=%s, products=%d",
        os.path.basename(csv_path),
        len(weekly_cap),
    )
