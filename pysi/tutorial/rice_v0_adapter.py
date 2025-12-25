# pysi/tutorial/rice_v0_adapter.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pandas as pd


@dataclass
class RiceV0Model:
    months: list[str]                 # ["2025-01", ...]
    demand: pd.Series                 # index=month, value=demand at MKT
    production: pd.Series             # index=month, value=production at MOM
    inv: pd.Series                    # computed inventory at DAD
    sales: pd.Series                  # actual sales (= demand fulfilled)
    shortage: pd.Series               # unmet demand
    capacity: pd.Series | None = None # optional capacity at MOM (for graph)


def load_rice_v0(data_dir: str | Path) -> RiceV0Model:
    data_dir = Path(data_dir)

    ts = pd.read_csv(data_dir / "rice_timeseries.csv")
    # normalize
    ts["month"] = ts["month"].astype(str)
    ts["node_name"] = ts["node_name"].astype(str)
    ts["item"] = ts["item"].astype(str)

    # months universe
    months = sorted(ts["month"].unique().tolist())

    def _series(node: str, item: str) -> pd.Series:
        s = (
            ts[(ts["node_name"] == node) & (ts["item"] == item)]
            .set_index("month")["value"]
            .reindex(months)
            .fillna(0.0)
            .astype(float)
        )
        return s

    demand = _series("MKT_RICE", "demand")
    production = _series("MOM_RICE", "production")

    # optional: capacity if you later add rows item="capacity"
    capacity = None
    if ((ts["node_name"] == "MOM_RICE") & (ts["item"] == "capacity")).any():
        capacity = _series("MOM_RICE", "capacity")

    # --- 追加：initial_inventory の読み取り（なければ 0） ---
    init_inv = 0.0
    if ((ts["node_name"] == "DAD_RICE") & (ts["item"] == "initial_inventory")).any():
        # 月列は何でも良いが、基本は先頭月に1行だけ置く想定
        init_inv_rows = ts[(ts["node_name"] == "DAD_RICE") & (ts["item"] == "initial_inventory")]
        init_inv = float(init_inv_rows["value"].iloc[0])

    # --- simplest PSI simulation (inventory buffer at DAD) ---
    inv = []
    sales = []
    shortage = []

    # ここが変更：inv_prev = 0.0 → init_inv
    inv_prev = init_inv
    for m in months:
        p = float(production.loc[m])
        d = float(demand.loc[m])

        inv_now_before_sales = inv_prev + p
        s = min(inv_now_before_sales, d)      # fulfill demand from inventory
        sh = max(d - s, 0.0)                  # unmet demand (shortage)
        inv_now = inv_now_before_sales - s    # ending inventory

        inv.append(inv_now)
        sales.append(s)
        shortage.append(sh)

        inv_prev = inv_now

    inv_s = pd.Series(inv, index=months, name="inventory")
    sales_s = pd.Series(sales, index=months, name="sales")
    shortage_s = pd.Series(shortage, index=months, name="shortage")

    return RiceV0Model(
        months=months,
        demand=demand.rename("demand"),
        production=production.rename("production"),
        inv=inv_s,
        sales=sales_s,
        shortage=shortage_s,
        capacity=capacity.rename("capacity") if capacity is not None else None,
    )
