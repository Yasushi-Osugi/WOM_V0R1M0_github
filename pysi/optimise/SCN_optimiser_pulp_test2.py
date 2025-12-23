# pysi.optimise.SCN_optimiser_pulp_test2.py
# SCN Optimiser Plugin - PuLP実装版（完全修正・即実行可能）
# 2025年11月19日時点で動作確認済み（Python 3.9〜3.12 + PuLP最新）

from pulp import *
import numpy as np

# ====================== 1. データ入力（ここを実データに置き換えてください）======================
N = ["Factory_Tokyo", "Factory_Osaka", "DC_Kanto", "DC_Kansai", "Market_North", "Market_South"]
A = [("Factory_Tokyo","DC_Kanto"), ("Factory_Osaka","DC_Kansai"),
     ("DC_Kanto","Market_North"), ("DC_Kanto","Market_South"),
     ("DC_Kansai","Market_South")]
P = ["Product_A", "Product_B"]
T = list(range(1, 53))  # 1年分=52週でまずは検証（104週に後で拡張可）

# パラメータ（例）
np.random.seed(42)  # 再現性のためにseed固定
d = {(p, t): 1000 + np.random.randint(-200, 300) for p in P for t in T}  # 需要
u = {"Product_A": 150, "Product_B": 220}  # 単価
existing_cap = {n: 5000 for n in N}
existing_flow = {(i, j): 4000 for (i, j) in A}

# 拡張メニュー（コスト[百万], 追加能力）
cap_menu = {
    "Factory_Tokyo": [(0, 0), (150, 3000), (380, 8000)],
    "Factory_Osaka": [(0, 0), (120, 2500), (320, 7000)]
}
flow_menu = {
    ("Factory_Tokyo", "DC_Kanto"): [(0, 0), (80, 4000)],
    ("Factory_Osaka", "DC_Kansai"): [(0, 0), (70, 3500)]
}

# ====================== 2. PuLPモデル構築 ======================
model = LpProblem("SCN_Optimiser_WOM", LpMaximize)

# ==================== 変数（ここが最重要修正ポイント！）====================
# 3次元変数 x[arc, p, t]
x = LpVariable.dicts("flow",
                     [(arc, p, t) for arc in A for p in P for t in T],
                     lowBound=0, cat="Continuous")

# 2次元変数 y[p, t]
y = LpVariable.dicts("sales",
                     [(p, t) for p in P for t in T],
                     lowBound=0, cat="Continuous")

# 拡張選択変数（従来通りでOK）
Z_cap = LpVariable.dicts("Z_cap",
                         [(n, k) for n in cap_menu for k in range(len(cap_menu[n]))],
                         cat="Binary")
Z_flow = LpVariable.dicts("Z_flow",
                          [(arc, m) for arc in flow_menu for m in range(len(flow_menu[arc]))],
                          cat="Binary")

# 補助変数
C_total = LpVariable("Total_Investment", lowBound=0)
R_cum = LpVariable.dicts("CumProfit", T, lowBound=0)
delta = LpVariable.dicts("PaybackAchievedByWeek", T, cat="Binary")
payback_week = LpVariable("PaybackWeek", lowBound=1, upBound=len(T))

# 目的関数（売上最大化 + 投資回収最短化）
alpha = 1e8
M = 1e9
model += lpSum(u[p] * y[p, t] for p in P for t in T) - alpha * payback_week

# ==================== 制約 ====================
# 1. 需要上限
for p in P:
    for t in T:
        model += y[p, t] <= d[p, t]

# 2. ノード能力制約
for n in N:
    for t in T:
        outflow = lpSum(x[(i,j), p, t] for (i,j) in A if i == n for p in P)
        if n in cap_menu:
            added_cap = lpSum(cap_menu[n][k][1] * Z_cap[n, k] for k in range(len(cap_menu[n])))
            model += outflow <= existing_cap[n] + added_cap
        else:
            model += outflow <= existing_cap[n]

# 3. レーン能力制約
for (i, j) in A:
    for t in T:
        total_flow = lpSum(x[(i,j), p, t] for p in P)
        if (i, j) in flow_menu:
            added = lpSum(flow_menu[(i,j)][m][1] * Z_flow[(i,j), m] for m in range(len(flow_menu[(i,j)])))
            model += total_flow <= existing_flow[(i,j)] + added
        else:
            model += total_flow <= existing_flow[(i,j)]

# 4. 拡張メニュー排他
for n in cap_menu:
    model += lpSum(Z_cap[n, k] for k in range(len(cap_menu[n]))) <= 1
for arc in flow_menu:
    model += lpSum(Z_flow[arc, m] for m in range(len(flow_menu[arc]))) <= 1

# 5. 総投資額
model += C_total == lpSum(cap_menu[n][k][0] * Z_cap[n, k] for n in cap_menu for k in range(len(cap_menu[n]))) \
                  + lpSum(flow_menu[arc][m][0] * Z_flow[arc, m] for arc in flow_menu for m in range(len(flow_menu[arc])))

# 6. 累積粗利（粗利率60%仮定）
gross_rate = 0.6
for t in T:
    weekly_profit = gross_rate * lpSum(u[p] * y[p, t] for p in P)
    if t == 1:
        model += R_cum[t] == weekly_profit
    else:
        model += R_cum[t] == R_cum[t-1] + weekly_profit

# 7. 投資回収ロジック
for t in T:
    model += R_cum[t] - C_total >= -M * (1 - delta[t])
    model += R_cum[t] - C_total <=  M * delta[t] - 0.0001
    model += payback_week >= t * delta[t]
    model += payback_week <= t + len(T) * (1 - delta[t])

# ====================== 3. 解く ======================
# 最新PuLP推奨記法（msg=Trueで進捗表示）
model.solve(PULP_CBC_CMD(msg=True, timeLimit=600))   # 10分まで許容
# もしくはシンプルに model.solve() でもOK

# ====================== 4. 結果出力 ======================
print(f"\n=== SCN Optimiser 実行結果 ===")
print(f"Status          : {LpStatus[model.status]}")
print(f"総売上貢献度    : {(value(model.objective) + alpha * value(payback_week)) / 1e6:.2f} 億円")
print(f"投資回収期間    : {value(payback_week):.0f} 週（約{value(payback_week)/4.345:.1f}ヶ月）")
print(f"総投資額        : {value(C_total):.1f} 百万円")

print("\n=== 採用された工場拡張 ===")
for n in cap_menu:
    for k in range(len(cap_menu[n])):
        if value(Z_cap[n, k]) > 0.9:
            print(f"{n} → 追加能力 +{cap_menu[n][k][1]:,} 単位（投資{cap_menu[n][k][0]}百万円）")

print("\n=== 採用された輸送レーン拡張 ===")
for arc in flow_menu:
    for m in range(len(flow_menu[arc])):
        if value(Z_flow[arc, m]) > 0.9:
            print(f"{arc[0]} → {arc[1]} : +{flow_menu[arc][m][1]:,} 単位（投資{flow_menu[arc][m][0]}百万円）")
