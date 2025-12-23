# SCN_optimiser_WOM_REALDATA_FINAL.py
# あなたの会社のPSI Planner実データ完全準拠版 WOM SCN Optimiser（2025.11.20）

import pandas as pd
from pulp import *

# ====================== 1. CSV読み込み =======================
df_out = pd.read_csv("product_tree_outbound.csv")
df_in  = pd.read_csv("product_tree_inbound.csv")
df_p   = pd.read_csv("sku_P_month_data.csv")      # 供給パターン（MOM拠点の生産可能量）
df_s   = pd.read_csv("sku_S_month_data.csv")      # 市場需要（CS_拠点）
df_cost_out = pd.read_csv("sku_cost_table_outbound.csv")

# ====================== 2. 拠点・レーン抽出 =======================
nodes = set(df_out['Parent_node']) | set(df_out['Child_node'])
nodes |= set(df_in['Parent_node'])  | set(df_in['Child_node'])
N = sorted(list(nodes))

A = list(zip(df_out['Parent_node'], df_out['Child_node'])) + \
    list(zip(df_in['Parent_node'],  df_in['Child_node']))

# ====================== 3. 製品リスト =======================
P = sorted(set(df_s['product_name'].unique()) | set(df_p['product_name'].unique()))

# ====================== 4. 需要 d[p,t]（sku_S_month_data.csvから） =======================
d = {}
for _, row in df_s.iterrows():
    p = row['product_name']
    node = str(row['node_name'])
    if not node.startswith('CS_'): continue               # 最終市場のみ
    for m in range(1, 13):
        val = pd.to_numeric(row[f'm{m}'], errors='coerce')
        if pd.isna(val) or val == 0: continue
        weekly = val / 4.345
        start_week = (m-1)*4 + 1
        for w in range(4):
            week = start_week + w
            if week > 52: break
            d[(p, week)] = d.get((p, week), 0) + weekly

# ====================== 5. 単価 u[p] =======================
customer_nodes = [n for n in N if str(n).startswith('CS_')]
u = {}
for p in P:
    mask = (df_cost_out['product_name'] == p) & (df_cost_out['node_name'].isin(customer_nodes))
    price = df_cost_out[mask]['price_sales_shipped']
    u[p] = price.mean() if not price.empty else 100.0

# ====================== 6. 既存能力（process_capa合計） =======================
existing_cap = {n: 0 for n in N}
for n in N:
    out_cap = df_out[df_out['Child_node'] == n]['process_capa'].sum()
    in_cap  = df_in[df_in['Child_node'] == n]['process_capa'].sum()
    existing_cap[n] = out_cap + in_cap

# 輸送能力（当面無制限）
existing_flow = {(i,j): 1e9 for i,j in A}

# ====================== 7. MOM拠点の季節別供給上限（sku_P_month_data.csv） =======================
mom_supply_limit = {}   # (node, week) -> 上限値
for _, row in df_p.iterrows():
    p = row['product_name']
    node = str(row['node_name'])
    if not node.startswith('MOM'): continue
    for m in range(1, 13):
        val = pd.to_numeric(row[f'm{m}'], errors='coerce')
        if pd.isna(val) or val == 0: continue
        weekly = val / 4.345
        start_week = (m-1)*4 + 1
        for w in range(4):
            week = start_week + w
            if week > 52: break
            mom_supply_limit[(node, week)] = max(mom_supply_limit.get((node, week), 0), weekly)

# ====================== 8. 拡張メニュー（仮 → 実務部門に依頼予定） =======================
cap_menu = {
    "MOMJPN":       [(0,0), (150, 3000), (380, 8000)],
    "MOMCAL":       [(0,0), (150, 3000), (380, 8000)],
    "MOMGSJP":      [(0,0), (120, 2500), (320, 7000)],
    "MOMKosihikari":[(0,0), (120, 2500), (320, 7000)]
}
flow_menu = {}   # 今回は輸送拡張なし

# ====================== 9. モデル構築 =======================
model = LpProblem("WOM_REALDATA", LpMaximize)
T = list(range(1, 53))

x = LpVariable.dicts("flow", [(a,p,t) for a in A for p in P for t in T], lowBound=0, cat="Continuous")
y = LpVariable.dicts("sales", [(p,t) for p in P for t in T], lowBound=0, cat="Continuous")
Z_cap = LpVariable.dicts("Z_cap", [(n,k) for n in cap_menu for k in range(len(cap_menu[n]))], cat="Binary")

C_total = LpVariable("Invest", 0)
R_cum = LpVariable.dicts("CumProfit", T, 0)

# 目的関数
model += lpSum(u.get(p,100) * y[p,t] for p in P for t in T) - 500 * C_total

# 制約1：需要上限
for p in P:
    for t in T:
        model += y[p,t] <= d.get((p,t), 0)

# 制約2：ノード能力制約（MOM拠点は季節別供給上限を優先）
for n in N:
    for t in T:
        outflow = lpSum(x[(i,j),p,t] for (i,j) in A if i == n for p in P)
        base_cap = existing_cap[n]
        added_cap = lpSum(cap_menu[n][k][1] * Z_cap[(n,k)] for k in range(len(cap_menu[n])) if n in cap_menu else 0)
        seasonal_limit = mom_supply_limit.get((n,t), 1e9) if n.startswith('MOM') else 1e9
        model += outflow <= base_cap + added_cap + seasonal_limit - base_cap  # 季節上限を上乗せ

# 制約3：レーン能力
for (i,j) in A:
    for t in T:
        model += lpSum(x[(i,j),p,t] for p in P) <= existing_flow[(i,j)]

# 制約4：拡張排他・投資額
for n in cap_menu:
    model += lpSum(Z_cap[(n,k)] for k in range(len(cap_menu[n]))) <= 1

model += C_total == lpSum(cap_menu[n][k][0] * Z_cap[(n,k)] for n in cap_menu for k in range(len(cap_menu[n])))

# 制約5：粗利累積
for t in T:
    profit = 0.6 * lpSum(u.get(p,100) * y[p,t] for p in P)
    if t == 1:
        model += R_cum[t] == profit
    else:
        model += R_cum[t] == R_cum[t-1] + profit

# 制約6：Sinkバランス
market_nodes = [n for n in N if str(n).startswith('CS_')]
for p in P:
    for t in T:
        inflow = lpSum(x[(i,j),p,t] for (i,j) in A if j in market_nodes)
        model += inflow >= y[p,t]
        model += inflow <= y[p,t] + 10000

# ====================== 実行 =======================
print("あなたの会社のデータで最適化実行中...")
model.solve(PULP_CBC_CMD(msg=True, timeLimit=600))

# ====================== 結果 =======================
sales = value(lpSum(u.get(p,100) * y[p,t] for p in P for t in T))
payback = next((t for t in T if value(R_cum[t]) >= value(C_total)), 53)

print("\n=== WOM SCN Optimiser あなたの会社向け結果 ===")
print(f"総売上貢献度 : {sales/1e6:.2f} 億円")
print(f"総投資額     : {value(C_total):.0f} 百万円")
print(f"投資回収期間 : {payback} 週")

print("\n採用された拡張投資:")
for n in cap_menu:
    for k in range(1, len(cap_menu[n])):
        if value(Z_cap[(n,k)]) > 0.9:
            print(f"  → {n} +{cap_menu[n][k][1]}能力 (投資{cap_menu[n][k][0]}百万円)")

print("\n【Lot PSI Plannerに渡すnode_capacity】")
for n in cap_menu:
    added = sum(cap_menu[n][k][1] * value(Z_cap[(n,k)]) for k in range(len(cap_menu[n])))
    print(f"{n}: {existing_cap[n] + added}")