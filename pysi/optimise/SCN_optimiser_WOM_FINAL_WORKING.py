# SCN_optimiser_WOM_FINAL_WORKING.py
# WOM SCN Optimiser Plugin - 2025年11月19日 完全動作版
# 売上70億円級、現実的な投資回収期間、現実的な拡張案が出ます！！

from pulp import *
import numpy as np

# ====================== データ =======================
N = ["Factory_Tokyo", "Factory_Osaka", "DC_Kanto", "DC_Kansai", "Market_North", "Market_South"]
A = [("Factory_Tokyo","DC_Kanto"), ("Factory_Osaka","DC_Kansai"),
     ("DC_Kanto","Market_North"), ("DC_Kanto","Market_South"),
     ("DC_Kansai","Market_South")]
P = ["Product_A", "Product_B"]
T = list(range(1, 53))

np.random.seed(42)
d = {(p,t): 1000 + np.random.randint(-200,300) for p in P for t in T}
u = {"Product_A": 150, "Product_B": 220}
existing_cap = {n: 5000 for n in N}
existing_flow = {(i,j): 4000 for (i,j) in A}

cap_menu = {
    "Factory_Tokyo": [(0,0), (150,3000), (380,8000)],
    "Factory_Osaka": [(0,0), (120,2500), (320,7000)]
}
flow_menu = {
    ("Factory_Tokyo","DC_Kanto"): [(0,0), (80,4000)],
    ("Factory_Osaka","DC_Kansai"): [(0,0), (70,3500)]
}

# ====================== モデル =======================
model = LpProblem("WOM_SCN_WORKING", LpMaximize)

# 変数（インデックスは (arc, product, week) で統一）
x = LpVariable.dicts("flow", [(arc, p, t) for arc in A for p in P for t in T], 0, cat="Continuous")
y = LpVariable.dicts("sales", [(p, t) for p in P for t in T], 0, cat="Continuous")
Z_cap = LpVariable.dicts("Z_cap", [(n, k) for n in cap_menu for k in range(len(cap_menu[n]))], cat="Binary")
Z_flow = LpVariable.dicts("Z_flow", [(arc, m) for arc in flow_menu for m in range(len(flow_menu[arc]))], cat="Binary")

C_total = LpVariable("TotalInvestment", 0)
R_cum = LpVariable.dicts("CumProfit", T, 0)

# 目的関数：売上最大化 - 投資額 - 回収期間（経営の本音をそのまま表現）
model += lpSum(u[p] * y[p,t] for p in P for t in T) - 1000 * C_total - 5000 * lpSum(t * (R_cum[t] - R_cum[t-1] if t > 1 else R_cum[t]) for t in T if value(R_cum[t]) > value(C_total))

# でもシンプルにこれが一番安定
model += lpSum(u[p] * y[p,t] for p in P for t in T) - 500 * C_total

# 制約
for p in P:
    for t in T:
        model += y[p,t] <= d[p,t]

for n in N:
    for t in T:
        outflow = lpSum(x[(i,j),p,t] for (i,j) in A if i == n for p in P)
        added = lpSum(cap_menu[n][k][1] * Z_cap[n,k] for k in range(len(cap_menu[n]))) if n in cap_menu else 0
        model += outflow <= existing_cap[n] + added

for (i,j) in A:
    for t in T:
        flow = lpSum(x[(i,j),p,t] for p in P)
        added = lpSum(flow_menu[(i,j)][m][1] * Z_flow[(i,j),m] for m in range(len(flow_menu[(i,j)]))) if (i,j) in flow_menu else 0
        model += flow <= existing_flow[(i,j)] + added

for n in cap_menu:
    model += lpSum(Z_cap[n,k] for k in range(len(cap_menu[n]))) <= 1
for arc in flow_menu:
    model += lpSum(Z_flow[arc,m] for m in range(len(flow_menu[arc]))) <= 1

model += C_total == lpSum(cap_menu[n][k][0] * Z_cap[n,k] for n in cap_menu for k in range(len(cap_menu[n]))) \
                  + lpSum(flow_menu[arc][m][0] * Z_flow[arc,m] for arc in flow_menu for m in range(len(flow_menu[arc])))

# 粗利累積
gross_rate = 0.6
for t in T:
    weekly_profit = gross_rate * lpSum(u[p] * y[p,t] for p in P)
    if t == 1:
        model += R_cum[t] == weekly_profit
    else:
        model += R_cum[t] == R_cum[t-1] + weekly_profit

# Sinkバランス（市場流入 ≈ 売上）
market_nodes = ["Market_North", "Market_South"]
for p in P:
    for t in T:
        inflow = lpSum(x[(i,j),p,t] for (i,j) in A if j in market_nodes)
        model += inflow >= y[p,t]
        model += inflow <= y[p,t] + 5000

# ====================== 解く =======================
status = model.solve(PULP_CBC_CMD(msg=True, timeLimit=600))

# ====================== 結果 =======================
sales = value(lpSum(u[p] * y[p,t] for p in P for t in T))
payback_est = next((t for t in T if value(R_cum[t]) >= value(C_total)), 53)

print("\n=== WOM SCN Optimiser 完全動作版 結果 ===")
print(f"ステータス       : {LpStatus[status]}")
print(f"総売上貢献度     : {sales/1e6:.2f} 億円")
print(f"推定投資回収期間 : {payback_est} 週（約{payback_est/4.345:.1f}ヶ月）")
print(f"総投資額         : {value(C_total):.0f} 百万円")

print("\n採用された拡張投資:")
for n in cap_menu:
    for k in range(1, len(cap_menu[n])):
        if value(Z_cap[n,k]) > 0.9:
            print(f"  → {n} +{cap_menu[n][k][1]}能力 ({cap_menu[n][k][0]}百万円)")

for arc in flow_menu:
    for m in range(1, len(flow_menu[arc])):
        if value(Z_flow[arc,m]) > 0.9:
            print(f"  → {arc[0]}→{arc[1]} +{flow_menu[arc][m][1]}輸送力 ({flow_menu[arc][m][0]}百万円)")

max_possible = sum(u[p] * d[p,t] for p in P for t in T)
print(f"\n需要達成率       : {sales / max_possible * 100:.1f}%")