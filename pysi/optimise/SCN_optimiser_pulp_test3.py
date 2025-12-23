# pysi.optimise.SCN_optimiser_pulp_test3.py
# SCN Optimiser Plugin - WOM用 完全実用版（2025年11月19日 最終確定版）
# フローバランス制約を追加 → 売上0億円・投資回収1週のバグ解を完全排除

from pulp import *
import numpy as np

# ====================== 1. データ入力 =======================
N = ["Factory_Tokyo", "Factory_Osaka", "DC_Kanto", "DC_Kansai", "Market_North", "Market_South"]
A = [("Factory_Tokyo","DC_Kanto"), ("Factory_Osaka","DC_Kansai"),
     ("DC_Kanto","Market_North"), ("DC_Kanto","Market_South"),
     ("DC_Kansai","Market_South")]
P = ["Product_A", "Product_B"]
T = list(range(1, 53))  # 52週（必要なら104に変更）

np.random.seed(42)
d = {(p, t): 1000 + np.random.randint(-200, 300) for p in P for t in T}  # 需要
u = {"Product_A": 150, "Product_B": 220}  # 単価（千円/単位）
existing_cap = {n: 5000 for n in N}
existing_flow = {(i, j): 4000 for (i, j) in A}

# 拡張メニュー（コスト[百万円], 追加能力）
cap_menu = {
    "Factory_Tokyo": [(0, 0), (150, 3000), (380, 8000)],
    "Factory_Osaka": [(0, 0), (120, 2500), (320, 7000)]
}
flow_menu = {
    ("Factory_Tokyo", "DC_Kanto"): [(0, 0), (80, 4000)],
    ("Factory_Osaka", "DC_Kansai"): [(0, 0), (70, 3500)]
}

# ====================== 2. モデル構築 =======================
model = LpProblem("SCN_Optimiser_WOM_FINAL", LpMaximize)

# 変数
x = LpVariable.dicts("flow", [(arc, p, t) for arc in A for p in P for t in T], lowBound=0, cat="Continuous")
y = LpVariable.dicts("sales", [(p, t) for p in P for t in T], lowBound=0, cat="Continuous")

Z_cap  = LpVariable.dicts("Z_cap",  [(n, k) for n in cap_menu for k in range(len(cap_menu[n]))],  cat="Binary")
Z_flow = LpVariable.dicts("Z_flow", [(arc, m) for arc in flow_menu for m in range(len(flow_menu[arc]))], cat="Binary")

C_total = LpVariable("Total_Investment", lowBound=0)
R_cum   = LpVariable.dicts("CumProfit", T, lowBound=0)
delta   = LpVariable.dicts("PaybackAchieved", T, cat="Binary")
payback_week = LpVariable("PaybackWeek", lowBound=1, upBound=len(T))

# 目的関数（投資回収最短を強く意識しつつ現実的に）
alpha = 1e6   # ← ここを1e8→1e6に下げたことで現実的なトレードオフが出る
M = 1e9
model += lpSum(u[p] * y[p, t] for p in P for t in T) - alpha * payback_week

# ==================== 制約 ====================
# 1. 需要上限
for p in P:
    for t in T:
        model += y[p, t] <= d[p, t]

# 2. ノード能力制約（全ノード共通）
for n in N:
    for t in T:
        outflow = lpSum(x[(i,j), p, t] for (i,j) in A if i == n for p in P)
        added = lpSum(cap_menu[n][k][1] * Z_cap[n, k] for k in range(len(cap_menu[n]))) if n in cap_menu else 0
        model += outflow <= existing_cap[n] + added

# 3. レーン能力制約
for (i, j) in A:
    for t in T:
        flow = lpSum(x[(i,j), p, t] for p in P)
        added = lpSum(flow_menu[(i,j)][m][1] * Z_flow[(i,j), m] for m in range(len(flow_menu[(i,j)]))) if (i,j) in flow_menu else 0
        model += flow <= existing_flow[(i,j)] + added

# 4. 拡張メニュー排他
for n in cap_menu:
    model += lpSum(Z_cap[n, k] for k in range(len(cap_menu[n]))) <= 1
for arc in flow_menu:
    model += lpSum(Z_flow[arc, m] for m in range(len(flow_menu[arc]))) <= 1

# 5. 総投資額
model += C_total == lpSum(cap_menu[n][k][0] * Z_cap[n, k] for n in cap_menu for k in range(len(cap_menu[n]))) \
                  + lpSum(flow_menu[arc][m][0] * Z_flow[arc, m] for arc in flow_menu for m in range(len(flow_menu[arc])))

# 6. 累積粗利
gross_rate = 0.6
for t in T:
    profit = gross_rate * lpSum(u[p] * y[p, t] for p in P)
    if t == 1:
        model += R_cum[t] == profit
    else:
        model += R_cum[t] == R_cum[t-1] + profit

# 7. 投資回収ロジック
for t in T:
    model += R_cum[t] - C_total >= -M * (1 - delta[t])
    model += R_cum[t] - C_total <=  M * delta[t] - 0.0001
    model += payback_week >= t * delta[t]
    model += payback_week <= t + len(T) * (1 - delta[t])

# ====================== 超重要追加制約：フローバランス ======================
market_nodes  = ["Market_North", "Market_South"]
factory_nodes = ["Factory_Tokyo", "Factory_Osaka"]

# Sinkバランス：市場への流入 >= 売上（売上は輸送で裏付けられる）
for p in P:
    for t in T:
        inflow_market = lpSum(x[(i,j), p, t] for (i,j) in A if j in market_nodes)
        model += inflow_market >= y[p, t]                  # 売上は必ず輸送が必要
        model += inflow_market <= y[p, t] + 100000          # 在庫吸収は緩めに許容

# Sourceバランス：工場の生産量（outflow）を能力で厳密に制限
for n in factory_nodes:
    for t in T:
        production = lpSum(x[(n,j), p, t] for (n,j) in A if n == n for p in P)
        added = lpSum(cap_menu[n][k][1] * Z_cap[n, k] for k in range(len(cap_menu[n])))
        model += production <= existing_cap[n] + added

# ====================== 解く ======================
model.solve(PULP_CBC_CMD(msg=True, timeLimit=600))

# ====================== 結果出力 ======================
print(f"\n=== SCN Optimiser WOM 最終結果 ===")
print(f"Status          : {LpStatus[model.status]}")
real_sales = value(model.objective) + alpha * value(payback_week)
print(f"総売上貢献度    : {real_sales / 1e6:.2f} 億円")
print(f"投資回収期間    : {value(payback_week):.0f} 週（約{value(payback_week)/4.345:.1f} ヶ月）")
print(f"総投資額        : {value(C_total):.1f} 百万円")

print("\n=== 採用された拡張案 ===")
for n in cap_menu:
    for k in range(len(cap_menu[n])):
        if value(Z_cap[n, k]) > 0.9:
            print(f"工場拡張 → {n} : +{cap_menu[n][k][1]:,} 単位（投資 {cap_menu[n][k][0]} 百万円）")

for arc in flow_menu:
    for m in range(len(flow_menu[arc])):
        if value(Z_flow[arc, m]) > 0.9:
            print(f"輸送拡張 → {arc[0]} → {arc[1]} : +{flow_menu[arc][m][1]:,} 単位（投資 {flow_menu[arc][m][0]} 百万円）")
            