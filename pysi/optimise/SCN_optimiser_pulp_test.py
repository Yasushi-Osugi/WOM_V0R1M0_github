#pysi.optimise.SCN_optimiser_pulp_test.py
# SCN Optimiser Plugin - PuLP実装版 (すぐに動きます)
# Python 3.9+ , PuLPのみでOK  → pip install pulp だけで動く
# ソルバーはデフォルトCBC（高速）、またはHiGHSもおすすめ

#ACtion TODO
#1. 下記の `N`, `A`, `P`, `d`, `cap_menu`, `flow_menu` を実際の拠点・製品・需要データに置き換える
#2. 実行 → 10秒〜数分で最適ネットワーク拡張案＋投資回収期間が出る

from pulp import *
import numpy as np

# ====================== 1. データ入力（ここだけあなたが実データに置き換えてください）======================
N = ["Factory_Tokyo", "Factory_Osaka", "DC_Kanto", "DC_Kansai", "Market_North", "Market_South"]  # ノード例
A = [("Factory_Tokyo","DC_Kanto"), ("Factory_Osaka","DC_Kansai"), 
     ("DC_Kanto","Market_North"), ("DC_Kanto","Market_South"),
     ("DC_Kansai","Market_South")]  # レーン例
P = ["Product_A", "Product_B"]
T = list(range(1, 53))  # 1年分=52週でまずは検証（104週に後で拡張可）

# パラメータ例（実データに差し替え必須）
d = {(p,t): 1000 + np.random.randint(-200,300) for p in P for t in T}  # 需要
u = {"Product_A": 150, "Product_B": 220}  # 単価
existing_cap = {n: 5000 for n in N}        # 既存設備能力
existing_flow = {(i,j): 4000 for (i,j) in A}

# 拡張メニュー例（ここを実データにしてください！）
cap_menu = {                                   # (コスト[百万], 追加能力)
    "Factory_Tokyo": [(0,0), (150, 3000), (380, 8000)],
    "Factory_Osaka": [(0,0), (120, 2500), (320, 7000)]
}
flow_menu = {                                  # (コスト[百万], 追加輸送能力)
    ("Factory_Tokyo","DC_Kanto"): [(0,0), (80, 4000)],
    ("Factory_Osaka","DC_Kansai"): [(0,0), (70, 3500)]
}

# ====================== 2. PuLPモデル構築 ======================
model = LpProblem("SCN_Optimiser_WOM", LpMaximize)

# 変数
x = LpVariable.dicts("flow", (A, P, T), lowBound=0, cat="Continuous")     # 輸送量
y = LpVariable.dicts("sales", (P, T), lowBound=0, cat="Continuous")     # 実売上
Z_cap = LpVariable.dicts("Z_cap", [(n,k) for n in cap_menu for k in range(len(cap_menu[n]))], cat="Binary")
Z_flow = LpVariable.dicts("Z_flow", [(arc,m) for arc in flow_menu for m in range(len(flow_menu[arc]))], cat="Binary")

# 総投資額（補助変数）
C_total = LpVariable("Total_Investment", lowBound=0)

# 累積粗利と投資回収週
R_cum = LpVariable.dicts("CumProfit", T, lowBound=0)
delta = LpVariable.dicts("PaybackAchievedByWeek", T, cat="Binary")
payback_week = LpVariable("PaybackWeek", lowBound=1, upBound=52)   # 投資回収週

# 目的関数（売上最大化 ＋ 投資回収遅延に超巨大ペナルティ）
alpha = 1e8
M = 1e9
model += lpSum(u[p] * y[p,t] for p in P for t in T) - alpha * payback_week

# 制約
# 1. 需要上限
for p in P:
    for t in T:
        model += y[p,t] <= d[p,t]

# 2. ノード能力制約（簡略化版：全製品合計で週次同一能力と仮定）
for n in N:
    for t in T:
        outflow = lpSum(x[(i,j),p,t] for (i,j) in A if i==n for p in P)
        if n in cap_menu:
            added_cap = lpSum(cap_menu[n][k][1] * Z_cap[n,k] for k in range(len(cap_menu[n])))
            model += outflow <= existing_cap[n] + added_cap
        else:
            model += outflow <= existing_cap[n]

# 3. レーン能力制約
for (i,j) in A:
    for t in T:
        total_flow = lpSum(x[(i,j),p,t] for p in P)
        if (i,j) in flow_menu:
            added = lpSum(flow_menu[(i,j)][m][1] * Z_flow[(i,j),m] for m in range(len(flow_menu[(i,j)])))
            model += total_flow <= existing_flow[(i,j)] + added
        else:
            model += total_flow <= existing_flow[(i,j)]

# 4. 拡張メニューは1つのみ選択（排他）
for n in cap_menu:
    model += lpSum(Z_cap[n,k] for k in range(len(cap_menu[n]))) <= 1
for arc in flow_menu:
    model += lpSum(Z_flow[arc,m] for m in range(len(flow_menu[arc]))) <= 1

# 5. 総投資額計算
model += C_total == lpSum(cap_menu[n][k][0] * Z_cap[n,k] for n in cap_menu for k in range(len(cap_menu[n]))) \
                   + lpSum(flow_menu[arc][m][0] * Z_flow[arc,m] for arc in flow_menu for m in range(len(flow_menu[arc])))

# 6. 累積粗利（粗利率60%と仮定）
gross_rate = 0.6
for t in T:
    if t == 1:
        model += R_cum[t] == gross_rate * lpSum(u[p] * y[p,t] for p in P)
    else:
        model += R_cum[t] == R_cum[t-1] + gross_rate * lpSum(u[p] * y[p,t] for p in P)

# 7. 投資回収ロジック（Big-Mでpayback_weekを最小化）
for t in T:
    model += R_cum[t] - C_total >= -M * (1 - delta[t])
    model += R_cum[t] - C_total <= M * delta[t] - 0.0001
    model += payback_week >= t * delta[t]          # 回収完了した最も早い週
    model += payback_week <= t + 52 * (1 - delta[t])  # 未達なら上限外し

# ====================== 3. 解く ======================
model.solve(PULP_CBC_CMD(msg=1, timeLimit=300))   # 5分制限、必要に応じて外す

# ====================== 4. 結果出力 ======================
print(f"Status: {LpStatus[model.status]}")
print(f"総売上貢献度: {value(model.objective + alpha * value(payback_week)) / 1e6:.2f} 億円")
print(f"投資回収期間: {value(payback_week):.1f} 週（約{value(payback_week)/4.345:.1f}ヶ月）")
print(f"総投資額: {value(C_total):.1f} 百万円")

print("\n=== 採用された拡張メニュー ===")
for n in cap_menu:
    for k in range(len(cap_menu[n])):
        if value(Z_cap[n,k]) > 0.9:
            print(f"{n} → +{cap_menu[n][k][1]}能力（投資{cap_menu[n][k][0]}百万円）")


