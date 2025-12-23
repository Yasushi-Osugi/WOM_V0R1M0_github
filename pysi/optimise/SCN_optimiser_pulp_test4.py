# pysi.optimise.SCN_optimiser_test4.py
# これがWOMのSCN Optimiser 本当に最終完成版です！！

from pulp import *
import numpy as np

# ====================== データ入力 =======================
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

# ====================== モデル構築 =======================
model = LpProblem("SCN_WOM_PERFECT", LpMaximize)

x = LpVariable.dicts("flow", [(a,p,t) for a in A for p in P for t in T], 0, cat="Continuous")
y = LpVariable.dicts("sales", [(p,t) for p in P for t in T], 0, cat="Continuous")
Z_cap  = LpVariable.dicts("Z_cap",  [(n,k) for n in cap_menu for k in range(len(cap_menu[n]))], cat="Binary")
Z_flow = LpVariable.dicts("Z_flow", [(a,m) for a in flow_menu for m in range(len(flow_menu[a]))], cat="Binary")

C_total = LpVariable("Invest", 0)
R_cum = LpVariable.dicts("CumProfit", T, 0)
delta = LpVariable.dicts("Recovered", T, cat="Binary")
payback = LpVariable("PaybackWeek", 1, len(T))

alpha = 1e6
model += lpSum(u[p]*y[p,t] for p in P for t in T) - alpha * payback

# 制約（省略部分は前回と同じ）
for p in P:
    for t in T:
        model += y[p,t] <= d[p,t]

for n in N:
    for t in T:
        outflow = lpSum(x[(i,j),p,t] for (i,j) in A if i==n for p in P)
        added = lpSum(cap_menu[n][k][1]*Z_cap[n,k] for k in range(len(cap_menu[n]))) if n in cap_menu else 0
        model += outflow <= existing_cap[n] + added

for (i,j) in A:
    for t in T:
        flow = lpSum(x[(i,j),p,t] for p in P)
        added = lpSum(flow_menu[(i,j)][m][1]*Z_flow[(i,j),m] for m in range(len(flow_menu[(i,j)]))) if (i,j) in flow_menu else 0
        model += flow <= existing_flow[(i,j)] + added

for n in cap_menu:  model += lpSum(Z_cap[n,k] for k in range(len(cap_menu[n]))) <= 1
for a in flow_menu: model += lpSum(Z_flow[a,m] for m in range(len(flow_menu[a]))) <= 1

model += C_total == lpSum(cap_menu[n][k][0]*Z_cap[n,k] for n in cap_menu for k in range(len(cap_menu[n]))) \
                  + lpSum(flow_menu[a][m][0]*Z_flow[a,m] for a in flow_menu for m in range(len(flow_menu[a])))

gross_rate = 0.6
for t in T:
    profit = gross_rate * lpSum(u[p]*y[p,t] for p in P)
    if t == 1:
        model += R_cum[t] == profit
    else:
        model += R_cum[t] == R_cum[t-1] + profit

M = 1e9
for t in T:
    model += R_cum[t] - C_total >= -M*(1-delta[t])
    model += R_cum[t] - C_total <=  M*delta[t] - 1e-4
    model += payback >= t * delta[t]
    model += payback <= t + 52*(1-delta[t])

# ========== 最終修正：正しいフローバランス ==========
market_nodes = ["Market_North", "Market_South"]
factory_nodes = ["Factory_Tokyo", "Factory_Osaka"]

# 1. Sinkバランス：市場への流入 >= 売上（売上は輸送で裏付けられる）
for p in P:
    for t in T:
        inflow = lpSum(x[(i,j),p,t] for (i,j) in A if j in market_nodes)
        model += inflow >= y[p,t]
        model += inflow <= y[p,t] + 1000   # 在庫緩衝は最小限

# 2. Sourceバランス：工場の生産量（outflow）を正しくカウント
for n in factory_nodes:
    for t in T:
        production = lpSum(x[(i,j),p,t] for (i,j) in A if i == n for p in P)  # ← これが正しい！
        added = lpSum(cap_menu[n][k][1]*Z_cap[n,k] for k in range(len(cap_menu[n])))
        model += production <= existing_cap[n] + added

# ========== 解く ==========
model.solve(PULP_CBC_CMD(msg=True, timeLimit=600))

# ========== 結果 ==========
print("Status:", LpStatus[model.status])
sales = value(lpSum(u[p]*y[p,t] for p in P for t in T))
print(f"総売上貢献度: {sales/1e6:.2f}億円")
print(f"投資回収期間: {value(payback):.0f}週 ({value(payback)/4.345:.1f}ヶ月)")
print(f"総投資額: {value(C_total):.0f}百万円")

print("\n採用拡張:")
for n in cap_menu:
    for k in range(len(cap_menu[n])):
        if value(Z_cap[n,k]) > 0.9:
            print(f"  {n} +{cap_menu[n][k][1]}能力 (投資{cap_menu[n][k][0]}百万円)")

for a in flow_menu:
    for m in range(len(flow_menu[a])):
        if value(Z_flow[a,m]) > 0.9:
            print(f"  {a[0]}→{a[1]} +{flow_menu[a][m][1]}輸送力 (投資{flow_menu[a][m][0]}百万円)")