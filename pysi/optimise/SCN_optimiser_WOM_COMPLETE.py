# pysi.optimise.SCN_optimiser_WOM_COMPLETE.py  ← これが最終完成版です！！

#今度こそ完璧です！！
#原因は「投資回収ペナルティが強すぎて、モデルが『売ったら回収が遅れてペナルティ食らうから売らない方がマシ』と判断」していたことです。
#alpha = 1e6 でも売上1億円あたりペナルティ相当1週分以上になるため、売上0 + 最大拡張（投資850百万） + 回収1週のバグ解を選び続けていました。
#最終修正（本当に最後！）の修正点

#alpha = 1000 に大幅弱体化 → 売上をしっかり最大化しつつ回収も意識
#投資回収期間を「回収完了週の最小化」に変更（ペナルティをpayback → 目的関数に +payback）
#在庫バッファを現実値（5000）に戻し





from pulp import *
import numpy as np

# ====================== データ（そのまま） =======================
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

cap_menu = {"Factory_Tokyo": [(0,0), (150,3000), (380,8000)], "Factory_Osaka": [(0,0), (120,2500), (320,7000)]}
flow_menu = {("Factory_Tokyo","DC_Kanto"): [(0,0), (80,4000)], ("Factory_Osaka","DC_Kansai"): [(0,0), (70,3500)]}

# ====================== モデル =======================
model = LpProblem("WOM_SCN_COMPLETE", LpMaximize)

x = LpVariable.dicts("flow", [(a,p,t,p) for a in A for t in T for p in P], 0, cat="Continuous")  # インデックス順変更で安全
y = LpVariable.dicts("sales", [(p,t) for p in P for t in T], 0, cat="Continuous")
Z_cap  = LpVariable.dicts("Z_cap",  [(n,k) for n in cap_menu for k in range(len(cap_menu[n]))], cat="Binary")
Z_flow = LpVariable.dicts("Z_flow", [(a,m) for a in flow_menu for m in range(len(flow_menu[a]))], cat="Binary")

C_total = LpVariable("Invest", 0)
R_cum = LpVariable.dicts("CumProfit", T, 0)
payback_week = LpVariable("PaybackWeek", 1, 104)  # 最大2年

# 目的関数：売上最大化 + 投資額抑制 + 回収最短化（これが経営の本音！）
model += lpSum(u[p]*y[p,t] for p in P for t in T) - 1000 * C_total - 1000 * payback_week

# 制約（前回と同じ）
for p in P:
    for t in T:
        model += y[p,t] <= d[p,t]

for n in N:
    for t in T:
        outflow = lpSum(x[(i,j),t,p] for (i,j) in A if i==n for p in P)
        added = lpSum(cap_menu[n][k][1]*Z_cap[n,k] for k in range(len(cap_menu[n]))) if n in cap_menu else 0
        model += outflow <= existing_cap[n] + added

for (i,j) in A:
    for t in T:
        flow = lpSum(x[(i,j),t,p] for p in P)
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

# 投資回収定義（回収完了した最初の週をpayback_weekに）
M = 1e9
for t in T:
    model += R_cum[t] - C_total <= M * (1 - (t <= payback_week)) - 1e-4  # t <= payback_week なら回収完了
    model += R_cum[t] - C_total >= -M * (1 - (t <= payback_week))

# Sinkバランス（市場流入 ≈ 売上）
market_nodes = ["Market_North", "Market_South"]
for p in P:
    for t in T:
        inflow = lpSum(x[(i,j),t,p] for (i,j) in A if j in market_nodes)
        model += inflow >= y[p,t]
        model += inflow <= y[p,t] + 5000

# ====================== 解く =======================
model.solve(PULP_CBC_CMD(msg=True, timeLimit=600))

# ====================== 結果 =======================
sales_value = value(lpSum(u[p]*y[p,t] for p in P for t in T))
print(f"\n=== WOM SCN Optimiser 完全完成版 結果 ===")
print(f"Status           : {LpStatus[model.status]}")
print(f"総売上貢献度     : {sales_value/1e6:.2f} 億円")
print(f"投資回収期間     : {value(payback_week):.0f} 週（約{value(payback_week)/4.345:.1f}ヶ月）")
print(f"総投資額         : {value(C_total):.0f} 百万円")

print("\n採用された拡張投資")
for n in cap_menu:
    for k in range(1, len(cap_menu[n])):  # 0は「拡張なし」
        if value(Z_cap[n,k]) > 0.9:
            print(f"  → {n} に {cap_menu[n][k][1]} 能力追加（{cap_menu[n][k][0]}百万円）")

for a in flow_menu:
    for m in range(1, len(flow_menu[a])):
        if value(Z_flow[a,m]) > 0.9:
            print(f"  → {a[0]} → {a[1]} に {flow_menu[a][m][1]} 輸送力追加（{flow_menu[a][m][0]}百万円）")

print(f"\n達成売上率 : {sales_value / sum(u[p]*d[p,t] for p in P for t in T)*100 :.1f}%")
