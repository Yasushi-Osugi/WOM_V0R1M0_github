# SCN_optimiser_WOM_REALDATA.py
# あなたの会社のPSI Planner実データ対応版 WOM SCN Optimiser（2025.11.20）
# CSVを読み込んで自動でN, A, P, d, u, existing_capを構築 → 最適化実行

import pandas as pd
import numpy as np
from pulp import *

# ====================== 1. CSV読み込み =======================
df_out = pd.read_csv("product_tree_outbound.csv")
df_in  = pd.read_csv("product_tree_inbound.csv")
df_p   = pd.read_csv("sku_P_month_data.csv")      # 需要予測
df_s   = pd.read_csv("sku_S_month_data.csv")      # 在庫（今回は未使用）
df_cost_out = pd.read_csv("sku_cost_table_outbound.csv")
df_geo = pd.read_csv("node_geo.csv")

# ====================== 2. 拠点・レーン抽出 =======================
nodes = set(df_out['Parent_node']) | set(df_out['Child_node'])
nodes |= set(df_in['Parent_node'])  | set(df_in['Child_node'])
N = sorted(list(nodes))

A_out = list(zip(df_out['Parent_node'], df_out['Child_node']))
A_in  = list(zip(df_in['Parent_node'],  df_in['Child_node']))
A = A_out + A_in

# ====================== 3. 製品・需要・単価 =======================
P = df_p['product_name'].unique().tolist()

# 月次需要 → 週次需要（1ヶ月 = 4.345週として均等割り）
d = {}
weeks_per_month = 4.345
for _, row in df_p.iterrows():
    p = row['product_name']
    node = row['node_name']   # 最終需要は市場ノードのみ
    if not node.startswith('CS_'): continue   # CS_で始まるノードのみ需要とする
    for m in range(1, 13):
        month_val = row[f'm{m}']
        if month_val == 0: continue
        weekly_val = month_val / weeks_per_month
        start_week = (m-1)*4 + 1
        for w in range(4):
            week = start_week + w
            if week > 52: break
            d[(p, week)] = d.get((p, week), 0) + weekly_val

# 単価（最終顧客ノードの販売価格）
customer_nodes = [n for n in N if n.startswith('CS_')]
u = {}
for p in P:
    prices = df_cost_out[(df_cost_out['product_name'] == p) &
                         (df_cost_out['node_name'].isin(customer_nodes))]['price_sales_shipped']
    u[p] = prices.mean() if not prices.empty else 100.0

# ====================== 4. 既存能力 =======================
existing_cap = {}
for n in N:
    capa_out = df_out[df_out['Child_node'] == n]['process_capa'].sum()
    capa_in  = df_in[df_in['Child_node'] == n]['process_capa'].sum()
    existing_cap[n] = capa_out + capa_in

# 輸送能力は仮に無制限（実データ化は別途）
existing_flow = {(i,j): 1e8 for i,j in A}

# ====================== 5. 拡張メニュー（仮置き）=======================
# ここは設備部・物流部に依頼して実データに置き換え
cap_menu = {
    "MOMJPN": [(0,0), (150, 3000), (380, 8000)],
    "MOMCAL": [(0,0), (150, 3000), (380, 8000)],
    "MOMGSJP": [(0,0), (120, 2500), (320, 7000)],
    "MOMKosihikari": [(0,0), (120, 2500), (320, 7000)]
}
flow_menu = {}  # 今回は輸送拡張なし（必要に応じて追加）

# ====================== 6. モデル構築 =======================
model = LpProblem("WOM_SCN_REALDATA", LpMaximize)

T = list(range(1, 53))

x = LpVariable.dicts("flow", [(arc, p, t) for arc in A for p in P for t in T], lowBound=0, cat="Continuous")
y = LpVariable.dicts("sales", [(p, t) for p in P for t in T], lowBound=0, cat="Continuous")
Z_cap = LpVariable.dicts("Z_cap", [(n,k) for n in cap_menu for k in range(len(cap_menu[n]))], cat="Binary")
Z_flow = {}  # 今回は未使用

C_total = LpVariable("TotalInvestment", lowBound=0)
R_cum = LpVariable.dicts("CumProfit", T, lowBound=0)

# 目的関数（売上最大 - 投資ペナルティ）
model += lpSum(u[p] * y[p,t] for p in P for t in T) - 500 * C_total

# 制約は前回と同じ（省略せず全記述）
for p in P:
    for t in T:
        model += y[p,t] <= d.get((p,t), 0)

for n in N:
    for t in T:
        outflow = lpSum(x[(i,j),p,t] for (i,j) in A if i==n for p in P if (i,j) in A)
        added = lpSum(cap_menu[n][k][1]*Z_cap[(n,k)] for k in range(len(cap_menu[n])) if n in cap_menu else 0)
        model += outflow <= existing_cap[n] + added

for (i,j) in A:
    for t in T:
        flow = lpSum(x[(i,j),p,t] for p in P)
        model += flow <= existing_flow[(i,j)]

for n in cap_menu:
    model += lpSum(Z_cap[(n,k)] for k in range(len(cap_menu[n]))) <= 1

model += C_total == lpSum(cap_menu[n][k][0]*Z_cap[(n,k)] for n in cap_menu for k in range(len(cap_menu[n])))

gross_rate = 0.6
for t in T:
    profit = gross_rate * lpSum(u[p] * y[p,t] for p in P)
    if t == 1:
        model += R_cum[t] == profit
    else:
        model += R_cum[t] == R_cum[t-1] + profit

# Sinkバランス
market_nodes = [n for n in N if n.startswith('CS_')]
for p in P:
    for t in T:
        inflow = lpSum(x[(i,j),p,t] for (i,j) in A if j in market_nodes)
        model += inflow >= y[p,t]
        model += inflow <= y[p,t] + 10000

# ====================== 実行 =======================
print("実データベースで最適化を開始します...")
model.solve(PULP_CBC_CMD(msg=True, timeLimit=600))

# ====================== 結果 =======================
sales = value(lpSum(u[p] * y[p,t] for p in P for t in T))
payback = next((t for t in T if value(R_cum[t]) >= value(C_total)), 53)

print("\n=== WOM SCN Optimiser 実データ版 結果 ===")
print(f"総売上貢献度 : {sales/1e6:.2f} 億円")
print(f"総投資額     : {value(C_total):.0f} 百万円")
print(f"投資回収期間 : {payback} 週")

print("\n採用された拡張投資:")
for n in cap_menu:
    for k in range(1, len(cap_menu[n])):
        if value(Z_cap[(n,k)]) > 0.9:
            print(f"  → {n} +{cap_menu[n][k][1]}能力 (投資{cap_menu[n][k][0]}百万円)")

print("\n【Lot PSI Plannerに渡す値】")
for n in cap_menu:
    added = sum(cap_menu[n][k][1] * value(Z_cap[(n,k)]) for k in range(len(cap_menu[n])))
    print(f"node_capacity['{n}'] = {existing_cap[n] + added}")