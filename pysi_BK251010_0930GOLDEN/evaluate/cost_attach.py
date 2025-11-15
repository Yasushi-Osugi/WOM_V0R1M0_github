#pysi.evaluate.cost_attach.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, Iterable
COST_KEYS = [
    "price_sales_shipped","marketing_promotion","sales_admin_cost",
    "logistics_costs","warehouse_cost","direct_materials_costs",
    "prod_indirect_labor","prod_indirect_others","direct_labor_costs",
    "depreciation_others","manufacturing_overhead","purchase_total_cost",
    "customs_tariff_rate","tax_portion",
]
def _walk(root) -> Iterable[object]:
    st=[root]; seen=set()
    while st:
        n=st.pop()
        if id(n) in seen: continue
        seen.add(id(n)); yield n
        for c in getattr(n, "children", []) or []:
            st.append(c)
def _normalize(row: Dict[str, float]) -> Dict[str, float]:
    z = {k: float(row.get(k, 0.0) or 0.0) for k in COST_KEYS}
    z["SGA_total"] = z["marketing_promotion"] + z["sales_admin_cost"]
    if z.get("tax_portion", 0.0) == 0.0:
        z["tax_portion"] = z["direct_materials_costs"] * z.get("customs_tariff_rate", 0.0)
    z["cost_total"] = (
        z["marketing_promotion"] + z["sales_admin_cost"] + z["tax_portion"] +
        z["logistics_costs"] + z["warehouse_cost"] + z["direct_materials_costs"] +
        z["prod_indirect_labor"] + z["prod_indirect_others"] +
        z["direct_labor_costs"] + z["depreciation_others"]
    )
    z["profit"] = z["price_sales_shipped"] - z["cost_total"]
    return z
def build_cost_lookup_from_df(cost_df, product_col="product_name", node_col="node_name"):
    lut: Dict[tuple, Dict[str, float]] = {}
    for _, r in cost_df.iterrows():
        key = (str(r[product_col]).strip(), str(r[node_col]).strip())
        lut[key] = _normalize(r)
    return lut
def attach_cost_to_tree(root, product: str, cost_lut: Dict[tuple, Dict[str, float]], verbose=False) -> int:
    cnt = 0
    for n in _walk(root):
        key = (product, getattr(n, "name", ""))
        row = (cost_lut.get(key) or
               cost_lut.get((product, "*")) or
               cost_lut.get(("*", key[1])))
        #“lut” は look-up table（ルックアップテーブル）の略です。
        #キー → 事前計算（or 既知）値 への辞書/配列マップのこと。
        #cost_lut[(product_name, node_name)] -> {cs_* の各コスト項目}
        #cost_lookup: Dict[tuple, Dict[str, float]]（= “look-up table / LUT”）で、
        #キー (product_name, node_name) → 値 {cs_*: float, ...} を O(1) で引く辞書
        if row:
            # 1 lot あたりの cs_* を Node に張る
            n.cs_price_sales_shipped    = row["price_sales_shipped"]
            n.cs_marketing_promotion    = row["marketing_promotion"]
            n.cs_sales_admin_cost       = row["sales_admin_cost"]
            n.cs_logistics_costs        = row["logistics_costs"]
            n.cs_warehouse_cost         = row["warehouse_cost"]
            n.cs_direct_materials_costs = row["direct_materials_costs"]
            n.cs_prod_indirect_labor    = row["prod_indirect_labor"]
            n.cs_prod_indirect_others   = row["prod_indirect_others"]
            n.cs_direct_labor_costs     = row["direct_labor_costs"]
            n.cs_depreciation_others    = row["depreciation_others"]
            n.cs_manufacturing_overhead = row.get("manufacturing_overhead", 0.0)
            n.cs_purchase_total_cost    = row.get("purchase_total_cost", 0.0)
            n.customs_tariff_rate       = row.get("customs_tariff_rate", 0.0)
            n.cs_tax_portion            = row.get("tax_portion", 0.0)
            n.cs_SGA_total              = row["SGA_total"]
            n.cs_cost_total             = row["cost_total"]
            n.cs_profit                 = row["profit"]
            # evaluate_cost_models_v2 の互換：固定費キーを併置しておくと便利
            n.cs_fixed_cost = n.cs_SGA_total
            cnt += 1
        else:
            if verbose:
                print(f"[COST] missing cost row for {key}")
    #@STOP
    #return cnt
## pysi/evaluate/cost_attach.py
#def attach_cost_to_tree(root, product: str, cost_lut: Dict[tuple, Dict[str, float]], verbose=False) -> tuple[int, list[str]]:
    cnt = 0
    missing: list[str] = []
    for n in _walk(root):
        node_name = getattr(n, "name", "")
        key = (product, node_name)
        row = (cost_lut.get(key) or cost_lut.get((product, "*")) or cost_lut.get(("*", node_name)))
        if row:
            # …（既存の張り付け処理）…
            cnt += 1
        else:
            missing.append(node_name)
            if verbose:
                print(f"[COST] missing cost row for key={key}")
    return cnt, missing
