
#250114gui_app.py
# gui/app.py
# ********************************
# library import
# ********************************
import os
import shutil
import threading
import gc
# ********************************
# DB
# ********************************
import pandas as pd
import sqlite3
# ********************************
# engines and GUI
# ********************************
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import font as tkfont, Tk, Menu, ttk
from tkinter.constants import BOTH, Y, X  # Import BOTH, Y, and X constants
from tkinter import Toplevel
from tkinter import ttk
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import networkx as nx
import datetime as dt
from datetime import datetime as dt_datetime, timedelta
import math
import copy
import pickle
# ********************************
# library import
# ********************************
#import mpld3
#from mpld3 import plugins
from collections import defaultdict
import numpy as np
from dateutil.relativedelta import relativedelta
import calendar
# ********************************
# Allocation logic
# ********************************
import csv
from datetime import date, timedelta
from math import floor
# ********************************
# Cost Evaluation
# ********************************
import json
# ********************************
# PySI library import
# ********************************
from pysi.utils.config import Config
from pysi.utils.file_io import *
#from utils.file_io import load_cost_table
#from utils.file_io import load_monthly_demand
from pysi.utils.calendar445 import Calendar445
from pysi.plan.demand_generate import convert_monthly_to_weekly
from pysi.plan.operations import *
# "plan.demand_processing" is merged in "plan.operations"
#from plan.demand_processing import *
#from pysi.plan.demand_processing import set_df_Slots2psi4demand
from pysi.network.node_base import Node, PlanNode, GUINode
from pysi.network.tree import *
#from network.tree import create_tree_set_attribute
#from network.tree import set_node_costs
#from network.tree import calc_all_psi2i4demand, set_lot_counts
#from PSI_plan.planning_operation import calcS2P, set_S2psi, get_set_childrenP2S2psi, calc_all_psi2i4demand, calcPS2I4demand
from pysi.evaluate.evaluate_cost_models_v2 import gui_run_initial_propagation, propagate_cost_to_plan_nodes, load_tobe_prices, assign_tobe_prices_to_leaf_nodes, load_asis_prices, assign_asis_prices_to_root_nodes
from pysi.gui.app_FastNetworkViewer import FastNetworkViewer
#from pysi.gui.app_NetworkGraphApp import NetworkGraphApp
# app.py 先頭の import に追記
#from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from pysi.evaluate.offering_price import build_offering_price_frame, plot_offering_price_grid

# app.py (冒頭の import 群の近く)
from pysi.scenario.store import save_run_results, list_runs
from pysi.scenario.store import list_scenarios, get_db_path_from
from pysi.evaluate.offering_price import build_offering_price_frame



# ***************************
# pie utility
# ***************************
# 追加インポート
#from matplotlib.figure import Figure
#from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
# pie ユーティリティ（前メッセージで提示した pie_utils.py を配置済み前提）
try:
    from pysi.gui.pie_utils import build_cost_pie_dict, pie_normalize
except Exception:
    # 最低限の代替（前メッセージと同等）
    from typing import Dict, Tuple
    def pie_normalize(values: Dict[str, float], mode: str="ratio", eps: float=1e-9) -> Tuple[Dict[str, float], float]:
        clean = {k: max(0.0, float(v or 0.0)) for k, v in values.items()}
        total = sum(clean.values())
        if total <= eps:
            return (clean if mode=="money" else {k:0.0 for k in clean}), 0.0
        if mode == "money":
            return clean, total
        ratios = {k: v/total for k, v in clean.items()}
        s = sum(ratios.values())
        if abs(1.0 - s) > 1e-12:
            kmax = max(ratios, key=lambda k: ratios[k])
            ratios[kmax] += (1.0 - s)
        return ratios, total
    def build_cost_pie_dict(row) -> Dict[str, float]:
        return {
            "Direct Materials":  float(row.get("direct_materials_costs", 0.0)),
            "Tariff":            float(row.get("tax_portion", 0.0)),
            "Logistics":         float(row.get("logistics_costs", 0.0)),
            "Warehouse":         float(row.get("warehouse_cost", 0.0)),
            "Marketing":         float(row.get("marketing_promotion", 0.0)),
            "Sales Admin":       float(row.get("sales_admin_cost", 0.0)),
            "Prod Indirect Labor":  float(row.get("prod_indirect_labor", 0.0)),
            "Prod Indirect Others": float(row.get("prod_indirect_others", 0.0)),
            "Direct Labor":      float(row.get("direct_labor_costs", 0.0)),
            "Depreciation":      float(row.get("depreciation_others", 0.0)),
            "Mfg Overhead":      float(row.get("manufacturing_overhead", 0.0)),
            "Profit":            float(row.get("profit", 0.0)),
        }
# ********************************
# Planning Engine
# ********************************
from pysi.plan.engines import run_engine
from pysi.plan import engines as eng
#@NO USE
# from pysi.network.node_base import eval_supply_chain_cost
# ********************************
# Definition start
# ********************************
def find_all_paths(node, path, paths):
    path.append(node.name)
    if not node.children:
        #print("leaf path", node.name, path)
        paths.append(path.copy())
    else:
        for child in node.children:
            # print("child path",child.name, path)
            find_all_paths(child, path, paths)
            for grandchild in child.children:
                #print("grandchild path", grandchild.name, path)
                find_all_paths(grandchild, path, paths)
                for g_grandchild in grandchild.children:
                    #print("g_grandchild path", g_grandchild.name, path)
                    find_all_paths(g_grandchild, path, paths)
                    for g1_grandchild in g_grandchild.children:
                        #print("g1_grandchild path", g1_grandchild.name, path)
                        find_all_paths(g1_grandchild, path, paths)
                        for g2_grandchild in g1_grandchild.children:
                            #print("g2_grandchild path", g2_grandchild.name, path)
                            find_all_paths(g2_grandchild, path, paths)
    path.pop()
def find_paths(root):
    paths = []
    find_all_paths(root, [], paths)
    return paths
# *********************************
# check_plan_range
# *********************************
def check_plan_range(df):  # df is dataframe
    #
    # getting start_year and end_year
    #
    start_year = node_data_min = df["year"].min()
    end_year = node_data_max = df["year"].max()
    # *********************************
    # plan initial setting
    # *********************************
    plan_year_st = int(start_year)  # 2024  # plan開始年
    # 3ヵ年または5ヵ年計画分のS計画を想定
    plan_range = int(end_year) - int(start_year) + 1 + 1  # +1はハミ出す期間
    plan_year_end = plan_year_st + plan_range
    return plan_range, plan_year_st
# 2. lot_id_list列を追加
def generate_lot_ids(row):
    # node_yyyy_ww = f"{row['node_name']}_{row['iso_year']}_{row['iso_week']}"
    node_yyyy_ww = f"{row['node_name']}{row['iso_year']}{row['iso_week']}"
    lots_count = row["S_lot"]
    # stack_list = [f"{node_yyyy_ww}_{i}" for i in range(lots_count)]
    #@240930 修正MEMO
    # ココの{i}をzfillで二桁にする
    #stack_list = [f"{node_yyyy_ww}{i:02}" for i in range(lots_count)]
    digit_count = 2
    stack_list = [f"{node_yyyy_ww}{str(i).zfill(digit_count)}" for i in range(lots_count)]
    return stack_list
# ******************************
# trans month 2 week 2 lot_id_list
# ******************************
def trans_month2week2lot_id_list(file_name, lot_size):
    df = pd.read_csv(file_name)
    # *********************************
    # check_plan_range
    # *********************************
    plan_range, plan_year_st = check_plan_range(df)  # df is dataframe
    df = df.melt(
        id_vars=["product_name", "node_name", "year"],
        var_name="month",
        value_name="value",
    )
    df["month"] = df["month"].str[1:].astype(int)
    df_daily = pd.DataFrame()
    for _, row in df.iterrows():
        daily_values = np.full(
            pd.Timestamp(row["year"], row["month"], 1).days_in_month, row["value"]
        )
        dates = pd.date_range(
            start=f"{row['year']}-{row['month']}-01", periods=len(daily_values)
        )
        df_temp = pd.DataFrame(
            {
                "product_name": row["product_name"],
                "node_name": row["node_name"],
                "date": dates,
                "value": daily_values,
            }
        )
        df_daily = pd.concat([df_daily, df_temp])
    #@24240930 STOP
    #df_daily["iso_year"] = df_daily["date"].dt.isocalendar().year
    #df_daily["iso_week"] = df_daily["date"].dt.isocalendar().week
    #
    #df_weekly = (
    #    df_daily.groupby(["product_name", "node_name", "iso_year", "iso_week"])["value"]
    #    .sum()
    #    .reset_index()
    #)
    df_daily["iso_year"] = df_daily["date"].dt.isocalendar().year
    # ISO週を２ケタ表示
    df_daily["iso_week"] = df_daily["date"].dt.isocalendar().week.astype(str).str.zfill(2)
    df_weekly = (
        df_daily.groupby(["product_name", "node_name", "iso_year", "iso_week"])["value"]
        .sum()
        .reset_index()
    )
    ## 1. S_lot列を追加
    # lot_size = 100  # ここに適切なlot_sizeを設定します
    df_weekly["S_lot"] = df_weekly["value"].apply(lambda x: math.ceil(x / lot_size))
    ## 2. lot_id_list列を追加
    # def generate_lot_ids(row):
    df_weekly["lot_id_list"] = df_weekly.apply(generate_lot_ids, axis=1)
    return df_weekly, plan_range, plan_year_st
def make_capa_year_month(input_file):
    #    # mother plant capacity parameter
    #    demand_supply_ratio = 1.2  # demand_supply_ratio = ttl_supply / ttl_demand
    # initial setting of total demand and supply
    # total_demandは、各行のm1からm12までの列の合計値
    df_capa = pd.read_csv(input_file)
    df_capa["total_demand"] = df_capa.iloc[:, 3:].sum(axis=1)
    # yearでグループ化して、月次需要数の総和を計算
    df_capa_year = df_capa.groupby(["year"], as_index=False).sum()
    return df_capa_year
#def trans_month2week2lot_id_list(file_name, lot_size)
def process_monthly_demand(file_name, lot_size):
    """
    Process monthly demand data and convert to weekly data.
    Parameters:
        file_name (str): Path to the monthly demand file.
        lot_size (int): Lot size for allocation.
    Returns:
        pd.DataFrame: Weekly demand data with ISO weeks and lot IDs.
    """
    monthly_data = load_monthly_demand(file_name)
    if monthly_data.empty:
        print("Error: Failed to load monthly demand data.")
        return None
    return convert_monthly_to_weekly(monthly_data, lot_size)
def read_set_cost(file_path, nodes_outbound):
    """
    Load cost table from file and set node costs.
    Parameters:
        file_path (str): Path to the cost table file.
        nodes_outbound (dict): Dictionary of outbound nodes.
    Returns:
        None
    """
    cost_table = load_cost_table(file_path)
    if cost_table is not None:
        set_node_costs(cost_table, nodes_outbound)
# ****************************
# 辞書をtree nodeのdemand & supplyに接続する
# ****************************
def set_dict2tree_psi(node, attr_name, node_psi_dict):
    setattr(node, attr_name, node_psi_dict.get(node.name))
    # node.psi4supply = node_psi_dict.get(node.name)
    for child in node.children:
        set_dict2tree_psi(child, attr_name, node_psi_dict)
# nodeを手繰りながらnode_psi_dict辞書を初期化する
def make_psi_space_dict(node, node_psi_dict, plan_range):
    psi_list = [[[] for j in range(4)] for w in range(53 * plan_range)]
    node_psi_dict[node.name] = psi_list  # 新しいdictにpsiをセット
    for child in node.children:
        make_psi_space_dict(child, node_psi_dict, plan_range)
    return node_psi_dict
# *******************
# 生産平準化の前処理　ロット・カウント
# *******************
def count_lots_yyyy(psi_list, yyyy_str):
    matrix = psi_list
    # 共通の文字列をカウントするための変数を初期化
    count_common_string = 0
    # Step 1: マトリクス内の各要素の文字列をループで調べる
    for row in matrix:
        for element in row:
            # Step 2: 各要素内の文字列が "2023" を含むかどうかを判定
            if yyyy_str in element:
                # Step 3: 含む場合はカウンターを増やす
                count_common_string += 1
    return count_common_string
def is_52_or_53_week_year(year):
    # 指定された年の12月31日を取得
    last_day_of_year = dt.date(year, 12, 31)
    # 12月31日のISO週番号を取得 (isocalendar()メソッドはタプルで[ISO年, ISO週番号, ISO曜日]を返す)
    _, iso_week, _ = last_day_of_year.isocalendar()
    # ISO週番号が1の場合は前年の最後の週なので、52週と判定
    if iso_week == 1:
        return 52
    else:
        return iso_week
def find_depth(node):
    if not node.parent:
        return 0
    else:
        return find_depth(node.parent) + 1
def find_all_leaves(node, leaves, depth=0):
    if not node.children:
        leaves.append((node, depth))  # (leafノード, 深さ) のタプルを追加
    else:
        for child in node.children:
            find_all_leaves(child, leaves, depth + 1)
def make_nodes_decouple_all(node):
    #
    #    root_node = build_tree()
    #    set_parent(root_node)
    #    leaves = []
    #    find_all_leaves(root_node, leaves)
    #    pickup_list = leaves[::-1]  # 階層の深い順に並べる
    leaves = []
    leaves_name = []
    nodes_decouple = []
    find_all_leaves(node, leaves)
    # find_all_leaves(root_node, leaves)
    pickup_list = sorted(leaves, key=lambda x: x[1], reverse=True)
    pickup_list = [leaf[0] for leaf in pickup_list]  # 深さ情報を取り除く
    # こうすることで、leaf nodeを階層の深い順に並べ替えた pickup_list が得られます。
    # 先に深さ情報を含めて並べ替え、最後に深さ情報を取り除くという流れになります。
    # 初期処理として、pickup_listをnodes_decoupleにcopy
    # pickup_listは使いまわしで、pop / insert or append / removeを繰り返す
    for nd in pickup_list:
        nodes_decouple.append(nd.name)
    nodes_decouple_all = []
    while len(pickup_list) > 0:
        # listのcopyを要素として追加
        nodes_decouple_all.append(nodes_decouple.copy())
        current_node = pickup_list.pop(0)
        del nodes_decouple[0]  # 並走するnode.nameの処理
        parent_node = current_node.parent
        if parent_node is None:
            break
        # 親ノードをpick up対象としてpickup_listに追加
        if current_node.parent:
            #    pickup_list.append(current_node.parent)
            #    nodes_decouple.append(current_node.parent.name)
            # if parent_node not in pickup_list:  # 重複追加を防ぐ
            # 親ノードの深さを見て、ソート順にpickup_listに追加
            depth = find_depth(parent_node)
            inserted = False
            for idx, node in enumerate(pickup_list):
                if find_depth(node) <= depth:
                    pickup_list.insert(idx, parent_node)
                    nodes_decouple.insert(idx, parent_node.name)
                    inserted = True
                    break
            if not inserted:
                pickup_list.append(parent_node)
                nodes_decouple.append(parent_node.name)
            # 親ノードから見た子ノードをpickup_listから削除
            for child in parent_node.children:
                if child in pickup_list:
                    pickup_list.remove(child)
                    nodes_decouple.remove(child.name)
        else:
            print("error: node dupplicated", parent_node.name)
    return nodes_decouple_all
    # +++++++++++++++++++++++++++++++++++++++++++++++
    # Mother Plant demand leveling
    # root_node_outbound / supply / [w][0] setting S_allocated&pre_prod&leveled
    # +++++++++++++++++++++++++++++++++++++++++++++++
def demand_leveling_on_ship(root_node_outbound, pre_prod_week, year_st, year_end):
    # input: root_node_outbound.psi4demand
    #        pre_prod_week =26
    #
    # output:root_node_outbound.psi4supply
    plan_range = root_node_outbound.plan_range
    #@241114
    # 需給バランスの問題は、ひとつ上のネットワーク全体のoptimizeで解く
    # ロット単位で供給を変化させて、weight=ロット(CPU_profit)利益でsimulate
    # 設備投資の回収期間を見る
    # 供給>=需要ならオペレーション問題
    # 供給<需要なら供給配分とオペレーション問題
    # optimiseで、ルートと量を決定
    # PSIで、operation revenue cost profitを算定 business 評価
    # 業界No1/2/3の供給戦略をsimulateして、business評価する
    # node_psi_dict_Ot4Dmでは、末端市場のleafnodeのみセット
    #
    # root_nodeのS psi_list[w][0]に、levelingされた確定出荷S_confirm_listをセッ    ト
    # 年間の総需要(総lots)をN週先行で生産する。
    # 例えば、３ヶ月先行は13週先行生産として、年間総需要を週平均にする。
    # S出荷で平準化して、confirmedS-I-P
    # conf_Sからconf_Pを生成して、conf_P-S-I  PUSH and PULL
    S_list = []
    S_allocated = []
    year_lots_list = []
    year_week_list = []
    leveling_S_in = []
    leveling_S_in = root_node_outbound.psi4demand
    # psi_listからS_listを生成する
    for psi in leveling_S_in:
        S_list.append(psi[0])
    # 開始年を取得する
    plan_year_st = year_st  # 開始年のセット in main()要修正
    #for yyyy in range(plan_year_st, plan_year_st + plan_range + 1):
    for yyyy in range(int(plan_year_st), int(plan_year_st + plan_range + 1)):
        year_lots = count_lots_yyyy(S_list, str(yyyy))
        year_lots_list.append(year_lots)
    #        # 結果を出力
    #       #print(yyyy, " year carrying lots:", year_lots)
    #
    #    # 結果を出力
    #   #print(" year_lots_list:", year_lots_list)
    # an image of sample data
    #
    # 2023  year carrying lots: 0
    # 2024  year carrying lots: 2919
    # 2025  year carrying lots: 2914
    # 2026  year carrying lots: 2986
    # 2027  year carrying lots: 2942
    # 2028  year carrying lots: 2913
    # 2029  year carrying lots: 0
    #
    # year_lots_list: [0, 2919, 2914, 2986, 2942, 2913, 0]
    year_list = []
    #for yyyy in range(plan_year_st, plan_year_st + plan_range + 1):
    for yyyy in range(int(plan_year_st), int(plan_year_st + plan_range + 1)):
        year_list.append(yyyy)
        # テスト用の年を指定
        year_to_check = yyyy
        # 指定された年のISO週数を取得
        week_count = is_52_or_53_week_year(year_to_check)
        year_week_list.append(week_count)
    #        # 結果を出力
    #       #print(year_to_check, " year has week_count:", week_count)
    #
    #    # 結果を出力
    #   #print(" year_week_list:", year_week_list)
    # print("year_list", year_list)
    # an image of sample data
    #
    # 2023  year has week_count: 52
    # 2024  year has week_count: 52
    # 2025  year has week_count: 52
    # 2026  year has week_count: 53
    # 2027  year has week_count: 52
    # 2028  year has week_count: 52
    # 2029  year has week_count: 52
    # year_week_list: [52, 52, 52, 53, 52, 52, 52]
    # *****************************
    # 生産平準化のための年間の週平均生産量(ロット数単位)
    # *****************************
    # *****************************
    # make_year_average_lots
    # *****************************
    # year_list     = [2023,2024,2025,2026,2027,2028,2029]
    # year_lots_list = [0, 2919, 2914, 2986, 2942, 2913, 0]
    # year_week_list = [52, 52, 52, 53, 52, 52, 52]
    year_average_lots_list = []
    for lots, weeks in zip(year_lots_list, year_week_list):
        average_lots_per_week = math.ceil(lots / weeks)
        year_average_lots_list.append(average_lots_per_week)
    # print("year_average_lots_list", year_average_lots_list)
    #
    # an image of sample data
    #
    # year_average_lots_list [0, 57, 57, 57, 57, 57, 0]
    # 年間の総需要(総lots)をN週先行で生産する。
    # 例えば、３ヶ月先行は13週先行生産として、年間総需要を週平均にする。
    #
    # 入力データの前提
    #
    # leveling_S_in[w][0] == S_listは、outboundのdemand_planで、
    # マザープラントの出荷ポジションのSで、
    # 5年分 週次 最終市場におけるlot_idリストが
    # LT offsetされた状態で入っている
    #
    # year_list     = [2023,2024,2025,2026,2027,2028,2029]
    # year_lots_list = [0, 2919, 2914, 2986, 2942, 2913, 0]
    # year_week_list = [52, 52, 52, 53, 52, 52, 52]
    # year_average_lots_list [0, 57, 57, 57, 57, 57, 0]
    # ********************************
    # 先行生産の週数
    # ********************************
    # precedence_production_week =13
    pre_prod_week =26 # 26週=6か月の先行生産をセット
    # pre_prod_week =13 # 13週=3か月の先行生産をセット
    # pre_prod_week = 6  # 6週=1.5か月の先行生産をセット
    # ********************************
    # 先行生産の開始週を求める
    # ********************************
    # 市場投入の前年において i= 0  year_list[i]           # 2023
    # 市場投入の前年のISO週の数 year_week_list[i]         # 52
    # 先行生産の開始週は、市場投入の前年のISO週の数 - 先行生産週
    pre_prod_start_week = 0
    i = 0
    pre_prod_start_week = year_week_list[i] - pre_prod_week
    # スタート週の前週まで、[]リストで埋めておく
    for i in range(pre_prod_start_week):
        S_allocated.append([])
    # ********************************
    # 最終市場からのLT offsetされた出荷要求lot_idリストを
    # Allocate demand to mother plant weekly slots
    # ********************************
    # S_listの週別lot_idリストを一直線のlot_idリストに変換する
    # mother plant weekly slots
    # 空リストを無視して、一直線のlot_idリストに変換
    # 空リストを除外して一つのリストに結合する処理
    S_one_list = [item for sublist in S_list if sublist for item in sublist]
    ## 結果表示
    ##print(S_one_list)
    # to be defined 毎年の定数でのlot_idの切り出し
    # listBの各要素で指定された数だけlistAから要素を切り出して
    # 新しいリストlistCを作成
    listA = S_one_list  # 5年分のlot_idリスト
    listB = year_lots_list  # 毎年毎の総ロット数
    listC = []  # 毎年のlot_idリスト
    start_idx = 0
    for i, num in enumerate(listB):
        end_idx = start_idx + num
        # original sample
        # listC.append(listA[start_idx:end_idx])
        # **********************************
        # "slice" and "allocate" at once
        # **********************************
        sliced_lots = listA[start_idx:end_idx]
        # 毎週の生産枠は、year_average_lots_listの平均値を取得する。
        N = year_average_lots_list[i]
        if N == 0:
            pass
        else:
            # その年の週次の出荷予定数が生成される。
            S_alloc_a_year = [
                sliced_lots[j : j + N] for j in range(0, len(sliced_lots), N)
            ]
            S_allocated.extend(S_alloc_a_year)
            # S_allocated.append(S_alloc_a_year)
        start_idx = end_idx
    ## 結果表示
    # print("S_allocated", S_allocated)
    # set psi on outbound supply
    # "JPN-OUT"
    #
    # ***********************************************
    #@241113 CHANGE root_node_outbound.psi4supplyが存在するという前提
    # ***********************************************
    #
    #node_name = root_node_outbound.name  # Nodeからnode_nameを取出す
    #
    ## for w, pSi in enumerate( S_allocated ):
    ##
    ##    node_psi_dict_Ot4Sp[node_name][w][0] = pSi
    # ***********************************************
    #@250628 MARK setting S_lots on "root supply" 4 PreProduction
    # ***********************************************
    # 1. setting "pre_prod_S" on "root supply"
    # "rice"demand[w][0]は平準化せずにそのままsupply[w][0]にセット
    #
    # <<NEXT ACTION>>
    # 2. calcS2P
    # 3. calcPSI
    #    self.root_node_outbound.calcS2P_4supply()
    #    self.root_node_outbound.calcPS2I4supply()
    for w in range(53 * plan_range):
        if w <= len(S_allocated) - 1:  # index=0 start
            root_node_outbound.psi4supply[w][0] = S_allocated[w]
            #node_psi_dict_Ot4Sp[node_name][w][0] = S_allocated[w]
        else:
            root_node_outbound.psi4supply[w][0] = []
            #node_psi_dict_Ot4Sp[node_name][w][0] = []
    # +++++++++++++++++++++++++++++++++++++++++++++++
def place_P_in_supply_LT(w, child, lot):  # lot LT_shift on P
    # *******************************************
    # supply_plan上で、PfixをSfixにPISでLT offsetする
    # *******************************************
    # **************************
    # Safety Stock as LT shift
    # **************************
    #@240925 STOP
    ## leadtimeとsafety_stock_weekは、ここでは同じ
    ## safety_stock_week = child.leadtime
    #LT_SS_week = child.leadtime
    #@240925 長期休暇がLT_SS_weekかchild.leadtimeかどちらにある場合は???
    #@240925
    # leadtimeとsafety_stock_weekは別もの
    LT_SS_week   = child.safety_stock_week
    LT_logi_week = child.leadtime
    # **************************
    # long vacation weeks
    # **************************
    lv_week = child.long_vacation_weeks
    ## P to S の計算処理
    # self.psi4supply = shiftP2S_LV(self.psi4supply, safety_stock_week, lv_week)
    ### S to P の計算処理
    ##self.psi4demand = shiftS2P_LV(self.psi4demand, safety_stock_week, lv_week)
    # my_list = [1, 2, 3, 4, 5]
    # for i in range(2, len(my_list)):
    #    my_list[i] = my_list[i-1] + my_list[i-2]
    # 0:S
    # 1:CO
    # 2:I
    # 3:P
    #@240925 STOP
    ## LT:leadtime SS:safty stockは1つ
    ## foreward planで、「親confirmed_S出荷=子confirmed_P着荷」と表現
    #eta_plan = w + LT_SS_week  # ETA=ETDなので、+LTすると次のETAとなる
    # LT_logi_weekで子nodeまでの物流LTを考慮
    eta_plan = w + LT_logi_week
    # etd_plan = w + ss # ss:safty stock
    # eta_plan = w - ss # ss:safty stock
    # *********************
    # 着荷週が事業所nodeの非稼働週の場合 +1次週の着荷とする
    # *********************
    # 着荷週を調整
    eta_shift = check_lv_week_fw(lv_week, eta_plan)  # ETA:Eatimate Time Arriv
    # リスト追加 extend
    # 安全在庫とカレンダ制約を考慮した着荷予定週Pに、w週Sからoffsetする
    # lot by lot operation
    # confirmed_P made by shifting parent_conf_S
    # ***********************
    # place_lot_supply_plan
    # ***********************
    # ここは、"REPLACE lot"するので、appendの前にchild psiをzero clearしてから
    #@240925 STOP
    ## 今回のmodelでは、輸送工程もpsi nodeと同等に扱っている(=POではない)ので
    ## 親のconfSを「そのままのWで」子のconfPに置く place_lotする
    #child.psi4supply[w][3].append(lot)
    ## 親のconfSを「eta_shiftしたWで」子のconfPに置く place_lotする
    # 親のconfSを「LT=輸送LT + 加工LT + SSでwをshiftして」子confSにplace_lot
    child.psi4supply[eta_shift][3].append(lot)
    # print("len(child.psi4supply)", len(child.psi4supply) ) # len() of psi list    # print("lot child.name eta_shift ",lot,  child.name, eta_shift )  # LT shift weeks
    # Sは、SS在庫分の後に出荷する
    ship_position = eta_shift + LT_SS_week
    # 出荷週を調整
    ship_shift = check_lv_week_fw(lv_week, ship_position)
    child.psi4supply[ship_shift][0].append(lot)
def find_path_to_leaf_with_parent(node, leaf_node, current_path=[]):
    current_path.append(leaf_node.name)
    if node.name == leaf_node.name:
        return current_path
    else:
        parent = leaf_node.parent
        path = find_path_to_leaf_with_parent(node, parent, current_path.copy())
    return path
#        if path:
#
#            return path
def extract_node_name(stringA):
    """
    Extract the node name from a string by removing the last 9 characters (YYYYWWNNN).
    Parameters:
        stringA (str): Input string (e.g., "LEAF01202601001").
    Returns:
        str: Node name (e.g., "LEAF01").
    """
    if len(stringA) > 10:
        # 最後の10文字を削除して返す #deep relation on "def generate_lot_ids()"
        return stringA[:-10]
    else:
        # 文字列が10文字以下の場合、削除せずそのまま返す（安全策）
        return stringA
# ******************************************
# confirmedSを出荷先ship2のPとSにshift&set
# ******************************************
# 出荷先node psiのPとSに、confirmed_SのlotsをLT shiftで置く
# main function is this: place_P_in_supply_LT(w, ship2node, lot)
def feedback_psi_lists(node, nodes):
#def feedback_psi_lists(node, node_psi_dict, nodes):
    # キーが存在する場合は対応する値valueが返り、存在しない場合はNoneが返る。
    if node.children == []:  # 子nodeがないleaf nodeの場合
        pass
    else:
        # ************************************
        # clearing children P[w][3] and S[w][0]
        # ************************************
        # replace lotするために、事前に、
        # 出荷先となるすべてのchildren nodesのS[w][0]とP[w][3]をクリア
        for child in node.children:
            for w in range(53 * node.plan_range):
                child.psi4supply[w][0] = []
                child.psi4supply[w][3] = []
        # lotidから、leaf_nodeを特定し、出荷先ship2nodeに出荷することは、
        # すべての子nodeに出荷することになる
        # ************************************
        # setting mother_confirmed_S
        # ************************************
        # このnode内での子nodeへの展開
        for w in range(53 * node.plan_range):
            #@STOP
            #print("node.psi4supply", node.psi4supply)
            confirmed_S_lots = node.psi4supply[w][0]  # 親の確定出荷confS lot
            print("confirmed_S_lots", confirmed_S_lots)
            # 出荷先nodeを特定して
            # 一般には、下記のLT shiftだが・・・・・
            # 出荷先の ETA = LT_shift(ETD) でP place_lot
            # 工程中の ETA = SS_shift(ETD) でS place_lot
            # 本モデルでは、輸送工程 = modal_nodeを想定して・・・・・
            # 出荷先の ETA = 出荷元ETD        でP place_lot
            # 工程中の ETA = LT&SS_shift(ETD) でS place_lot
            # というイビツなモデル定義・・・・・
            # 直感的なPO=INVOICEという考え方に戻すべきかも・・・・・
            #
            # modal shiftのmodelingをLT_shiftとの拡張で考える???
            # modal = BOAT/AIR/QURIE
            # LT_shift(modal, w, ,,,,
            for lot in confirmed_S_lots:
                if lot == []:
                    pass
                else:
                    # *********************************************************
                    # child#ship2node = find_node_to_ship(node, lot)
                    # lotidからleaf_nodeのpointerを返す
                    print("lot_ID", lot)
                    leaf_node_name = extract_node_name(lot)
                    print("lot_ID leaf_node_name", lot, leaf_node_name )
                    leaf_node = nodes[leaf_node_name]
                    # 末端からあるnodeAまでleaf_nodeまでのnode_listをpathで返す
                    current_path = []
                    path = []
                    path = find_path_to_leaf_with_parent(node, leaf_node, current_path)
                    # nodes_listを逆にひっくり返す
                    path.reverse()
                    # 出荷先nodeはnodeAの次node、path[1]になる
                    ship2node_name = path[1]
                    ship2node = nodes[ship2node_name]
                    # ここでsupply planを更新している
                    # lot: 親nodeの確定出荷confirmed_S lotsを
                    # ship2node: 子nodeの出荷先を(lot_IDから)特定してある
                    # 出荷先node psiのPとSに、confirmed_SのlotsをLT shiftで置く
                    place_P_in_supply_LT(w, ship2node, lot)
    for child in node.children:
        feedback_psi_lists(child, nodes)
        #feedback_psi_lists(child, node_psi_dict, nodes)
def copy_P_demand2supply(node): # TOBE 240926
#def update_child_PS(node): # TOBE 240926
    # 明示的に.copyする。
    plan_len = 53 * node.plan_range
    for w in range(0, plan_len):
        node.psi4supply[w][3] = node.psi4demand[w][3].copy()
def PULL_process(node):
    # *******************************************
    # decouple nodeは、pull_Sで出荷指示する
    # *******************************************
    #@241002 childで、親nodeの確定S=確定P=demandのPで計算済み
    # copy S&P demand2supply for PULL
    copy_S_demand2supply(node)
    copy_P_demand2supply(node)
    # 自分のnodeをPS2Iで確定する
    node.calcPS2I4supply()  # calc_psi with PULL_S&P
    print(f"PULL_process applied to {node.name}")
def apply_pull_process(node):
    #@241002 MOVE
    #PULL_process(node)
    for child in node.children:
        PULL_process(child)
        apply_pull_process(child)
def copy_S_demand2supply(node): # TOBE 240926
#def update_child_PS(node): # TOBE 240926
    # 明示的に.copyする。
    plan_len = 53 * node.plan_range
    for w in range(0, plan_len):
        node.psi4supply[w][0] = node.psi4demand[w][0].copy()
def PUSH_process(node):
    # ***************
    # decoupl nodeに入って最初にcalcPS2Iで状態を整える
    # ***************
    node.calcPS2I4supply()  # calc_psi with PULL_S
    # STOP STOP
    ##@241002 decoupling nodeのみpullSで確定ship
    ## *******************************************
    ## decouple nodeは、pull_Sで出荷指示する
    ## *******************************************
    ## copy S demand2supply
    #copy_S_demand2supply(node)
    #
    ## 自分のnodeをPS2Iで確定する
    #node.calcPS2I4supply()  # calc_psi with PUSH_S
    print(f"PUSH_process applied to {node.name}")
def push_pull_all_psi2i_decouple4supply5(node, decouple_nodes):
    print("node in supply_proc", node.name )
    print("push_pull_all_psi2i_decouple4supply5")
    print("node.name & decouple_nodes", node.name, decouple_nodes)
    #@STOP
    #if  node.name == "DADJPN":
    #    print("DADJPN.psi4demand", node.psi4demand )
    #    print("DADJPN.psi4supply", node.psi4supply )
    if node.name in decouple_nodes:
        # ***************
        # decoupl nodeに入って最初にcalcPS2Iで状態を整える
        # ***************
        node.calcPS2I4supply()  # calc_psi with PULL_S
        #@241002 decoupling nodeのみpullSで確定ship
        # *******************************************
        # decouple nodeは、pull_Sで出荷指示する
        # *******************************************
        copy_S_demand2supply(node)
        PUSH_process(node)         # supply SP2Iしてからの
        apply_pull_process(node)   # demandSに切り替え
    else:
        PUSH_process(node)
        for child in node.children:
            push_pull_all_psi2i_decouple4supply5(child, decouple_nodes)
def map_psi_lots2df(node, D_S_flag, psi_lots):
    if D_S_flag == "demand":
        matrix = node.psi4demand
    elif D_S_flag == "supply":
        matrix = node.psi4supply
    else:
        print("error: wrong D_S_flag is defined")
        return pd.DataFrame()
    for week, row in enumerate(matrix):
        for scoip, lots in enumerate(row):
            for step_no, lot_id in enumerate(lots):
                psi_lots.append([node.name, week, scoip, step_no, lot_id])
    for child in node.children:
        map_psi_lots2df(child, D_S_flag, psi_lots)
    columns = ["node_name", "week", "s-co-i-p", "step_no", "lot_id"]
    df = pd.DataFrame(psi_lots, columns=columns)
    return df
# **************************
# collect_psi_data
# **************************
def collect_psi_data(node, D_S_flag, week_start, week_end, psi_data):
    if D_S_flag not in ["demand", "supply"]:
        print("error: D_S_flag should be 'demand' or 'supply'")
        return
    psi_lots = []
    df_plan = map_psi_lots2df(node, D_S_flag, psi_lots)
    if df_plan.empty:
        print(f"[{node.name}] No data for PSI ({D_S_flag})")
        return
    # week_end の範囲を調整（データ内最大weekに合わせる）
    max_week = df_plan["week"].max()
    week_end = min(week_end, max_week)
    df_filtered = df_plan[
        (df_plan["node_name"] == node.name) &
        (df_plan["week"] >= week_start) &
        (df_plan["week"] <= week_end)
    ]
    print(f"[{node.name}] PSI df shape: {df_filtered.shape}")
    print(df_filtered[df_filtered["s-co-i-p"] == 3].head())  # P
    print(df_filtered[df_filtered["s-co-i-p"] == 2].head())  # I
    print(df_filtered[df_filtered["s-co-i-p"] == 0].head())  # S
    # 分割＆集計
    line_data_2I = df_filtered[df_filtered["s-co-i-p"] == 2]
    bar_data_0S = df_filtered[df_filtered["s-co-i-p"] == 0]
    bar_data_3P = df_filtered[df_filtered["s-co-i-p"] == 3]
    line_plot_data_2I = line_data_2I.groupby("week")["lot_id"].count()
    bar_plot_data_3P = bar_data_3P.groupby("week")["lot_id"].count()
    bar_plot_data_0S = bar_data_0S.groupby("week")["lot_id"].count()
    # インデックスはintに（描画エラー防止）
    line_plot_data_2I.index = line_plot_data_2I.index.astype(int)
    bar_plot_data_3P.index = bar_plot_data_3P.index.astype(int)
    bar_plot_data_0S.index = bar_plot_data_0S.index.astype(int)
    # 指標評価
    revenue = round(getattr(node, "eval_cs_price_sales_shipped", 0))
    profit = round(getattr(node, "eval_cs_profit", 0))
    profit_ratio = round((profit / revenue) * 100, 1) if revenue != 0 else 0
    psi_data.append((
        node.name, revenue, profit, profit_ratio,
        line_plot_data_2I, bar_plot_data_3P, bar_plot_data_0S
    ))
# node is "node_opt"
def collect_psi_data_opt(node, node_out, D_S_flag, week_start, week_end, psi_data):
    if D_S_flag == "demand":
        psi_lots = []
        df_demand_plan = map_psi_lots2df(node, D_S_flag, psi_lots)
        df_init = df_demand_plan
    elif D_S_flag == "supply":
        psi_lots = []
        df_supply_plan = map_psi_lots2df(node, D_S_flag, psi_lots)
        df_init = df_supply_plan
    else:
        print("error: D_S_flag should be demand or supply")
        return
    condition1 = df_init["node_name"] == node.name
    condition2 = (df_init["week"] >= week_start) & (df_init["week"] <= week_end)
    df = df_init[condition1 & condition2]
    line_data_2I = df[df["s-co-i-p"].isin([2])]
    bar_data_0S = df[df["s-co-i-p"] == 0]
    bar_data_3P = df[df["s-co-i-p"] == 3]
    line_plot_data_2I = line_data_2I.groupby("week")["lot_id"].count()
    bar_plot_data_3P = bar_data_3P.groupby("week")["lot_id"].count()
    bar_plot_data_0S = bar_data_0S.groupby("week")["lot_id"].count()
    # ノードのREVENUEとPROFITを四捨五入
    # root_out_optからroot_outboundの世界へ変換する
    #@241225 be checked
    #@ STOP
    ##@ TEST node_optとnode_originに、revenueとprofit属性を追加
    #revenue = round(node.revenue)
    #profit  = round(node.profit)
    #@241225 STOP "self.nodes_outbound"がscopeにない
    #node_origin = self.nodes_outbound[node.name]
    #
    # nodeをoptからoutに切り替え
    revenue = round(node_out.eval_cs_price_sales_shipped)
    profit = round(node_out.eval_cs_profit)
    # PROFIT_RATIOを計算して四捨五入
    profit_ratio = round((profit / revenue) * 100, 1) if revenue != 0 else 0
    psi_data.append((node.name, revenue, profit, profit_ratio, line_plot_data_2I, bar_plot_data_3P, bar_plot_data_0S))
#@250110 STOP
## gui/app.py
#class PSIPlannerApp:
#    def __init__(self, root, config):
#        self.root = root
#        self.config = config
#        self.root.title(self.config.APP_NAME)
#
#        self.tree_structure = None
#
#        # 必ず setup_ui を先に呼び出す
#        self.setup_ui()
#
#        # 必要な初期化処理を後から呼び出す
#        self.initialize_parameters()
#
#
#
#        # PSI planner
#        self.outbound_data = None
#        self.inbound_data = None
#
#        self.root_node_outbound = None
#        self.nodes_outbound = None
#        self.leaf_nodes_out = []
#
#        self.root_node_inbound = None
#        self.nodes_inbound = None
#        self.leaf_nodes_in = []
#
#        self.total_revenue = 0
#        self.total_profit = 0
#        self.profit_ratio = 0
#
#        # View settings
#        self.G = None
#        self.pos_E2E = None
#        self.fig_network = None
#        self.ax_network = None
#
#        # Initialize parameters
#        self.initialize_parameters()
def is_picklable(value):
    try:
        pickle.dumps(value)
    except (pickle.PicklingError, TypeError):
        return False
    return True
class PSIPlannerApp4save:
    #def __init__(self, root):
    def __init__(self):
        #self.root = root
        #self.root.title("Global Weekly PSI Planner")
        self.root_node = None  # root_nodeの定義を追加
        self.lot_size     = 2000      # 初期値
        self.plan_year_st = 2022      # 初期値
        self.plan_range   = 2         # 初期値
        self.pre_proc_LT  = 13        # 初期値 13week = 3month
        self.market_potential = 0     # 初期値 0
        self.target_share     = 0.5   # 初期値 0.5 = 50%
        self.total_supply     = 0     # 初期値 0
        #@ STOP
        #self.setup_ui()
        self.outbound_data = None
        self.inbound_data = None
        # PySI tree
        self.root_node_outbound = None
        self.nodes_outbound     = {}
        self.leaf_nodes_out     = []
        self.root_node_inbound  = None
        self.nodes_inbound      = {}
        self.leaf_nodes_in      = []
        self.root_node_out_opt  = None
        self.nodes_out_opt      = None
        self.leaf_nodes_opt     = []
        self.optimized_root     = None
        self.optimized_nodes    = None
        #@250730 ADD
        # PySI tree by product
        self.root_node_outbound_byprod = None
        self.nodes_outbound_byprod     = None
        self.leaf_nodes_out_byprod     = []
        self.root_node_inbound_byprod  = None
        self.nodes_inbound_byprod      = None
        self.leaf_nodes_in_byprod      = []
        # Evaluation on PSI
        self.total_revenue = 0
        self.total_profit  = 0
        self.profit_ratio  = 0
        # view
        self.G = None
        # Optimise
        self.Gdm_structure = None
        self.Gdm = None
        self.Gsp = None
        self.pos_E2E = None
        self.flowDict_opt = {} #None
        self.flowCost_opt = {} #None
        self.total_supply_plan = 0
        # loading files
        self.directory = None
        self.load_directory = None
        self.base_leaf_name = None
        # supply_plan / decoupling / buffer stock
        self.decouple_node_dic = {}
        self.decouple_node_selected = []
    #@ STOP
    #def update_from_psiplannerapp(self, psi_planner_app):
    #    self.__dict__.update(psi_planner_app.__dict__)
    #
    #def update_psiplannerapp(self, psi_planner_app):
    #    psi_planner_app.__dict__.update(self.__dict__)
#@ STOP
#    def update_from_psiplannerapp(self, psi_planner_app):
#        attributes = {key: value for key, value in psi_planner_app.__dict__.items() if key != 'root'}
#        self.__dict__.update(attributes)
#
#    def update_psiplannerapp(self, psi_planner_app):
#        attributes = {key: value for key, value in self.__dict__.items()}
#        psi_planner_app.__dict__.update(attributes)
    def update_from_psiplannerapp(self, psi_planner_app):
        attributes = {key: value for key, value in psi_planner_app.__dict__.items()
                      if key != 'root' and is_picklable(value) and not isinstance(value, (tk.Tk, tk.Widget, tk.Toplevel, tk.Variable))}
        self.__dict__.update(attributes)
    def update_psiplannerapp(self, psi_planner_app):
        attributes = {key: value for key, value in self.__dict__.items()}
        psi_planner_app.__dict__.update(attributes)
    def overlay_price_on_axes(self, ax, node, product_name: str, weeks=None):
        """
        PSIの棒グラフ(ax)に、単価/原価ラインをオーバーレイする。
        - 単価: offering_price_TOBE があれば優先、なければ ASIS
        - 原価: unit_cost_dm + unit_cost_tariff（存在すれば）
        """
        import numpy as np
        W = 0
        if hasattr(node, "psi4demand") and isinstance(node.psi4demand, list):
            W = len(node.psi4demand)
        if weeks is None:
            weeks = np.arange(W) if W else np.arange(0, 52)
        # 価格（定数ライン）
        unit_price = getattr(node, "offering_price_TOBE", None)
        if unit_price is None:
            unit_price = getattr(node, "offering_price_ASIS", None)
        # 原価（定数ライン）
        dm = getattr(node, "unit_cost_dm", None)
        tr = getattr(node, "unit_cost_tariff", None)
        unit_cost = None
        if (dm is not None) or (tr is not None):
            unit_cost = (dm or 0.0) + (tr or 0.0)
        if (unit_price is None) and (unit_cost is None):
            return  # オーバーレイ情報無し
        ax2 = ax.twinx()
        handles = []; labels = []
        if unit_price is not None:
            h1, = ax2.plot(weeks, [unit_price]*len(weeks), color="#1f77b4", linewidth=2.0, label="Unit Price")
            handles.append(h1); labels.append("Unit Price")
        if unit_cost is not None:
            h2, = ax2.plot(weeks, [unit_cost]*len(weeks), color="#FF7F0E", linewidth=1.8, linestyle="--", label="Unit Cost")
            handles.append(h2); labels.append("Unit Cost")
        ax2.set_ylabel("Price")
        # 既存凡例と結合（重なりを避けて右上へ）
        h0, l0 = ax.get_legend_handles_labels()
        ax.legend(h0+handles, l0+labels, loc="upper right", fontsize=8, frameon=True)
# **************************
# cost_stracture
# **************************
def make_stack_bar4cost_stracture(cost_dict):
    attributes_B = [
        'cs_direct_materials_costs',
        'cs_marketing_promotion',
        'cs_sales_admin_cost',
        'cs_tax_portion',
        'cs_logistics_costs',
        'cs_warehouse_cost',
        'cs_prod_indirect_labor',
        'cs_prod_indirect_others',
        'cs_direct_labor_costs',
        'cs_depreciation_others',
        'cs_profit',
    ]
    colors = {
        'cs_direct_materials_costs': 'lightgray',
        'cs_marketing_promotion': 'darkblue',
        'cs_sales_admin_cost': 'blue',
        'cs_tax_portion': 'gray',
        'cs_logistics_costs': 'cyan',
        'cs_warehouse_cost': 'magenta',
        'cs_prod_indirect_labor': 'green',
        'cs_prod_indirect_others': 'lightgreen',
        'cs_direct_labor_costs': 'limegreen',
        'cs_depreciation_others': 'yellowgreen',
        'cs_profit': 'gold',
    }
    nodes = list(cost_dict.keys())
    bar_width = 0.3
    plt.close('all')  # 🔴【追加】過去のグラフをすべて閉じる
    # 画面サイズを取得 (PCの解像度)
    root = tk.Tk()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    root.destroy()
    # 縦2つに並べるためのウィンドウサイズ (フルサイズの半分)
    win_width = screen_width
    win_height = screen_height // 2
    # 🔴【修正】ウィンドウサイズを大きく
    fig, ax = plt.subplots(figsize=(12, 6), dpi=100)
    # 🔴【修正】bottoms を適切に初期化 (ゼロ配列)
    bottoms = np.zeros(len(nodes))
    for attr in attributes_B:
        values = [cost_dict[node][attr] for node in cost_dict]
        ax.bar(nodes, values, bar_width, label=attr, color=colors[attr], bottom=bottoms)
        bottoms += values
        # Add text on bars
        for i, value in enumerate(values):
            if value > 0:
                ax.text(i, bottoms[i] - value / 2, f'{value:.1f}', ha='center', va='center', fontsize=6, color='black')
    # Add total values on top of bars
    total_values = [sum(cost_dict[node][attr] for attr in attributes_B) for node in cost_dict]
    for i, total in enumerate(total_values):
        ax.text(i, total + 2, f'{total:.1f}', ha='center', va='bottom', fontsize=6)
    ax.set_title('Supply Chain Cost Structure', fontsize=10)
    ax.set_xlabel('Node', fontsize=8)
    ax.set_ylabel('Amount', fontsize=8)
    # 凡例を左上に配置
    ax.legend(title='Attribute', fontsize=6, loc='upper left')
    # X軸ラベルを回転
    ax.set_xticks(range(len(nodes)))
    ax.set_xticklabels(nodes, rotation=30, fontsize=7)
    # 余白調整
    fig.subplots_adjust(left=0.2, right=0.85, top=0.9, bottom=0.3)
    # 🔴【修正】ウィンドウを画面下半分に移動
    mng = plt.get_current_fig_manager()
    #try:
    #    # Windows/macOS (TkAgg)
    #    mng.window.geometry(f"{win_width}x{win_height}+0+{win_height}")
    #except AttributeError:
    #    # Linux (Qt5Agg)
    #    mng.window.setGeometry(0, win_height, win_width, win_height)
    plt.show()
# *******************************************
# P_month_data.csv 2 weekly 2 allocation
# *******************************************
def convert_monthly_to_weekly_p(df: pd.DataFrame, lot_size: int):
    """
    Convert P_month_data.csv to weekly format with P_lot IDs.
    Parameters:
        df (pd.DataFrame): Monthly production data.
        lot_size (int): Lot size for production units.
    Returns:
        Tuple[pd.DataFrame, int, int]: Weekly production DataFrame with P_lots, planning range, and starting year.
    """
    # 1. 計画期間の取得
    start_year = df["year"].min()
    end_year = df["year"].max()
    plan_year_st = int(start_year)
    plan_range = int(end_year - start_year + 2)  # +1年分の余剰を含む
    # 2. データ整形（月次→日次）
    df = df.melt(id_vars=["product_name", "node_name", "year"], var_name="month", value_name="value")
    df["month"] = df["month"].str[1:].astype(int)
    df["year"] = df["year"].astype(int)
    df_daily = pd.DataFrame()
    for _, row in df.iterrows():
        year, month, value = row["year"], row["month"], row["value"]
        if pd.isna(value): continue
        days = pd.Timestamp(year, month, 1).days_in_month
        dates = pd.date_range(f"{year}-{month:02d}-01", periods=days)
        daily = pd.DataFrame({
            "product_name": row["product_name"],
            "node_name": row["node_name"],
            "date": dates,
            "value": [value] * days
        })
        df_daily = pd.concat([df_daily, daily])
    # 3. ISO週に変換
    df_daily["iso_year"] = df_daily["date"].dt.isocalendar().year
    df_daily["iso_week"] = df_daily["date"].dt.isocalendar().week.astype(str).str.zfill(2)
    df_weekly = df_daily.groupby(
        ["product_name", "node_name", "iso_year", "iso_week"]
    )["value"].sum().reset_index()
    # 4. P_lot数とlot ID生成
    df_weekly["P_lot"] = df_weekly["value"].apply(lambda x: math.ceil(x / lot_size))
    df_weekly["lot_id_list"] = df_weekly.apply(generate_p_lot_ids, axis=1)
    return df_weekly, plan_range, plan_year_st
def generate_p_lot_ids(row):
    lot_count = row["P_lot"]
    return [
        f"P_{row['node_name']}_{row['iso_year']}{row['iso_week']}_{i+1:04d}"
        for i in range(lot_count)
    ]
# ********************************:
def set_df_Plots2psi4supply(nodes_outbound: dict, df_weekly: pd.DataFrame, plan_year_st: int):
    """
    convert_monthly_to_weekly_p() で作成された P_lots を週別に psi4supply[w][3] にセットする。
    Parameters:
        nodes_outbound (dict): ノード名 → Nodeインスタンスの辞書（通常は self.nodes_outbound）
        df_weekly (DataFrame): 週次展開された P_lot データ（lot_id_list 列を含む）
        plan_year_st (int): 計画開始年（PSI Planner 全体で使用される基準年）
    """
    for _, row in df_weekly.iterrows():
        node_name = row["node_name"]
        iso_year = int(row["iso_year"])
        iso_week = int(row["iso_week"])
        lot_ids = row["lot_id_list"]
        # 年を跨ぐ週インデックス計算（PSI Plannerの週ベース表現に合わせる）
        week_index = (iso_year - plan_year_st) * 53 + int(iso_week)
        if node_name not in nodes_outbound:
            print(f"[Warning] Node '{node_name}' not found in nodes_outbound.")
            continue
        node = nodes_outbound[node_name]
        if len(node.psi4supply) <= week_index:
            print(f"[Warning] Week index {week_index} exceeds range for node '{node_name}'.")
            continue
        # psi4supply[w][3] = Production Lots
        node.psi4supply[week_index][3].extend(lot_ids)
from collections import defaultdict
from typing import Dict, List, Tuple
def perform_allocation(node, demand_map: Dict[int, List[str]], supply_weeks: List[Dict], lot_links_enabled=True) -> Tuple[Dict[int, List[str]], List[Dict], List[str]]:
    """
    指定ノードに対して需要S_lotsを供給週に割り当て、psi4supplyに流し込む。
    Parameters:
        node: Nodeインスタンス
        demand_map: {week: [S_lot_id, ...]} の辞書（psi4demandから抽出）
        supply_weeks: [{'week': w, 'capacity': n}, ...] 形式の供給スロット
        lot_links_enabled: 紐付け情報を保持するかどうか
    Returns:
        Tuple of:
            - allocation_result: {week: [S_lot_id, ...]}
            - allocation_links: [{'s_lot': ..., 'p_week': ...}]
            - warnings: [str, ...]
    """
    allocation_result = defaultdict(list)
    allocation_links = []
    warnings = []
    week_capacity = {w['week']: w['capacity'] for w in supply_weeks}
    sorted_weeks = sorted(week_capacity.keys())
    all_lots = []
    for w in sorted(demand_map):
        all_lots.extend(demand_map[w])
    week_idx = 0
    for s_lot in all_lots:
        attempts = 0
        assigned = False
        while attempts < len(sorted_weeks):
            current_week = sorted_weeks[week_idx % len(sorted_weeks)]
            if len(allocation_result[current_week]) < week_capacity[current_week]:
                allocation_result[current_week].append(s_lot)
                if lot_links_enabled:
                    allocation_links.append({
                        "s_lot": s_lot,
                        "p_week": current_week
                    })
                assigned = True
                break
            week_idx += 1
            attempts += 1
        if not assigned:
            warnings.append(f"Cannot allocate {s_lot}: all weeks full")
        week_idx += 1
    # PSI Planner node に反映
    for w, lots in allocation_result.items():
        node.psi4supply[w][3] = lots  # P(w)スロット
    if lot_links_enabled:
        node.allocation_links = allocation_links  # optional: 保存用
    return dict(allocation_result), allocation_links, warnings
# **** MyGPT messages ****
#### この関数を使うことで、load_data_files() や allocation phase の整理が簡単になり、GUI上でも拡張しやすくなります。
#### 必要であれば、allocation_links をCSV出力したり、可視化したりする関数も追加できます。ご希望があればお知らせください。
# *******************************************
# End of P_month_data.csv 2 weekly 2 allocation
# *******************************************
# gui/app.py
class PSIPlannerApp:
    def __init__(self, root, config, psi_env):
        self.root = root
        self.config = config
        self.root.title(self.config.APP_NAME)
        # === 追加: backend 環境 ===
        self.psi = psi_env  # PlanEnv or SqlPlanEnv
        self.psi_env = psi_env  # PlanEnv or SqlPlanEnv
        #self.psi = psi_env = PlanEnv(cfg) # PlanEnv or SqlPlanEnv
        #@250821 ADD {product_name:root_node,,,,}
        self.global_nodes = {**psi_env.global_nodes}
        #self.gui_prod_root_OT = {**psi_env.prod_tree_dict_OT}
        #self.gui_prod_root_IN = {**psi_env.prod_tree_dict_IN}
        #self.gui_prod_root_all = {**psi_env.prod_tree_dict_OT, **psi_env.prod_tree_dict_IN}
        self.info_window = None
        self.tree_structure = None
        # setup_uiの前にproduct selectを初期化
        self.product_name_list = []
        self.product_selected = None
        #@250826 製品選択comb box初期処理
        # ★ ここで一度だけ env → app へコピー
        self._hydrate_from_env()

        # Scenario
        # setup_uiの前にset
        #self.active_scenario_id = None   # None=ベース
        # …既存コードの直後〜最初のUI生成前あたりで
        if not hasattr(self, "active_scenario_id"):
            self.active_scenario_id = None  # None = BASE

        # 必ず setup_ui を先に呼び出す
        self.setup_ui()

        # 必要な初期化処理を後から呼び出す
        self.initialize_parameters()
        #@ STOP moved to config.py
        #self.lot_size     = 2000      # 初期値
        #self.plan_year_st = 2022      # 初期値
        #self.plan_range   = 2         # 初期値
        #self.pre_proc_LT  = 13        # 初期値 13week = 3month
        #self.market_potential = 0     # 初期値 0
        #self.target_share     = 0.5   # 初期値 0.5 = 50%
        #self.total_supply     = 0     # 初期値 0
        
        # ********************************
        # PSI planner
        # ********************************
        self.outbound_data = None
        self.inbound_data = None
        # PySI tree
        self.node_dict          = {} # nodes_all IN&OUT
        self.root_node_outbound = None
        self.nodes_outbound     = None
        self.leaf_nodes_out     = []
        self.root_node_inbound  = None
        self.nodes_inbound      = None
        self.leaf_nodes_in      = []
        self.root_node_out_opt  = None
        self.nodes_out_opt      = None
        self.leaf_nodes_opt     = []
        self.optimized_root     = None
        self.optimized_nodes    = None
        self.node_psi_dict_In4Dm = {}  # 需要側 PSI 辞書
        self.node_psi_dict_In4Sp = {}  # 供給側 PSI 辞書
        # Evaluation on PSI
        self.total_revenue = 0
        self.total_profit  = 0
        self.profit_ratio  = 0
        # by product select view
        self.prod_tree_dict_IN = {}
        self.prod_tree_dict_OT = {}
        # view
        self.select_node = None
        self.G = None
        # Optimise
        self.Gdm_structure = None
        self.Gdm = None
        self.Gsp = None
        self.pos_E2E = None
        self.flowDict_opt = {} #None
        self.flowCost_opt = {} #None
        self.total_supply_plan = 0
        # loading files
        self.directory = None
        self.load_directory = None
        self.base_leaf_name = {} # { product_name: leaf_node_name, ,,,}



        # supply_plan / decoupling / buffer stock
        self.decouple_node_dic = {}
        self.decouple_node_selected = []

        # === ここを追加 ===
        if self.psi is not None:
            print("[DEBUG] env class:", type(self.psi).__name__)
            print("[DEBUG] products:", getattr(self.psi, "product_name_list", []))
            self._bind_env_to_gui(self.psi)
        else:
            print("[DEBUG] psi env is None (CSVメニューから読み込み想定)")
        # どこか早いタイミングで（__init__ の末尾など）
        self.total_revenue = 0
        self.total_profit  = 0
        self.decouple_node_selected = []   # ← これが無いと AttributeError
        # env バインドが済んだ直後あたりで
        self._ensure_plan_window()
        # cost_attach
        self.cost_df = None


    def _set_network_title(self):
        self._ensure_network_axes()
        ax = self.ax_network
        rev = getattr(self, "total_revenue", 0) or 0
        prof = getattr(self, "total_profit", 0) or 0
        # 数値化（念のため）
        try:
            rev = round(float(rev))
            prof = round(float(prof))
        except Exception:
            rev = int(rev or 0)
            prof = int(prof or 0)
        ratio = round((prof / rev) * 100, 1) if rev else 0.0
        ax.set_title(
            f"PySI Optimized Supply Chain Network\n"
            f"REVENUE: {rev:,} | PROFIT: {prof:,} | PROFIT_RATIO: {ratio}%",
            fontsize=10
        )
    def _detect_default_decouple_nodes(self, product_name: str | None = None):
        """
        デカップル（バッファ）拠点の初期集合を返す。
        優先: node.stock_buffer / node.decouple_node フラグ
        次点: 名前が 'DAD' で始まる拠点（完成品出荷ヤード）
        """
        names = set()
        # Planツリー（製品別）が取れるならそこから
        env = getattr(self, "psi", None)
        root = None
        if product_name and env and getattr(env, "prod_tree_dict_OT", None):
            root = env.prod_tree_dict_OT.get(product_name)
        if root is None:
            # フォールバック：現在の outbound ノード辞書
            nodes_dict = getattr(self, "nodes_outbound", {}) or {}
            for n in nodes_dict.values():
                if getattr(n, "stock_buffer", False) or getattr(n, "decouple_node", False):
                    names.add(n.name)
                elif str(getattr(n, "name", "")).startswith("DAD"):
                    names.add(n.name)
            return sorted(names)
        # 製品ツリーを走査
        stack = [root]
        while stack:
            n = stack.pop()
            # flag があれば優先
            if getattr(n, "stock_buffer", False) or getattr(n, "decouple_node", False):
                names.add(n.name)
            # 無ければ DAD*
            elif str(getattr(n, "name", "")).startswith("DAD"):
                names.add(n.name)
            for c in getattr(n, "children", []) or []:
                stack.append(c)
        return sorted(names)
    # @FIX: 計画ウィンドウ（開始年・年数）を必ず決める
    def _ensure_plan_window(self):
        # 既に入っていれば何もしない
        if getattr(self, "plan_year_st", None) and getattr(self, "plan_range", None):
            return
        # まずはデフォルト（最後の砦）
        plan_year_st = 2024
        plan_range   = 3   # 年数
        # Config に既定があれば優先
        cfg = getattr(self, "config", None)
        if cfg:
            plan_year_st = int(getattr(cfg, "plan_year_st", plan_year_st) or plan_year_st)
            plan_range   = int(getattr(cfg, "plan_range",   plan_range)   or plan_range)
        # SqlPlanEnv に値がぶら下がっていれば最優先
        env = getattr(self, "psi", None)
        if env:
            py = getattr(env, "plan_year_st", None)
            pr = getattr(env, "plan_range", None)
            if isinstance(py, int) and py > 0: plan_year_st = py
            if isinstance(pr, int) and pr > 0: plan_range   = pr
            # さらに DB から推定（calendar445 or weekly_demand）
            db_path = getattr(env, "db_path", None)
            if not db_path:
                # env.con（sqlite3.Connection）を持っているケース
                con = getattr(env, "con", None)
            else:
                try:
                    con = sqlite3.connect(db_path)
                except Exception:
                    con = None
            try:
                if con:
                    cur = con.cursor()
                    # calendar445 があればそこから（最も確実）
                    try:
                        row = cur.execute("SELECT MIN(iso_year), MAX(iso_year) FROM calendar445").fetchone()
                        if row and row[0] is not None:
                            plan_year_st = int(row[0])
                            plan_range   = int(row[1] - row[0] + 1)
                    except Exception:
                        # weekly_demand からも推定できる
                        row = cur.execute("SELECT MIN(iso_year), MAX(iso_year) FROM weekly_demand").fetchone()
                        if row and row[0] is not None:
                            plan_year_st = int(row[0])
                            plan_range   = int(row[1] - row[0] + 1)
            finally:
                if db_path and con:
                    try: con.close()
                    except: pass
        # 確定
        self.plan_year_st = int(plan_year_st)
        self.plan_range   = int(plan_range)
        # もしエントリがあるなら同期しておく（存在しない環境でもOKなように try で）
        try:
            if hasattr(self, "plan_year_entry"):
                self.plan_year_entry.delete(0, "end")
                self.plan_year_entry.insert(0, str(self.plan_year_st))
            if hasattr(self, "plan_range_entry"):
                self.plan_range_entry.delete(0, "end")
                self.plan_range_entry.insert(0, str(self.plan_range))
        except Exception:
            pass
        print(f"[PLAN] plan_year_st={self.plan_year_st}, plan_range={self.plan_range}")
    # 同ファイルのどこか（クラス内）に追加
    def _hydrate_from_env(self):
        env = getattr(self, "psi", None)
        self.prod_tree_dict_OT = (getattr(env, "prod_tree_dict_OT", {}) or {})
        self.prod_tree_dict_IN = (getattr(env, "prod_tree_dict_IN", {}) or {})
        # 製品リスト
        keys_ot = list(self.prod_tree_dict_OT.keys())
        keys_in = list(self.prod_tree_dict_IN.keys())
        self.product_name_list = sorted(set(keys_ot or keys_in))
        # 初期選択
        if self.product_name_list and not getattr(self, "product_selected", None):
            self.product_selected = self.product_name_list[0]
        # ルートの初期セット（無ければ None のままでもOK）
        p = self.product_selected
        self.root_node_outbound = self.prod_tree_dict_OT.get(p) if p else None
        self.root_node_inbound  = self.prod_tree_dict_IN.get(p, self.root_node_outbound) if p else None
    def _bind_env_to_gui(self, env):
        # 1) 製品リスト
        self.product_name_list = list(getattr(env, "product_name_list", []))
        if not self.product_name_list:
            print("[WARN] product_name_list is empty; skip binding.")
            return
        # 2) prod ツリー辞書を GUI 側にコピー（INが空ならOTでフォールバック）
        env_ot = getattr(env, "prod_tree_dict_OT", {}) or {}
        env_in = getattr(env, "prod_tree_dict_IN", {}) or {}
        if not env_in:
            env_in = env_ot
        # dictコピー（参照切り離し）
        self.prod_tree_dict_OT = dict(env_ot)
        self.prod_tree_dict_IN = dict(env_in)
        # 3) 選択製品の決定
        if not getattr(self, "product_selected", None) or self.product_selected not in self.product_name_list:
            self.product_selected = self.product_name_list[0]
        # 4) ルート取得（INが無ければOTにフォールバック）
        r_ot = self.prod_tree_dict_OT.get(self.product_selected)
        r_in = self.prod_tree_dict_IN.get(self.product_selected, r_ot)
        if r_ot is None:
            print(f"[WARN] No root found for product={self.product_selected}; skip show_psi.")
            return
        # 5) 物理 Node 世界の辞書（on_network_click 用）を dict 化
        self.nodes_outbound = {} if r_ot is None else {n.name: n for n in self._walk_nodes(r_ot)}
        self.nodes_inbound  = {} if r_in is None else {n.name: n for n in self._walk_nodes(r_in)}
        # 6) 以降、UI部品（コンボ等）更新...（省略）
        # 7) 最後に描画呼び出し
        #self.show_psi_overview("outbound", "demand", self.product_selected)
        self.show_psi_by_product("outbound", "demand", self.product_selected)
    def _bind_env_to_gui(self, env):
        """SQL/CSVバックエンドからGUIへ、製品リストとツリー辞書を安全にバインドする。"""
        # 0) envを保持
        self.psi = env
        # 1) 製品リストの受け取り
        products = list(getattr(env, "product_name_list", []))
        if not products:
            print("[WARN] _bind_env_to_gui: product_name_list is empty; skip drawing.")
        self.product_name_list = products
        # 2) prodツリー辞書をコピー（INが空ならOTをフォールバック）
        env_ot = dict(getattr(env, "prod_tree_dict_OT", {}) or {})
        env_in = dict(getattr(env, "prod_tree_dict_IN", {}) or {})
        #@250916 STOP GO
        if not env_in:
            env_in = env_ot.copy()
        self.prod_tree_dict_OT = env_ot
        self.prod_tree_dict_IN = env_in
        # 3) 選択製品を決定（前回選択を優先）
        prev = getattr(self, "product_selected", None)
        if prev in products:
            selected = prev
        else:
            selected = products[0] if products else None
        self.product_selected = selected
        # 4) プルダウン（Combobox）に値を投入＆選択反映
        if hasattr(self, "cb_product"):
            try:
                self.cb_product["values"] = products
                if selected is not None:
                    self.cb_product.set(selected)
            except Exception as e:
                print(f"[WARN] combobox bind failed: {e}")
        # 5) ルート取得（INはOTフォールバック）
        r_ot = self.prod_tree_dict_OT.get(selected) if selected else None
        r_in = self.prod_tree_dict_IN.get(selected, r_ot) if selected else None
        self.root_node_outbound = r_ot
        self.root_node_inbound  = r_in
        # 6) 各世界の辞書を構築
        #   - PlanNode世界（製品別 PSI用）
        self.nodes_prod_outbound = {n.name: n for n in self._walk_nodes(r_ot)} if r_ot else {}
        self.nodes_prod_inbound  = {n.name: n for n in self._walk_nodes(r_in)} if r_in else {}
        #   - 物理ノード世界（GUIネットワーク用）※必要なら同根でOK / ここで辞書化しておく
        self.nodes_outbound = {n.name: n for n in self._walk_nodes(r_ot)} if r_ot else {}
        self.nodes_inbound  = {n.name: n for n in self._walk_nodes(r_in)} if r_in else {}
        # 7) 描画（存在チェック付き）
        # ネットワーク図（関数名はプロジェクトに合わせて）
        try:
            if hasattr(self, "view_nx_matlib4opt"):
                self.view_nx_matlib4opt()  # ネットワーク更新
            elif hasattr(self, "show_network_by_product"):
                self.show_network_by_product(selected)
        except Exception as e:
            print(f"[INFO] network view skipped: {e}")
        # PSIパネル
        #cb_product がまだ作られていないタイミング（初期化順の競合）
        #psi が未バインド／製品辞書が空のとき
        #prod が辞書にない値（古い状態が残っている等）
        try:
            if not getattr(self, "psi", None):
                return  # まだ環境がない
            names = list((getattr(self.psi, "prod_tree_dict_OT", {}) or {}).keys())
            prod = ""
            if hasattr(self, "cb_product"):
                prod = (self.cb_product.get() or "").strip()
            if not prod:
                prod = (getattr(self, "product_selected", "") or (names[0] if names else ""))
            if prod and prod in names:
                self.product_selected = prod  # 状態をそろえる
                #self.show_psi_overview(prod, primary_layer="supply", fallback_to_demand=True)
                self.show_psi_overview(prod, primary_layer="supply",
                            fallback_to_demand=True, skip_empty=True)
        except Exception as e:
            print(f"[INFO] network view skipped: {e}")
        #@STOP
        #if selected:
        #    #self.show_psi_overview("outbound", "demand", selected)
        #    #self.show_psi_by_product("outbound", "demand", selected)
        #    self.show_psi_overview(prod, primary_layer="supply",
        #                fallback_to_demand=True, skip_empty=True)
    # --- ユーティリティ: DFSでノード列挙 ---
    #def _walk_nodes_OLD(self, root):
    #    stack = [root]; seen = set()
    #    while stack:
    #        n = stack.pop()
    #        if id(n) in seen:
    #            continue
    #        seen.add(id(n))
    #        yield n
    #        for c in getattr(n, "children", []) or []:
    #            stack.append(c)
    def _walk_nodes(self, root, order: str = "post"):
        """
        木の走査ヘルパ
        order="post": 子→親（post-order）
        order="pre" : 親→子（pre-order）
        """
        if not root:
            return []
        if order == "post":
            st = [(root, False)]
            out = []
            while st:
                n, done = st.pop()
                if n is None:
                    continue
                if done:
                    out.append(n)
                else:
                    st.append((n, True))
                    for c in getattr(n, 'children', []) or []:
                        st.append((c, False))
            return out
        # pre
        st = [root]
        out = []
        while st:
            n = st.pop()
            if n is None:
                continue
            out.append(n)
            ch = getattr(n, 'children', []) or []
            for c in reversed(ch):
                st.append(c)
        return out
    def _apply_selected_product(self, prod: str):
        """env から root/out/in・ノード集合・葉集合を self.* に反映"""
        # 1) root を取得（SqlPlanEnv でも PlanEnv でもOK）
        r_ot = r_in = None
        if hasattr(self.psi, "get_roots"):
            try:
                r_ot, r_in = self.psi.get_roots(prod)
            except Exception:
                pass
        if r_ot is None:
            r_ot = (getattr(self, "prod_tree_dict_OT", {}) or {}).get(prod)
        if r_in is None:
            r_in = (getattr(self, "prod_tree_dict_IN", {}) or {}).get(prod, r_ot)
        self.root_node_outbound = r_ot
        self.root_node_inbound  = r_in
        # 2) ノード集合と葉集合（必要最小限）
        def _walk(n):
            if n is None:
                return []
            st, seen, out = [n], set(), []
            while st:
                x = st.pop()
                if id(x) in seen:
                    continue
                seen.add(id(x))
                out.append(x)
                for c in getattr(x, "children", []) or []:
                    st.append(c)
            return out
        def _leaves(n):
            return [x for x in _walk(n) if not getattr(x, "children", [])]
        #_walk_nodes は generator なので、そのままだと .get() は使えません
        #代入時に {n.name: n for n in ...} で 名前→Node の辞書に変換
        #念のため if n is not None を入れておくと安全
        #ルートが None の可能性がある場合は、内包表記の前で空辞書にフォールバック
        self.nodes_outbound = {} if r_ot is None else {n.name: n for n in self._walk_nodes(r_ot)}
        self.nodes_inbound  = {} if r_in is None else {n.name: n for n in self._walk_nodes(r_in)}
        self.leaf_nodes_out = _leaves(r_ot)
        self.leaf_nodes_in  = _leaves(r_in)
        # デバッグ
        if self.root_node_outbound is None:
            print(f"[WARN] root_node_outbound is None for product={prod}")
    # --- Matplotlib Axes の確保（無ければ作る） ---
    def _ensure_network_axes(self, parent=None):
        if getattr(self, "canvas_network", None) and self.canvas_network.get_tk_widget().winfo_exists():
            return  # 既にある
        if parent is None:
            parent = getattr(self, "left_panel", None) or self.frame
        fig = Figure(figsize=(6, 4), dpi=100)
        ax  = fig.add_subplot(111)
        cv  = FigureCanvasTkAgg(fig, master=parent)
        cv.get_tk_widget().pack(fill="both", expand=True)
        self.fig_network   = fig
        self.ax_network    = ax
        self.canvas_network= cv
    # PSIPlannerApp クラス内に1本だけ
    def _ensure_psi_area(self, parent):
        import tkinter as tk
        from tkinter import ttk
        # すでに同じ親に作られていてウィジェットも生きているなら何もしない
        if (getattr(self, "_psi_area_parent", None) is parent and
            getattr(self, "canvas_psi", None) and
            self.canvas_psi.winfo_exists()):
            return
        # ── 既存を片付ける（親が違う／壊れている場合は作り直し）──
        for name in ("canvas_psi", "vsb_psi", "scrollable_frame"):
            w = getattr(self, name, None)
            if w:
                try:
                    w.destroy()
                except Exception:
                    pass
                setattr(self, name, None)
        self._psi_window = None
        # ── 新規構築（必ず parent 配下に作る）──
        self.canvas_psi = tk.Canvas(parent, highlightthickness=0)
        self.vsb_psi    = ttk.Scrollbar(parent, orient="vertical",
                                        command=self.canvas_psi.yview)
        self.canvas_psi.configure(yscrollcommand=self.vsb_psi.set)
        self.canvas_psi.pack(side="left", fill="both", expand=True)
        self.vsb_psi.pack(side="right", fill="y")
        self.scrollable_frame = ttk.Frame(self.canvas_psi)
        self._psi_window = self.canvas_psi.create_window(
            (0, 0), window=self.scrollable_frame, anchor="nw"
        )
        def _on_cfg(event=None):
            # スクロール領域と横幅フィット
            self.canvas_psi.configure(scrollregion=self.canvas_psi.bbox("all"))
            try:
                self.canvas_psi.itemconfigure(self._psi_window,
                                            width=self.canvas_psi.winfo_width())
            except Exception:
                pass
        self.scrollable_frame.bind("<Configure>", _on_cfg)
        self.canvas_psi.bind("<Configure>", _on_cfg)
        # 親を記録（次回の無駄な再作成を防止）
        self._psi_area_parent = parent
    #@STOP
    #def _get_selected_product(self) -> str | None:
    #    """Combobox または保持済みの product_selected から現在の製品名を返す"""
    #    try:
    #        if getattr(self, "cb_product", None):
    #            name = (self.cb_product.get() or "").strip()
    #            if name:
    #                return name
    #    except Exception:
    #        pass
    #    return getattr(self, "product_selected", None)
    def _get_selected_product(self) -> str | None:
        """Combobox優先で現在の製品名を返す。なければ既存の保持値。"""
        name = ""
        try:
            name = (self.cb_product.get() or "").strip()
        except Exception:
            pass
        if not name:
            name = getattr(self, "product_selected", None)
        return name or None
    def on_product_changed(self, *_):
        #@STOP GO
        # ==== helper for product selection ====
        prod = self._get_selected_product()
        if not prod:
            return
        self.product_selected = prod
        self._ensure_plan_window()   # ← 追加
        # 選択値の決定（既存ロジックでOK）
        selected = None
        if hasattr(self, "cb_product"):
            try: selected = self.cb_product.get()
            except Exception: pass
        if not selected:
            selected = getattr(self, "product_selected", None) or (
                self.product_name_list[0] if getattr(self, "product_name_list", None) else None
            )
        self.product_selected = selected
        # ★ ここで必ず初期化（安全）
        self.decouple_node_selected = self._detect_default_decouple_nodes(selected)
        # 既存：root の再セット/辞書の再構築など
        r_ot = self.prod_tree_dict_OT.get(selected) if selected else None
        r_in = self.prod_tree_dict_IN.get(selected, r_ot) if selected else None
        self.root_node_outbound = r_ot
        self.root_node_inbound  = r_in
        self.nodes_prod_outbound = {n.name: n for n in self._walk_nodes(r_ot)} if r_ot else {}
        self.nodes_prod_inbound  = {n.name: n for n in self._walk_nodes(r_in)} if r_in else {}
        self.nodes_outbound      = {n.name: n for n in self._walk_nodes(r_ot)} if r_ot else {}
        self.nodes_inbound       = {n.name: n for n in self._walk_nodes(r_in)} if r_in else {}
        # 描画
        # ← これだけでOK（現在の view_mode に合わせて片方だけ描画、右のPSIも揃う）
        self._redraw_current_view(selected)
        #try:
        #    if hasattr(self, "view_nx_matlib4opt"):
        #        self.view_nx_matlib4opt()
        #    elif hasattr(self, "show_network_by_product"):
        #        self.show_network_by_product(selected)
        #except Exception as e:
        #    print(f"[INFO] network view skipped: {e}")
        #if selected:
        #    self.show_psi_by_product("outbound", "demand", selected)
    #重要ポイント
    #ここでは prod という未定義変数は使わず、name を最後まで渡します。
    #show_psi_overview() は内部で古い Figure/Canvas を破棄しているので、常に最新のグラフに差し替わります。
    #3) 既存の _refresh_views() も “選択名” を使うよう安全化（任意）
    def _refresh_views_ANY(self):
        selected = self._get_selected_product()
        try:
            eval_supply_chain_cost(self.root_node_outbound)
            eval_supply_chain_cost(self.root_node_inbound)
        except Exception as e:
            print("[WARN] eval_supply_chain_cost:", e)
        try:
            self.view_nx_matlib4opt()
        except Exception as e:
            print("[WARN] network redraw:", e)
        try:
            if selected:
                if not getattr(self, "scrollable_frame", None):
                    self._ensure_psi_area(self.frame_psi)
                self.show_psi_overview(
                    selected,
                    primary_layer="supply",
                    fallback_to_demand=True,
                    skip_empty=True,
                )
        except Exception as e:
            print("[WARN] psi overview:", e)
## app.py （抜粋）
#from pysi.plan import engines as eng
#
#class PSIPlannerApp:
#    ...
    def _get_roots_safe(self):
        prod, out_root, in_root = self._get_roots()
        if not (out_root and in_root):
            print("[WARN] roots not ready");
            return None, None
        return out_root, in_root
    
    def run_outbound_backward_leaf_to_MOM(self):
        out_root, in_root = self._get_roots_safe()
        if not out_root: return
        out_rt, in_rt = eng.outbound_backward_leaf_to_MOM(out_root, in_root, layer="demand")
        self.root_node_outbound, self.root_node_inbound = out_rt, in_rt
        self._refresh_views()
    
    def run_inbound_mom_leveling(self):
        out_root, in_root = self._get_roots_safe()
        if not in_root: return
        mom_name = self.var_mom.get().strip() or "MOM"
        out_rt, in_rt = eng.inbound_MOM_leveling_vs_capacity(out_root, in_root, mom_name=mom_name)
        self.root_node_outbound, self.root_node_inbound = out_rt, in_rt
        self._refresh_views()
    
    def run_inbound_backward_MOM_to_leaf(self):
        out_root, in_root = self._get_roots_safe()
        if not in_root: return
        out_rt, in_rt = eng.inbound_backward_MOM_to_leaf(out_root, in_root, layer="demand")
        self.root_node_outbound, self.root_node_inbound = out_rt, in_rt
        self._refresh_views()
    
    def run_inbound_forward_leaf_to_MOM(self):
        out_root, in_root = self._get_roots_safe()
        if not in_root: return
        out_rt, in_rt = eng.inbound_forward_leaf_to_MOM(out_root, in_root, layer="supply")
        self.root_node_outbound, self.root_node_inbound = out_rt, in_rt
        self._refresh_views()
    
    def run_push_pull(self):
        out_root, in_root = self._get_roots_safe()
        if not out_root: return
        # **** PUSH&PULL planning engine ****
        decouples = self.decouple_node_selected or []
        out_rt, in_rt = eng.push_pull(out_root, in_root, decouple_nodes=decouples)
        self.root_node_outbound, self.root_node_inbound = out_rt, in_rt
        # run_push_pull() の冒頭～Evaluator直前
        self._ensure_cost_df()  # ← 追加
    
        #@STOP
        #from pysi.evaluate.cost_attach import build_cost_lookup_from_df, attach_cost_to_tree
        #cost_lut = build_cost_lookup_from_df(self.cost_df)
        #prod = self.product_selected
        #
        #self.root_node_outbound_byprod = self.prod_tree_dict_OT[prod]
        #self.root_node_inbound_byprod  = self.prod_tree_dict_IN[prod]
        #attach_cost_to_tree(self.root_node_outbound_byprod, prod, cost_lut, verbose=False)
        #attach_cost_to_tree(self.root_node_inbound_byprod,  prod, cost_lut, verbose=False)
        #
        #self.update_evaluation_results4multi_product()
        #@STOP
        #self._ensure_cost_df()
    
        from pysi.evaluate.cost_attach import build_cost_lookup_from_df, attach_cost_to_tree
    
        lut = build_cost_lookup_from_df(self.cost_df)
        prod = self.product_selected
        out_root = self.prod_tree_dict_OT[prod]
        in_root  = self.prod_tree_dict_IN[prod]
        ok_out, miss_out = attach_cost_to_tree(out_root, prod, lut, verbose=True)
        ok_in,  miss_in  = attach_cost_to_tree(in_root,  prod, lut, verbose=True)
        print(f"[COST] attach OUT: {ok_out} ok, {len(miss_out)} missing -> {miss_out}")
        print(f"[COST] attach IN : {ok_in} ok, {len(miss_in)} missing -> {miss_in}")

        #@STOP
        ## **** attach cost to nodes (selected product only) ****
        #try:
        #    from pysi.evaluate.cost_attach import build_cost_lookup_from_df, attach_cost_to_tree
        #    cost_lut = build_cost_lookup_from_df(self.cost_df)  # product_name,node_name 列が前提
        #    prod = self.product_selected
        #
        #    # 評価で使う “製品別ルート” に貼る（OUT/IN 両方）
        #    self.root_node_outbound_byprod = self.prod_tree_dict_OT[prod]
        #    self.root_node_inbound_byprod  = self.prod_tree_dict_IN[prod]
        #
        #    attach_cost_to_tree(self.root_node_outbound_byprod, prod, cost_lut, verbose=False)
        #    attach_cost_to_tree(self.root_node_inbound_byprod,  prod, cost_lut, verbose=False)
        #
        #except Exception as e:
        #    print("[COST] attach failed:", e)

        # **** Evaluator ****
        self.update_evaluation_results4multi_product()
        self._refresh_views()

    def _refresh_views(self):
        #self.update_evaluation_results()
        #self.decouple_node_selected = []
        #self.view_nx_matlib()
        ## PSI 表示はGUI内の既存ハンドラで
        prod, out_root, in_root = self._get_roots()
        try:
            eval_supply_chain_cost(self.root_node_outbound)
            eval_supply_chain_cost(self.root_node_inbound)
        except Exception as e:
            print("[WARN] eval_supply_chain_cost:", e)
        # 再描画（既存の描画関数名に合わせて調整）
        try:
            self.view_nx_matlib4opt()
        except Exception as e:
            print("[WARN] network redraw:", e)
        # 旧：
        # self.show_psi_by_product("outbound", "demand", prod)
        # self.show_psi_by_product("outbound", "supply", prod)
        # self.show_psi_by_product("inbound",  "demand", prod)
        # self.show_psi_by_product("inbound",  "supply", prod)
        # 新：俯瞰 1 枚（基本は supply）
        try:
            #self.show_psi_overview(prod, primary_layer="supply", fallback_to_demand=True)
            #self.show_psi_overview(prod, layer="supply", skip_empty=True)
            #self.show_psi_overview(prod, primary_layer="supply",
            #            fallback_to_demand=True, skip_empty=True)
            #@STOP
            #_selected = self._get_selected_product()
            if prod:
                self.show_psi_overview(prod, primary_layer="supply", fallback_to_demand=True)
            #if _selected:
                #self.show_psi_overview(_selected, primary_layer="supply", fallback_to_demand=True)
        except Exception as e:
            print("[WARN] psi overview:", e)
    # ==== helper
    def _safe_initial_overview(self):
        try:
            if not getattr(self, "psi", None):
                return
            names = list((getattr(self.psi, "prod_tree_dict_OT", {}) or {}).keys())
            prod = ""
            if hasattr(self, "cb_product"):
                prod = (self.cb_product.get() or "").strip()
            if not prod:
                prod = (getattr(self, "product_selected", "") or (names[0] if names else ""))
            if prod and prod in names:
                self.product_selected = prod
                self.show_psi_overview(prod, primary_layer="supply",
                                    fallback_to_demand=True, skip_empty=True)
        except Exception as e:
            import traceback; traceback.print_exc()
            print("[WARN] initial psi overview:", e)






    # **************************
    # scenario RUN and Save and compare
    # **************************
    # DBパス取得のヘルパ（あなたの実装に合わせて）
    def _get_db_path(self) -> str:
        try:
            return self.psi.db_path  # SQL版ならこういう属性があるはず
        except Exception:
            from pysi.gui.utils import get_db_path_from  # もし既存にあれば
            return get_db_path_from(self)

    def _run_and_save_OLD(self):
                
        from pysi.scenario.store import save_run_results, list_runs

        sid = getattr(self, "active_scenario_id", None)
        # まず既存のフル実行を回す（あなたの実装に合わせて）
        try:
            self._run_full_pipeline()
        except Exception as e:
            import traceback; traceback.print_exc()
        # その後に保存
        dbp = self._get_db_path()
        run_id = save_run_results(dbp, sid, label=f"{sid or 'BASE'} (GUI)")
        from tkinter import messagebox
        messagebox.showinfo("Scenario Run", f"Saved results.\nrun_id = {run_id}")


    def _run_and_save_OLD2(self):
        # 1) （あれば）フルパイプライン
        try:
            self._run_full_pipeline()
        except Exception as e:
            print("[WARN] full pipeline failed; saving snapshot only:", e)

        # 2) DBへ保存
        from pysi.scenario.store import save_run_results, get_db_path_from
        dbp = get_db_path_from(self.psi if hasattr(self, "psi") else self)
        sid = getattr(self, "active_scenario_id", None)
        run_id = save_run_results(dbp, sid, label=f"{sid or 'BASE'} (GUI)")
        print("[OK] saved run:", run_id)

        # 3) ちょっとしたフィードバック
        from tkinter import messagebox
        messagebox.showinfo("Run & Save", f"saved run: {run_id}")




    def _show_compare_popup_OLD(self):
        import sqlite3
        import matplotlib.pyplot as plt
        
        from pysi.scenario.store import save_run_results, list_runs

        dbp = self._get_db_path()
        sid  = getattr(self, "active_scenario_id", None)

        # 直近2本を取得（なければ警告）
        runs = list_runs(dbp, scenario_id=sid, limit=2)
        if len(runs) < 2:
            from tkinter import messagebox
            messagebox.showwarning("Compare Runs", "比較できるrunが2本以上ありません。")
            return

        # run_id抽出（最新→古い順に入ってくる想定）
        rA, rB = runs[0][0], runs[1][0]

        con = sqlite3.connect(dbp)
        sA = con.execute("SELECT total_revenue,total_cost,total_profit,profit_ratio FROM scenario_result_summary WHERE run_id=?", (rA,)).fetchone()
        sB = con.execute("SELECT total_revenue,total_cost,total_profit,profit_ratio FROM scenario_result_summary WHERE run_id=?", (rB,)).fetchone()
        con.close()

        if not sA or not sB:
            from tkinter import messagebox
            messagebox.showwarning("Compare Runs", "summaryが見つかりません。Run & Save を実行してください。")
            return

        import numpy as np
        labels = ["Revenue","Profit","Profit Ratio"]
        A = [float(sA[0] or 0), float(sA[2] or 0), float(sA[3] or 0)]
        B = [float(sB[0] or 0), float(sB[2] or 0), float(sB[3] or 0)]

        x = np.arange(len(labels)); w = 0.35
        fig, ax = plt.subplots(figsize=(6,3))
        ax.bar(x - w/2, A, width=w, label=rA[-8:], color="#4E79A7")
        ax.bar(x + w/2, B, width=w, label=rB[-8:], color="#F28E2B")
        ax.set_xticks(x, labels)
        ax.set_title(f"Scenario Compare ({sid or 'BASE'})")
        ax.legend()
        fig.tight_layout()
        plt.show()



    def _show_compare_popup_OLD2(self):
        import sqlite3
        import matplotlib.pyplot as plt
        import numpy as np
        from tkinter import messagebox

        from pysi.scenario.store import list_runs

        dbp = self._get_db_path()
        sid = getattr(self, "active_scenario_id", None)

        # まずは「現在シナリオ」の直近2本
        runs = list_runs(dbp, scenario_id=sid, limit=2)

        # 足りなければ「全シナリオ」から直近2本にフォールバック
        if len(runs) < 2:
            runs = list_runs(dbp, scenario_id=None, limit=2)

        if len(runs) < 2:
            messagebox.showwarning("Compare Runs", "比較できるrunが2本以上ありません。")
            return

        # run_id, scenario_id を取り出し（最新→古い）
        (rA_id, rA_sid, *_), (rB_id, rB_sid, *_) = runs

        con = sqlite3.connect(dbp)
        try:
            sA = con.execute(
                "SELECT total_revenue,total_cost,total_profit,profit_ratio "
                "FROM scenario_result_summary WHERE run_id=?", (rA_id,)
            ).fetchone()
            sB = con.execute(
                "SELECT total_revenue,total_cost,total_profit,profit_ratio "
                "FROM scenario_result_summary WHERE run_id=?", (rB_id,)
            ).fetchone()
        finally:
            con.close()

        if not sA or not sB:
            messagebox.showwarning("Compare Runs", "summaryが見つかりません。Run & Save を実行してください。")
            return

        labels = ["Revenue","Profit","Profit Ratio"]
        A = [float(sA[0] or 0), float(sA[2] or 0), float(sA[3] or 0)]
        B = [float(sB[0] or 0), float(sB[2] or 0), float(sB[3] or 0)]

        x = np.arange(len(labels)); w = 0.35
        fig, ax = plt.subplots(figsize=(6,3))
        # ラベルにシナリオIDを併記（BASEは見やすく）
        def _sid(s): return (s or "BASE")
        ax.bar(x - w/2, A, width=w, label=f"{_sid(rA_sid)} / {str(rA_id)[-8:]}", color="#4E79A7")
        ax.bar(x + w/2, B, width=w, label=f"{_sid(rB_sid)} / {str(rB_id)[-8:]}", color="#F28E2B")
        ax.set_xticks(x, labels)
        ax.set_title(f"Scenario Compare (view={_sid(sid)})")
        ax.legend()
        fig.tight_layout()
        plt.show()


    def _run_and_save_OLD(self):
        # 1) 計画 ①②③④⑤ をまとめて実行（手動と二重にならない）
        try:

            self._run_planning_sequence()

        except Exception as e:
            print("[WARN] planning sequence failed; saving snapshot only:", e)

        # 2) DBへ保存（GUIの cost_df を優先して渡す）
        from pysi.scenario.store import save_run_results, get_db_path_from
        dbp = get_db_path_from(self.psi if hasattr(self, "psi") else self)
        sid = getattr(self, "active_scenario_id", None)


        run_id = save_run_results(
            dbp, sid,
            label=f"{sid or 'BASE'} (GUI)",
            cost_df_override=getattr(self, "cost_df", None)  # ★ここが肝
        )


        print("[OK] saved run:", run_id)

        from tkinter import messagebox
        messagebox.showinfo("Run & Save", f"saved run: {run_id}")

    def _run_and_save(self):
        """
        右パネルの「Run & Save Results」ハンドラ。
        - ①②③④⑤ の計画シーケンスを一括実行
        - 実行前/後で Hook を発火（before_scenario_run / after_scenario_run）
        - DB に結果を書き出し、Run ID をダイアログで通知
        """
        # ---- HookBus（無ければ NOOP） ----
        try:
            from pysi.hooks.core import hooks as _hooks
        except Exception:
            class _Noop:
                def do_action(self, *a, **k):  # フォールバック
                    pass
            _hooks = _Noop()

        # ---- 共有情報（Hook にも渡す）----
        from pysi.scenario.store import save_run_results, get_db_path_from
        dbp = get_db_path_from(self.psi if hasattr(self, "psi") else self)
        sid = getattr(self, "active_scenario_id", None)

        # 1) PSI 実行の **直前** にフック
        _hooks.do_action(
            "before_scenario_run",
            gui=self,
            db_path=dbp,
            scenario_id=sid
        )

        # 2) 計画 ①②③④⑤ をまとめて実行（手動と二重にならない）
        try:
            self._run_planning_sequence()
        except Exception as e:
            print("[WARN] planning sequence failed; saving snapshot only:", e)

        # 3) DBへ保存（GUIで保持している cost_df を優先して渡す）
        run_id = None
        try:
            run_id = save_run_results(
                dbp,
                sid,
                label=f"{sid or 'BASE'} (GUI)",
                cost_df_override=getattr(self, "cost_df", None)  # ★ GUIの円グラフに使っている cost_df を優先
            )
            print("[OK] saved run:", run_id)
        except Exception as e:
            print("[ERROR] save_run_results failed:", e)
            # 失敗しても after フックは「run_id=None」で発火させておく（プラグイン側で分岐可能）

        # 4) 保存完了の **直後** にフック
        _hooks.do_action(
            "after_scenario_run",
            gui=self,
            db_path=dbp,
            scenario_id=sid,
            run_id=run_id
        )

        # 5) フィードバック
        from tkinter import messagebox
        if run_id is not None:
            messagebox.showinfo("Run & Save", f"saved run: {run_id}")
        else:
            messagebox.showwarning("Run & Save", "Run の保存に失敗しました（ログを確認してください）。")





    def _show_compare_popup_OLD3(self):
        import sqlite3, tkinter as tk
        from tkinter import messagebox
        import numpy as np
        import matplotlib
        matplotlib.rcParams["figure.dpi"] = 120  # 見やすさ
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        from pysi.scenario.store import list_runs

        dbp = self._get_db_path()
        sid = getattr(self, "active_scenario_id", None)

        # 1) まずは「現在シナリオ」の直近2本
        runs = list_runs(dbp, scenario_id=sid, limit=2)
        # 2) 足りなければ「全シナリオ」から直近2本にフォールバック
        if len(runs) < 2:
            runs = list_runs(dbp, scenario_id=None, limit=2)

        if len(runs) < 2:
            messagebox.showwarning("Compare Runs", "比較できるrunが2本以上ありません。")
            return

        # run_id, scenario_id を取り出し（最新→古い）
        (rA_id, rA_sid, *_), (rB_id, rB_sid, *_) = runs

        con = sqlite3.connect(dbp)
        try:
            q = "SELECT total_revenue,total_cost,total_profit,profit_ratio FROM scenario_result_summary WHERE run_id=?"
            sA = con.execute(q, (rA_id,)).fetchone()
            sB = con.execute(q, (rB_id,)).fetchone()
        finally:
            con.close()

        if not sA or not sB:
            messagebox.showwarning("Compare Runs", "summaryが見つかりません。Run & Save を実行してください。")
            return

        # データ準備
        labels = ["Revenue", "Profit", "Profit Ratio"]
        A = [float(sA[0] or 0), float(sA[2] or 0), float(sA[3] or 0)]
        B = [float(sB[0] or 0), float(sB[2] or 0), float(sB[3] or 0)]
        x = np.arange(len(labels)); w = 0.38

        # === Tk に埋め込む ===
        top = tk.Toplevel(self.root)
        top.title("Compare Runs")
        top.geometry("720x360")

        fig = Figure(figsize=(6.8, 3.0))
        ax = fig.add_subplot(111)
        ax.bar(x - w/2, A, width=w, label=f"{(rA_sid or 'BASE')} / {str(rA_id)[-8:]}", color="#4E79A7")
        ax.bar(x + w/2, B, width=w, label=f"{(rB_sid or 'BASE')} / {str(rB_id)[-8:]}", color="#F28E2B")
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_title(f"Scenario Compare (view={sid or 'BASE'})")
        ax.legend()
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=top)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)


    # pysi/gui/app.py の _show_compare_popup を置き換え
    def _show_compare_popup_OLD4(self):
        import sqlite3, tkinter as tk
        from tkinter import ttk, messagebox
        import numpy as np
        import matplotlib.pyplot as plt

        from pysi.scenario.store import list_runs, get_db_path_from

        dbp = get_db_path_from(self.psi if hasattr(self, "psi") else self)
        sid  = getattr(self, "active_scenario_id", None)

        # 直近の全ラン（シナリオ横断で十分多めに）
        all_runs = list_runs(dbp, scenario_id=None, limit=200)
        if not all_runs:
            messagebox.showwarning("Compare Runs", "保存済みの Run が見つかりません。")
            return

        # 表示用ラベル
        def _fmt(r):
            run_id, scn, started_at, label = r
            scn_disp = (scn or "BASE")
            meta = f"{started_at or ''}".strip()
            tag  = f"{label or ''}".strip()
            right = " / ".join([x for x in [scn_disp, meta, tag] if x])
            return f"{run_id}  —  {right}"

        labels = [_fmt(r) for r in all_runs]
        id_by_label = { _fmt(r): str(r[0]) for r in all_runs }
        scn_by_label = { _fmt(r): (r[1] or "BASE") for r in all_runs }

        # シナリオ別の最新リスト
        from collections import defaultdict
        by_scn = defaultdict(list)
        for r in all_runs:
            by_scn[r[1]].append(r)  # r[1] は None(BASE) or "TOBE_S1" 等

        def _latest(scn):   # 最新1本
            rr = by_scn.get(scn, [])
            return _fmt(rr[0]) if rr else None

        def _latest_two_same_scn(scn):  # 同一シナリオの最新2本
            rr = by_scn.get(scn, [])
            return ( _fmt(rr[0]), _fmt(rr[1]) ) if len(rr) >= 2 else ( _fmt(rr[0]) if rr else None, None )

        # UI
        win = tk.Toplevel(self.root)
        win.title("Compare Runs")

        frm = ttk.Frame(win); frm.pack(fill="both", expand=True, padx=8, pady=8)

        ttk.Label(frm, text="Run A").grid(row=0, column=0, sticky="w")
        cbA = ttk.Combobox(frm, values=labels, width=80, state="readonly"); cbA.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Label(frm, text="Run B").grid(row=1, column=0, sticky="w")
        cbB = ttk.Combobox(frm, values=labels, width=80, state="readonly"); cbB.grid(row=1, column=1, sticky="ew", padx=6)

        frm.rowconfigure(2, minsize=8)

        # プリセット・ボタン
        btns = ttk.Frame(frm); btns.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4,2))
        def use_same_scn():
            a, b = _latest_two_same_scn(sid)
            if a: cbA.set(a)
            if b: cbB.set(b)
        def use_vs_base():
            a = _latest(sid)
            b = _latest(None)
            if a: cbA.set(a)
            if b: cbB.set(b)
        def use_global_two():
            if len(labels) >= 2:
                cbA.set(labels[0]); cbB.set(labels[1])

        ttk.Button(btns, text="同一シナリオの最新2本", command=use_same_scn).pack(side="left", padx=2)
        ttk.Button(btns, text="現在シナリオ最新 vs BASE最新", command=use_vs_base).pack(side="left", padx=2)
        ttk.Button(btns, text="全体の最新2本（横断）", command=use_global_two).pack(side="left", padx=2)

        # デフォルト：同一シナリオの最新2本、なければ全体2本
        if len(by_scn.get(sid, [])) >= 2:
            use_same_scn()
        else:
            use_global_two()

        # 実行
        def _do_compare():
            la, lb = cbA.get(), cbB.get()
            if not la or not lb:
                messagebox.showwarning("Compare Runs", "Run A と Run B を選択してください。")
                return
            rA, rB = id_by_label[la], id_by_label[lb]

            con = sqlite3.connect(dbp)
            sA = con.execute(
                "SELECT total_revenue,total_cost,total_profit,profit_ratio FROM scenario_result_summary WHERE run_id=?",
                (rA,)
            ).fetchone()
            sB = con.execute(
                "SELECT total_revenue,total_cost,total_profit,profit_ratio FROM scenario_result_summary WHERE run_id=?",
                (rB,)
            ).fetchone()
            con.close()

            if not sA or not sB:
                messagebox.showwarning("Compare Runs", "summaryが見つかりません。Run & Save を実行してください。")
                return

            labels3 = ["Revenue","Profit","Profit Ratio"]
            A = [float(sA[0] or 0), float(sA[2] or 0), float(sA[3] or 0)]
            B = [float(sB[0] or 0), float(sB[2] or 0), float(sB[3] or 0)]

            x = np.arange(len(labels3)); w = 0.35
            fig, ax = plt.subplots(figsize=(6.0, 3.2))
            ax.bar(x - w/2, A, width=w, label=f"{scn_by_label[la]} / {rA}", color="#4E79A7")
            ax.bar(x + w/2, B, width=w, label=f"{scn_by_label[lb]} / {rB}", color="#F28E2B")
            ax.set_xticks(x, labels3)
            ax.set_title(f"Scenario Compare")
            ax.legend()
            fig.tight_layout()
            plt.show()

        go = ttk.Button(frm, text="Compare", command=_do_compare); go.grid(row=3, column=1, sticky="e", pady=(8,0))
        frm.columnconfigure(1, weight=1)



    def _show_compare_popup_OLD5(self):
        """
        Compare Runs… ダイアログ。
        - Run A / Run B を任意に選ぶ
        - プリセット: 同一シナリオ最新2本 / 現在シナリオ最新 vs BASE最新 / 全体の最新2本
        - 図は Tkinter の Toplevel に Figure を埋め込んで表示（plt.show は使わない）
        """
        import tkinter as tk
        from tkinter import ttk, messagebox
        import sqlite3, numpy as np
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
        from pysi.scenario.store import get_db_path_from

        dbp = get_db_path_from(self.psi if hasattr(self, "psi") else self)
        cur_sid = getattr(self, "active_scenario_id", None)   # None => BASE

        # --------------------------
        # DB helpers
        # --------------------------
        def _fetch_rows(sql, args=()):
            con = sqlite3.connect(dbp)
            try:
                return con.execute(sql, args).fetchall()
            finally:
                con.close()

        def fetch_runs_for_sid(sid, limit=20):
            """sid=None のときは NULL と 'BASE' の両方を拾う"""
            if sid is None:
                return _fetch_rows("""
                    SELECT run_id, scenario_id, started_at, COALESCE(label,'')
                    FROM scenario_run
                    WHERE scenario_id IS NULL OR scenario_id='BASE'
                    ORDER BY rowid DESC LIMIT ?""", (limit,))
            else:
                return _fetch_rows("""
                    SELECT run_id, scenario_id, started_at, COALESCE(label,'')
                    FROM scenario_run
                    WHERE scenario_id = ?
                    ORDER BY rowid DESC LIMIT ?""", (sid, limit))

        def fetch_latest_two_overall():
            return _fetch_rows("""
                SELECT run_id, scenario_id, started_at, COALESCE(label,'')
                FROM scenario_run
                ORDER BY rowid DESC LIMIT 2""")

        def fetch_summary(run_id):
            rows = _fetch_rows("""
                SELECT total_revenue,total_cost,total_profit,profit_ratio
                FROM scenario_result_summary WHERE run_id=?""", (run_id,))
            return rows[0] if rows else None

        # --------------------------
        # データ→表示文字列
        # --------------------------
        def _disp_of(row):
            rid, sid, started, label = row
            sid_disp = sid if (sid and sid != "BASE") else "BASE"
            ts = (started or "")
            lab = (label or "").strip()
            return f"{rid:>4} — {sid_disp} / {ts} / {lab}"

        # 候補（最新50件を横断で）
        rows_all = _fetch_rows("""
            SELECT run_id, scenario_id, started_at, COALESCE(label,'')
            FROM scenario_run
            ORDER BY rowid DESC LIMIT 50""")
        choices = [_disp_of(r) for r in rows_all]
        disp2row = {_disp_of(r): r for r in rows_all}

        # --------------------------
        # ダイアログ UI
        # --------------------------
        win = tk.Toplevel(self.root)
        win.title("Compare Runs")
        win.resizable(True, False)

        frm = ttk.Frame(win); frm.pack(fill="x", padx=8, pady=8)
        ttk.Label(frm, text="Run A").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        cbA = ttk.Combobox(frm, values=choices, state="readonly", width=64)
        cbA.grid(row=0, column=1, sticky="ew", padx=4, pady=2)

        ttk.Label(frm, text="Run B").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        cbB = ttk.Combobox(frm, values=choices, state="readonly", width=64)
        cbB.grid(row=1, column=1, sticky="ew", padx=4, pady=2)

        frm.columnconfigure(1, weight=1)

        # プリセットボタン列
        btnrow = ttk.Frame(win); btnrow.pack(fill="x", padx=8, pady=(0,6))

        def set_from_rows(rows):
            vals = [_disp_of(r) for r in rows]
            if len(vals) >= 1: cbA.set(vals[0])
            if len(vals) >= 2: cbB.set(vals[1])

        def pick_same_scenario_latest2():
            rs = fetch_runs_for_sid(cur_sid, limit=2)
            if len(rs) < 2:
                messagebox.showwarning("Compare Runs", "このシナリオで比較できる run が2本ありません。")
                return
            set_from_rows(rs)

        def pick_current_vs_base():
            cur = fetch_runs_for_sid(cur_sid, limit=1)
            base = fetch_runs_for_sid(None,     limit=1)
            if not cur or not base:
                messagebox.showwarning("Compare Runs", "必要な run が見つかりません。")
                return
            set_from_rows(cur + base)

        def pick_overall_latest2():
            rs = fetch_latest_two_overall()
            if len(rs) < 2:
                messagebox.showwarning("Compare Runs", "比較できる run が2本ありません。")
                return
            set_from_rows(rs)

        ttk.Button(btnrow, text="同一シナリオの最新2本", command=pick_same_scenario_latest2).pack(side="left", padx=2)
        ttk.Button(btnrow, text="現在シナリオ最新 vs BASE最新", command=pick_current_vs_base).pack(side="left", padx=2)
        ttk.Button(btnrow, text="全体の最新2本（横断）", command=pick_overall_latest2).pack(side="left", padx=2)

        # Compare 実行
        act = ttk.Frame(win); act.pack(fill="x", padx=8, pady=(4,8))
        def _parse_scn_from_disp(disp):
            try:
                return disp.split("—",1)[1].split("/",1)[0].strip()
            except Exception:
                return ""

        def do_compare_OLD():
            selA, selB = cbA.get(), cbB.get()
            if selA not in disp2row or selB not in disp2row:
                messagebox.showwarning("Compare Runs", "Run A/B を選択してください。")
                return

            rA = disp2row[selA][0]
            rB = disp2row[selB][0]
            sA = fetch_summary(rA)
            sB = fetch_summary(rB)
            if not sA or not sB:
                messagebox.showwarning("Compare Runs", "summary が見つかりません。Run & Save を実行してください。")
                return

            def f(x):
                try: return float(x or 0.0)
                except Exception: return 0.0

            A = [f(sA[0]), f(sA[2]), f(sA[3])]   # revenue, profit, profit_ratio
            B = [f(sB[0]), f(sB[2]), f(sB[3])]

            # ====== 埋め込み Figure ======
            figwin = tk.Toplevel(win)
            scnA = _parse_scn_from_disp(selA)
            scnB = _parse_scn_from_disp(selB)
            figwin.title(f"Scenario Compare  ({scnA} / {rA}  vs  {scnB} / {rB})")

            fig = Figure(figsize=(6.2, 3.2), dpi=100)
            ax  = fig.add_subplot(111)

            labels = ["Revenue", "Profit", "Profit Ratio"]
            x = np.arange(len(labels)); w = 0.35
            ax.bar(x - w/2, A, width=w, label=f"{scnA} / {rA}", color="#4E79A7")
            ax.bar(x + w/2, B, width=w, label=f"{scnB} / {rB}", color="#F28E2B")
            ax.set_xticks(x, labels)
            ax.set_title("Scenario Compare")
            ax.legend()
            fig.tight_layout()

            canvas = FigureCanvasTkAgg(fig, master=figwin)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)

            try:
                toolbar = NavigationToolbar2Tk(canvas, figwin)
                toolbar.update()
            except Exception:
                pass

            # 参照保持（GC対策）
            figwin._canvas = canvas
            figwin._fig = fig




        def do_compare():
            # A/B の選択取得とバリデーション
            selA, selB = cbA.get(), cbB.get()
            if selA not in disp2row or selB not in disp2row:
                messagebox.showwarning("Compare Runs", "Run A/B を選択してください。")
                return

            # DB から summary を取得
            rA = disp2row[selA][0]
            rB = disp2row[selB][0]
            sA = fetch_summary(rA)
            sB = fetch_summary(rB)
            if not sA or not sB:
                messagebox.showwarning("Compare Runs", "summary が見つかりません。Run & Save を実行してください。")
                return

            # 安全 float 変換
            def f(x):
                try:
                    return float(x or 0.0)
                except Exception:
                    return 0.0

            # ==== ここは既存 ====
            A = [f(sA[0]), f(sA[2]), f(sA[3])]
            B = [f(sB[0]), f(sB[2]), f(sB[3])]

            # ① 利益率は % に変換して表示ラベルも合わせる
            A[2] *= 100.0
            B[2] *= 100.0
            labels = ["Revenue", "Profit", "Profit Ratio (%)"]

            # ==== 埋め込み Figure （既存）====
            import numpy as np
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
            from matplotlib.ticker import FuncFormatter

            figwin = tk.Toplevel(win)
            scnA = _parse_scn_from_disp(selA)
            scnB = _parse_scn_from_disp(selB)
            figwin.title(f"Scenario Compare  ({scnA} / {rA}  vs  {scnB} / {rB})")

            fig = Figure(figsize=(6.6, 3.4), dpi=100)
            ax  = fig.add_subplot(111)
            x = np.arange(len(labels)); w = 0.35
            b1 = ax.bar(x - w/2, A, width=w, label=f"{scnA} / {rA}", color="#4E79A7")
            b2 = ax.bar(x + w/2, B, width=w, label=f"{scnB} / {rB}", color="#F28E2B")
            ax.set_xticks(x, labels)
            ax.legend()

            # ② Y軸の桁区切り（Revenue/Profit の桁が大きくても読みやすく）
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _:
                f"{v:,.0f}" if max(A[:2] + B[:2]) >= 10 else f"{v:.2f}"
            ))

            # ③ 棒の上に値を表示（利益率は小数1桁、他は桁区切り）
            def _fmt_val(i, v):
                return f"{v:,.0f}" if i in (0, 1) else f"{v:.1f}%"

            for i, rect in enumerate(b1):
                ax.text(rect.get_x() + rect.get_width()/2, rect.get_height(),
                        _fmt_val(i, A[i]), ha="center", va="bottom",
                        fontsize=9, color="#2c3e50")
            for i, rect in enumerate(b2):
                ax.text(rect.get_x() + rect.get_width()/2, rect.get_height(),
                        _fmt_val(i, B[i]), ha="center", va="bottom",
                        fontsize=9, color="#2c3e50")

            # ④ 差分をタイトルに（Δ表示）
            d_rev = A[0] - B[0]; d_prf = A[1] - B[1]; d_prr = A[2] - B[2]
            ax.set_title(f"Scenario Compare  |  ΔRev={d_rev:,.0f}, ΔProfit={d_prf:,.0f}, ΔPR={d_prr:.1f}pt")

            fig.tight_layout()

            # Tk へ埋め込み
            canvas = FigureCanvasTkAgg(fig, master=figwin)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)

            # ツールバー（拡大・保存など）
            try:
                toolbar = NavigationToolbar2Tk(canvas, figwin)
                toolbar.update()
            except Exception:
                pass

            # 参照保持（GC対策）
            figwin._canvas = canvas
            figwin._fig = fig




            # ==== ここから追加：ノード別 Breakdown 可視化 ====

            import sqlite3 as _sqlite
            import numpy as _np
            import pandas as _pd
            from matplotlib.ticker import FuncFormatter


            # 表示色（円グラフと揃えめ）
            _COLORS = {
                "Direct Materials": "#1f77b4",
                "Tariff":           "#d62728",
                "Logistics":        "#2ca02c",
                "Warehouse":        "#17becf",
                "Mfg Overhead":     "#aec7e8",
                "Other Costs":      "#7f7f7f",
            }

            def _fetch_breakdown_df(run_id: str, only_sales: bool=False) -> _pd.DataFrame:
                """
                scenario_result_node からノード別の売上・利益・コスト内訳を集計して返す。
                内訳: Direct Materials / Tariff / Logistics / Warehouse / Mfg Overhead / Other Costs
                """
                con = _sqlite.connect(dbp)
                try:
                    q = """
                        SELECT node_name,
                            SUM(COALESCE(revenue,0.0))                     AS revenue,
                            SUM(COALESCE(profit,0.0))                      AS profit,
                            SUM(COALESCE(direct_materials_costs,0.0))      AS dm,
                            SUM(COALESCE(tax_portion,0.0))                 AS tariff,
                            SUM(COALESCE(logistics_costs,0.0))             AS logistics,
                            SUM(COALESCE(warehouse_cost,0.0))              AS warehouse,
                            SUM(COALESCE(manufacturing_overhead,0.0))      AS mfg_oh,
                            SUM(COALESCE(cost,0.0))                        AS total_cost
                        FROM scenario_result_node
                        WHERE run_id = ?
                        GROUP BY node_name
                        ORDER BY node_name
                    """
                    df = _pd.read_sql_query(q, con, params=(run_id,))
                finally:
                    con.close()

                if df.empty:
                    return df

                # 内訳を整形
                for c in ["revenue","profit","dm","tariff","logistics","warehouse","mfg_oh","total_cost"]:
                    if c in df.columns:
                        df[c] = _pd.to_numeric(df[c], errors="coerce").fillna(0.0)
                    else:
                        df[c] = 0.0

                df["other_costs"] = (df["total_cost"] - (df["dm"]+df["tariff"]+df["logistics"]+df["warehouse"]+df["mfg_oh"])).clip(lower=0.0)

                if only_sales:
                    # 末端（販売）に近いノードだけ見たいとき（CS_/RT_ など）。
                    mask = df["node_name"].astype(str).str.startswith(("CS_","RT_"))
                    if mask.any():
                        df = df.loc[mask].copy()

                return df

            def _plot_breakdown_single(df: _pd.DataFrame, title: str):
                """単一ランのノード別積み上げ棒（コスト内訳）＋売上＆利益の棒を描く。"""
                if df.empty:
                    messagebox.showinfo("Breakdown", "該当ランに明細がありません。Run & Save を実行してください。")
                    return

                # X はノード
                nodes = df["node_name"].tolist()
                x = _np.arange(len(nodes))
                width = 0.55

                figwin = tk.Toplevel(win)
                figwin.title(title)

                fig = Figure(figsize=(8.5, 4.6), dpi=100)
                ax = fig.add_subplot(111)

                # コストの積み上げ
                stacks = [
                    ("Direct Materials", df["dm"].values, _COLORS["Direct Materials"]),
                    ("Tariff",           df["tariff"].values, _COLORS["Tariff"]),
                    ("Logistics",        df["logistics"].values, _COLORS["Logistics"]),
                    ("Warehouse",        df["warehouse"].values, _COLORS["Warehouse"]),
                    ("Mfg Overhead",     df["mfg_oh"].values, _COLORS["Mfg Overhead"]),
                    ("Other Costs",      df["other_costs"].values, _COLORS["Other Costs"]),
                ]

                bottom = _np.zeros(len(df))
                bars_for_legend = []
                for label, vals, color in stacks:
                    b = ax.bar(x, vals, width=width, bottom=bottom, label=label, color=color, alpha=0.90)
                    bottom += vals
                    bars_for_legend.append(b)

                # 右軸に 売上/利益 を重ねる（棒が重ならないように細く）
                ax2 = ax.twinx()
                w2 = 0.32
                br = ax2.bar(x - (width/2 + 0.06), df["revenue"].values, width=w2, label="Revenue", color="#4E79A7", alpha=0.75)
                bp = ax2.bar(x + (width/2 + 0.06), df["profit"].values,  width=w2, label="Profit",  color="#F28E2B", alpha=0.75)

                # 軸・凡例
                ax.set_xticks(x, nodes, rotation=30, ha="right")
                ax.set_ylabel("Cost (sum of components)")
                ax2.set_ylabel("Revenue / Profit")

                # 桁区切り
                fmt = FuncFormatter(lambda v, _p: f"{v:,.0f}" if abs(v) >= 10 else f"{v:.2f}")
                ax.yaxis.set_major_formatter(fmt)
                ax2.yaxis.set_major_formatter(fmt)

                # 合計コストを各棒の上に
                total_cost = df["total_cost"].values
                for xi, tc in enumerate(total_cost):
                    ax.text(xi, tc + max(total_cost)*0.02, f"{tc:,.0f}", ha="center", va="bottom", fontsize=9, color="#333")

                # 凡例（左右軸まとめる）
                leg1 = ax.legend(loc="upper left", ncols=3, fontsize=8, frameon=False)
                leg2 = ax2.legend(loc="upper right", fontsize=8, frameon=False)
                ax.add_artist(leg1); ax2.add_artist(leg2)

                ax.set_title(title)
                fig.tight_layout()

                canvas = FigureCanvasTkAgg(fig, master=figwin)
                canvas.draw()
                canvas.get_tk_widget().pack(fill="both", expand=True)
                try:
                    NavigationToolbar2Tk(canvas, figwin).update()
                except Exception:
                    pass
                figwin._canvas, figwin._fig = canvas, fig  # keep refs

            def _plot_breakdown_compare(dfA: _pd.DataFrame, dfB: _pd.DataFrame, title: str):
                """A/B を横並びで比較（各内訳は「合算」棒の中に色で、AとBは左右並べる）。"""
                if dfA.empty or dfB.empty:
                    messagebox.showinfo("Compare Breakdown", "どちらかのランに明細がありません。Run & Save を実行してください。")
                    return

                # ノードのマスターを合わせる（無いノードは0）
                nodes = sorted(set(dfA["node_name"]).union(dfB["node_name"]))
                def _reindex(df):
                    df2 = df.set_index("node_name").reindex(nodes).fillna(0.0).reset_index()
                    return df2
                A = _reindex(dfA); B = _reindex(dfB)

                x = _np.arange(len(nodes))
                width = 0.36

                figwin = tk.Toplevel(win); figwin.title(title)
                fig = Figure(figsize=(9.5, 5.0), dpi=100)
                ax = fig.add_subplot(111)

                # A の積み上げ
                bottom = _np.zeros(len(A))
                for label, col, color in [
                    ("Direct Materials","dm",       _COLORS["Direct Materials"]),
                    ("Tariff",          "tariff",   _COLORS["Tariff"]),
                    ("Logistics",       "logistics",_COLORS["Logistics"]),
                    ("Warehouse",       "warehouse",_COLORS["Warehouse"]),
                    ("Mfg Overhead",    "mfg_oh",   _COLORS["Mfg Overhead"]),
                    ("Other Costs",     "other_costs", _COLORS["Other Costs"]),
                ]:
                    vals = A[col].values
                    ax.bar(x - width/2, vals, width=width, bottom=bottom, color=color, alpha=0.9, label=label if col=="dm" else None)
                    bottom += vals

                # B の積み上げ
                bottom = _np.zeros(len(B))
                for label, col, color in [
                    ("Direct Materials","dm",       _COLORS["Direct Materials"]),
                    ("Tariff",          "tariff",   _COLORS["Tariff"]),
                    ("Logistics",       "logistics",_COLORS["Logistics"]),
                    ("Warehouse",       "warehouse",_COLORS["Warehouse"]),
                    ("Mfg Overhead",    "mfg_oh",   _COLORS["Mfg Overhead"]),
                    ("Other Costs",     "other_costs", _COLORS["Other Costs"]),
                ]:
                    vals = B[col].values
                    ax.bar(x + width/2, vals, width=width, bottom=bottom, color=color, alpha=0.5)
                    bottom += vals

                # 右軸：売上/利益（A/B を細い棒で）
                ax2 = ax.twinx()
                w2 = 0.20
                ax2.bar(x - (width/2 + 0.10), A["revenue"].values, width=w2, color="#4E79A7", alpha=0.85, label="Revenue A")
                ax2.bar(x - (width/2 - 0.10), A["profit"].values,  width=w2, color="#F28E2B", alpha=0.85, label="Profit A")
                ax2.bar(x + (width/2 - 0.10), B["revenue"].values, width=w2, color="#4E79A7", alpha=0.45, label="Revenue B")
                ax2.bar(x + (width/2 + 0.10), B["profit"].values,  width=w2, color="#F28E2B", alpha=0.45, label="Profit B")

                ax.set_xticks(x, nodes, rotation=30, ha="right")
                fmt = FuncFormatter(lambda v, _p: f"{v:,.0f}" if abs(v) >= 10 else f"{v:.2f}")
                ax.yaxis.set_major_formatter(fmt)
                ax2.yaxis.set_major_formatter(fmt)

                # 凡例（2段）
                ax.legend(loc="upper left", ncols=3, fontsize=8, frameon=False, title="Cost components")
                ax2.legend(loc="upper right", fontsize=8, frameon=False, title="Revenue / Profit")

                ax.set_title(title)
                fig.tight_layout()

                canvas = FigureCanvasTkAgg(fig, master=figwin)
                canvas.draw()
                canvas.get_tk_widget().pack(fill="both", expand=True)
                try:
                    NavigationToolbar2Tk(canvas, figwin).update()
                except Exception:
                    pass
                figwin._canvas, figwin._fig = canvas, fig  # keep refs

            # ==== ここまでユーティリティ ====

            # Breakdown ボタン群を追加
            row_btn = ttk.Frame(win); row_btn.pack(fill="x", padx=6, pady=(0,6))

            def _on_breakdown_A():
                selA = cbA.get()
                if selA not in disp2row: return
                rA = disp2row[selA][0]
                dfA = _fetch_breakdown_df(rA, only_sales=False)
                _plot_breakdown_single(dfA, title=f"Breakdown  |  {selA}")

            def _on_breakdown_B():
                selB = cbB.get()
                if selB not in disp2row: return
                rB = disp2row[selB][0]
                dfB = _fetch_breakdown_df(rB, only_sales=False)
                _plot_breakdown_single(dfB, title=f"Breakdown  |  {selB}")

            def _on_compare_breakdown():
                selA, selB = cbA.get(), cbB.get()
                if selA not in disp2row or selB not in disp2row:
                    return
                rA, rB = disp2row[selA][0], disp2row[selB][0]
                dfA = _fetch_breakdown_df(rA, only_sales=False)
                dfB = _fetch_breakdown_df(rB, only_sales=False)
                _plot_breakdown_compare(dfA, dfB, title=f"Breakdown Compare  |  {selA}  vs  {selB}")

            ttk.Button(row_btn, text="Breakdown (A)",       command=_on_breakdown_A).pack(side="left", padx=4)
            ttk.Button(row_btn, text="Breakdown (B)",       command=_on_breakdown_B).pack(side="left", padx=4)
            ttk.Button(row_btn, text="Compare Breakdown",   command=_on_compare_breakdown).pack(side="left", padx=12)
            # ==== 追加ここまで ====





        ttk.Button(act, text="Compare", command=do_compare).pack(side="right")

        # 既定選択：同一シナリオの最新2本 → 無ければ全体最新2本
        rs = fetch_runs_for_sid(cur_sid, limit=2)
        if len(rs) >= 2:
            set_from_rows(rs)
        else:
            pick_overall_latest2()



    def _show_compare_popup_OLD6(self):
        """
        Compare Runs… ダイアログ。
        - Run A / Run B を任意に選ぶ
        - プリセット: 同一シナリオ最新2本 / 現在シナリオ最新 vs BASE最新 / 全体の最新2本
        - グラフは Tkinter の Toplevel に Figure を埋め込んで表示（plt.show は使わない）
        - Breakdown: 従来の A/B 表示に加え、adv 版（差分ラベル/ネットワーク順/CS-RT フィルタ/比率/CSV）
        """
        import tkinter as tk
        from tkinter import ttk, messagebox
        import sqlite3, numpy as np
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
        from pysi.scenario.store import get_db_path_from

        dbp = get_db_path_from(self.psi if hasattr(self, "psi") else self)
        cur_sid = getattr(self, "active_scenario_id", None)   # None => BASE

        # --------------------------
        # DB helpers
        # --------------------------
        def _fetch_rows(sql, args=()):
            con = sqlite3.connect(dbp)
            try:
                return con.execute(sql, args).fetchall()
            finally:
                con.close()

        def fetch_runs_for_sid(sid, limit=20):
            """sid=None のときは NULL と 'BASE' の両方を拾う"""
            if sid is None:
                return _fetch_rows("""
                    SELECT run_id, scenario_id, started_at, COALESCE(label,'')
                    FROM scenario_run
                    WHERE scenario_id IS NULL OR scenario_id='BASE'
                    ORDER BY rowid DESC LIMIT ?""", (limit,))
            else:
                return _fetch_rows("""
                    SELECT run_id, scenario_id, started_at, COALESCE(label,'')
                    FROM scenario_run
                    WHERE scenario_id = ?
                    ORDER BY rowid DESC LIMIT ?""", (sid, limit))

        def fetch_latest_two_overall():
            return _fetch_rows("""
                SELECT run_id, scenario_id, started_at, COALESCE(label,'')
                FROM scenario_run
                ORDER BY rowid DESC LIMIT 2""")

        def fetch_summary(run_id):
            rows = _fetch_rows("""
                SELECT total_revenue,total_cost,total_profit,profit_ratio
                FROM scenario_result_summary WHERE run_id=?""", (run_id,))
            return rows[0] if rows else None

        # --------------------------
        # データ→表示文字列
        # --------------------------
        def _disp_of(row):
            rid, sid, started, label = row
            sid_disp = sid if (sid and sid != "BASE") else "BASE"
            ts = (started or "")
            lab = (label or "").strip()
            return f"{rid:>4} — {sid_disp} / {ts} / {lab}"

        # 候補（最新50件を横断で）
        rows_all = _fetch_rows("""
            SELECT run_id, scenario_id, started_at, COALESCE(label,'')
            FROM scenario_run
            ORDER BY rowid DESC LIMIT 50""")
        choices = [_disp_of(r) for r in rows_all]
        disp2row = {_disp_of(r): r for r in rows_all}

        # --------------------------
        # ダイアログ UI
        # --------------------------
        win = tk.Toplevel(self.root)
        win.title("Compare Runs")
        win.resizable(True, False)

        frm = ttk.Frame(win); frm.pack(fill="x", padx=8, pady=8)
        ttk.Label(frm, text="Run A").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        cbA = ttk.Combobox(frm, values=choices, state="readonly", width=64)
        cbA.grid(row=0, column=1, sticky="ew", padx=4, pady=2)

        ttk.Label(frm, text="Run B").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        cbB = ttk.Combobox(frm, values=choices, state="readonly", width=64)
        cbB.grid(row=1, column=1, sticky="ew", padx=4, pady=2)

        frm.columnconfigure(1, weight=1)

        # プリセットボタン列
        btnrow = ttk.Frame(win); btnrow.pack(fill="x", padx=8, pady=(0,6))

        def set_from_rows(rows):
            vals = [_disp_of(r) for r in rows]
            if len(vals) >= 1: cbA.set(vals[0])
            if len(vals) >= 2: cbB.set(vals[1])

        def pick_same_scenario_latest2():
            rs = fetch_runs_for_sid(cur_sid, limit=2)
            if len(rs) < 2:
                messagebox.showwarning("Compare Runs", "このシナリオで比較できる run が2本ありません。")
                return
            set_from_rows(rs)

        def pick_current_vs_base():
            cur = fetch_runs_for_sid(cur_sid, limit=1)
            base = fetch_runs_for_sid(None,     limit=1)
            if not cur or not base:
                messagebox.showwarning("Compare Runs", "必要な run が見つかりません。")
                return
            set_from_rows(cur + base)

        def pick_overall_latest2():
            rs = fetch_latest_two_overall()
            if len(rs) < 2:
                messagebox.showwarning("Compare Runs", "比較できる run が2本ありません。")
                return
            set_from_rows(rs)

        ttk.Button(btnrow, text="同一シナリオの最新2本", command=pick_same_scenario_latest2).pack(side="left", padx=2)
        ttk.Button(btnrow, text="現在シナリオ最新 vs BASE最新", command=pick_current_vs_base).pack(side="left", padx=2)
        ttk.Button(btnrow, text="全体の最新2本（横断）", command=pick_overall_latest2).pack(side="left", padx=2)

        # Compare 実行（サマリー棒グラフ）
        act = ttk.Frame(win); act.pack(fill="x", padx=8, pady=(4,8))
        def _parse_scn_from_disp(disp):
            try:
                return disp.split("—",1)[1].split("/",1)[0].strip()
            except Exception:
                return ""

        def do_compare():
            # A/B の選択取得とバリデーション
            selA, selB = cbA.get(), cbB.get()
            if selA not in disp2row or selB not in disp2row:
                messagebox.showwarning("Compare Runs", "Run A/B を選択してください。")
                return

            # DB から summary を取得
            rA = disp2row[selA][0]
            rB = disp2row[selB][0]
            sA = fetch_summary(rA)
            sB = fetch_summary(rB)
            if not sA or not sB:
                messagebox.showwarning("Compare Runs", "summary が見つかりません。Run & Save を実行してください。")
                return

            # 安全 float 変換
            def f(x):
                try:
                    return float(x or 0.0)
                except Exception:
                    return 0.0

            # 値（Revenue, Profit, Profit Ratio）
            A = [f(sA[0]), f(sA[2]), f(sA[3])]
            B = [f(sB[0]), f(sB[2]), f(sB[3])]
            # 利益率は % 表示
            A[2] *= 100.0
            B[2] *= 100.0
            labels = ["Revenue", "Profit", "Profit Ratio (%)"]

            # Tk 埋め込み Figure
            from matplotlib.ticker import FuncFormatter
            figwin = tk.Toplevel(win)
            scnA = _parse_scn_from_disp(selA)
            scnB = _parse_scn_from_disp(selB)
            figwin.title(f"Scenario Compare  ({scnA} / {rA}  vs  {scnB} / {rB})")

            fig = Figure(figsize=(6.6, 3.4), dpi=100)
            ax  = fig.add_subplot(111)
            x = np.arange(len(labels)); w = 0.35
            b1 = ax.bar(x - w/2, A, width=w, label=f"{scnA} / {rA}", color="#4E79A7")
            b2 = ax.bar(x + w/2, B, width=w, label=f"{scnB} / {rB}", color="#F28E2B")
            ax.set_xticks(x, labels)
            ax.legend()

            # Y軸の桁区切り
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _:
                f"{v:,.0f}" if max(A[:2] + B[:2]) >= 10 else f"{v:.2f}"
            ))

            # 棒ラベル
            def _fmt_val(i, v):
                return f"{v:,.0f}" if i in (0, 1) else f"{v:.1f}%"
            for i, rect in enumerate(b1):
                ax.text(rect.get_x() + rect.get_width()/2, rect.get_height(),
                        _fmt_val(i, A[i]), ha="center", va="bottom",
                        fontsize=9, color="#2c3e50")
            for i, rect in enumerate(b2):
                ax.text(rect.get_x() + rect.get_width()/2, rect.get_height(),
                        _fmt_val(i, B[i]), ha="center", va="bottom",
                        fontsize=9, color="#2c3e50")

            # Δ表示
            d_rev = A[0] - B[0]; d_prf = A[1] - B[1]; d_prr = A[2] - B[2]
            ax.set_title(f"Scenario Compare  |  ΔRev={d_rev:,.0f}, ΔProfit={d_prf:,.0f}, ΔPR={d_prr:.1f}pt")

            fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=figwin)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)
            try:
                toolbar = NavigationToolbar2Tk(canvas, figwin); toolbar.update()
            except Exception:
                pass
            figwin._canvas = canvas; figwin._fig = fig  # keep refs

        ttk.Button(act, text="Compare", command=do_compare).pack(side="right")

        # ==== 従来の Breakdown（単体 / 比較） ====
        import sqlite3 as _sqlite
        import numpy as _np
        import pandas as _pd
        from matplotlib.ticker import FuncFormatter as _Fmt

        _COLORS = {
            "Direct Materials": "#1f77b4",
            "Tariff":           "#d62728",
            "Logistics":        "#2ca02c",
            "Warehouse":        "#17becf",
            "Mfg Overhead":     "#aec7e8",
            "Other Costs":      "#7f7f7f",
        }

        def _fetch_breakdown_df(run_id: str, only_sales: bool=False) -> _pd.DataFrame:
            con = _sqlite.connect(dbp)
            try:
                q = """
                    SELECT node_name,
                        SUM(COALESCE(revenue,0.0))                     AS revenue,
                        SUM(COALESCE(profit,0.0))                      AS profit,
                        SUM(COALESCE(direct_materials_costs,0.0))      AS dm,
                        SUM(COALESCE(tax_portion,0.0))                 AS tariff,
                        SUM(COALESCE(logistics_costs,0.0))             AS logistics,
                        SUM(COALESCE(warehouse_cost,0.0))              AS warehouse,
                        SUM(COALESCE(manufacturing_overhead,0.0))      AS mfg_oh,
                        SUM(COALESCE(cost,0.0))                        AS total_cost
                    FROM scenario_result_node
                    WHERE run_id = ?
                    GROUP BY node_name
                    ORDER BY node_name
                """
                df = _pd.read_sql_query(q, con, params=(run_id,))
            finally:
                con.close()

            if df.empty:
                return df

            for c in ["revenue","profit","dm","tariff","logistics","warehouse","mfg_oh","total_cost"]:
                if c in df.columns:
                    df[c] = _pd.to_numeric(df[c], errors="coerce").fillna(0.0)
                else:
                    df[c] = 0.0

            df["other_costs"] = (df["total_cost"] - (df["dm"]+df["tariff"]+df["logistics"]+df["warehouse"]+df["mfg_oh"])).clip(lower=0.0)

            if only_sales:
                mask = df["node_name"].astype(str).str.startswith(("CS_","RT_"))
                if mask.any():
                    df = df.loc[mask].copy()

            return df

        def _plot_breakdown_single(df: _pd.DataFrame, title: str):
            if df.empty:
                messagebox.showinfo("Breakdown", "該当ランに明細がありません。Run & Save を実行してください。")
                return
            nodes = df["node_name"].tolist()
            x = _np.arange(len(nodes)); width = 0.55

            figwin = tk.Toplevel(win); figwin.title(title)
            fig = Figure(figsize=(8.5, 4.6), dpi=100); ax = fig.add_subplot(111)

            stacks = [
                ("Direct Materials", df["dm"].values, _COLORS["Direct Materials"]),
                ("Tariff",           df["tariff"].values, _COLORS["Tariff"]),
                ("Logistics",        df["logistics"].values, _COLORS["Logistics"]),
                ("Warehouse",        df["warehouse"].values, _COLORS["Warehouse"]),
                ("Mfg Overhead",     df["mfg_oh"].values, _COLORS["Mfg Overhead"]),
                ("Other Costs",      df["other_costs"].values, _COLORS["Other Costs"]),
            ]
            bottom = _np.zeros(len(df))
            for label, vals, color in stacks:
                ax.bar(x, vals, width=width, bottom=bottom, label=label, color=color, alpha=0.90)
                bottom += vals

            ax2 = ax.twinx()
            w2 = 0.32
            ax2.bar(x - (width/2 + 0.06), df["revenue"].values, width=w2, label="Revenue", color="#4E79A7", alpha=0.75)
            ax2.bar(x + (width/2 + 0.06), df["profit"].values,  width=w2, label="Profit",  color="#F28E2B", alpha=0.75)

            ax.set_xticks(x, nodes, rotation=30, ha="right")
            ax.set_ylabel("Cost (sum of components)")
            ax2.set_ylabel("Revenue / Profit")
            fmt = _Fmt(lambda v, _p: f"{v:,.0f}" if abs(v) >= 10 else f"{v:.2f}")
            ax.yaxis.set_major_formatter(fmt); ax2.yaxis.set_major_formatter(fmt)

            total_cost = df["total_cost"].values
            for xi, tc in enumerate(total_cost):
                ax.text(xi, tc + max(total_cost)*0.02, f"{tc:,.0f}", ha="center", va="bottom", fontsize=9, color="#333")

            leg1 = ax.legend(loc="upper left", ncols=3, fontsize=8, frameon=False)
            leg2 = ax2.legend(loc="upper right", fontsize=8, frameon=False)
            ax.add_artist(leg1); ax2.add_artist(leg2)

            ax.set_title(title); fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=figwin); canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)
            try: NavigationToolbar2Tk(canvas, figwin).update()
            except Exception: pass
            figwin._canvas, figwin._fig = canvas, fig

        def _plot_breakdown_compare(dfA: _pd.DataFrame, dfB: _pd.DataFrame, title: str):
            if dfA.empty or dfB.empty:
                messagebox.showinfo("Compare Breakdown", "どちらかのランに明細がありません。Run & Save を実行してください。")
                return
            nodes = sorted(set(dfA["node_name"]).union(dfB["node_name"]))
            def _reindex(df):
                df2 = df.set_index("node_name").reindex(nodes).fillna(0.0).reset_index()
                return df2
            A = _reindex(dfA); B = _reindex(dfB)

            x = _np.arange(len(nodes)); width = 0.36
            figwin = tk.Toplevel(win); figwin.title(title)
            fig = Figure(figsize=(9.5, 5.0), dpi=100); ax = fig.add_subplot(111)

            bottom = _np.zeros(len(A))
            for label, col, color in [
                ("Direct Materials","dm",       _COLORS["Direct Materials"]),
                ("Tariff",          "tariff",   _COLORS["Tariff"]),
                ("Logistics",       "logistics",_COLORS["Logistics"]),
                ("Warehouse",       "warehouse",_COLORS["Warehouse"]),
                ("Mfg Overhead",    "mfg_oh",   _COLORS["Mfg Overhead"]),
                ("Other Costs",     "other_costs", _COLORS["Other Costs"]),
            ]:
                vals = A[col].values
                ax.bar(x - width/2, vals, width=width, bottom=bottom, color=color, alpha=0.9, label=label if col=="dm" else None)
                bottom += vals

            bottom = _np.zeros(len(B))
            for label, col, color in [
                ("Direct Materials","dm",       _COLORS["Direct Materials"]),
                ("Tariff",          "tariff",   _COLORS["Tariff"]),
                ("Logistics",       "logistics",_COLORS["Logistics"]),
                ("Warehouse",       "warehouse",_COLORS["Warehouse"]),
                ("Mfg Overhead",    "mfg_oh",   _COLORS["Mfg Overhead"]),
                ("Other Costs",     "other_costs", _COLORS["Other Costs"]),
            ]:
                vals = B[col].values
                ax.bar(x + width/2, vals, width=width, bottom=bottom, color=color, alpha=0.5)
                bottom += vals

            ax2 = ax.twinx(); w2 = 0.20
            ax2.bar(x - (width/2 + 0.10), A["revenue"].values, width=w2, color="#4E79A7", alpha=0.85, label="Revenue A")
            ax2.bar(x - (width/2 - 0.10), A["profit"].values,  width=w2, color="#F28E2B", alpha=0.85, label="Profit A")
            ax2.bar(x + (width/2 - 0.10), B["revenue"].values, width=w2, color="#4E79A7", alpha=0.45, label="Revenue B")
            ax2.bar(x + (width/2 + 0.10), B["profit"].values,  width=w2, color="#F28E2B", alpha=0.45, label="Profit B")

            ax.set_xticks(x, nodes, rotation=30, ha="right")
            fmt = _Fmt(lambda v, _p: f"{v:,.0f}" if abs(v) >= 10 else f"{v:.2f}")
            ax.yaxis.set_major_formatter(fmt); ax2.yaxis.set_major_formatter(fmt)

            ax.legend(loc="upper left", ncols=3, fontsize=8, frameon=False, title="Cost components")
            ax2.legend(loc="upper right", fontsize=8, frameon=False, title="Revenue / Profit")

            ax.set_title(title); fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=figwin); canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)
            try: NavigationToolbar2Tk(canvas, figwin).update()
            except Exception: pass
            figwin._canvas, figwin._fig = canvas, fig

        # Breakdown ボタン（従来版）
        row_btn = ttk.Frame(win); row_btn.pack(fill="x", padx=6, pady=(0,6))
        def _on_breakdown_A():
            selA = cbA.get()
            if selA not in disp2row: return
            rA = disp2row[selA][0]
            dfA = _fetch_breakdown_df(rA, only_sales=False)
            _plot_breakdown_single(dfA, title=f"Breakdown  |  {selA}")

        def _on_breakdown_B():
            selB = cbB.get()
            if selB not in disp2row: return
            rB = disp2row[selB][0]
            dfB = _fetch_breakdown_df(rB, only_sales=False)
            _plot_breakdown_single(dfB, title=f"Breakdown  |  {selB}")

        def _on_compare_breakdown():
            selA, selB = cbA.get(), cbB.get()
            if selA not in disp2row or selB not in disp2row: return
            rA, rB = disp2row[selA][0], disp2row[selB][0]
            dfA = _fetch_breakdown_df(rA, only_sales=False)
            dfB = _fetch_breakdown_df(rB, only_sales=False)
            _plot_breakdown_compare(dfA, dfB, title=f"Breakdown Compare  |  {selA}  vs  {selB}")

        ttk.Button(row_btn, text="Breakdown (A)",     command=_on_breakdown_A).pack(side="left", padx=4)
        ttk.Button(row_btn, text="Breakdown (B)",     command=_on_breakdown_B).pack(side="left", padx=4)
        ttk.Button(row_btn, text="Compare Breakdown", command=_on_compare_breakdown).pack(side="left", padx=12)

        # ==== PATCH: Compare Breakdown（差分ラベル / 並び順 / only_sales / 比率 / CSV）====
        import sqlite3 as _sq_adv, numpy as _np_adv, pandas as _pd_adv
        from matplotlib.figure import Figure as _FigAdv
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg as _CanvasAdv, NavigationToolbar2Tk as _ToolbarAdv
        import tkinter as _tk
        from tkinter import ttk as _ttk, filedialog as _fd

        def _show_breakdown_compare_adv():
            # ---------- ユーティリティ ----------
            def _get_run_id(sel_disp: str) -> str:
                return disp2row[sel_disp][0]

            def _fetch_node_df(run_id: str) -> _pd_adv.DataFrame:
                con = _sq_adv.connect(dbp)
                try:
                    cols = [
                        "node_name","product_name","revenue","profit",
                        "direct_materials_costs","logistics_costs","warehouse_cost",
                        "manufacturing_overhead","tax_portion","cost"
                    ]
                    exist = [c[1] for c in con.execute("PRAGMA table_info(scenario_result_node)")]
                    cols_use = [c for c in cols if c in exist]
                    q = f"SELECT {', '.join(cols_use)} FROM scenario_result_node WHERE run_id=?"
                    df = _pd_adv.read_sql_query(q, con, params=(run_id,))
                finally:
                    con.close()

                for c in ("revenue","profit","direct_materials_costs","logistics_costs",
                        "warehouse_cost","manufacturing_overhead","tax_portion","cost"):
                    if c in df.columns:
                        df[c] = _pd_adv.to_numeric(df[c], errors="coerce").fillna(0.0)
                    else:
                        df[c] = 0.0

                comp_known = df[["direct_materials_costs","logistics_costs","warehouse_cost",
                                "manufacturing_overhead","tax_portion"]].sum(axis=1)
                df["other_costs"] = (df["cost"] - comp_known).clip(lower=0.0)
                df["total_cost"]  = df[["direct_materials_costs","logistics_costs","warehouse_cost",
                                        "manufacturing_overhead","tax_portion","other_costs"]].sum(axis=1)
                return df

            def _sort_nodes(names: list[str]) -> list[str]:
                pos = getattr(self, "pos_E2E", {}) or {}
                def key(n):
                    p = pos.get(n)
                    return (p[0] if p else float("inf"), n)
                return sorted(names, key=key)

            def _filter_nodes_sales(names: list[str]) -> list[str]:
                return [n for n in names if str(n).startswith("CS_") or str(n).startswith("RT_")]

            def _build_export_df(dfA: _pd_adv.DataFrame, dfB: _pd_adv.DataFrame, nodes: list[str]) -> _pd_adv.DataFrame:
                take = ["direct_materials_costs","logistics_costs","warehouse_cost",
                        "manufacturing_overhead","tax_portion","other_costs","total_cost","revenue","profit"]
                A = (dfA[dfA["node_name"].isin(nodes)][["node_name"]+take]
                        .set_index("node_name").rename(columns={c:f"{c}_A" for c in take}))
                B = (dfB[dfB["node_name"].isin(nodes)][["node_name"]+take]
                        .set_index("node_name").rename(columns={c:f"{c}_B" for c in take}))
                out = A.join(B, how="outer").fillna(0.0)
                out["delta_revenue"]   = out["revenue_A"]   - out["revenue_B"]
                out["delta_profit"]    = out["profit_A"]    - out["profit_B"]
                out["delta_total_cost"]= out["total_cost_A"]- out["total_cost_B"]
                return out.loc[nodes]

            # ---------- UI ----------
            selA, selB = cbA.get(), cbB.get()
            if selA not in disp2row or selB not in disp2row:
                messagebox.showwarning("Compare Runs", "Run A/B を選択してください。")
                return

            rA, rB = _get_run_id(selA), _get_run_id(selB)
            figwin = _tk.Toplevel(win)
            figwin.title(f"Breakdown Compare  |  {selA}  vs  {selB}")

            top = _ttk.Frame(figwin); top.pack(fill="x", padx=6, pady=4)
            var_only_sales = _tk.BooleanVar(value=False)
            var_ratio      = _tk.BooleanVar(value=False)
            _ttk.Checkbutton(top, text="only CS_/RT_ nodes",  variable=var_only_sales,
                            command=lambda: _redraw()).pack(side="left", padx=4)
            _ttk.Checkbutton(top, text="Cost as % (ratio mode)", variable=var_ratio,
                            command=lambda: _redraw()).pack(side="left", padx=4)
            _ttk.Button(top, text="Export CSV…", command=lambda: _export_csv()).pack(side="right", padx=4)

            fig = _FigAdv(figsize=(8.6, 4.2), dpi=100)
            ax = fig.add_subplot(111)
            canvas = _CanvasAdv(fig, master=figwin)
            canvas.draw(); canvas.get_tk_widget().pack(fill="both", expand=True)
            try:
                _ToolbarAdv(canvas, figwin).update()
            except Exception:
                pass

            # 描画ロジック
            dfA_full, dfB_full = _fetch_node_df(rA), _fetch_node_df(rB)
            comp_cols = ["direct_materials_costs","logistics_costs","warehouse_cost",
                        "manufacturing_overhead","tax_portion","other_costs"]

            def _redraw():
                ax.clear()
                nodes = sorted(set(dfA_full["node_name"]).union(dfB_full["node_name"]))
                nodes = _sort_nodes(nodes)
                if var_only_sales.get():
                    nodes = _filter_nodes_sales(nodes)
                if not nodes:
                    ax.text(0.5, 0.5, "No nodes to display", ha="center", va="center",
                            transform=ax.transAxes)
                    canvas.draw(); return

                dfA = dfA_full[dfA_full["node_name"].isin(nodes)].set_index("node_name").reindex(nodes).fillna(0.0)
                dfB = dfB_full[dfB_full["node_name"].isin(nodes)].set_index("node_name").reindex(nodes).fillna(0.0)

                if var_ratio.get():
                    baseA = dfA["total_cost"].replace(0, np.nan)
                    baseB = dfB["total_cost"].replace(0, np.nan)
                    partsA = (dfA[comp_cols].div(baseA, axis=0)*100.0).fillna(0.0)
                    partsB = (dfB[comp_cols].div(baseB, axis=0)*100.0).fillna(0.0)
                    y_label = "Cost (%)"; y_max = 100.0
                else:
                    partsA = dfA[comp_cols]; partsB = dfB[comp_cols]
                    y_label = "Cost (money)"
                    y_max = max(float(dfA["total_cost"].max()), float(dfB["total_cost"].max()))*1.15 + 1e-9

                x = _np_adv.arange(len(nodes)); w = 0.42
                bottomA = _np_adv.zeros(len(nodes)); bottomB = _np_adv.zeros(len(nodes))
                color_map = {
                    "direct_materials_costs": "#1f77b4",
                    "logistics_costs": "#2ca02c",
                    "warehouse_cost": "#17becf",
                    "manufacturing_overhead": "#8c564b",
                    "tax_portion": "#d62728",
                    "other_costs": "#7f7f7f",
                }
                for c in comp_cols:
                    a = partsA[c].to_numpy(); b = partsB[c].to_numpy()
                    ax.bar(x - w/2, a, width=w, bottom=bottomA, color=color_map[c],
                        label=c if (c==comp_cols[0]) else None)
                    ax.bar(x + w/2, b, width=w, bottom=bottomB, color=color_map[c])
                    bottomA += a; bottomB += b

                # 右軸：Revenue / Profit（実額）
                ax2 = ax.twinx()
                revA, revB = dfA["revenue"].to_numpy(), dfB["revenue"].to_numpy()
                prfA, prfB = dfA["profit"].to_numpy(),  dfB["profit"].to_numpy()
                ax2.bar(x - w/2, revA, width=w*0.35, color="#4E79A7", alpha=0.35, label="Revenue A")
                ax2.bar(x + w/2, revB, width=w*0.35, color="#4E79A7", alpha=0.70, hatch="//", label="Revenue B")
                ax2.bar(x - w/2, prfA, width=w*0.35, color="#F28E2B", alpha=0.35, bottom=revA*0, label="Profit A")
                ax2.bar(x + w/2, prfB, width=w*0.35, color="#F28E2B", alpha=0.70, hatch="\\\\", bottom=revB*0, label="Profit B")

                # Δラベル（棒の上）
                d_rev = revA - revB; d_prf = prfA - prfB
                totA = dfA["total_cost"].to_numpy(); totB = dfB["total_cost"].to_numpy()
                d_cst = totA - totB
                tops = np.maximum(bottomA, bottomB)
                for i, xi in enumerate(x):
                    txt = f"ΔR={d_rev[i]:,.0f}\nΔP={d_prf[i]:,.0f}\nΔC={d_cst[i]:,.0f}"
                    ax.text(xi, tops[i] + (y_max*0.02 if not var_ratio.get() else 3),
                            txt, ha="center", va="bottom", fontsize=8, color="#444")

                ax.set_ylabel(y_label)
                ax.set_xticks(x, nodes, rotation=40, ha="right")
                if var_ratio.get(): ax.set_ylim(0, 100)
                ax.grid(axis="y", linestyle=":", alpha=0.4)
                ax.set_title(f"Cost Breakdown  |  {selA}  vs  {selB}")
                import matplotlib.ticker as mtick
                ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v,_: f"{v:,.0f}"))
                ax2.set_ylabel("Revenue / Profit (money)")
                ax2.legend(loc="upper right", fontsize=9)

                fig.tight_layout(); canvas.draw()

            def _export_csv():
                nodes = sorted(set(dfA_full["node_name"]).union(dfB_full["node_name"]))
                nodes = _sort_nodes(nodes)
                if var_only_sales.get(): nodes = _filter_nodes_sales(nodes)
                df_out = _build_export_df(dfA_full, dfB_full, nodes)
                path = _fd.asksaveasfilename(
                    parent=figwin,
                    defaultextension=".csv",
                    filetypes=[("CSV", "*.csv"), ("All Files", "*.*")],
                    initialfile="breakdown_compare.csv",
                    title="Export breakdown as CSV"
                )
                if path:
                    df_out.to_csv(path, encoding="utf-8-sig", float_format="%.6g")

            _redraw()

        # adv 版ボタンを追加
        ttk.Button(row_btn, text="Compare Breakdown (adv)", command=_show_breakdown_compare_adv)\
        .pack(side="left", padx=12)

        # 既定選択：同一シナリオの最新2本 → 無ければ全体最新2本
        rs = fetch_runs_for_sid(cur_sid, limit=2)
        if len(rs) >= 2:
            set_from_rows(rs)
        else:
            pick_overall_latest2()




    def _show_compare_popup(self):
        """
        Compare Runs… ダイアログ。
        - Run A / Run B を任意に選ぶ
        - プリセット: 同一シナリオ最新2本 / 現在シナリオ最新 vs BASE最新 / 全体の最新2本
        - グラフは Tkinter の Toplevel に Figure を埋め込んで表示（plt.show は使わない）
        - Breakdown: 従来の A/B 表示に加え、adv 版（差分ラベル/ネットワーク順/CS-RT フィルタ/比率/CSV）
        """
        import tkinter as tk
        from tkinter import ttk, messagebox
        import sqlite3, numpy as np
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
        from pysi.scenario.store import get_db_path_from

        dbp = get_db_path_from(self.psi if hasattr(self, "psi") else self)
        cur_sid = getattr(self, "active_scenario_id", None)   # None => BASE

        # --------------------------
        # DB helpers
        # --------------------------
        def _fetch_rows(sql, args=()):
            con = sqlite3.connect(dbp)
            try:
                return con.execute(sql, args).fetchall()
            finally:
                con.close()

        def fetch_runs_for_sid(sid, limit=20):
            """sid=None のときは NULL と 'BASE' の両方を拾う"""
            if sid is None:
                return _fetch_rows("""
                    SELECT run_id, scenario_id, started_at, COALESCE(label,'')
                    FROM scenario_run
                    WHERE scenario_id IS NULL OR scenario_id='BASE'
                    ORDER BY rowid DESC LIMIT ?""", (limit,))
            else:
                return _fetch_rows("""
                    SELECT run_id, scenario_id, started_at, COALESCE(label,'')
                    FROM scenario_run
                    WHERE scenario_id = ?
                    ORDER BY rowid DESC LIMIT ?""", (sid, limit))

        def fetch_latest_two_overall():
            return _fetch_rows("""
                SELECT run_id, scenario_id, started_at, COALESCE(label,'')
                FROM scenario_run
                ORDER BY rowid DESC LIMIT 2""")

        def fetch_summary(run_id):
            rows = _fetch_rows("""
                SELECT total_revenue,total_cost,total_profit,profit_ratio
                FROM scenario_result_summary WHERE run_id=?""", (run_id,))
            return rows[0] if rows else None

        # --------------------------
        # データ→表示文字列
        # --------------------------
        def _disp_of(row):
            rid, sid, started, label = row
            sid_disp = sid if (sid and sid != "BASE") else "BASE"
            ts = (started or "")
            lab = (label or "").strip()
            return f"{rid:>4} — {sid_disp} / {ts} / {lab}"

        # 候補（最新50件を横断で）
        rows_all = _fetch_rows("""
            SELECT run_id, scenario_id, started_at, COALESCE(label,'')
            FROM scenario_run
            ORDER BY rowid DESC LIMIT 50""")
        choices = [_disp_of(r) for r in rows_all]
        disp2row = {_disp_of(r): r for r in rows_all}

        # --------------------------
        # ダイアログ UI
        # --------------------------
        win = tk.Toplevel(self.root)
        win.title("Compare Runs")
        win.resizable(True, False)

        frm = ttk.Frame(win); frm.pack(fill="x", padx=8, pady=8)
        ttk.Label(frm, text="Run A").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        cbA = ttk.Combobox(frm, values=choices, state="readonly", width=64)
        cbA.grid(row=0, column=1, sticky="ew", padx=4, pady=2)

        ttk.Label(frm, text="Run B").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        cbB = ttk.Combobox(frm, values=choices, state="readonly", width=64)
        cbB.grid(row=1, column=1, sticky="ew", padx=4, pady=2)

        frm.columnconfigure(1, weight=1)

        # プリセットボタン列
        btnrow = ttk.Frame(win); btnrow.pack(fill="x", padx=8, pady=(0,6))

        def set_from_rows(rows):
            vals = [_disp_of(r) for r in rows]
            if len(vals) >= 1: cbA.set(vals[0])
            if len(vals) >= 2: cbB.set(vals[1])

        def pick_same_scenario_latest2():
            rs = fetch_runs_for_sid(cur_sid, limit=2)
            if len(rs) < 2:
                messagebox.showwarning("Compare Runs", "このシナリオで比較できる run が2本ありません。")
                return
            set_from_rows(rs)

        def pick_current_vs_base():
            cur = fetch_runs_for_sid(cur_sid, limit=1)
            base = fetch_runs_for_sid(None,     limit=1)
            if not cur or not base:
                messagebox.showwarning("Compare Runs", "必要な run が見つかりません。")
                return
            set_from_rows(cur + base)

        def pick_overall_latest2():
            rs = fetch_latest_two_overall()
            if len(rs) < 2:
                messagebox.showwarning("Compare Runs", "比較できる run が2本ありません。")
                return
            set_from_rows(rs)

        ttk.Button(btnrow, text="同一シナリオの最新2本", command=pick_same_scenario_latest2).pack(side="left", padx=2)
        ttk.Button(btnrow, text="現在シナリオ最新 vs BASE最新", command=pick_current_vs_base).pack(side="left", padx=2)
        ttk.Button(btnrow, text="全体の最新2本（横断）", command=pick_overall_latest2).pack(side="left", padx=2)

        # Compare 実行（サマリー棒グラフ）
        act = ttk.Frame(win); act.pack(fill="x", padx=8, pady=(4,8))
        def _parse_scn_from_disp(disp):
            try:
                return disp.split("—",1)[1].split("/",1)[0].strip()
            except Exception:
                return ""

        def do_compare():
            # A/B の選択取得とバリデーション
            selA, selB = cbA.get(), cbB.get()
            if selA not in disp2row or selB not in disp2row:
                messagebox.showwarning("Compare Runs", "Run A/B を選択してください。")
                return

            # DB から summary を取得
            rA = disp2row[selA][0]
            rB = disp2row[selB][0]
            sA = fetch_summary(rA)
            sB = fetch_summary(rB)
            if not sA or not sB:
                messagebox.showwarning("Compare Runs", "summary が見つかりません。Run & Save を実行してください。")
                return

            # 安全 float 変換
            def f(x):
                try:
                    return float(x or 0.0)
                except Exception:
                    return 0.0

            # 値（Revenue, Profit, Profit Ratio）
            A = [f(sA[0]), f(sA[2]), f(sA[3])]
            B = [f(sB[0]), f(sB[2]), f(sB[3])]
            # 利益率は % 表示
            A[2] *= 100.0
            B[2] *= 100.0
            labels = ["Revenue", "Profit", "Profit Ratio (%)"]

            # Tk 埋め込み Figure
            from matplotlib.ticker import FuncFormatter
            figwin = tk.Toplevel(win)
            scnA = _parse_scn_from_disp(selA)
            scnB = _parse_scn_from_disp(selB)
            figwin.title(f"Scenario Compare  ({scnA} / {rA}  vs  {scnB} / {rB})")

            fig = Figure(figsize=(6.6, 3.4), dpi=100)
            ax  = fig.add_subplot(111)
            x = np.arange(len(labels)); w = 0.35
            b1 = ax.bar(x - w/2, A, width=w, label=f"{scnA} / {rA}", color="#4E79A7")
            b2 = ax.bar(x + w/2, B, width=w, label=f"{scnB} / {rB}", color="#F28E2B")
            ax.set_xticks(x, labels)
            ax.legend()

            # Y軸の桁区切り
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _:
                f"{v:,.0f}" if max(A[:2] + B[:2]) >= 10 else f"{v:.2f}"
            ))

            # 棒ラベル
            def _fmt_val(i, v):
                return f"{v:,.0f}" if i in (0, 1) else f"{v:.1f}%"
            for i, rect in enumerate(b1):
                ax.text(rect.get_x() + rect.get_width()/2, rect.get_height(),
                        _fmt_val(i, A[i]), ha="center", va="bottom",
                        fontsize=9, color="#2c3e50")
            for i, rect in enumerate(b2):
                ax.text(rect.get_x() + rect.get_width()/2, rect.get_height(),
                        _fmt_val(i, B[i]), ha="center", va="bottom",
                        fontsize=9, color="#2c3e50")

            # Δ表示
            d_rev = A[0] - B[0]; d_prf = A[1] - B[1]; d_prr = A[2] - B[2]
            ax.set_title(f"Scenario Compare  |  ΔRev={d_rev:,.0f}, ΔProfit={d_prf:,.0f}, ΔPR={d_prr:.1f}pt")

            fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=figwin)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)
            try:
                toolbar = NavigationToolbar2Tk(canvas, figwin); toolbar.update()
            except Exception:
                pass
            figwin._canvas = canvas; figwin._fig = fig  # keep refs

        ttk.Button(act, text="Compare", command=do_compare).pack(side="right")

        # ==== 従来の Breakdown（単体 / 比較） ====
        import sqlite3 as _sqlite
        import numpy as _np
        import pandas as _pd
        from matplotlib.ticker import FuncFormatter as _Fmt

        _COLORS = {
            "Direct Materials": "#1f77b4",
            "Tariff":           "#d62728",
            "Logistics":        "#2ca02c",
            "Warehouse":        "#17becf",
            "Mfg Overhead":     "#aec7e8",
            "Other Costs":      "#7f7f7f",
        }

        def _fetch_breakdown_df(run_id: str, only_sales: bool=False) -> _pd.DataFrame:
            con = _sqlite.connect(dbp)
            try:
                q = """
                    SELECT node_name,
                        SUM(COALESCE(revenue,0.0))                     AS revenue,
                        SUM(COALESCE(profit,0.0))                      AS profit,
                        SUM(COALESCE(direct_materials_costs,0.0))      AS dm,
                        SUM(COALESCE(tax_portion,0.0))                 AS tariff,
                        SUM(COALESCE(logistics_costs,0.0))             AS logistics,
                        SUM(COALESCE(warehouse_cost,0.0))              AS warehouse,
                        SUM(COALESCE(manufacturing_overhead,0.0))      AS mfg_oh,
                        SUM(COALESCE(cost,0.0))                        AS total_cost
                    FROM scenario_result_node
                    WHERE run_id = ?
                    GROUP BY node_name
                    ORDER BY node_name
                """
                df = _pd.read_sql_query(q, con, params=(run_id,))
            finally:
                con.close()

            if df.empty:
                return df

            for c in ["revenue","profit","dm","tariff","logistics","warehouse","mfg_oh","total_cost"]:
                if c in df.columns:
                    df[c] = _pd.to_numeric(df[c], errors="coerce").fillna(0.0)
                else:
                    df[c] = 0.0

            df["other_costs"] = (df["total_cost"] - (df["dm"]+df["tariff"]+df["logistics"]+df["warehouse"]+df["mfg_oh"])).clip(lower=0.0)

            if only_sales:
                mask = df["node_name"].astype(str).str.startswith(("CS_","RT_"))
                if mask.any():
                    df = df.loc[mask].copy()

            return df

        def _plot_breakdown_single(df: _pd.DataFrame, title: str):
            if df.empty:
                messagebox.showinfo("Breakdown", "該当ランに明細がありません。Run & Save を実行してください。")
                return
            nodes = df["node_name"].tolist()
            x = _np.arange(len(nodes)); width = 0.55

            figwin = tk.Toplevel(win); figwin.title(title)
            fig = Figure(figsize=(8.5, 4.6), dpi=100); ax = fig.add_subplot(111)

            stacks = [
                ("Direct Materials", df["dm"].values, _COLORS["Direct Materials"]),
                ("Tariff",           df["tariff"].values, _COLORS["Tariff"]),
                ("Logistics",        df["logistics"].values, _COLORS["Logistics"]),
                ("Warehouse",        df["warehouse"].values, _COLORS["Warehouse"]),
                ("Mfg Overhead",     df["mfg_oh"].values, _COLORS["Mfg Overhead"]),
                ("Other Costs",      df["other_costs"].values, _COLORS["Other Costs"]),
            ]
            bottom = _np.zeros(len(df))
            for label, vals, color in stacks:
                ax.bar(x, vals, width=width, bottom=bottom, label=label, color=color, alpha=0.90)
                bottom += vals

            ax2 = ax.twinx()
            w2 = 0.32
            ax2.bar(x - (width/2 + 0.06), df["revenue"].values, width=w2, label="Revenue", color="#4E79A7", alpha=0.75)
            ax2.bar(x + (width/2 + 0.06), df["profit"].values,  width=w2, label="Profit",  color="#F28E2B", alpha=0.75)

            ax.set_xticks(x, nodes, rotation=30, ha="right")
            ax.set_ylabel("Cost (sum of components)")
            ax2.set_ylabel("Revenue / Profit")
            fmt = _Fmt(lambda v, _p: f"{v:,.0f}" if abs(v) >= 10 else f"{v:.2f}")
            ax.yaxis.set_major_formatter(fmt); ax2.yaxis.set_major_formatter(fmt)

            total_cost = df["total_cost"].values
            for xi, tc in enumerate(total_cost):
                ax.text(xi, tc + max(total_cost)*0.02, f"{tc:,.0f}", ha="center", va="bottom", fontsize=9, color="#333")

            leg1 = ax.legend(loc="upper left", ncols=3, fontsize=8, frameon=False)
            leg2 = ax2.legend(loc="upper right", fontsize=8, frameon=False)
            ax.add_artist(leg1); ax2.add_artist(leg2)

            ax.set_title(title); fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=figwin); canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)
            try: NavigationToolbar2Tk(canvas, figwin).update()
            except Exception: pass
            figwin._canvas, figwin._fig = canvas, fig

        def _plot_breakdown_compare(dfA: _pd.DataFrame, dfB: _pd.DataFrame, title: str):
            if dfA.empty or dfB.empty:
                messagebox.showinfo("Compare Breakdown", "どちらかのランに明細がありません。Run & Save を実行してください。")
                return
            nodes = sorted(set(dfA["node_name"]).union(dfB["node_name"]))
            def _reindex(df):
                df2 = df.set_index("node_name").reindex(nodes).fillna(0.0).reset_index()
                return df2
            A = _reindex(dfA); B = _reindex(dfB)

            x = _np.arange(len(nodes)); width = 0.36
            figwin = tk.Toplevel(win); figwin.title(title)
            fig = Figure(figsize=(9.5, 5.0), dpi=100); ax = fig.add_subplot(111)

            bottom = _np.zeros(len(A))
            for label, col, color in [
                ("Direct Materials","dm",       _COLORS["Direct Materials"]),
                ("Tariff",          "tariff",   _COLORS["Tariff"]),
                ("Logistics",       "logistics",_COLORS["Logistics"]),
                ("Warehouse",       "warehouse",_COLORS["Warehouse"]),
                ("Mfg Overhead",    "mfg_oh",   _COLORS["Mfg Overhead"]),
                ("Other Costs",     "other_costs", _COLORS["Other Costs"]),
            ]:
                vals = A[col].values
                ax.bar(x - width/2, vals, width=width, bottom=bottom, color=color, alpha=0.9, label=label if col=="dm" else None)
                bottom += vals

            bottom = _np.zeros(len(B))
            for label, col, color in [
                ("Direct Materials","dm",       _COLORS["Direct Materials"]),
                ("Tariff",          "tariff",   _COLORS["Tariff"]),
                ("Logistics",       "logistics",_COLORS["Logistics"]),
                ("Warehouse",       "warehouse",_COLORS["Warehouse"]),
                ("Mfg Overhead",    "mfg_oh",   _COLORS["Mfg Overhead"]),
                ("Other Costs",     "other_costs", _COLORS["Other Costs"]),
            ]:
                vals = B[col].values
                ax.bar(x + width/2, vals, width=width, bottom=bottom, color=color, alpha=0.5)
                bottom += vals

            ax2 = ax.twinx(); w2 = 0.20
            ax2.bar(x - (width/2 + 0.10), A["revenue"].values, width=w2, color="#4E79A7", alpha=0.85, label="Revenue A")
            ax2.bar(x - (width/2 - 0.10), A["profit"].values,  width=w2, color="#F28E2B", alpha=0.85, label="Profit A")
            ax2.bar(x + (width/2 - 0.10), B["revenue"].values, width=w2, color="#4E79A7", alpha=0.45, label="Revenue B")
            ax2.bar(x + (width/2 + 0.10), B["profit"].values,  width=w2, color="#F28E2B", alpha=0.45, label="Profit B")

            ax.set_xticks(x, nodes, rotation=30, ha="right")
            fmt = _Fmt(lambda v, _p: f"{v:,.0f}" if abs(v) >= 10 else f"{v:.2f}")
            ax.yaxis.set_major_formatter(fmt); ax2.yaxis.set_major_formatter(fmt)

            ax.legend(loc="upper left", ncols=3, fontsize=8, frameon=False, title="Cost components")
            ax2.legend(loc="upper right", fontsize=8, frameon=False, title="Revenue / Profit")

            ax.set_title(title); fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=figwin); canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)
            try: NavigationToolbar2Tk(canvas, figwin).update()
            except Exception: pass
            figwin._canvas, figwin._fig = canvas, fig

        # Breakdown ボタン（従来版）
        row_btn = ttk.Frame(win); row_btn.pack(fill="x", padx=6, pady=(0,6))
        def _on_breakdown_A():
            selA = cbA.get()
            if selA not in disp2row: return
            rA = disp2row[selA][0]
            dfA = _fetch_breakdown_df(rA, only_sales=False)
            _plot_breakdown_single(dfA, title=f"Breakdown  |  {selA}")

        def _on_breakdown_B():
            selB = cbB.get()
            if selB not in disp2row: return
            rB = disp2row[selB][0]
            dfB = _fetch_breakdown_df(rB, only_sales=False)
            _plot_breakdown_single(dfB, title=f"Breakdown  |  {selB}")

        def _on_compare_breakdown():
            selA, selB = cbA.get(), cbB.get()
            if selA not in disp2row or selB not in disp2row: return
            rA, rB = disp2row[selA][0], disp2row[selB][0]
            dfA = _fetch_breakdown_df(rA, only_sales=False)
            dfB = _fetch_breakdown_df(rB, only_sales=False)
            _plot_breakdown_compare(dfA, dfB, title=f"Breakdown Compare  |  {selA}  vs  {selB}")

        ttk.Button(row_btn, text="Breakdown (A)",     command=_on_breakdown_A).pack(side="left", padx=4)
        ttk.Button(row_btn, text="Breakdown (B)",     command=_on_breakdown_B).pack(side="left", padx=4)
        ttk.Button(row_btn, text="Compare Breakdown", command=_on_compare_breakdown).pack(side="left", padx=12)

        # ==== PATCH: Compare Breakdown（差分ラベル / 並び順 / only_sales / 比率 / CSV / 重複潰し）====
        import sqlite3 as _sq_adv, numpy as _np_adv, pandas as _pd_adv
        from matplotlib.figure import Figure as _FigAdv
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg as _CanvasAdv, NavigationToolbar2Tk as _ToolbarAdv
        import tkinter as _tk
        from tkinter import ttk as _ttk, filedialog as _fd

        def _show_breakdown_compare_adv():
            # ---------- ユーティリティ ----------
            def _get_run_id(sel_disp: str) -> str:
                return disp2row[sel_disp][0]

            # === code-1: 重複ノードを groupby で集計して返す ===
            def _fetch_node_df(run_id: str) -> _pd_adv.DataFrame:
                con = _sq_adv.connect(dbp)
                try:
                    cols = [
                        "node_name","product_name","revenue","profit",
                        "direct_materials_costs","logistics_costs","warehouse_cost",
                        "manufacturing_overhead","tax_portion","cost"
                    ]
                    exist = [c[1] for c in con.execute("PRAGMA table_info(scenario_result_node)")]
                    cols_use = [c for c in cols if c in exist]
                    q = f"SELECT {', '.join(cols_use)} FROM scenario_result_node WHERE run_id=?"
                    df = _pd_adv.read_sql_query(q, con, params=(run_id,))
                finally:
                    con.close()

                # 数値化
                for c in ("revenue","profit","direct_materials_costs","logistics_costs",
                        "warehouse_cost","manufacturing_overhead","tax_portion","cost"):
                    if c in df.columns:
                        df[c] = _pd_adv.to_numeric(df[c], errors="coerce").fillna(0.0)
                    else:
                        df[c] = 0.0

                # product_name は集計の邪魔になるので落とす
                if "product_name" in df.columns:
                    df = df.drop(columns=["product_name"])

                # other / total 計算
                comp_known = df[["direct_materials_costs","logistics_costs","warehouse_cost",
                                "manufacturing_overhead","tax_portion"]].sum(axis=1)
                df["other_costs"] = (df["cost"] - comp_known).clip(lower=0.0)
                df["total_cost"]  = df[["direct_materials_costs","logistics_costs","warehouse_cost",
                                        "manufacturing_overhead","tax_portion","other_costs"]].sum(axis=1)

                # ★ ノード単位に集計して重複排除（ここがポイント）
                df = df.groupby("node_name", as_index=False).sum(numeric_only=True)

                return df

            def _sort_nodes(names: list[str]) -> list[str]:
                pos = getattr(self, "pos_E2E", {}) or {}
                # ユニーク化してから並び替え
                uniq = list(dict.fromkeys(names))
                def key(n):
                    p = pos.get(n)
                    return (p[0] if p else float("inf"), n)
                return sorted(uniq, key=key)

            def _filter_nodes_sales(names: list[str]) -> list[str]:
                return [n for n in names if str(n).startswith("CS_") or str(n).startswith("RT_")]

            def _build_export_df(dfA: _pd_adv.DataFrame, dfB: _pd_adv.DataFrame, nodes: list[str]) -> _pd_adv.DataFrame:
                take = ["direct_materials_costs","logistics_costs","warehouse_cost",
                        "manufacturing_overhead","tax_portion","other_costs","total_cost","revenue","profit"]
                A = (dfA[dfA["node_name"].isin(nodes)][["node_name"]+take]
                        .set_index("node_name").rename(columns={c:f"{c}_A" for c in take}))
                B = (dfB[dfB["node_name"].isin(nodes)][["node_name"]+take]
                        .set_index("node_name").rename(columns={c:f"{c}_B" for c in take}))
                out = A.join(B, how="outer").fillna(0.0)
                out["delta_revenue"]    = out["revenue_A"]    - out["revenue_B"]
                out["delta_profit"]     = out["profit_A"]     - out["profit_B"]
                out["delta_total_cost"] = out["total_cost_A"] - out["total_cost_B"]
                return out.loc[nodes]

            # ---------- UI ----------
            selA, selB = cbA.get(), cbB.get()
            if selA not in disp2row or selB not in disp2row:
                messagebox.showwarning("Compare Runs", "Run A/B を選択してください。")
                return

            rA, rB = _get_run_id(selA), _get_run_id(selB)
            figwin = _tk.Toplevel(win)
            figwin.title(f"Breakdown Compare  |  {selA}  vs  {selB}")

            top = _ttk.Frame(figwin); top.pack(fill="x", padx=6, pady=4)
            var_only_sales = _tk.BooleanVar(value=False)
            var_ratio      = _tk.BooleanVar(value=False)
            _ttk.Checkbutton(top, text="only CS_/RT_ nodes",  variable=var_only_sales,
                            command=lambda: _redraw()).pack(side="left", padx=4)
            _ttk.Checkbutton(top, text="Cost as % (ratio mode)", variable=var_ratio,
                            command=lambda: _redraw()).pack(side="left", padx=4)
            _ttk.Button(top, text="Export CSV…", command=lambda: _export_csv()).pack(side="right", padx=4)

            fig = _FigAdv(figsize=(8.6, 4.2), dpi=100)
            ax = fig.add_subplot(111)
            canvas = _CanvasAdv(fig, master=figwin)
            canvas.draw(); canvas.get_tk_widget().pack(fill="both", expand=True)
            try:
                _ToolbarAdv(canvas, figwin).update()
            except Exception:
                pass

            # 描画ロジック
            dfA_full, dfB_full = _fetch_node_df(rA), _fetch_node_df(rB)
            comp_cols = ["direct_materials_costs","logistics_costs","warehouse_cost",
                        "manufacturing_overhead","tax_portion","other_costs"]

            def _redraw():
                ax.clear()
                nodes = sorted(set(dfA_full["node_name"]).union(dfB_full["node_name"]))
                nodes = _sort_nodes(nodes)
                if var_only_sales.get():
                    nodes = _filter_nodes_sales(nodes)
                if not nodes:
                    ax.text(0.5, 0.5, "No nodes to display", ha="center", va="center",
                            transform=ax.transAxes)
                    canvas.draw(); return

                # === code-2: 可視化用DFを groupby→reindex で整形（重複潰し） ===
                dfA = (dfA_full[dfA_full["node_name"].isin(nodes)]
                    .groupby("node_name", as_index=True).sum(numeric_only=True)
                    .reindex(nodes).fillna(0.0))
                dfB = (dfB_full[dfB_full["node_name"].isin(nodes)]
                    .groupby("node_name", as_index=True).sum(numeric_only=True)
                    .reindex(nodes).fillna(0.0))

                if var_ratio.get():
                    baseA = dfA["total_cost"].replace(0, _np_adv.nan)
                    baseB = dfB["total_cost"].replace(0, _np_adv.nan)
                    partsA = (dfA[comp_cols].div(baseA, axis=0)*100.0).fillna(0.0)
                    partsB = (dfB[comp_cols].div(baseB, axis=0)*100.0).fillna(0.0)
                    y_label = "Cost (%)"; y_max = 100.0
                else:
                    partsA = dfA[comp_cols]; partsB = dfB[comp_cols]
                    y_label = "Cost (money)"
                    y_max = float(max(dfA["total_cost"].max(), dfB["total_cost"].max()))*1.15 + 1e-9

                x = _np_adv.arange(len(nodes)); w = 0.42
                bottomA = _np_adv.zeros(len(nodes)); bottomB = _np_adv.zeros(len(nodes))
                color_map = {
                    "direct_materials_costs": "#1f77b4",
                    "logistics_costs": "#2ca02c",
                    "warehouse_cost": "#17becf",
                    "manufacturing_overhead": "#8c564b",
                    "tax_portion": "#d62728",
                    "other_costs": "#7f7f7f",
                }
                for c in comp_cols:
                    a = partsA[c].to_numpy(); b = partsB[c].to_numpy()
                    ax.bar(x - w/2, a, width=w, bottom=bottomA, color=color_map[c],
                        label=c if (c==comp_cols[0]) else None)
                    ax.bar(x + w/2, b, width=w, bottom=bottomB, color=color_map[c])
                    bottomA += a; bottomB += b

                # 右軸：Revenue / Profit（実額）
                ax2 = ax.twinx()
                revA, revB = dfA["revenue"].to_numpy(), dfB["revenue"].to_numpy()
                prfA, prfB = dfA["profit"].to_numpy(),  dfB["profit"].to_numpy()
                ax2.bar(x - w/2, revA, width=w*0.35, color="#4E79A7", alpha=0.35, label="Revenue A")
                ax2.bar(x + w/2, revB, width=w*0.35, color="#4E79A7", alpha=0.70, hatch="//", label="Revenue B")
                ax2.bar(x - w/2, prfA, width=w*0.35, color="#F28E2B", alpha=0.35, bottom=revA*0, label="Profit A")
                ax2.bar(x + w/2, prfB, width=w*0.35, color="#F28E2B", alpha=0.70, hatch="\\\\", bottom=revB*0, label="Profit B")

                # Δラベル（棒の上）
                d_rev = revA - revB; d_prf = prfA - prfB
                totA = dfA["total_cost"].to_numpy(); totB = dfB["total_cost"].to_numpy()
                d_cst = totA - totB
                tops = _np_adv.maximum(bottomA, bottomB)
                for i, xi in enumerate(x):
                    txt = f"ΔR={d_rev[i]:,.0f}\nΔP={d_prf[i]:,.0f}\nΔC={d_cst[i]:,.0f}"
                    ax.text(xi, tops[i] + (y_max*0.02 if not var_ratio.get() else 3),
                            txt, ha="center", va="bottom", fontsize=8, color="#444")

                ax.set_ylabel(y_label)
                ax.set_xticks(x, nodes, rotation=40, ha="right")
                if var_ratio.get(): ax.set_ylim(0, 100)
                ax.grid(axis="y", linestyle=":", alpha=0.4)
                ax.set_title(f"Cost Breakdown  |  {selA}  vs  {selB}")
                import matplotlib.ticker as mtick
                ax2.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v,_: f"{v:,.0f}"))
                ax2.set_ylabel("Revenue / Profit (money)")
                ax2.legend(loc="upper right", fontsize=9)

                fig.tight_layout(); canvas.draw()

            def _export_csv():
                nodes = sorted(set(dfA_full["node_name"]).union(dfB_full["node_name"]))
                nodes = _sort_nodes(nodes)
                if var_only_sales.get(): nodes = _filter_nodes_sales(nodes)
                df_out = _build_export_df(dfA_full, dfB_full, nodes)
                path = _fd.asksaveasfilename(
                    parent=figwin,
                    defaultextension=".csv",
                    filetypes=[("CSV", "*.csv"), ("All Files", "*.*")],
                    initialfile="breakdown_compare.csv",
                    title="Export breakdown as CSV"
                )
                if path:
                    df_out.to_csv(path, encoding="utf-8-sig", float_format="%.6g")

            _redraw()

        # adv 版ボタンを追加
        ttk.Button(row_btn, text="Compare Breakdown (adv)", command=_show_breakdown_compare_adv)\
            .pack(side="left", padx=12)

        # 既定選択：同一シナリオの最新2本 → 無ければ全体最新2本
        rs = fetch_runs_for_sid(cur_sid, limit=2)
        if len(rs) >= 2:
            set_from_rows(rs)
        else:
            pick_overall_latest2()






    # --- 追加：①②③④⑤を一括実行し、評価とビュー更新まで行う ---
    def _run_planning_sequence(self, *, use_selected_decouples: bool = True):
        import pysi.plan.engines as eng

        # roots
        prod, out_root, in_root = self._get_roots()
        if not (out_root and in_root):
            print("[WARN] roots not ready"); return

        mom_name = (self.var_mom.get().strip() if hasattr(self, "var_mom") else "") or "MOM"

        # ① Outbound/Demand Backward (leaf→MOM)
        out_root, in_root = eng.outbound_backward_leaf_to_MOM(out_root, in_root, layer="demand")
        # ② Inbound/Demand MOM Leveling (vs capacity)
        out_root, in_root = eng.inbound_MOM_leveling_vs_capacity(out_root, in_root, mom_name=mom_name)
        # ③ Inbound/Demand Backward (MOM→leaf)
        out_root, in_root = eng.inbound_backward_MOM_to_leaf(out_root, in_root, layer="demand")
        # ④ Inbound/Supply Forward (leaf→MOM)
        out_root, in_root = eng.inbound_forward_leaf_to_MOM(out_root, in_root, layer="supply")
        # ⑤ Outbound/Supply PUSH（必要に応じて decouple 指定）
        decouples = (self.decouple_node_selected or []) if use_selected_decouples else None
        out_root, in_root = eng.push_pull(out_root, in_root, decouple_nodes=decouples)

        # 計画結果をアプリに反映
        self.root_node_outbound, self.root_node_inbound = out_root, in_root

        # --- 評価（ツリーにコスト貼付け＆DataFrame化） ---
        try:
            self.update_evaluation_results4multi_product()  # 既存の総合評価
            self._ensure_cost_df()                          # cost_df を再構築（円グラフが見ているDF）
        except Exception as e:
            print("[WARN] evaluation:", e)

        # 最後に1回だけ再描画
        try:
            self._refresh_views()
        except Exception as e:
            print("[WARN] refresh views:", e)









    # **************************
    # setup_ui
    # **************************
    def setup_ui(self):
        print("setup_ui is processing")
        # ===== 基本スタイル =====
        custom_font = tkfont.Font(family="Helvetica", size=12)
        self.root.option_add('*TearOffMenu*Font', custom_font)
        self.root.option_add('*Menu*Font', custom_font)
        style = ttk.Style()
        style.configure("TLabel",   font=('Helvetica', 10))
        style.configure("TButton",  font=('Helvetica', 10))
        style.configure("Disabled.TButton", font=('Helvetica', 10))
        # ===== メニュー =====
        menubar   = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        is_sql = hasattr(self, "psi") and self.psi is not None and \
                self.psi.__class__.__name__.lower().startswith("sql")
        if is_sql:
            file_menu.add_command(label="RELOAD from SQL", command=self.reload_from_sql)
            file_menu.add_separator()
            file_menu.add_command(label="OPEN: select Directory", state="disabled")
            file_menu.add_command(label="SAVE: to Directory",    state="disabled")
            file_menu.add_command(label="LOAD: from Directory",   state="disabled")
        else:
            file_menu.add_command(label="OPEN: select Directory", command=self.load_data_files)
            file_menu.add_separator()
            file_menu.add_command(label="SAVE: to Directory", command=self.save_to_directory)
            file_menu.add_command(label="LOAD: from Directory", command=self.load_from_directory)
        file_menu.add_separator()
        file_menu.add_command(label="EXIT", command=self.on_exit)
        menubar.add_cascade(label=" FILE  ", menu=file_menu)
        # View
        self.view_mode = "network"
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Network Graph",            command=lambda: self._switch_view("network"))
        view_menu.add_command(label="World Map (global)",       command=lambda: self._switch_view("worldmap"))
        view_menu.add_command(label="World Map (fit to data)",  command=lambda: self._switch_view("worldmap_fit"))
        menubar.add_cascade(label="View", menu=view_menu)
        # Optimize
        optimize_menu = tk.Menu(menubar, tearoff=0)
        optimize_menu.add_command(label="Save Objective Value", command=self.Save_Objective_Value)
        optimize_menu.add_separator()
        optimize_menu.add_command(label="Weight: Cost Stracture on Common Plan Unit", command=self.show_cost_stracture_bar_graph)
        optimize_menu.add_command(label="Capacity: Market Demand", command=self.show_month_data_csv)
        menubar.add_cascade(label="Optimize Parameter", menu=optimize_menu)
        # Report
        report_menu = tk.Menu(menubar, tearoff=0)
        report_menu.add_command(label="Outbound: PSI to csv file",       command=self.outbound_psi_to_csv)
        report_menu.add_command(label="Outbound: Lot by Lot data to csv",command=self.outbound_lot_by_lot_to_csv)
        report_menu.add_separator()
        report_menu.add_command(label="Inbound: PSI to csv file",         command=self.inbound_psi_to_csv)
        report_menu.add_command(label="Inbound: Lot by Lot data to csv",  command=self.inbound_lot_by_lot_to_csv)
        report_menu.add_separator()
        report_menu.add_command(label="Value Chain: Cost Stracture a Lot",command=self.lot_cost_structure_to_csv)
        report_menu.add_command(label="Supply Chain: Revenue Profit",     command=self.supplychain_performance_to_csv)
        menubar.add_cascade(label="Report", menu=report_menu)
        #@251002 STOP
        ## Revenue/Profit
        #revenue_profit_menu = tk.Menu(menubar, tearoff=0)
        #revenue_profit_menu.add_command(label="Revenue and Profit", command=self.show_revenue_profit)
        #menubar.add_cascade(label="Revenue and Profit", menu=revenue_profit_menu)
        # Evaluation
        #@251002 sample code for Offering Price
        ## どこかのコントロール群を組んでいる箇所に
        #_btn("Show Offering Price (selected)", lambda: self.show_offering_price_board(products="selected"))
        #_btn("Show Offering Price (all)",      lambda: self.show_offering_price_board(products=None))
        #evaluation_menu = tk.Menu(menubar, tearoff=0)
        #evaluation_menu.add_command(label="Show Offering Price (selected)", command=self.show_offering_price_board(products="selected"))
        #evaluation_menu.add_command(label="Show Offering Price (all)", command=self.show_offering_price_board(products=None))
        #evaluation_menu.add_command(label="Revenue and Profit", command=self.show_revenue_profit)
        #menubar.add_cascade(label="Evaluation", menu=evaluation_menu)
        # Evaluation
        # メニューバー作成部
        evaluation_menu = tk.Menu(menubar, tearoff=0)
        evaluation_menu.add_command(
            label="Show Offering Price (selected)",
            command=lambda: self.show_offering_price_board(products="selected"))
        evaluation_menu.add_command(
            label="Show Offering Price (all)",
            command=lambda: self.show_offering_price_board(products=None))
        evaluation_menu.add_command(
            label="Revenue and Profit",
            command=self.show_revenue_profit)
        menubar.add_cascade(label="Evaluation", menu=evaluation_menu)
        # Cashflow
        cashflow_menu = tk.Menu(menubar, tearoff=0)
        cashflow_menu.add_command(label="PSI Price for CF", command=self.psi_price4cf)
        cashflow_menu.add_command(label="Cash Out&In&Net",  command=self.cashflow_out_in_net)
        menubar.add_cascade(label="Cash Flow", menu=cashflow_menu)
        # Overview
        overview_menu = tk.Menu(menubar, tearoff=0)
        overview_menu.add_command(label="3D overview on Lots based Plan", command=self.show_3d_overview)
        menubar.add_cascade(label="3D overview", menu=overview_menu)
        self.root.config(menu=menubar)
        # =====================================================================
        # ★ レイアウト：HORIZONTAL PanedWindow (Network｜PSI｜Controls)
        # =====================================================================
        self.main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main.pack(fill=tk.BOTH, expand=True)
        self.frame_network  = ttk.Frame(self.main)         # 左：ネットワーク／地図
        self.frame_psi      = ttk.Frame(self.main, width=520)   # 中：PSI（スクロール）
        self.frame_controls = ttk.Frame(self.main, width=320)   # 右：各種コントロール
        self.main.add(self.frame_network,  weight=3)
        self.main.add(self.frame_psi,      weight=2)   # PSI に横幅を確保
        self.main.add(self.frame_controls, weight=1)
        # PanedWindow 作成・追加の直後に入れる
        for orphan_name in ('main_panel', 'left_panel', 'right_panel', 'right_psi'):
            w = getattr(self, orphan_name, None)
            if w:
                try:
                    w.destroy()
                except Exception:
                    pass
                try:
                    delattr(self, orphan_name)
                except Exception:
                    pass


        # =====================================================================
        # 右：コントロールパネルをスクロール可能に
        # =====================================================================
        CTRL_H = None  # 縦は親フレームに任せる（PanedWindow の高さに追従）
        self.ctrl_canvas = tk.Canvas(self.frame_controls, highlightthickness=0, height=CTRL_H)
        self.ctrl_vsb    = ttk.Scrollbar(self.frame_controls, orient="vertical", command=self.ctrl_canvas.yview)
        self.ctrl_canvas.configure(yscrollcommand=self.ctrl_vsb.set)

        # pack（PanedWindow の子なので pack でOK）
        self.ctrl_canvas.pack(side="left", fill="both", expand=True)
        self.ctrl_vsb.pack(side="right", fill="y")
        
        # コントロール群を入れる実体フレーム
        self.right_ctrl   = ttk.Frame(self.ctrl_canvas)
        self.ctrl_window  = self.ctrl_canvas.create_window((0, 0), window=self.right_ctrl, anchor="nw")
        def _ctrl_on_config(event=None):
            self.ctrl_canvas.configure(scrollregion=self.ctrl_canvas.bbox("all"))
            try:
                self.ctrl_canvas.itemconfigure(self.ctrl_window, width=self.ctrl_canvas.winfo_width())
            except Exception:
                pass
        self.right_ctrl.bind("<Configure>",  _ctrl_on_config)
        self.ctrl_canvas.bind("<Configure>", _ctrl_on_config)
        
        # 互換のため、従来コードが self.frame を親とみなす箇所に対応
        self.frame = self.right_ctrl
        
        # =====================================================================
        # 中：PSI 表示領域（スクロール可）
        # =====================================================================
        self._ensure_psi_area(self.frame_psi)  # self.canvas_psi / self.scrollable_frame を作成
        
        # =====================================================================
        # 左：ネットワーク（または地図）の Axes/Canvas を用意
        # =====================================================================
        self._ensure_network_axes(self.frame_network)
        
        # =====================================================================
        # 4A) Select Product（右パネルの最上段）
        # =====================================================================
        frm = ttk.LabelFrame(self.right_ctrl, text="Select Product")
        frm.pack(fill="x", padx=2, pady=2)
        self.product_name_list = sorted((getattr(self.psi, "prod_tree_dict_OT", {}) or {}).keys())
        self.cb_product = ttk.Combobox(frm, values=self.product_name_list, state="readonly", width=18)
        self.cb_product.pack(fill="x", padx=2, pady=2)
        # 初期選択
        if getattr(self, "product_selected", None) in self.product_name_list:
            self.cb_product.set(self.product_selected)
        elif self.product_name_list:
            self.cb_product.current(0)
            self.product_selected = self.product_name_list[0]
        # コンボのイベント
        self.cb_product.bind("<<ComboboxSelected>>", self.on_product_changed)


        # =====================================================================
        # 4B) Select Scenario（右パネルのProdcut 下）
        # =====================================================================
        # --- Select Scenario コンボ ---
        frm_scn = ttk.LabelFrame(self.right_ctrl, text="Scenario")
        frm_scn.pack(fill="x", padx=2, pady=2)

        def _refresh_scenario_list():
            dbp = get_db_path_from(self.psi if hasattr(self, "psi") else self)
            items = list_scenarios(dbp)  # [(id, name)]
            # 先頭に「BASE(None)」を入れる
            display = ["BASE (None)"] + [f"{sid}  —  {name}" for sid, name in items]
            self.cb_scn["values"] = display
            # 既に選択があれば復元、無ければ先頭に
            cur = "BASE (None)" if not self.active_scenario_id else \
                next((x for x in display if x.startswith(self.active_scenario_id)), "BASE (None)")
            self.cb_scn.set(cur)

        self.cb_scn = ttk.Combobox(frm_scn, state="readonly")
        self.cb_scn.pack(fill="x", padx=2, pady=2)

        def _on_scenario_changed(event=None):
            val = self.cb_scn.get()
            self.active_scenario_id = None if val.startswith("BASE") else val.split("—", 1)[0].strip()
            print(f"[SCENARIO] active_scenario_id = {self.active_scenario_id}")
            try:
                # Offering Price ボードを開いているなら再描画（なければ無害）
                self.show_offering_price_board(products="selected")
            except Exception:
                pass

        self.cb_scn.bind("<<ComboboxSelected>>", _on_scenario_changed)
        _refresh_scenario_list()

        # =====================================================================
        # 4C) Run and Save Scenario（右パネルのSelect Scenario 下）
        # =====================================================================
        # ファイル冒頭の imports に追加
        from pysi.scenario.store import save_run_results, list_runs
        #offering_price import build_offering_price_frame  # 既にあれば重複不要


        # ...Scenarioセクションの後あたりに追記...
        row = ttk.Frame(frm_scn); row.pack(fill="x", padx=2, pady=(2,4))
        ttk.Button(row, text="Run & Save Results", command=self._run_and_save).pack(side="left", padx=4)
        ttk.Button(row, text="Compare Runs…",    command=self._show_compare_popup).pack(side="left", padx=4)




        # =====================================================================
        # ★ Planning Engines（右パネル）
        # =====================================================================
        self.frm_engine = ttk.LabelFrame(self.right_ctrl, text="Planning Engines")
        self.frm_engine.pack(fill="x", padx=2, pady=4)
        def _btn(txt, cmd):
            b = ttk.Button(self.frm_engine, text=txt, command=cmd)
            b.pack(fill="x", padx=6, pady=2)
            return b
        _btn("① Outbound/Demand Backward (leaf→MOM)",        lambda: self.run_outbound_backward_leaf_to_MOM())
        _btn("② Inbound/Demand MOM Leveling (vs capacity)",   lambda: self.run_inbound_mom_leveling())
        _btn("③ Inbound/Demand Backward (MOM→leaf)",         lambda: self.run_inbound_backward_MOM_to_leaf())
        _btn("④ Inbound/Supply Forward (leaf→MOM→DAD)",      lambda: self.run_inbound_forward_leaf_to_MOM())
        _btn("⑤ Outbound/Supply PUSH (DAD→BUFFER)",          lambda: self.run_push_pull())
        _btn("⑥ Outbound/Supply PULL (BUFFER→leaf)",         lambda: self.run_push_pull())
        ttk.Separator(self.frm_engine, orient="horizontal").pack(fill="x", padx=6, pady=4)
        _btn("▶ Run Full PSI (①→②→③→④→⑤→⑥)", self._run_full_pipeline)
        # MOM/BUFFER の入力
        self.var_mom = tk.StringVar(value="MOM")
        self.var_buf = tk.StringVar(value="BUFFER")
        row = ttk.Frame(self.frm_engine); row.pack(fill="x", padx=6, pady=(6,2))
        ttk.Label(row, text="MOM name:").pack(side="left")
        ttk.Entry(row, textvariable=self.var_mom, width=18).pack(side="left", padx=6)
        row2 = ttk.Frame(self.frm_engine); row2.pack(fill="x", padx=6, pady=(0,6))
        ttk.Label(row2, text="BUFFER name:").pack(side="left")
        ttk.Entry(row2, textvariable=self.var_buf, width=18).pack(side="left", padx=6)
        # =====================================================================
        # 右パネル：各種パラメータ UI（以降は従来通り self.frame=self.right_ctrl を親に）
        # =====================================================================
        for label, attr, val in [
            ("MarketPotential", "gmp_entry", ""),
            ("TargetShare (%)", "ts_entry", self.config.DEFAULT_TARGET_SHARE * 100),
            ("Total Supply:    ", "tsp_entry", "")
        ]:
            ttk.Label(self.frame, text=label, background='navy', foreground='white',
                    font=('Helvetica', 10, 'bold')).pack(padx=2, pady=2)
            entry = tk.Entry(self.frame, width=10)
            if val != "": entry.insert(0, val)
            entry.pack(padx=2, pady=2)
            if attr == "tsp_entry": entry.config(bg='lightgrey')
            setattr(self, attr, entry)
        self.gmp_entry.bind("<Return>", self.update_total_supply_plan)
        self.ts_entry.bind("<Return>",  self.update_total_supply_plan)
        ttk.Label(self.frame, text="\n\n").pack()
        for label, attr, val in [
            ("Lot Size:", "lot_size_entry", self.config.DEFAULT_LOT_SIZE),
            ("Plan Year Start:", "plan_year_entry", self.config.DEFAULT_START_YEAR),
            ("Plan Range:", "plan_range_entry", self.config.DEFAULT_PLAN_RANGE),
            ("pre_proc_LT:", "pre_proc_LT_entry", self.config.DEFAULT_PRE_PROC_LT)
        ]:
            ttk.Label(self.frame, text=label).pack()
            entry = tk.Entry(self.frame, width=10); entry.insert(0, str(val))
            entry.pack(); setattr(self, attr, entry)
        ttk.Label(self.frame, text="\n\n").pack()
        self.Demand_Pl_button = ttk.Button(self.frame, text="Demand PlanMult", command=self.demand_planning4multi_product)
        self.Demand_Pl_button.pack(side=tk.TOP)
        self.Demand_Lv_button = ttk.Button(self.frame, text="Demand Leveling", command=self.demand_leveling4multi_prod)
        self.Demand_Lv_button.pack()
        ttk.Label(self.frame, text="\n\n").pack()
        for label, attr, cmd in [
            ("Supply PlanMult ",     "supply_planning_button", self.supply_planning4multi_product),
            ("Eval Buffer Stock ",   "eval_buffer_stock_button", self.eval_buffer_stock),
            ("OPT Supply Alloc",     "optimize_button", self.optimize_network),
            ("Inbound DmBw P",       "Inbound_DmBw_button", self.Inbound_DmBw),
            ("Inbound SpFw P",       "Inbound_SpFw_button", self.Inbound_SpFw)
        ]:
            button = ttk.Button(self.frame, text=label, command=cmd)
            button.pack(); setattr(self, attr, button)
        ttk.Label(self.frame, text="\n\n").pack()
        for label, attr in [
            ("Total Revenue:", "total_revenue_entry"),
            ("Total Profit:     ", "total_profit_entry"),
            ("Profit Ratio:     ", "profit_ratio_entry")
        ]:
            ttk.Label(self.frame, text=label, background='darkgreen', foreground='white',
                    font=('Helvetica', 10, 'bold')).pack(padx=2, pady=2)
            entry = tk.Entry(self.frame, width=10, state='readonly')
            entry.pack(padx=2, pady=2)
            setattr(self, attr, entry)
        # =====================================================================
        # 安全網：plan_range の既定値
        # =====================================================================
        if not hasattr(self, "plan_range"):
            try:
                self.plan_range = int(self.plan_range_entry.get())
            except Exception:
                self.plan_range = int(getattr(self.config, "DEFAULT_PLAN_RANGE", 3))
        # =====================================================================
        # 初回描画（ネットワーク → PSI）
        # =====================================================================
        self.view_nx_matlib4opt()  # 既存のネットワーク描画
        # 選択中の製品を取得して PSI を描く（未選択でも落ちない）
        try:
            prod = (self.cb_product.get() or getattr(self, "product_selected", None))
            if prod:
                # 初期は supply を基本に、空なら demand にフォールバック表示
                self.show_psi_overview(prod, primary_layer="supply", fallback_to_demand=True)
        except Exception as e:
            print("[WARN] initial psi overview:", e)

    def _ensure_cost_df(self):
        if getattr(self, "cost_df", None) is not None:
            return self.cost_df
        # 循環参照が怖い場合のローカル import 版
        from pysi.evaluate.cost_df_loader import (
            build_cost_df_from_csv_dir,
            build_cost_df_from_sql,
            normalize_cost_df_columns,
        )
        backend = getattr(self, "backend", "sql")  # "csv" or "sql"
        if backend == "csv":
            data_dir = getattr(self, "data_dir", "./data")
            self.cost_df = build_cost_df_from_csv_dir(data_dir)
        else:
            db_path = getattr(self, "db_path", "./var/psi.sqlite")
            #@251001 ADD
            from pysi.evaluate.pmpl_propagate import rebuild_pmpl
            rebuild_pmpl(db_path, mode="both", overwrite=False)

            #@251010 ADD for Hook and Plugin
            sid = getattr(self, "active_scenario_id", None)   # ★ ここが“どこから持ってくるか”の答え

            # BASE は None 扱いでOK（プラグイン側は scenario_id が None/BASE のときは素通しにできる）
            if isinstance(sid, str) and sid.strip().upper() == "BASE":
                sid = None

            self.cost_df = build_cost_df_from_sql(db_path, scenario_id=sid)
            #self.cost_df = build_cost_df_from_sql(db_path)

        self.cost_df = normalize_cost_df_columns(self.cost_df)
        return self.cost_df
    

    def reload_from_sql(self):
        """DBを再読込し、GUIへ即反映。"""
        prev = getattr(self, "product_selected", None)
        if hasattr(self.psi, "reload"):
            self.psi.reload()
        self._bind_env_to_gui(self.psi)  # product_name_list / 辞書を再バインド
        # 可能なら以前の選択に戻す
        if prev and prev in self.product_name_list:
            self.cb_product.set(prev)
            self.on_product_changed(None)
    def update_total_supply_plan(self, event):
        try:
            market_potential = float(self.gmp_entry.get().replace(',', ''))
            target_share = float(self.ts_entry.get().replace('%', ''))/100
        except ValueError:
            print("Invalid input for Global Market Potential or Target Share.")
            return
        # Total Supply Planの再計算
        total_supply_plan = round(market_potential * target_share)
        self.total_supply_plan = total_supply_plan
        # Total Supply Planフィールドの更新
        self.tsp_entry.config(state='normal')
        self.tsp_entry.delete(0, tk.END)
        self.tsp_entry.insert(0, "{:,}".format(total_supply_plan))  # 3桁毎にカンマ区切りで表示
        self.tsp_entry.config(state='normal')
    def initialize_parameters(self):
        print("Initializing parameters")
        self.lot_size     = self.config.DEFAULT_LOT_SIZE
        self.plan_year_st = self.config.DEFAULT_START_YEAR
        self.plan_range   = self.config.DEFAULT_PLAN_RANGE
        self.pre_proc_LT  = self.config.DEFAULT_PRE_PROC_LT
        # self.market_potential = 0 # initial setting from "demand_generate"
        self.target_share = self.config.DEFAULT_TARGET_SHARE
        self.total_supply = 0
        if not hasattr(self, 'gmp_entry') or not hasattr(self, 'ts_entry') or not hasattr(self, 'tsp_entry'):
            raise AttributeError("Required UI components (gmp_entry, ts_entry, tsp_entry) have not been initialized.")
        print("Setting market potential and share")
        # Calculation and setting of Global Market Potential
        market_potential = getattr(self, 'market_potential', self.config.DEFAULT_MARKET_POTENTIAL)  # Including initial settings
        self.gmp_entry.delete(0, tk.END)
        self.gmp_entry.insert(0, "{:,}".format(market_potential))  # Display with comma separated thousands
        # Initial setting of Target Share (already set in setup_ui)
        # Calculation and setting of Total Supply Plan
        target_share = float(self.ts_entry.get().replace('%', ''))/100  # Convert string to float and remove %
        total_supply_plan = round(market_potential * target_share)
        self.tsp_entry.delete(0, tk.END)
        self.tsp_entry.insert(0, "{:,}".format(total_supply_plan))  # Display with comma separated thousands
        #self.global_market_potential  = global_market_potential
        self.market_potential         = market_potential
        self.target_share             = target_share
        self.total_supply_plan        = total_supply_plan
        print(f"At initialization - market_potential: {self.market_potential}, target_share: {self.target_share}")  # Add log
    def updated_parameters(self):
        print(f"updated_parameters更新前 - market_potential: {self.market_potential}, target_share: {self.target_share}")  # ログ追加
        # Market Potentialの計算と設定
        market_potential = self.market_potential
        print("market_potential", market_potential)
        self.gmp_entry.delete(0, tk.END)
        self.gmp_entry.insert(0, "{:,}".format(market_potential))  # 3桁毎にカンマ区切りで表示
        # Target Shareの初期値設定（すでにsetup_uiで設定済み）
        #@ ADD: Keep the current target_share value if user has not entered a new value
        if self.ts_entry.get():
            target_share = float(self.ts_entry.get().replace('%', '')) / 100  # 文字列を浮動小数点数に変換して%を除去
        else:
            target_share = self.target_share
        # Total Supply Planの計算と設定
        total_supply_plan = round(market_potential * target_share)
        self.tsp_entry.delete(0, tk.END)
        self.tsp_entry.insert(0, "{:,}".format(total_supply_plan))  # 3桁毎にカンマ区切りで表示
        self.market_potential = market_potential
        self.target_share = target_share
        self.total_supply_plan = total_supply_plan
        print(f"updated_parameters更新時 - market_potential: {self.market_potential}, target_share: {self.target_share}")  # ログ追加
# ******************************
# actions
# ******************************
    def derive_weekly_capacity_from_plots(self):
        """
        node.psi4supply[w][3] に入っている P_lots の数をその週のキャパシティとみなして weekly_cap_dict を作成。
        """
        self.weekly_cap_dict = {}
        for node_name, node in self.nodes_outbound.items():
            self.weekly_cap_dict[node_name] = []
            for week_index, week_data in enumerate(node.psi4supply):
                lot_ids = week_data[3]
                if lot_ids:
                    self.weekly_cap_dict[node_name].append({
                        "week": week_index,
                        "capacity": len(lot_ids)
                    })
        print(f"[INFO] Weekly capacity derived from psi4supply for {len(self.weekly_cap_dict)} nodes")
#@250720 TODO memo
# 0a. SKU based S_month 2 week 2 psi4xxx
# 0b. SKU based evaluation
# 1. SKU based demand_planning
# 2. SKU based P_month allocation
# 3. SKU based suppy planning and PUSH/PULL planning
# *****************************
# 1.Done: load_data_files building GUI_node and PSI_node
# 2.Done: linking GUI_node 2 sku_dict[product_name] 2 sku=PSI_node
# 3.Done: setting cost paramete
# 4.TODO: setting S_month 2 psi4demand
# 5.TODO: showing network
# *****************************
    #@250808 ADD ******************
    # export offring_price ASIS/TOBE to csv
    # *****************************
    def export_offering_prices(self, output_csv_path):
        header = ["product_name", "node_name", "offering_price_ASIS", "offering_price_TOBE"]
        rows = []
        for node_name, node in self.nodes_outbound.items():  # inboundも必要なら追加ループ
            for product_name, plan_node in node.sku_dict.items():
                rows.append([
                    product_name,
                    node_name,
                    plan_node.offering_price_ASIS,
                    plan_node.offering_price_TOBE
                ])
        with open(output_csv_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
        print(f"[INFO] offering price CSV exported: {output_csv_path}")
#@250630 STOP GO

    def load_data_files(self):
        directory = filedialog.askdirectory(title="Select Data Directory")
        if directory:
            try:
                self.lot_size = int(self.lot_size_entry.get())
                self.plan_year_st = int(self.plan_year_entry.get())
                self.plan_range = int(self.plan_range_entry.get())
            except ValueError:
                print("Invalid input for lot size, plan year start, or plan range. Using default values.")
            self.outbound_data = []
            self.inbound_data = []
            data_file_list = os.listdir(directory)
            print("data_file_list", data_file_list)
            self.directory = directory
            self.load_directory = directory
            # --- Load Tree Structures ---
            if "product_tree_outbound.csv" in data_file_list:
                file_path_OT = os.path.join(directory, "product_tree_outbound.csv")
                nodes_outbound, root_node_name_out = create_tree_set_attribute(file_path_OT)
                root_node_outbound = nodes_outbound[root_node_name_out]
                def make_leaf_nodes(node, leaf_list):
                    if not node.children:
                        leaf_list.append(node.name)
                    for child in node.children:
                        make_leaf_nodes(child, leaf_list)
                    return leaf_list
                leaf_nodes_out = make_leaf_nodes(root_node_outbound, [])
                self.nodes_outbound = nodes_outbound
                self.root_node_outbound = root_node_outbound
                self.leaf_nodes_out = leaf_nodes_out
                set_positions(root_node_outbound)
                set_parent_all(root_node_outbound)
                print_parent_all(root_node_outbound)
            else:
                print("error: product_tree_outbound.csv is missed")
            if "product_tree_inbound.csv" in data_file_list:
                file_path_IN = os.path.join(directory, "product_tree_inbound.csv")
                nodes_inbound, root_node_name_in = create_tree_set_attribute(file_path_IN)
                root_node_inbound = nodes_inbound[root_node_name_in]
                self.nodes_inbound = nodes_inbound
                self.root_node_inbound = root_node_inbound
                set_positions(root_node_inbound)
                set_parent_all(root_node_inbound)
                print_parent_all(root_node_inbound)
            else:
                print("error: product_tree_inbound.csv is missed")
            # **************************************
            # join nodes_outbound and nodes_inbound
            # **************************************
            # マージ前に重複チェック（ログ出力あり）
            overlapping_keys = set(nodes_inbound) & set(nodes_outbound)
            if overlapping_keys:
                print(f"[Warn] Overlapping node names: {overlapping_keys}")
            #@STOP python 3.9 upper
            #node_dict = nodes_inbound | nodes_outbound
            # **************************************
            # this is Nodes_all for GUI handling
            # **************************************
            node_dict = {**nodes_inbound, **nodes_outbound}
            #  注意：重複キーがあると、後に出てくる辞書の値で上書きされます。
            # "supply_point"がoutboundとinboundで重複しoutboundで上書きされる
            #@250726 ココでby productのPlanNodeを生成
            # **************************************
            # make subtree by product_name from "csv files"
            # **************************************
            def build_prod_tree_from_csv(csv_data, product_name):
                node_dict = {}
                # 対象 product のみ抽出
                rows = [row for row in csv_data if row["Product_name"] == product_name]
                for row in rows:
                    p_name = row["Parent_node"]
                    c_name = row["Child_node"]
                    # ノード生成（product依存で一意）
                    if p_name not in node_dict:
                        node_dict[p_name] = PlanNode(name=p_name) #@250726MARK
                        #node_dict[p_name] = Node(name=p_name) #@250726MARK
                    if c_name not in node_dict:
                        node_dict[c_name] = PlanNode(name=c_name)
                        #node_dict[c_name] = Node(name=c_name)
                    parent = node_dict[p_name]
                    child = node_dict[c_name]
                    child.lot_size = int(row["lot_size"])
                    child.leadtime = int(row["leadtime"])
                    # SKUインスタンスを割り当て（planning用）
                    # ← PSI計算後にpsi4demandなどを持たせる
                    child.sku = SKU(product_name, child.name)
                    #@250728 STOP see "link_planning_nodes_to_gui_sku" in end_of_loading
                    ##@250728 MEMO linkage plan_node2gui_node
                    #gui_node = nodes_all[child.name]         # picking up gui_node
                    #gui_node.sku_dict[product_name] = child　# linking plan_node 2 gui_node
                    ##@250728 MEMO "plan_node = sku"となるので、planning engineはplan_nodeで良いsku無し
                    #@250726 STOP by productのPlanNodeの世界なので、node直下にskuがあり、sku_dictはxxx
                    #@250728 sku_dict[product_name] = plan_nodeとして、GUINodeとPlanNodeをlinkする
                    #        このlinkingは、plan_nodeのbuilding processで行う
                    ##@250725 MEMO setting for Multi-Product
                    #child.sku_dict[product_name] = SKU(product_name, child.name)
                    child.parent = parent
                    parent.add_child(child)
                return node_dict  # this is all nodes
                #return node_dict["supply_point"]  # root node
            prod_tree_dict_IN = {} # inbound  {product_name:subtree, ,,,}
            prod_tree_dict_OT = {} # outbound {product_name:subtree, ,,,}
            product_name_list = list(node_dict["supply_point"].sku_dict.keys())
            print("product_name_list", product_name_list)
            # initial setting product_name
            self.product_name_list = product_name_list
            self.product_selected = product_name_list[0]
            # initial setting for "Select Product" BOX UI
            self.cb_product['values'] = self.product_name_list
            if self.product_name_list:
                self.cb_product.current(0)
            prod_nodes = {} # by product tree node"s"
            product_tree_dict = {}
            for prod_nm in product_name_list:
                print("product_nm 4 subtree", prod_nm )
                #@250717 node4psi tree上のnode辞書も見えるようにしておく
                csv_data = read_csv_as_dictlist(file_path_OT)
                node4psi_dict_OT = build_prod_tree_from_csv(csv_data, prod_nm)
                # setting outbound root node
                prod_tree_root_OT = node4psi_dict_OT["supply_point"]
                prod_tree_dict_OT[prod_nm] = prod_tree_root_OT # by product root_node
                csv_data = read_csv_as_dictlist(file_path_IN)
                node4psi_dict_IN = build_prod_tree_from_csv(csv_data, prod_nm)
                # setting inbound root node
                prod_tree_root_IN = node4psi_dict_IN["supply_point"]
                prod_tree_dict_IN[prod_nm] = prod_tree_root_IN # by Product root_node
                #@250717 STOP root_nodeのみ
                #prod_tree_dict_OT[prod_nm] = build_prod_tree_from_csv(csv_data, prod_nm)
                #prod_tree_dict_IN[prod_nm] = build_prod_tree_from_csv(csv_data, prod_nm)
                #@250726 MEMO by Productでroot_nodeとnodesを生成後、
                # PlanNodeのroot_nodeからselfたどって? self.xxxとしてセットする
                def make_leaf_nodes(node, list):
                    if node.children == []: # leaf_nodeの場合
                        list.append(node.name)
                    else:
                        pass
                    for child in node.children:
                        make_leaf_nodes(child, list)
                    return list
                leaf_nodes = []
                leaf_nodes = make_leaf_nodes(prod_tree_root_OT, leaf_nodes)
                #leaf_nodes = make_leaf_nodes(root_node_out, leaf_nodes)
                #@250726 STOP このself.はGUI
                ## PlanNodeのinstanceも、self.xxx/plan_node.xxxの属性名は共通
                #leaf_nodes_out = make_leaf_nodes(prod_tree_root_OT, [])
                #
                #self.nodes_outbound = node4psi_dict_OT
                #self.root_node_outbound = prod_tree_root_OT
                #
                #self.leaf_nodes_out = leaf_nodes_out
                #
                ## このby ProductのpositionsはPlanNodeでは未使用GUINodeを使う
                ##set_positions(prod_tree_root_OT)
                #@250726 STOP 各nodeがtree全体の情報nodesを持つのは冗長
                #for node_name in list( node4psi_dict_OT.keys() ):
                #    plan_node = node4psi_dict_OT[node_name]
                #
                #    plan_node.nodes_outbound = node4psi_dict_OT
                #    plan_node.root_node_outbound = prod_tree_root_OT
                #
                #    leaf_nodes_out = make_leaf_nodes(prod_tree_root_OT, [])
                #    plan_node.leaf_nodes_out = leaf_nodes_out
                #@250726 GO
                set_parent_all(prod_tree_root_OT)
                print_parent_all(prod_tree_root_OT)
                #leaf_nodes_out = make_leaf_nodes(root_node_outbound, [])
                #self.nodes_outbound = nodes_outbound
                #self.root_node_outbound = root_node_outbound
                #self.leaf_nodes_out = leaf_nodes_out
                #set_positions(root_node_outbound)
                #set_parent_all(root_node_outbound)
                #print_parent_all(root_node_outbound)
                #@250726 STOP このself.はGUI
                ## nodes_inbound, root_node_name_in = create_tree_set_attribute(file_path_IN)
                ## root_node_inbound = nodes_inbound[root_node_name_in]
                #
                #self.nodes_inbound = node4psi_dict_IN
                #self.root_node_inbound = prod_tree_root_IN
                #
                ## このby ProductのpositionsはPlanNodeでは未使用GUINodeを使う
                ##set_positions(prod_tree_root_IN)
                #
                #@250726 STOP 各nodeがtree全体の情報nodesを持つのは冗長
                #for node_name in list( node4psi_dict_IN.keys() ):
                #    plan_node = node4psi_dict_IN[node_name]
                #
                #    plan_node.nodes_inbound = node4psi_dict_IN
                #    plan_node.root_node_inbound = prod_tree_root_IN
                #
                #    leaf_nodes_in = make_leaf_nodes(prod_tree_root_IN, [])
                #    plan_node.leaf_nodes_in = leaf_nodes_in
                #@250726 GO
                set_parent_all(prod_tree_root_IN)
                print_parent_all(prod_tree_root_IN)
                #nodes_inbound, root_node_name_in = create_tree_set_attribute(file_path_IN)
                #root_node_inbound = nodes_inbound[root_node_name_in]
                #
                #self.nodes_inbound = nodes_inbound
                #self.root_node_inbound = root_node_inbound
                #set_positions(root_node_inbound)
                #set_parent_all(root_node_inbound)
                #print_parent_all(root_node_inbound)
            # **************************
            # GUI-計算構造のリンク
            # **************************
            # 設計項目	内容
            # plan_node.name	GUIと計算ノードの一致キーは "Node.name"
            # gui_node_dict[name]	GUI上の全ノードを辞書化しておく
            #@250728 STOP
            ## sku_dict[product_name]	GUI上のSKU単位で .psi_node_refをセット
            ## psi_node_ref	計算結果（PSI/Costなど）の直接参照ポインタ
            #@250728 GO
            # sku_dict[product_name]	gui_nodeのby product(SKU単位)で、ここにplan_nodeを直接セット
            # "plan_node=sku"という意味合い
            def link_planning_nodes_to_gui_sku(product_tree_root, gui_node_dict, product_name):
                """
                product_tree_root: 計算用Node（product別）
                gui_node_dict: GUI上の全ノード（node.name -> Nodeインスタンス）
                product_name: 対象製品名（'JPN_Koshihikari'など）
                SKUオブジェクトに計算ノード（Node）のポインタを渡す
                """
                def traverse_and_link(plan_node):
                    gui_node = gui_node_dict.get(plan_node.name)
                    if gui_node is not None:
                        #@250728 STOP
                        #sku = gui_node.sku_dict.get(product_name)
                        #if sku:
                        #    #計算ノードへのリンク
                        #    sku.psi_node_ref = plan_node
                        #@250728 GO
                        gui_node.sku_dict[product_name] = plan_node # Plan2GUI direct setting
                    for child in plan_node.children:
                        traverse_and_link(child)
                traverse_and_link(product_tree_root)
            for prod_nm in product_name_list:
                link_planning_nodes_to_gui_sku(prod_tree_dict_OT[prod_nm], nodes_outbound, prod_nm)
                link_planning_nodes_to_gui_sku(prod_tree_dict_IN[prod_nm], nodes_inbound, prod_nm)
            # save to self.xxx
            self.prod_tree_dict_OT = prod_tree_dict_OT
            self.prod_tree_dict_IN = prod_tree_dict_IN
            # 検証表示
            for prod_nm in product_name_list:
                print("検証表示product_nm 4 subtree", prod_nm )
                if prod_tree_root_IN:
                    print("Inbound prod_tree:")
                    prod_tree_dict_IN[prod_nm].print_tree()
                if prod_tree_root_OT:
                    print("Outbound prod_tree:")
                    prod_tree_dict_OT[prod_nm].print_tree()
            # **************************************
            # end of GUI_node, PSI_node and sku data building
            # **************************************
            # **************************************
            # setting cost parameters
            # **************************************
            #@250719 ADD
            def load_cost_param_csv(filepath):
                import csv
                param_dict = {}
                with open(filepath, newline='', encoding="utf-8-sig") as f:
                #with open(filepath, newline='', encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    print("CSV columns:", reader.fieldnames)  # デバッグ用
                    #reader = csv.DictReader(f, delimiter="\t") # タブ区切りに
                    #print("CSV columns:", reader.fieldnames)   # 確認用に追加
                    #reader = csv.DictReader(f)
                    for row in reader:
                        product = row["product_name"]
                        node = row["node_name"]
                        if product not in param_dict:
                            param_dict[product] = {}
                        param_dict[product][node] = {
                            "price": float(row.get("price_sales_shipped", 0)),
                            "cost_total": float(row.get("cost_total", 0)),
                            "profit_margin": float(row.get("profit", 0)),  # optional
                            "marketing": float(row.get("marketing_promotion", 0)),
                            "sales_admin_cost": float(row.get("sales_admin_cost", 0)),
                            "SGA_total": float(row.get("SGA_total", 0)),
                            "transport_cost": float(row.get("logistics_costs", 0)),
                            "storage_cost": float(row.get("warehouse_cost", 0)),
                            "purchase_price": float(row.get("direct_materials_costs", 0)),
                            "tariff_cost": float(row.get("tariff_cost", 0)),
                            "purchase_total_cost": float(row.get("purchase_total_cost", 0)),
                            "direct_labor_cost": float(row.get("direct_labor_costs", 0)),
                            "fixed_cost": float(row.get("manufacturing_overhead", 0)),
                            # optional: detail for GUI use
                            "prod_indirect_labor": float(row.get("prod_indirect_labor", 0)),
                            "prod_indirect_cost": float(row.get("prod_indirect_others", 0)),
                            "depreciation_cost": float(row.get("depreciation_others", 0)),
                            # ... 他の詳細項目も追加可
                        }
                return param_dict
            if "sku_cost_table_outbound.csv" in data_file_list:
                cost_param_OT_dict = load_cost_param_csv(os.path.join(directory, "sku_cost_table_outbound.csv"))
                print("cost_param_OT_dict", cost_param_OT_dict)
                #@STOP
                #load_sku_cost_master(os.path.join(directory, "sku_cost_table_outbound.csv"), self.nodes_outbound)
                #@STOP
                #read_set_cost(os.path.join(directory, "node_cost_table_outbound.csv"), self.nodes_outbound)
            else:
                print("error: sku_cost_table_outbound.csv is missed")
            if "sku_cost_table_inbound.csv" in data_file_list:
                cost_param_IN_dict = load_cost_param_csv(os.path.join(directory, "sku_cost_table_inbound.csv"))
                #@STOP
                #load_sku_cost_master(os.path.join(directory, "sku_cost_table_inbound.csv"), self.nodes_inbound)
                #@STOP
                #read_set_cost(os.path.join(directory, "node_cost_table_inbound.csv"), self.nodes_inbound)
            else:
                print("error: sku_cost_table_inbound.csv is missed")
            ## Cost structure demand
            #self.price_sales_shipped = 0
            #self.cost_total = 0
            #self.profit = 0
            #self.marketing_promotion = 0
            #self.sales_admin_cost = 0
            #self.SGA_total = 0
            #self.custom_tax = 0
            #self.tax_portion = 0
            #self.logistics_costs = 0
            #self.warehouse_cost = 0
            #self.direct_materials_costs = 0
            #self.purchase_total_cost = 0
            #self.prod_indirect_labor = 0
            #self.prod_indirect_others = 0
            #self.direct_labor_costs = 0
            #self.depreciation_others = 0
            #self.manufacturing_overhead = 0
            # this is "product_tree" operation / that is "PlanNode"
            def cost_param_setter(product_tree_root, param_dict, product_name):
                def traverse(node):
                    node_name = node.name
                    if product_name in param_dict and node_name in param_dict[product_name]:
                        param_set = param_dict[product_name][node_name]
                        #@250801 memo node is an instance of "PlanNode"
                        sku = node.sku
                        sku.price               = param_set.get("price", 0)
                        sku.cost_total          = param_set.get("cost_total", 0)
                        sku.profit_margin       = param_set.get("profit_margin", 0)
                        sku.marketing           = param_set.get("marketing", 0)
                        sku.sales_admin_cost    = param_set.get("sales_admin_cost", 0)
                        sku.SGA_total           = param_set.get("SGA_total", 0)
                        sku.transport_cost      = param_set.get("transport_cost", 0)
                        sku.storage_cost        = param_set.get("storage_cost", 0)
                        sku.purchase_price      = param_set.get("purchase_price", 0)
                        sku.tariff_cost         = param_set.get("tariff_cost", 0)
                        sku.purchase_total_cost = param_set.get("purchase_total_cost", 0)
                        sku.direct_labor_costs  = param_set.get("direct_labor_costs", 0)
                        sku.fixed_cost          = param_set.get("fixed_cost", 0)
                        sku.prod_indirect_labor = param_set.get("prod_indirect_labor", 0)
                        sku.prod_indirect_cost  = param_set.get("prod_indirect_cost", 0)
                        sku.depreciation_cost   = param_set.get("depreciation_cost", 0)
                        #sku.price               = param_set.get("sku.price", 0)
                        #sku.cost_total          = param_set.get("sku.cost_total", 0)
                        #sku.profit_margin       = param_set.get("sku.profit_margin", 0)
                        #sku.marketing           = param_set.get("sku.marketing", 0)
                        #sku.sales_admin_cost    = param_set.get("sku.sales_admin_cost", 0)
                        #sku.SGA_total           = param_set.get("sku.SGA_total", 0)
                        #sku.transport_cost      = param_set.get("sku.transport_cost", 0)
                        #sku.storage_cost        = param_set.get("sku.storage_cost", 0)
                        #sku.purchase_price      = param_set.get("sku.purchase_price", 0)
                        #sku.tariff_cost         = param_set.get("tariff_cost", 0)
                        #sku.purchase_total_cost = param_set.get("sku.purchase_total_cost", 0)
                        #sku.direct_labor_costs  = param_set.get("sku.direct_labor_costs", 0)
                        #sku.fixed_cost          = param_set.get("sku.fixed_cost", 0)
                        #sku.prod_indirect_labor = param_set.get("sku.prod_indirect_labor", 0)
                        #sku.prod_indirect_cost  = param_set.get("sku.prod_indirect_cost", 0)
                        #sku.depreciation_cost   = param_set.get("sku.depreciation_cost", 0)
                        #sku.price = param_set.get("price", 0)
                        #sku.transport_cost = param_set.get("transport_cost", 0)
                        #sku.storage_cost = param_set.get("storage_cost", 0)
                        #sku.purchase_price = param_set.get("purchase_price", 0)
                        #sku.fixed_cost = param_set.get("fixed_cost", 0)
                        #sku.other_cost = param_set.get("other_cost", 0)
                        #sku.total_cost = (
                        #    sku.purchase_price + sku.transport_cost + sku.storage_cost +
                        #    sku.tariff_cost + sku.fixed_cost + sku.other_cost
                        #)
                        # ✅ PlanNode 側へコピー
                        node.cs_price_sales_shipped    = sku.price
                        node.cs_cost_total             = sku.cost_total
                        node.cs_profit                 = sku.profit_margin
                        node.cs_marketing_promotion    = sku.marketing
                        node.cs_sales_admin_cost       = sku.sales_admin_cost
                        node.cs_SGA_total              = sku.SGA_total
                        node.cs_logistics_costs        = sku.transport_cost
                        node.cs_warehouse_cost         = sku.storage_cost
                        node.cs_direct_materials_costs = sku.purchase_price
                        node.cs_tax_portion            = sku.tariff_cost
                        node.cs_purchase_total_cost    = sku.purchase_total_cost
                        node.cs_direct_labor_costs     = sku.direct_labor_costs
                        node.cs_manufacturing_overhead = sku.fixed_cost
                        node.cs_prod_indirect_labor    = sku.prod_indirect_labor
                        node.cs_prod_indirect_others   = sku.prod_indirect_cost
                        node.cs_depreciation_others    = sku.depreciation_cost
                        #node.eval_cs_price_sales_shipped = sku.price
                        #node.eval_cs_profit = sku.price - sku.total_cost
                        #node.eval_cs_SGA_total = param_set.get("SGA_total", 0)
                        #node.eval_cs_tax_portion = sku.tariff_cost
                        #node.eval_cs_logistics_costs = sku.transport_cost
                        #node.eval_cs_warehouse_cost = sku.storage_cost
                        #node.eval_cs_direct_materials_costs = sku.purchase_price
                    for child in node.children:
                        traverse(child)
                traverse(product_tree_root)
            # 読み込んだ辞書を全製品ツリーに適用
            for product_name in list(prod_tree_dict_OT.keys()):
                #@250729 ADD
                print("cost_param_OT_dict", cost_param_OT_dict)
                cost_param_setter(prod_tree_dict_OT[product_name], cost_param_OT_dict, product_name)
                #cost_param_setter(subtree_OT_dict[product_name], cost_param_OT_dict, product_name)
            for product_name in list(prod_tree_dict_IN.keys()):
                cost_param_setter(prod_tree_dict_IN[product_name], cost_param_IN_dict, product_name)
                #cost_param_setter(subtree_IN_dict[product_name], cost_param_IN_dict, product_name)
                #cost_param_setter(product_tree_dict[product_name], param_dict, product_name)
            #@250719 ADD from import
            # *****************************
            # cost propagation
            # *****************************
            # 0.setting price table
            selling_price_table_csv = os.path.join(directory, "selling_price_table.csv")
            tobe_price_dict = load_tobe_prices(selling_price_table_csv)
            assign_tobe_prices_to_leaf_nodes(prod_tree_dict_OT, tobe_price_dict)
            shipping_price_table_csv = os.path.join(directory, "shipping_price_table.csv")
            asis_price_dict = load_asis_prices(shipping_price_table_csv)
            assign_asis_prices_to_root_nodes(prod_tree_dict_OT, asis_price_dict)
            print("offering_price check: self.nodes_outbound[ CS_JPN ].sku_dict[ JPN_Koshihikari ].offering_price_TOBE", self.nodes_outbound["CS_JPN"].sku_dict["JPN_Koshihikari"].offering_price_TOBE)
            print("offering_price check: self.nodes_outbound[ DADJPN ].sku_dict[ JPN_RICE_1 ].offering_price_TOBE", self.nodes_outbound["DADJPN"].sku_dict["JPN_RICE_1"].offering_price_TOBE)
            # 1.initial propagation 実行
            print("cost propagation processing")
            gui_run_initial_propagation(prod_tree_dict_OT, directory)
            #@250807 STOP
            #gui_run_initial_propagation(prod_tree_dict_IN, directory)
            print("offering_price check: self.nodes_outbound[ CS_JPN ].sku_dict[ JPN_Koshihikari ].offering_price_TOBE", self.nodes_outbound["CS_JPN"].sku_dict["JPN_Koshihikari"].offering_price_TOBE)
            print("offering_price check: self.nodes_outbound[ DADJPN ].sku_dict[ JPN_RICE_1 ].offering_price_TOBE", self.nodes_outbound["DADJPN"].sku_dict["JPN_RICE_1"].offering_price_TOBE)
            # 2.PlanNodeへの評価値のコピー
            print("propagate_cost_to_plan_nodes start...")
            #self.print_cost_sku()
            #self.print_cost_node_cs()
            #self.print_cost_node_eval_cs()
            propagate_cost_to_plan_nodes(prod_tree_dict_OT)
            propagate_cost_to_plan_nodes(prod_tree_dict_IN)
            print("propagate_cost_to_plan_nodes end...")
            #self.print_cost_sku()
            #self.print_cost_node_cs()
            #self.print_cost_node_eval_cs()
#@250720 STOP
#            #@250720 ADD この後のloading processがココで止まる
#            self.view_nx_matlib4opt()
#
#
#    #@250720 ADD loading processの続きを仮設で定義
#    def load_data_files_CONTONUE(self):
            # **************************************
            # setting S_month 2 psi4demand
            # **************************************
            if "S_month_data.csv" in data_file_list:
                in_file_path = os.path.join(directory, "S_month_data.csv")
                df_weekly, plan_range, plan_year_st = process_monthly_demand(in_file_path, self.lot_size)
                self.plan_year_st = plan_year_st
                self.plan_range = plan_range
                self.plan_year_entry.delete(0, tk.END)
                self.plan_year_entry.insert(0, str(self.plan_year_st))
                self.plan_range_entry.delete(0, tk.END)
                self.plan_range_entry.insert(0, str(self.plan_range))
                df_weekly.to_csv(os.path.join(directory, "S_iso_week_data.csv"), index=False)
            else:
                print("error: S_month_data.csv is missed")
            # ****************************************
            # Original Node base demand setting
            # ****************************************
            root_node_outbound.set_plan_range_lot_counts(plan_range, plan_year_st)
            root_node_inbound.set_plan_range_lot_counts(plan_range, plan_year_st)
            node_psi_dict_Ot4Dm = make_psi_space_dict(root_node_outbound, {}, plan_range)
            node_psi_dict_Ot4Sp = make_psi_space_dict(root_node_outbound, {}, plan_range)
            self.node_psi_dict_In4Dm = make_psi_space_dict(root_node_inbound, {}, plan_range)
            self.node_psi_dict_In4Sp = make_psi_space_dict(root_node_inbound, {}, plan_range)
            set_dict2tree_psi(root_node_outbound, "psi4demand", node_psi_dict_Ot4Dm)
            set_dict2tree_psi(root_node_outbound, "psi4supply", node_psi_dict_Ot4Sp)
            set_dict2tree_psi(root_node_inbound, "psi4demand", self.node_psi_dict_In4Dm)
            set_dict2tree_psi(root_node_inbound, "psi4supply", self.node_psi_dict_In4Sp)
            # **********************************
            # make&set weekly demand "Slots" on leaf_node, propagate2root
            # initial setting psi4"demand"[w][0] to psi4"supply"[w][0]
            # **********************************
            #set_df_Slots2psi4demand(self.root_node_outbound, df_weekly)
            set_df_Slots2psi4demand(root_node_outbound, df_weekly)
            # convert_monthly_to_weekly() → set_df_Slots2psi4demand() の後
            for node in self.nodes_outbound.values():
                print(f"[{node.name}] demand lots per week:",
                      [len(node.psi4demand[w][0]) for w in range(1, self.plan_range + 1)])
                      #[len(node.psi4demand[w][0]) for w in range(1, min(self.plan_range + 1, 10))])
            # ****************************************
            # by Product tree with PlanNode  demand setting
            # ****************************************
            for prod_nm in product_name_list:
                prod_tree_root_OT = prod_tree_dict_OT[prod_nm]
                prod_tree_root_IN = prod_tree_dict_IN[prod_nm]
                prod_tree_root_OT.set_plan_range_lot_counts(plan_range, plan_year_st)
                prod_tree_root_IN.set_plan_range_lot_counts(plan_range, plan_year_st)
                #root_node_outbound.set_plan_range_lot_counts(plan_range, plan_year_st)
                #root_node_inbound.set_plan_range_lot_counts(plan_range, plan_year_st)
                node_psi_dict_Ot4Dm = make_psi_space_dict(prod_tree_root_OT, {}, plan_range)
                node_psi_dict_Ot4Sp = make_psi_space_dict(prod_tree_root_OT, {}, plan_range)
                self.node_psi_dict_In4Dm = make_psi_space_dict(prod_tree_root_IN, {}, plan_range)
                self.node_psi_dict_In4Sp = make_psi_space_dict(prod_tree_root_IN, {}, plan_range)
                #node_psi_dict_Ot4Dm = make_psi_space_dict(root_node_outbound, {}, plan_range)
                #node_psi_dict_Ot4Sp = make_psi_space_dict(root_node_outbound, {}, plan_range)
                #self.node_psi_dict_In4Dm = make_psi_space_dict(root_node_inbound, {}, plan_range)
                #self.node_psi_dict_In4Sp = make_psi_space_dict(root_node_inbound, {}, plan_range)
                set_dict2tree_psi(prod_tree_root_OT, "psi4demand", node_psi_dict_Ot4Dm)
                set_dict2tree_psi(prod_tree_root_OT, "psi4supply", node_psi_dict_Ot4Sp)
                set_dict2tree_psi(prod_tree_root_IN, "psi4demand", self.node_psi_dict_In4Dm)
                set_dict2tree_psi(prod_tree_root_IN, "psi4supply", self.node_psi_dict_In4Sp)
                # **********************************
                # make&set weekly demand "Slots" on leaf_node, propagate2root
                # initial setting psi4"demand"[w][0] to psi4"supply"[w][0]
                # **********************************
                #set_df_Slots2psi4demand(self.root_node_outbound, df_weekly)
                set_df_Slots2psi4demand(prod_tree_root_OT, df_weekly)
                # convert_monthly_to_weekly() → set_df_Slots2psi4demand() の後
                #for node in self.prod_tree_dict_OT[prod_nm].values():
                for node in self.nodes_outbound.values():
                    print(f"[{node.name}] by Product demand lots per week:",
                          [len(node.psi4demand[w][0]) for w in range(1, self.plan_range + 1)])
                          #[len(node.psi4demand[w][0]) for w in range(1, min(self.plan_range + 1, 10))])
                #prod_tree_root_OT = prod_tree_dict_OT[prod_nm]
        # *****************************
        # export offring_price ASIS/TOBE to csv
        # *****************************
        filename = "offering_price_ASIS_TOBE.csv"
        output_csv_path = os.path.join(self.directory, filename)
        self.export_offering_prices(output_csv_path)
        #@STOP can NOT eval before "psi" loading
        ## eval area
        #self.update_evaluation_results()
        # network area
        self.decouple_node_selected = []
        #self.decouple_node_selected = decouple_node_names
        self.view_nx_matlib4opt()
        #self.view_nx_matlib4opt_WO_capa()
        # _init_ self.product_selected = self.product_name_list[0]
        #product_name = self.product_selected
        product_name = self.product_name_list[1]
        # PSI area
        self.root.after(1000, self.show_psi_by_product("outbound", "demand", product_name))
        #@STOP
        ## PSI area
        ##self.root.after(1000, self.show_psi("outbound", "supply"))
        #
        #self.root.after(1000, lambda: self.show_psi("outbound", "supply"))
        ## lambda: にすることで、1000ms 後に初めて show_psi() を実行する
        # ****************************
        # market potential Graph viewing
        # ****************************
        self.initialize_parameters()
        # Enable buttons after loading is complete
        self.supply_planning_button.config(state="normal")
        self.eval_buffer_stock_button.config(state="normal")
        print("Data files loaded and buttons enabled.")
        # Return focus to the main window
        self.root.focus_force()
        # ****************************
        # passing following process
        # ****************************
        pass
# **** A PART of ORIGINAL load_data_files END *****
# **** call_backs *****
    def save_data(self, save_directory):
        print(f"保存前 - market_potential: {self.market_potential}, target_share: {self.target_share}")  # ログ追加
        print(f"保存前 - total_revenue : {self.total_revenue}, total_profit : {self.total_profit}")
        psi_planner_app_save = PSIPlannerApp4save()
        psi_planner_app_save.update_from_psiplannerapp(self)
        print(f"保存時 - market_potential: {psi_planner_app_save.market_potential}, target_share: {psi_planner_app_save.target_share}")  # ログ追加
        print(f"保存時 - total_revenue: {psi_planner_app_save.total_revenue}, total_profit: {psi_planner_app_save.total_profit}")
        with open(os.path.join(save_directory, 'psi_planner_app.pkl'), "wb") as f:
            pickle.dump(psi_planner_app_save.__dict__, f)
        print("データを保存しました。")
    def save_to_directory(self):
        # 1. Save先となるdirectoryの問い合わせ
        save_directory = filedialog.askdirectory()
        if not save_directory:
            return  # ユーザーがキャンセルした場合
        # 2. 初期処理のcsv fileのコピー
        for filename in os.listdir(self.directory):
            if filename.endswith('.csv'):
                full_file_name = os.path.join(self.directory, filename)
                if os.path.isfile(full_file_name):
                    shutil.copy(full_file_name, save_directory)
        # 3. Tree構造の保存
        with open(os.path.join(save_directory, 'root_node_outbound.pkl'), 'wb') as f:
            pickle.dump(self.root_node_outbound, f)
            print(f"root_node_outbound saved: {self.root_node_outbound}")
        with open(os.path.join(save_directory, 'root_node_inbound.pkl'), 'wb') as f:
            pickle.dump(self.root_node_inbound, f)
            print(f"root_node_inbound saved: {self.root_node_inbound}")
        with open(os.path.join(save_directory, 'root_node_out_opt.pkl'), 'wb') as f:
            pickle.dump(self.root_node_out_opt, f)
            print(f"root_node_out_opt saved: {self.root_node_out_opt}")
        # 4. グラフデータの保存
        nx.write_gml(self.G, f"{save_directory}/G.gml")
        nx.write_gml(self.Gdm_structure, f"{save_directory}/Gdm_structure.gml")
        nx.write_gml(self.Gsp, f"{save_directory}/Gsp.gml")
        print(f"グラフが{save_directory}に保存されました")
        nx.write_gpickle(self.G, os.path.join(save_directory, 'G.gpickle'))
        nx.write_gpickle(self.Gdm_structure, os.path.join(save_directory, 'Gdm_structure.gpickle'))
        nx.write_gpickle(self.Gsp, os.path.join(save_directory, 'Gsp.gpickle'))
        print("Graph data saved.")
        # saveの前にself.market_potential,,,をupdate
        #self.initialize_parameters()
        self.updated_parameters()
        # 5. PSIPlannerAppのデータ・インスタンスの保存
        self.save_data(save_directory)
        # 追加：ファイルの存在とサイズの確認
        for filename in ['root_node_outbound.pkl', 'root_node_inbound.pkl', 'psi_planner_app.pkl']:
            full_file_name = os.path.join(save_directory, filename)
            if os.path.exists(full_file_name):
                file_size = os.path.getsize(full_file_name)
                print(f"{filename} exists, size: {file_size} bytes")
            else:
                print(f"{filename} does not exist")
        # 6. 完了メッセージの表示
        messagebox.showinfo("Save Completed", "Plan data save is completed")
    def load_data(self, load_directory):
        with open(os.path.join(load_directory, 'psi_planner_app.pkl'), "rb") as f:
            loaded_attributes = pickle.load(f)
    #@ STOP this is a sample code for "fixed file"
    #def load_data(self, filename="saved_data.pkl"):
    #    with open(filename, "rb") as f:
    #        loaded_attributes = pickle.load(f)
        psi_planner_app_save = PSIPlannerApp4save()
        psi_planner_app_save.__dict__.update(loaded_attributes)
        # 選択的にインスタンス変数を更新
        self.root_node = psi_planner_app_save.root_node
        #@ STOP
        #self.D_S_flag = psi_planner_app_save.D_S_flag
        #self.week_start = psi_planner_app_save.week_start
        #self.week_end = psi_planner_app_save.week_end
        self.decouple_node_selected=psi_planner_app_save.decouple_node_selected
        self.G = psi_planner_app_save.G
        self.Gdm = psi_planner_app_save.Gdm
        self.Gdm_structure = psi_planner_app_save.Gdm_structure
        self.Gsp = psi_planner_app_save.Gsp
        self.pos_E2E = psi_planner_app_save.pos_E2E
        self.total_revenue = psi_planner_app_save.total_revenue
        print("load_data: self.total_revenue", self.total_revenue)
        self.total_profit = psi_planner_app_save.total_profit
        print("load_data: self.total_profit", self.total_profit)
        self.flowDict_opt = psi_planner_app_save.flowDict_opt
        self.flowCost_opt = psi_planner_app_save.flowCost_opt
        self.market_potential = psi_planner_app_save.market_potential
        print("self.market_potential", self.market_potential)
        self.target_share = psi_planner_app_save.target_share
        print("self.target_share", self.target_share)
        # エントリウィジェットに反映する
        self.ts_entry.delete(0, tk.END)
        self.ts_entry.insert(0, f"{self.target_share * 100:.0f}")  # 保存された値を反映
        print(f"読み込み時 - market_potential: {self.market_potential}, target_share: {self.target_share}")  # ログ追加
        print("データをロードしました。")
    def regenerate_nodes(self, root_node):
        nodes = {}
        def traverse(node):
            nodes[node.name] = node
            for child in node.children:
                traverse(child)
        traverse(root_node)
        return nodes
    def load_from_directory(self):
        # 1. Load元となるdirectoryの問い合わせ
        load_directory = filedialog.askdirectory()
        if not load_directory:
            return  # ユーザーがキャンセルした場合
        # 2. Tree構造の読み込み
        self.load_directory = load_directory
        self.directory      = load_directory # for "optimized network"
        self._load_tree_structure(load_directory)
        # 3. PSIPlannerAppのデータ・インスタンスの読み込み
        self.load_data(load_directory)
        # if "save files" are NOT optimized one
        if os.path.exists(f"{load_directory}/root_node_out_opt.pkl"):
            pass
        else:
            self.flowDict_opt = {}  # NO optimize
        ## 3. PSIPlannerAppのデータ・インスタンスの読み込みと更新
        #self.selective_update(load_directory)
        # 4. nodes_outboundとnodes_inboundを再生成
        self.nodes_outbound = self.regenerate_nodes(self.root_node_outbound)
        self.nodes_inbound = self.regenerate_nodes(self.root_node_inbound)
        #self.nodes_out_opt = self.regenerate_nodes(self.root_node_out_opt)
        print("load_from_directory self.decouple_node_selected", self.decouple_node_selected)
        #@241224 ADD
        # eval area
        self.update_evaluation_results()
        ## 5. ネットワークグラフの描画
        #self.draw_networkx_graph()
        #@ STOP RUN change2OPT
        # 5. ネットワークグラフの描画
        self.view_nx_matlib4opt()
        #self.view_nx_matlib()
        #@ MOVED
        self.updated_parameters()
        #@ STOP RUN
        # 6. PSIの表示
        if self.root_node_out_opt == None:
            self.root.after(1000, self.show_psi("outbound", "supply"))
            #@ STOP
            ## パラメータの初期化と更新を呼び出し
            #self.updated_parameters()
        else:  # is root_node_out_opt
            self.root.after(1000, self.show_psi_graph4opt)
            #@ STOP
            ## パラメータの初期化と更新を呼び出し
            #self.set_market_potential(self.root_node_out_opt)
            #self.updated_parameters()
            ##self.initialize_parameters()
        # 7. 完了メッセージの表示
        messagebox.showinfo("Load Completed", "Plan data load is completed")
    def on_exit(self):
        # 確認ダイアログの表示
        if messagebox.askokcancel("Quit", "Do you really want to exit?"):
            # 全てのスレッドを終了
            for thread in threading.enumerate():
                if thread is not threading.main_thread():
                    thread.join(timeout=1)
            #for widget in self.root.winfo_children():
            #    widget.destroy()
            #self.root.destroy()
            self.root.quit()
    # **********************************
    # sub global supply chain network
    # **********************************
    # メニュー項目	             ズーム挙動	赤いルートハイライト	備考
    # Network Graph	            なし（別ビュー）	あり	ネットワークグラフ表示
    # World Map (global)	    地球全体表示	    あり	赤線で選択製品ルートを表示
    # World Map (fit to data)	ノードにフィット	あり	fromノード左寄せ・緯度フィット
    def _show_worldmap_global(self):
        """
        地球全体を表示しつつ、選択された製品のルートをハイライト
        """
        self.world_map_fit = False
        self.show_world_map(self.product_selected)
    def _show_worldmap_fit(self):
        """
        選択された製品のノード範囲に自動フィット（水平フォーカスあり）
        """
        self.world_map_fit = True
        self.show_world_map(self.product_selected)
    # **********************************
    # network graph helpper for GREY and RED color
    # **********************************
    def _iter_parent_child(self, root):
        if not root: return
        st=[root]; seen=set()
        while st:
            p=st.pop()
            if id(p) in seen: continue
            seen.add(id(p))
            for c in getattr(p, "children", []) or []:
                yield p.name, c.name
                st.append(c)
    def _edges_all_products(self):
        """全製品の親子エッジの和集合"""
        env = getattr(self, "psi", None)
        edges=set()
        if env and getattr(env, "prod_tree_dict_OT", None):
            for _prod, _root in env.prod_tree_dict_OT.items():
                for u,v in self._iter_parent_child(_root):
                    edges.add((u,v))
        return edges
    def _edges_for_product(self, product):
        """選択製品の親子エッジ集合"""
        env = getattr(self, "psi", None)
        root = None
        if env and getattr(env, "prod_tree_dict_OT", None):
            root = env.prod_tree_dict_OT.get(product)
        edges=set()
        for u,v in self._iter_parent_child(root):
            edges.add((u,v))
        return edges
    # **********************************
    # sub menus
    # **********************************
    # viewing Cost Stracture / an image of Value Chain
    def show_cost_stracture_bar_graph(self):
        try:
            if self.root_node_outbound is None or self.root_node_inbound is None:
                raise ValueError("Data has not been loaded yet")
            self.show_nodes_cs_lot_G_Sales_Procure(self.root_node_outbound, self.root_node_inbound)
        except ValueError as ve:
            print(f"error: {ve}")
            tk.messagebox.showerror("error", str(ve))
        except AttributeError:
            print("Error: Required attributes are missing from the node. Please check if the data is loaded.")
            tk.messagebox.showerror("Error", "Required attributes are missing from the node. Please check if the data is loaded.")
        except Exception as e:
            print(f"An unexpected error has occurred: {e}")
            tk.messagebox.showerror("Error", f"An unexpected error has occurred: {e}")
    def show_nodes_cs_lot_G_Sales_Procure(self, root_node_outbound, root_node_inbound):
        attributes = [
            'cs_direct_materials_costs',
            'cs_marketing_promotion',
            'cs_sales_admin_cost',
            'cs_tax_portion',
            'cs_logistics_costs',
            'cs_warehouse_cost',
            'cs_prod_indirect_labor',
            'cs_prod_indirect_others',
            'cs_direct_labor_costs',
            'cs_depreciation_others',
            'cs_profit',
        ]
        def dump_node_amt_all_in(node, node_amt_all):
            for child in node.children:
                dump_node_amt_all_in(child, node_amt_all)
            amt_list = {attr: getattr(node, attr) for attr in attributes}
            if node.name == "JPN":
                node_amt_all["JPN_IN"] = amt_list
            else:
                node_amt_all[node.name] = amt_list
            return node_amt_all
        def dump_node_amt_all_out(node, node_amt_all):
            amt_list = {attr: getattr(node, attr) for attr in attributes}
            if node.name == "JPN":
                node_amt_all["JPN_OUT"] = amt_list
            else:
                node_amt_all[node.name] = amt_list
            for child in node.children:
                dump_node_amt_all_out(child, node_amt_all)
            return node_amt_all
        node_amt_sum_in = dump_node_amt_all_in(root_node_inbound, {})
        node_amt_sum_out = dump_node_amt_all_out(root_node_outbound, {})
        node_amt_sum_in_out = {**node_amt_sum_in, **node_amt_sum_out}
        print("node_amt_sum_out", node_amt_sum_out)
        make_stack_bar4cost_stracture(node_amt_sum_out)
        # CSVファイルへのエクスポートを呼び出す
        self.export_cost_structure_to_csv(root_node_outbound, root_node_inbound, "cost_structure.csv")
        ## 供給配分の最適化 DADxxx2leaf_nodes profit_ratio CSVファイル
        #self.calculate_net_profit_rates(root_node_outbound)
    def export_cost_structure_to_csv(self, root_node_outbound, root_node_inbound, file_path):
        attributes = [
            'cs_direct_materials_costs',
            'cs_marketing_promotion',
            'cs_sales_admin_cost',
            'cs_tax_portion',
            'cs_logistics_costs',
            'cs_warehouse_cost',
            'cs_prod_indirect_labor',
            'cs_prod_indirect_others',
            'cs_direct_labor_costs',
            'cs_depreciation_others',
            'cs_profit',
        ]
        def dump_node_amt_all_in(node, node_amt_all):
            for child in node.children:
                dump_node_amt_all_in(child, node_amt_all)
            amt_list = {attr: getattr(node, attr) for attr in attributes}
            if node.name == "JPN":
                node_amt_all["JPN_IN"] = amt_list
            else:
                node_amt_all[node.name] = amt_list
            return node_amt_all
        def dump_node_amt_all_out(node, node_amt_all):
            amt_list = {attr: getattr(node, attr) for attr in attributes}
            if node.name == "JPN":
                node_amt_all["JPN_OUT"] = amt_list
            else:
                node_amt_all[node.name] = amt_list
            for child in node.children:
                dump_node_amt_all_out(child, node_amt_all)
            return node_amt_all
        node_amt_sum_in = dump_node_amt_all_in(root_node_inbound, {})
        node_amt_sum_out = dump_node_amt_all_out(root_node_outbound, {})
        node_amt_sum_in_out = {**node_amt_sum_in, **node_amt_sum_out}
        # 横持ちでデータフレームを作成
        data = []
        for node_name, costs in node_amt_sum_in_out.items():
            row = [node_name] + [costs[attr] for attr in attributes]
            data.append(row)
        df = pd.DataFrame(data, columns=["node_name"] + attributes)
        # CSVファイルにエクスポート
        df.to_csv(file_path, index=False)
        print(f"Cost structure exported to {file_path}")
        # leaf_nodes list is this
        print(self.leaf_nodes_out)
    def Save_Objective_Value(self):
        # 供給配分の最適化 DADxxx2leaf_nodes profit_ratio CSVファイル
        self.calculate_net_profit_rates(self.root_node_outbound)
    def calculate_net_profit_rates(self, root_node_outbound, output_file="net_profit_ratio.csv"):
        # **** 対象コスト項目
        target_cost_attributes = [
            'cs_cost_total'
            #'cs_logistics_costs',
            #'cs_warehouse_cost',
            #'cs_sales_admin_cost',
            #'cs_marketing_promotion'
        ]
        results = []
        ## Cost Structure
        #self.cs_price_sales_shipped = 0
        #self.cs_cost_total = 0
        #self.cs_profit = 0
        #self.cs_marketing_promotion = 0 #<=
        #self.cs_sales_admin_cost = 0    #<=
        #self.cs_SGA_total = 0
        ##self.cs_custom_tax = 0 # stop tariff_rate
        #self.cs_tax_portion = 0             #
        #self.cs_logistics_costs = 0         #
        #self.cs_warehouse_cost = 0          #
        #self.cs_direct_materials_costs = 0  #
        #self.cs_purchase_total_cost = 0
        #self.cs_prod_indirect_labor = 0     #
        #self.cs_prod_indirect_others = 0    #
        #self.cs_direct_labor_costs = 0      #
        #self.cs_depreciation_others = 0     #
        #self.cs_manufacturing_overhead = 0
        for leaf_name in self.leaf_nodes_out:
            node = self.nodes_outbound[leaf_name]
            #node = nodes_outbound.get(leaf_name)
            print(f"Checking init node: {node.name}")
            total_cost = 0.0
            total_profit = 0.0
            # **** ルート探索：Leaf Nodeからrootまで遡る
            while node is not None:
            #while node.name != "supply_point":
                print(f"Checking node: {node.name}")
                #for attr in target_cost_attributes:
                #    if not hasattr(node, attr):
                #        print(f"⚠️ 属性 {attr} がノード {node.name} に存在しません")
                #    total_cost += getattr(node, attr, 0.0)
                total_cost   += getattr(node, 'cs_cost_total', 0.0)
                total_profit += getattr(node, 'cs_profit', 0.0)
                # 親が"supply_point"なら、これ以上遡らずに終了
                print("node.parent.name", node.parent.name)
                if node.parent and node.parent.name == "supply_point":
                    #node = None
                    break
                else:
                    node = node.parent
                ## DADxxxのノードで停止する
                #if node.parent is None or "DAD" in node.parent.name:
                #    node = None
                #else:
                #    node = node.parent
                #node = node.parent
            #while node is not None:
            #    for attr in target_cost_attributes:
            #        total_cost += getattr(node, attr, 0.0)
            #    total_profit += getattr(node, 'cs_profit', 0.0)
            #    node = node.parent
            # **** 純利益率計算
            total_amount = total_cost + total_profit
            net_profit_rate = total_profit / total_amount if total_amount > 0 else 0.0
            results.append({
                "Source": node.name,
                #"Source": root_node_outbound.name,
                "Target": leaf_name,
                "Total_Cost": round(total_cost, 4),
                "Total_Profit": round(total_profit, 4),
                "Net_Profit_Rate": round(net_profit_rate, 4)
            })
        # **** DataFrame化とCSV出力
        df_result = pd.DataFrame(results)
        # ファイル保存ダイアログを表示して保存先ファイルパスを取得
        save_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not save_path:
            return  # ユーザーがキャンセルした場合
        df_result.to_csv(save_path, index=False)
        #df_result.to_csv(output_file, index=False)
        print(f"✔ 純利益率データを出力しました：{save_path}")
    def show_month_data_csv(self):
        pass
    def outbound_psi_to_csv(self):
        # ファイル保存ダイアログを表示して保存先ファイルパスを取得
        save_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not save_path:
            return  # ユーザーがキャンセルした場合
        # planの出力期間をcalculation
        output_period_outbound = 53 * self.root_node_outbound.plan_range
        # dataの収集
        data = []
        def collect_data(node, output_period):
            for attr in range(4):  # 0:"Sales", 1:"CarryOver", 2:"Inventory", 3:"Purchase"
                row = [node.name, attr]
                for week_no in range(output_period):
                    count = len(node.psi4supply[week_no][attr])
                    row.append(count)
                data.append(row)
            for child in node.children:
                collect_data(child, output_period)
        # root_node_outboundのtree構造を走査してdataを収集
        headers_outbound = ["node_name", "PSI_attribute"] + [f"w{i+1}" for i in range(output_period_outbound)]
        collect_data(self.root_node_outbound, output_period_outbound)
        # dataフレームを作成してCSVファイルに保存
        df_outbound = pd.DataFrame(data[:len(data)], columns=headers_outbound)
        # STOP
        # # 複数のdataフレームを1つにaggregateする場合
        # df_combined = pd.concat([df_outbound, df_inbound])
        df_outbound.to_csv(save_path, index=False)
        # 完了メッセージを表示
        messagebox.showinfo("CSV Export", f"PSI data has been exported to {save_path}")
    def outbound_lot_by_lot_to_csv(self):
        # ファイル保存ダイアログを表示して保存先ファイルパスを取得
        save_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not save_path:
            return  # ユーザーがキャンセルした場合
        # 計画の出力期間を計算
        #output_period_outbound = 53 * self.plan_range
        output_period_outbound = 53 * self.root_node_outbound.plan_range
        start_year = self.plan_year_st
        # ヘッダーの作成
        headers = ["tier", "node_name", "parent", "PSI_attribute", "year", "week_no", "lot_id"]
        # データの収集
        data = []
        def collect_data(node, output_period, tier_no, parent_name):
            for attr in range(4):  # 0:"Sales", 1:"CarryOver", 2:"Inventory", 3:"Purchase"
                for week_no in range(output_period):
                    year = start_year + week_no // 53
                    week = week_no % 53 + 1
                    lot_ids = node.psi4supply[week_no][attr]
                    if not lot_ids:  # 空リストの場合、空文字を追加
                        lot_ids = [""]
                    for lot_id in lot_ids:
                        data.append([tier_no, node.name, parent_name, attr, year, week, lot_id])
            for child in node.children:
                collect_data(child, output_period, tier_no + 1, node.name)
        # root_node_outboundのツリー構造を走査してデータを収集
        collect_data(self.root_node_outbound, output_period_outbound, 0, "root")
        # データフレームを作成してCSVファイルに保存
        df = pd.DataFrame(data, columns=headers)
        df.to_csv(save_path, index=False)
        # 完了メッセージを表示
        messagebox.showinfo("CSV Export", f"Lot by Lot data has been exported to {save_path}")
#    def inbound_psi_to_csv(self):
#        pass
#
#    def inbound_lot_by_lot_to_csv(self):
#        pass
#
#    def lot_cost_structure_to_csv(self):
#        pass
#
#    def supplychain_performance_to_csv(self):
#        pass
#
#    def psi_for_excel(self):
#        pass
#
    def inbound_psi_to_csv(self):
        # ファイル保存ダイアログを表示して保存先ファイルパスを取得
        save_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not save_path:
            return  # ユーザーがキャンセルした場合
        # planの出力期間をcalculation
        output_period_inbound = 53 * self.root_node_inbound.plan_range
        # dataの収集
        data = []
        def collect_data(node, output_period):
            for attr in range(4):  # 0:"Sales", 1:"CarryOver", 2:"Inventory", 3:"Purchase"
                row = [node.name, attr]
                for week_no in range(output_period):
                    count = len(node.psi4supply[week_no][attr])
                    row.append(count)
                data.append(row)
            for child in node.children:
                collect_data(child, output_period)
        # root_node_inboundのtree構造を走査してdataを収集
        headers_inbound = ["node_name", "PSI_attribute"] + [f"w{i+1}" for i in range(output_period_inbound)]
        collect_data(self.root_node_inbound, output_period_inbound)
        # dataフレームを作成してCSVファイルに保存
        df_inbound = pd.DataFrame(data[:len(data)], columns=headers_inbound)
        df_inbound.to_csv(save_path, index=False)
        # 完了メッセージを表示
        messagebox.showinfo("CSV Export", f"PSI data has been exported to {save_path}")
    def inbound_lot_by_lot_to_csv(self):
        # ファイル保存ダイアログを表示して保存先ファイルパスを取得
        save_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not save_path:
            return  # ユーザーがキャンセルした場合
        # planの出力期間をcalculation
        output_period_inbound = 53 * self.root_node_inbound.plan_range
        start_year = self.plan_year_st
        # ヘッダーの作成
        headers = ["tier", "node_name", "parent", "PSI_attribute", "year", "week_no", "lot_id"]
        # dataの収集
        data = []
        def collect_data(node, output_period, tier_no, parent_name):
            for attr in range(4):  # 0:"Sales", 1:"CarryOver", 2:"Inventory", 3:"Purchase"
                for week_no in range(output_period):
                    year = start_year + week_no // 53
                    week = week_no % 53 + 1
                    lot_ids = node.psi4supply[week_no][attr]
                    if not lot_ids:  # 空リストの場合、空文字を追加
                        lot_ids = [""]
                    for lot_id in lot_ids:
                        data.append([tier_no, node.name, parent_name, attr, year, week, lot_id])
            for child in node.children:
                collect_data(child, output_period, tier_no + 1, node.name)
        # root_node_outboundのtree構造を走査してdataを収集
        collect_data(self.root_node_inbound, output_period_inbound, 0, "root")
        # dataフレームを作成してCSVファイルに保存
        df = pd.DataFrame(data, columns=headers)
        df.to_csv(save_path, index=False)
        # 完了メッセージを表示
        messagebox.showinfo("CSV Export", f"Lot by Lot data has been exported to {save_path}")
    def lot_cost_structure_to_csv(self):
        # "PSI for Excel"のprocess内容を定義
        # ファイル保存ダイアログを表示して保存先ファイルパスを取得
        save_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not save_path:
            return  # ユーザーがキャンセルした場合
        self.export_cost_structure_to_csv(self.root_node_outbound, self.root_node_inbound, save_path)
        # 完了メッセージを表示
        messagebox.showinfo("CSV Export", f"export_cost_structure_to_csv data has been exported to {save_path}")
    def show_cost_structure_bar_graph(self):
        try:
            if self.root_node_outbound is None or self.root_node_inbound is None:
                raise ValueError("Data has not been loaded yet")
            show_nodes_cs_lot_G_Sales_Procure(self.root_node_outbound, self.root_node_inbound)
        except ValueError as ve:
            print(f"error: {ve}")
            tk.messagebox.showerror("error", str(ve))
        except AttributeError:
            print("Error: Required attributes are missing from the node. Please check if the data is loaded.")
            tk.messagebox.showerror("Error", "Required attributes are missing from the node. Please check if the data is loaded.")
        except Exception as e:
            print(f"An unexpected error has occurred: {e}")
            tk.messagebox.showerror("Error", f"An unexpected error has occurred: {e}")
    def outbound_rev_prof_csv(self):
        # "PSI for Excel"のprocess内容を定義
        pass
    def supplychain_performance_to_csv(self):
        # ファイル保存ダイアログを表示して保存先ファイルパスを取得
        save_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not save_path:
            return  # ユーザーがキャンセルした場合
        self.export_performance_to_csv(self.root_node_outbound, self.root_node_inbound, save_path)
        # 完了メッセージを表示
        messagebox.showinfo("CSV Export", f"Business performance data has been exported to {save_path}")
    def export_performance_to_csv(self, root_node_outbound, root_node_inbound, file_path):
        attributes = [
# evaluated cost = Cost Structure X lot_counts
            #@250322 STOP
            #"cs_custom_tax",             # political TAX parameter
            # "cs_WH_cost_coefficiet",    # operational cost parameter
            # "purchase_total_cost" is followings
            "cs_direct_materials_costs", # material
            "cs_tax_portion",            # portion calculated by TAX xx%
            "cs_logistics_costs",        # inbound logistic cost
            # plant operations are followings
            "cs_warehouse_cost",
            # eval_cs_manufacturing_overhead
            "cs_prod_indirect_labor",    # man indirect
            "cs_prod_indirect_others",   # expense
            "cs_direct_labor_costs",     # man direct
            "cs_depreciation_others",    # machine
            # Sales side operations
            "cs_marketing_promotion",
            "cs_sales_admin_cost",
            # cash generated
            "cs_profit",
            # sub total cost item
            "cs_purchase_total_cost",    # material + TAX + logi cost
            "cs_manufacturing_overhead",
            "cs_SGA_total",  # marketing_promotion + sales_admin_cost
            "cs_cost_total",
            "cs_price_sales_shipped", # revenue
        ]
        def dump_node_amt_all_in(node, node_amt_all):
            for child in node.children:
                dump_node_amt_all_in(child, node_amt_all)
            amt_list = {attr: getattr(node, attr) for attr in attributes}
            if node.name == "JPN":
                node_amt_all["JPN_IN"] = amt_list
            else:
                node_amt_all[node.name] = amt_list
            return node_amt_all
        def dump_node_amt_all_out(node, node_amt_all):
            amt_list = {attr: getattr(node, attr) for attr in attributes}
            if node.name == "JPN":
                node_amt_all["JPN_OUT"] = amt_list
            else:
                node_amt_all[node.name] = amt_list
            for child in node.children:
                dump_node_amt_all_out(child, node_amt_all)
            return node_amt_all
        node_amt_sum_in = dump_node_amt_all_in(root_node_inbound, {})
        node_amt_sum_out = dump_node_amt_all_out(root_node_outbound, {})
        node_amt_sum_in_out = {**node_amt_sum_in, **node_amt_sum_out}
        # 横持ちでdataフレームを作成
        data = []
        for node_name, performance in node_amt_sum_in_out.items():
            row = [node_name] + [performance[attr] for attr in attributes]
            data.append(row)
        df = pd.DataFrame(data, columns=["node_name"] + attributes)
        # CSVファイルにエクスポート
        df.to_csv(file_path, index=False)
        print(f"Business performance data exported to {file_path}")
#@250218
# ******************
    def print_cost_sku(self):
        sku = self.select_node.sku_dict[self.product_selected]
        print("select_node plan_node =", self.select_node.name, sku.name)
        print("sku.cs_profit                ", sku.cs_profit                )
        print("sku.cs_SGA_total             ", sku.cs_SGA_total             )
        print("sku.cs_tax_portion           ", sku.cs_tax_portion           )
        print("sku.cs_logistics_costs       ", sku.cs_logistics_costs       )
        print("sku.cs_warehouse_cost        ", sku.cs_warehouse_cost        )
        print("sku.cs_direct_materials_costs", sku.cs_direct_materials_costs)
    def print_cost_node_cs(self):
        plan_node = self.select_node.sku_dict[self.product_selected]
        print("select_node plan_node =", self.select_node.name, plan_node.name)
        print("plan_node.cs_profit                ", plan_node.cs_profit                )
        print("plan_node.cs_SGA_total             ", plan_node.cs_SGA_total             )
        print("plan_node.cs_tax_portion           ", plan_node.cs_tax_portion           )
        print("plan_node.cs_logistics_costs       ", plan_node.cs_logistics_costs       )
        print("plan_node.cs_warehouse_cost        ", plan_node.cs_warehouse_cost        )
        print("plan_node.cs_direct_materials_costs", plan_node.cs_direct_materials_costs)
    def print_cost_node_eval_cs(self):
        plan_node = self.select_node.sku_dict[self.product_selected]
        print("select_node plan_node =", self.select_node.name, plan_node.name)
        print("plan_node.eval_cs_profit                ", plan_node.eval_cs_profit                )
        print("plan_node.eval_cs_SGA_total             ", plan_node.eval_cs_SGA_total             )
        print("plan_node.eval_cs_tax_portion           ", plan_node.eval_cs_tax_portion           )
        print("plan_node.eval_cs_logistics_costs       ", plan_node.eval_cs_logistics_costs       )
        print("plan_node.eval_cs_warehouse_cost        ", plan_node.eval_cs_warehouse_cost        )
        print("plan_node.eval_cs_direct_materials_costs", plan_node.eval_cs_direct_materials_costs)
    #def show_3d_overview(self):
    #    pass
    def show_3d_overview(self):
        # CSVファイルを読み込む
        file_path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
        if not file_path:
            return  # ユーザーがキャンセルした場合
        # CSVファイルを読み込む
        df = pd.read_csv(file_path)
        # TreeViewを作成してノードを選択させる
        tree_window = tk.Toplevel(self.root)
        tree_window.title("Select Node")
        tree = ttk.Treeview(tree_window)
        tree.pack(fill=tk.BOTH, expand=True)
        # ユニークなノード名のリストを抽出
        node_list = df[['tier', 'node_name', 'parent']].drop_duplicates().sort_values(by='tier')
        # ルートノードを追加
        root_node = tree.insert('', 'end', text='root', iid='root')
        node_id_map = {"root": root_node}
        # ノードをツリー構造に追加
        def add_node(parent, tier, node_name, node_id):
            tree.insert(parent, 'end', node_id, text=f"Tier {tier}: {node_name}")
        for _, row in node_list.iterrows():
            node_id = f"{row['tier']}_{row['node_name']}"
            parent_node_name = row.get("parent", "root")
            if parent_node_name in node_id_map:
                parent = node_id_map[parent_node_name]
                add_node(parent, row["tier"], row["node_name"], node_id)
                node_id_map[row["node_name"]] = node_id
            else:
                # 親ノードが見つからない場合はルートノードを使用
                add_node(root_node, row["tier"], row["node_name"], node_id)
                node_id_map[row["node_name"]] = node_id
        # 選択ボタンの設定
        def select_node():
            selected_item = tree.selection()
            if selected_item:
                node_name = tree.item(selected_item[0], "text").split(": ")[1]
                tree_window.destroy()
                self.plot_3d_graph(df, node_name)
        select_button = tk.Button(tree_window, text="Select", command=select_node)
        select_button.pack()
    def plot_3d_graph(self, df, node_name):
        psi_attr_map = {0: "lightblue", 1: "darkblue", 2: "brown", 3: "gold"}
        x = []
        y = []
        z = []
        labels = []
        colors = []
        week_no_dict = {}
        max_z_value_lot_id_map = {}
        lot_position_map = {}
        for _, row in df.iterrows():
            if row["node_name"] == node_name and pd.notna(row["lot_id"]):
                x_value = row["PSI_attribute"]
                year = row['year']
                week_no = row['week_no']
                # Calculate week_no_serial
                start_year = df['year'].min()
                week_no_serial = (year - start_year) * 53 + week_no
                week_no_dict[week_no_serial] = f"{year}{str(week_no).zfill(2)}"
                y_value = week_no_serial
                lot_id = row['lot_id']
                if (x_value, y_value) not in lot_position_map:
                    lot_position_map[(x_value, y_value)] = 0
                z_value = lot_position_map[(x_value, y_value)] + 1
                lot_position_map[(x_value, y_value)] = z_value
                # Update max z_value for the corresponding (x_value, y_value)
                if (x_value, y_value) not in max_z_value_lot_id_map or z_value > max_z_value_lot_id_map[(x_value, y_value)][0]:
                    max_z_value_lot_id_map[(x_value, y_value)] = (z_value, lot_id)
                x.append(x_value)
                y.append(y_value)
                z.append(z_value)
                labels.append(lot_id)
                colors.append(psi_attr_map[row["PSI_attribute"]])
        # Tkinterのウィンドウを作成
        plot_window = tk.Toplevel(self.root)
        plot_window.title(f"3D Plot for {node_name}")
        # Figureを作成
        fig = plt.figure(figsize=(16, 12))  # 図のサイズを指定
        ax = fig.add_subplot(111, projection='3d')
        # 3Dプロットの作成
        scatter = ax.scatter(x, y, z, c=colors, s=1, depthshade=True)  # s=1でプロットサイズを小さく設定
        ax.set_xlabel('PSI Attribute')
        ax.set_ylabel('Time (YYYYWW)')
        ax.set_zlabel('Lot ID Position')
        # x軸のラベル設定
        ax.set_xticks(list(psi_attr_map.keys()))
        ax.set_xticklabels(["Sales", "CarryOver", "Inventory", "Purchase"], rotation=45, ha='right')
        # y軸のラベル設定
        y_ticks = [week_no_serial for week_no_serial in week_no_dict.keys() if week_no_serial % 2 != 0]
        y_labels = [week_no_dict[week_no_serial] for week_no_serial in y_ticks]
        ax.set_yticks(y_ticks)
        ax.set_yticklabels(y_labels, rotation=45, ha='right', fontsize=6)  # フォントサイズをさらに小さく設定
        # 各座標に対応するlot_idの表示（z軸の最大値のみ）
        for (x_value, y_value), (z_value, lot_id) in max_z_value_lot_id_map.items():
            ax.text(x_value, y_value, z_value, lot_id, fontsize=4, color='black', ha='center', va='center')
        # FigureをTkinterのCanvasに追加
        canvas = FigureCanvasTkAgg(fig, master=plot_window)
        canvas.draw()
        canvas.get_tk_widget().pack()
        # Tkinterのメインループを開始
        plot_window.mainloop()
        # プロットをPNGとして保存
        plt.savefig("interactive_plot.png")
        print("Interactive plot saved as interactive_plot.png")
    # PSI and Price for Cash Flow 出力関数
    def psi_price4cf(self):
        print("psi_price4cf")
        # 出力ファイルの保存パス設定
        save_path = os.path.join(self.load_directory, "PSI_PRICE_4_CashFlow.csv")
        print("Save to", save_path)
        # 出力期間の計算
        output_period_outbound = 53 * self.root_node_outbound.plan_range
        # データの収集
        data = []
        def collect_data(node, output_period):
            for attr in range(4):  # 0:"Sales", 1:"CarryOver", 2:"Inventory", 3:"Purchase"
                if attr == 0:
                    price = node.cs_price_sales_shipped
                elif attr == 1:
                    price = node.cs_purchase_total_cost
                elif attr == 2:
                    price = node.cs_purchase_total_cost
                elif attr == 3:
                    price = node.cs_direct_materials_costs
                else:
                    price = 0  # 予期しない値の場合
                row = [node.name, price, attr]
                for week_no in range(output_period):
                    count = len(node.psi4supply[week_no][attr])
                    row.append(count)
                data.append(row)
            for child in node.children:
                collect_data(child, output_period)
        # ヘッダーの設定
        headers_outbound = ["node_name", "Price", "PSI_attribute"] + [f"w{i+1}" for i in range(output_period_outbound)]
        # root_node_outbound のツリー構造を走査してデータを収集
        collect_data(self.root_node_outbound, output_period_outbound)
        # DataFrame を作成して CSV に保存
        df_outbound = pd.DataFrame(data, columns=headers_outbound)
        df_outbound.to_csv(save_path, index=False)
        # 完了メッセージを表示
        messagebox.showinfo("CSV Export", f"PSI and Price for CashFlow data has been exported to {save_path}")
    #9. Ensure Data Accuracy
    #Before displaying the chart:
    #
    #Verify that eval_cs_price_sales_shipped and eval_cs_profit are up-to-date.
    #If necessary, call a method like update_evaluation_results() to refresh the data prior to collection.
    #For example:
    #    self.update_evaluation_results()  # Ensure data is current
    #    performance_data = self.collect_performance_data()
    # This recursive function:
    # Traverses the supply chain tree starting from the root node (root_node_outbound).
    # Stores each node’s revenue and profit in a dictionary, keyed by node name.
    def collect_performance_data(self):
        performance_data = {}
        def traverse(node):
            performance_data[node.name] = {
                'revenue': node.eval_cs_price_sales_shipped,
                'profit': node.eval_cs_profit
            }
            for child in node.children:
                traverse(child)
        traverse(self.root_node_outbound)
        return performance_data
    # Extracts node names, revenues, and profits from the collected data.
    # Plots two bars per node (revenue in blue, profit in green).
    # Adds labels, a title, and a legend for clarity.
    #import matplotlib.pyplot as plt
    #import tkinter as tk
    #from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    def show_revenue_profit(self):
        # Collect data
        performance_data = self.collect_performance_data()
        nodes = list(performance_data.keys())
        revenues = [data['revenue'] for data in performance_data.values()]
        profits = [data['profit'] for data in performance_data.values()]
        total_costs = [revenue - profit for revenue, profit in zip(revenues, profits)]
        profit_ratios = [round((profit / revenue) * 100, 2) if revenue != 0 else 0 for profit, revenue in zip(profits, revenues)]
        # Create bar chart
        fig, ax = plt.subplots(figsize=(6, 9))  # グラフサイズ調整
        bar_width = 0.35
        index = range(len(nodes))
        # Plot stacked bars
        bars1 = ax.bar(index, total_costs, bar_width, label='Total Cost', color='red', alpha=0.8)
        bars2 = ax.bar(index, profits, bar_width, bottom=total_costs, label='Profit', color='green', alpha=0.8)
        # Add value labels on top of bars (adjusting position)
        for idx, (bar1, bar2) in enumerate(zip(bars1, bars2)):
            height = bar1.get_height() + bar2.get_height()
            formatted_revenue = f'{int(round(revenues[idx])):,}'
            formatted_profit_ratio = f'{profit_ratios[idx]:.2f}%'
            # **数値ラベルの配置調整**
            ax.text(bar1.get_x() + bar1.get_width() / 2.0,
                    height + 300,  # 上にずらす
                    formatted_revenue, ha='center', va='bottom', fontsize=6, color='black')
            ax.text(bar1.get_x() + bar1.get_width() / 2.0,
                    height + bar2.get_height() / 2 + 600,  # さらに上にずらす
                    formatted_profit_ratio, ha='center', va='bottom', fontsize=6, color='black')
        # Customize chart
        ax.set_xlabel('Supply Chain Nodes', fontsize=8)
        ax.set_ylabel('Amount', fontsize=8)
        ax.set_title('Revenue and Profit Ratio by Node', fontsize=10)
        ax.set_xticks([i for i in index])
        ax.set_xticklabels(nodes, rotation=90, ha='right', fontsize=6)
        ax.legend(fontsize=8)
        # Reduce chart margins
        fig.tight_layout()
        # Display in GUI
        self.display_chart(fig)
    def display_chart(self, fig):
        # Clear previous content
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        # Embed chart
        canvas = FigureCanvasTkAgg(fig, master=self.scrollable_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    def cashflow_out_in_net(self):
        print("cashflow_out_in_net")
        # CSVファイルの保存パスを固定
        cashflow_save_path = os.path.join(self.load_directory, "CashFlow_AR_AP_shift.csv")
        profile_outbound_path = os.path.join(self.load_directory, "profile_tree_outbound.csv")
        print("Save to", cashflow_save_path)
        # 出力期間の計算
        output_period_outbound = 53 * self.root_node_outbound.plan_range
        # データの収集
        data = []
        def collect_data(node, output_period, level, position):
            ar_days = node.AR_lead_time  # 売掛金回収期間（例: 30日）
            ap_days = node.AP_lead_time  # 買掛金支払期間（例: 45日）
            ar_shift = int(ar_days // 7)
            ap_shift = int(ap_days // 7)
            weekly_values_cash_in = []
            weekly_values_cash_out = []
            for attr in range(4):  # 0:"Sales", 1:"CarryOver", 2:"Inventory", 3:"Purchase"
                if attr == 0:
                    price = node.cs_price_sales_shipped
                elif attr in [1, 2]:
                    price = node.cs_purchase_total_cost
                elif attr == 3:
                    price = node.cs_direct_materials_costs
                else:
                    price = 0
                row = [node.name, level, position, price, attr]
                weekly_values = [len(node.psi4supply[week_no][attr]) * price for week_no in range(output_period)]
                row.extend(weekly_values)
                data.append(row)
                if attr == 0:
                    weekly_values_cash_in = np.roll(weekly_values, ar_shift)
                    row = [node.name, level, position, price, "IN"]
                elif attr == 3:
                    weekly_values_cash_out = np.roll(weekly_values, ap_shift)
                    row = [node.name, level, position, price, "OUT"]
                else:
                    continue
                row.extend(weekly_values)
                data.append(row)
            # Net Cashの計算
            row = [node.name, level, position, price, "NET"]
            max_length = output_period
            if len(weekly_values_cash_in) == 0:
                weekly_values_cash_in = np.zeros(max_length)
            if len(weekly_values_cash_out) == 0:
                weekly_values_cash_out = np.zeros(max_length)
            weekly_values_cash_net = np.array(weekly_values_cash_in) - np.array(weekly_values_cash_out)
            row.extend(weekly_values_cash_net)
            data.append(row)
            for i, child in enumerate(node.children):
                collect_data(child, output_period, level + 1, i + 1)
        # CSVヘッダーの設定
        headers_outbound = ["node_name", "Level", "Position", "Price", "PSI_attribute"] + [f"w{i+1}" for i in range(output_period_outbound)]
        # データ収集
        collect_data(self.root_node_outbound, output_period_outbound, 0, 1)
        # DataFrame作成 & CSV保存
        df_outbound = pd.DataFrame(data, columns=headers_outbound)
        df_outbound.to_csv(cashflow_save_path, index=False)
        # CSVデータを別ウィンドウで表示
        self.plot_cash_flow_window(cashflow_save_path, profile_outbound_path)
    # Function to plot cash flow graph with spacing adjustment
    def plot_cash_flow(self, node_data, parent_frame):
        node_name = node_data['node_name'].iloc[0]
        pivot_data = node_data.pivot(index='Week', columns='PSI_attribute', values='Cash Flow').fillna(0)
        pivot_data = pivot_data.rename(columns={'IN': 'Cash In', 'OUT': 'Cash Out', 'NET': 'Net Cash Flow'})
        for col in ['Cash In', 'Cash Out', 'Net Cash Flow']:
            if col not in pivot_data.columns:
                pivot_data[col] = 0
        fig, ax1 = plt.subplots(figsize=(2.3, 1.2), dpi=100)  # Smaller width and height
        fig.subplots_adjust(wspace=0.3, hspace=0.3)  # Adjust space between subplots
        bar_width = 0.2
        ax1.bar(pivot_data.index - bar_width/2, pivot_data["Cash In"], width=bar_width, label="Cash In", color='#d3d3d3', alpha=0.7)
        ax1.bar(pivot_data.index + bar_width/2, pivot_data["Cash Out"], width=bar_width, label="Cash Out", color='#ff69b4', alpha=0.7)
        ax2 = ax1.twinx()
        ax2.plot(pivot_data.index, pivot_data["Net Cash Flow"], label="Net Cash Flow", marker='o', linestyle='-', color='#1f77b4', linewidth=1, markersize=2)
        # Smaller font size for better fitting
        ax1.set_xlabel("Weeks", fontsize=10) #@250702 fantsize 6=>10
        ax1.set_ylabel("Cash In / Cash Out", fontsize=10)
        ax2.set_ylabel("Net Cash Flow", fontsize=10)
        ax1.legend(loc='upper left', fontsize=10) #@250702 fantsize 5=>10
        ax2.legend(loc='upper right', fontsize=10)
        # Change tick label font sizes
        ax1.tick_params(axis='x', labelsize=4)
        ax1.tick_params(axis='y', labelsize=4)
        ax2.tick_params(axis='y', labelsize=4)
        fig.suptitle(f'Cash Flow for {node_name}', fontsize=10) #@250702 fantsize 7=>10
        canvas = FigureCanvasTkAgg(fig, master=parent_frame)
        canvas.draw()
        canvas.get_tk_widget().grid(row=0, column=0, padx=2, pady=2)
        plt.close(fig)  # Close figure to free memory
    def traverse_and_plot(self, data, tree_structure, root_node_name, scrollable_frame, parent_col):
        node_queue = [(root_node_name, 0)]  # Queue for BFS traversal (node_name, level)
        row_counter = 0  # Start at row 0
        root_node_processed = False
        while node_queue:
            current_node_name, current_level = node_queue.pop(0)
            children = tree_structure[tree_structure[parent_col] == current_node_name]
            if not root_node_processed:
                for _, child in children.iterrows():
                    child_node_name = child['Child_node']
                    node_queue.append((child_node_name, current_level + 1))
                root_node_processed = True
                continue
            if len(children) > 0:
                node_data = data[data['node_name'] == current_node_name]
                row_frame = tk.Frame(scrollable_frame)
                row_frame.grid(row=row_counter, column=0, sticky="w", padx=5, pady=5)
                if not node_data.empty and current_level > 0:
                    parent_frame = tk.Frame(row_frame)
                    parent_frame.pack(side=tk.LEFT, padx=5, pady=5)
                    self.plot_cash_flow(node_data, parent_frame)
                for _, child in children.iterrows():
                    child_node_name = child['Child_node']
                    node_queue.append((child_node_name, current_level + 1))
                    child_data = data[data['node_name'] == child_node_name]
                    if not child_data.empty:
                        child_frame = tk.Frame(row_frame)
                        child_frame.pack(side=tk.LEFT, padx=5, pady=5)
                        self.plot_cash_flow(child_data, child_frame)
                row_counter += 1
    def traverse_and_plot_preorder(self, data, tree_structure, root_node_name, scrollable_frame, parent_col):
        node_stack = [(root_node_name, 0)]  # Stack for Preorder traversal (node_name, level)
        row_counter = 0  # Start at row 0
        while node_stack:
            current_node_name, current_level = node_stack.pop()
            children = tree_structure[tree_structure[parent_col] == current_node_name]
            node_data = data[data['node_name'] == current_node_name]
            row_frame = tk.Frame(scrollable_frame)
            row_frame.grid(row=row_counter, column=0, sticky="w", padx=5, pady=5)
            if not node_data.empty:
                parent_frame = tk.Frame(row_frame)
                parent_frame.pack(side=tk.LEFT, padx=5, pady=5)
                self.plot_cash_flow(node_data, parent_frame)
            for _, child in children.iterrows():
                child_node_name = child['Child_node']
                node_stack.append((child_node_name, current_level + 1))
            row_counter += 1
    def plot_cash_flow_window(self, cashflow_save_path, profile_outbound_path):
        df = pd.read_csv(cashflow_save_path)
        df = df.drop(columns=['Price'])
        df_melted = df.melt(id_vars=['node_name', 'Level', 'Position', 'PSI_attribute'], var_name='Week', value_name='Cash Flow')
        df_melted['Week'] = df_melted['Week'].str.extract(r'(\d+)').astype(int)
        cash_flow_data = df_melted.groupby(['node_name', 'Level', 'Position', 'PSI_attribute', 'Week'])['Cash Flow'].sum().reset_index()
        cash_window = tk.Toplevel(self.root)
        cash_window.title("Cash Flow Analyzer")
        cash_window.geometry("1400x800")
        frame = ttk.Frame(cash_window)
        frame.pack(pady=10)
        canvas = tk.Canvas(cash_window)
        #scrollable_frame = ttk.Frame(canvas)
        #canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        #canvas.pack(fill=tk.BOTH, expand=True)
        v_scrollbar = tk.Scrollbar(cash_window, orient="vertical", command=canvas.yview)
        h_scrollbar = tk.Scrollbar(cash_window, orient="horizontal", command=canvas.xview)
        scrollable_frame = tk.Frame(canvas)
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=BOTH, expand=True)
        v_scrollbar.pack(side=tk.RIGHT, fill=Y)
        h_scrollbar.pack(side=tk.BOTTOM, fill=X)
        # Load tree structure from CSV file
        def load_tree_structure(file_path):
            df = pd.read_csv(file_path)
            print("CSV Columns:", df.columns.tolist())  # Debugging: Print columns to identify correct names
            return df
        ## Load tree structure from CSV file
        #def load_tree_structure(file_path="profile_tree_outbound.csv"):
        #    df = pd.read_csv(file_path)
        #    print("CSV Columns:", df.columns.tolist())  # Debugging: Print columns to identify correct names
        #    return df
        # Identify parent column dynamically
        def get_parent_column(tree_structure):
            possible_names = ["Parent_node", "Parent_no", "Parent", "ParentNode"]
            for col in possible_names:
                if col in tree_structure.columns:
                    print("Detected Parent Column:", col)  # Debugging: Confirm detected column
                    return col
            raise KeyError("Parent column not found in tree structure CSV.")
        #tree_structure = load_tree_structure()
        tree_structure = load_tree_structure(profile_outbound_path)
        parent_col = get_parent_column(tree_structure)
        print("parent_col", parent_col)
        # Load and process CSV file for cash flow data
        def load_and_process_csv(file_path):
            df = pd.read_csv(file_path)
            cash_flow_data = df.drop(columns=['Price'])
            cash_flow_long = cash_flow_data.melt(id_vars=['node_name', 'Level', 'Position', 'PSI_attribute'], var_name='Week', value_name='Cash Flow')
            cash_flow_long['Week'] = cash_flow_long['Week'].str.extract(r'(\d+)').astype(int)
            return cash_flow_long.groupby(['node_name', 'Level', 'Position', 'PSI_attribute', 'Week'])['Cash Flow'].sum().reset_index()
        cash_flow_agg = load_and_process_csv(cashflow_save_path)
        unique_nodes = tree_structure[parent_col].unique()
        root_node = unique_nodes[0] if len(unique_nodes) > 0 else None
        print("root_node", root_node)
            #if root_node:
        self.traverse_and_plot(cash_flow_agg, tree_structure, root_node, scrollable_frame, parent_col)
        #self.traverse_and_plot_preorder(cash_flow_data, tree_structure, tree_structure[parent_col].iloc[0], scrollable_frame, parent_col)
    def plot_cash_flow(self, node_data, parent_frame):
        node_name = node_data['node_name'].iloc[0]
        pivot_data = node_data.pivot(index='Week', columns='PSI_attribute', values='Cash Flow').fillna(0)
        pivot_data = pivot_data.rename(columns={'IN': 'Cash In', 'OUT': 'Cash Out', 'NET': 'Net Cash Flow'})
        for col in ['Cash In', 'Cash Out', 'Net Cash Flow']:
            if col not in pivot_data.columns:
                pivot_data[col] = 0
        fig, ax1 = plt.subplots(figsize=(3, 1.5), dpi=100)
        fig.subplots_adjust(wspace=0.2)
        bar_width = 0.2
        ax1.bar(pivot_data.index - bar_width / 2, pivot_data["Cash In"], width=bar_width, label="Cash In", color='#d3d3d3', alpha=0.7)
        ax1.bar(pivot_data.index + bar_width / 2, pivot_data["Cash Out"], width=bar_width, label="Cash Out", color='#ff69b4', alpha=0.7)
        ax2 = ax1.twinx()
        ax2.plot(pivot_data.index, pivot_data["Net Cash Flow"], label="Net Cash Flow", marker='o', linestyle='-', color='#1f77b4', linewidth=1, markersize=2)
        ax1.set_xlabel("Weeks", fontsize=10) #@250702 fantsize 6=>10
        ax1.set_ylabel("Cash In / Cash Out", fontsize=10)
        ax2.set_ylabel("Net Cash Flow", fontsize=10)
        ax1.legend(loc='upper left', fontsize=10) #@250702 fantsize 5=>10
        ax2.legend(loc='upper right', fontsize=10)
        ax1.tick_params(axis='x', labelsize=8)
        ax1.tick_params(axis='y', labelsize=8)
        ax2.tick_params(axis='y', labelsize=8)
        fig.suptitle(f'Cash Flow for {node_name}', fontsize=10) #@250702 fantsize 7=>10
        canvas = FigureCanvasTkAgg(fig, master=parent_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        plt.close(fig)
    # ******************************
    # define planning ENGINE
    # ******************************
    #def demand_planning(self):
    #    pass
    def demand_planning(self):
        # Implement forward planning logic here
        print("Forward planning executed.")
        #@240903@241106
        calc_all_psi2i4demand(self.root_node_outbound)
        self.update_evaluation_results()
        #@241212 add
        self.decouple_node_selected = []
        self.view_nx_matlib()
        self.root.after(1000, self.show_psi("outbound", "demand"))
        #self.root.after(1000, self.show_psi_graph)
        #self.show_psi_graph() # this event do not live
    def demand_planning4multi_product(self):
        # Implement forward planning logic here
        print("demand_planning4multi_product planning executed.")
        #@250730 ADD multi_product Focus on Selected Product # root is "supply_point"
        self.root_node_outbound_byprod = self.prod_tree_dict_OT[self.product_selected]
        self.root_node_inbound_byprod  = self.prod_tree_dict_IN[self.product_selected]
        #@240903@241106
        calc_all_psi2i4demand(self.root_node_outbound_byprod)
        #self.update_evaluation_results()
        self.update_evaluation_results4multi_product()
        #@241212 add
        self.decouple_node_selected = []
        #self.view_nx_matlib()
        self.view_nx_matlib4opt()
        self.root.after(1000, self.show_psi_by_product("outbound", "demand", self.product_selected))
        #show_psi_by_product(self, bound, layer, product_name)
        #self.root.after(1000, self.show_psi_graph)
        #self.show_psi_graph() # this event do not live
    #def demand_leveling(self):
    #    pass
    #@250120 STOP with "name chaged"
    def demand_leveling(self):
        # Demand Leveling logic here
        print("Demand Leveling executed.")
        # *********************************
        # Demand LEVELing on shipping yard / with pre_production week
        # *********************************
        year_st  = 2020
        year_end = 2021
        year_st  = self.plan_year_st
        year_end = year_st + self.plan_range - 1
        pre_prod_week = self.pre_proc_LT
        # STOP
        #year_st = df_capa_year["year"].min()
        #year_end = df_capa_year["year"].max()
        # root_node_outboundのsupplyの"S"のみを平準化して生成している
        demand_leveling_on_ship(self.root_node_outbound, pre_prod_week, year_st, year_end)
        # root_node_outboundのsupplyの"PSI"を生成している
        ##@241114 KEY CODE
        self.root_node_outbound.calcS2P_4supply()  #mother plantのconfirm S=> P
        self.root_node_outbound.calcPS2I4supply()  #mother plantのPS=>I
        #@241114 KEY CODE
        # ***************************************
        # その3　都度のparent searchを実行 setPS_on_ship2node
        # ***************************************
        feedback_psi_lists(self.root_node_outbound, self.nodes_outbound)
        #feedback_psi_lists(self.root_node_outbound, node_psi_dict_Ot4Sp, self.nodes_outbound)
        # STOP
        #decouple_node_names = [] # initial PUSH with NO decouple node
        ##push_pull_on_decouple
        #push_pull_all_psi2i_decouple4supply5(
        #    self.root_node_outbound,
        #    decouple_node_names )
        #@241114 KEY CODE
        #@240903
        #calc_all_psi2i4demand(self.root_node_outbound)
        #calc_all_psi2i4supply(self.root_node_outbound)
        self.update_evaluation_results()
        # PSI計画の初期状態をバックアップ
        self.psi_backup_to_file(self.root_node_outbound, 'psi_backup.pkl')
        self.view_nx_matlib()
        self.root.after(1000, self.show_psi("outbound", "supply"))
        #self.root.after(1000, self.show_psi_graph)
    def demand_leveling4multi_prod(self):
        # Demand Leveling logic here
        print("Demand Leveling4multi_prod executed.")
        #@250730 ADD multi_product Focus on Selected Product # root is "supply_point"
        self.root_node_outbound_byprod = self.prod_tree_dict_OT[self.product_selected]
        self.root_node_inbound_byprod  = self.prod_tree_dict_IN[self.product_selected]
        # *********************************
        # Demand LEVELing on shipping yard / with pre_production week
        # *********************************
        year_st  = 2020
        year_end = 2021
        year_st  = self.plan_year_st
        year_end = year_st + self.plan_range - 1
        pre_prod_week = self.pre_proc_LT
        # STOP
        #year_st = df_capa_year["year"].min()
        #year_end = df_capa_year["year"].max()
        # root_node_outboundのsupplyの"S"のみを平準化して生成している
        demand_leveling_on_ship(self.root_node_outbound_byprod, pre_prod_week, year_st, year_end)
        # root_node_outboundのsupplyの"PSI"を生成している
        ##@241114 KEY CODE
        # node.calcXXXはPlanNodeのmethod
        self.root_node_outbound_byprod.calcS2P_4supply()  #mother plantのconfirm S=> P
        self.root_node_outbound_byprod.calcPS2I4supply()  #mother plantのPS=>I
        #@241114 KEY CODE
        # ***************************************
        # その3　都度のparent searchを実行 setPS_on_ship2node
        # ***************************************
        def make_nodes(node):
            nodes = {}
            def traverse(n):
                if n is None:
                    return
                # ノード名をキーにノード自身を格納
                nodes[n.name] = n
                # 子ノードがある場合は再帰的に探索
                for child in getattr(n, 'children', []):
                    traverse(child)
            traverse(node)
            return nodes
        nodes_outbound_byprod = make_nodes(self.root_node_outbound_byprod)
        feedback_psi_lists(self.root_node_outbound_byprod, nodes_outbound_byprod)
        #feedback_psi_lists(self.root_node_outbound_byprod, self.nodes_outbound)
        #feedback_psi_lists(self.root_node_outbound, node_psi_dict_Ot4Sp, self.nodes_outbound)
        # STOP
        #decouple_node_names = [] # initial PUSH with NO decouple node
        ##push_pull_on_decouple
        #push_pull_all_psi2i_decouple4supply5(
        #    self.root_node_outbound,
        #    decouple_node_names )
        #@241114 KEY CODE
        #@240903
        #calc_all_psi2i4demand(self.root_node_outbound)
        #calc_all_psi2i4supply(self.root_node_outbound)
        self.update_evaluation_results4multi_product()
        #@250730 STOP
        ## PSI計画の初期状態をバックアップ
        #self.psi_backup_to_file(self.root_node_outbound, 'psi_backup.pkl')
        self.view_nx_matlib4opt()
        self.root.after(1000, self.show_psi_by_product("outbound", "supply", self.product_selected))
        #self.root.after(1000, self.show_psi_graph)
    def psi_backup(self, node, status_name):
        return copy.deepcopy(node)
    def psi_restore(self, node_backup, status_name):
        return copy.deepcopy(node_backup)
    def psi_backup_to_file(self, node, filename):
        with open(filename, 'wb') as file:
            pickle.dump(node, file)
    def psi_restore_from_file(self, filename):
        with open(filename, 'rb') as file:
            node_backup = pickle.load(file)
        return node_backup
    def supply_planning4multi_product(self):
        #@250730 ADD multi_product Focus on Selected Product # root is "supply_point"
        self.root_node_outbound_byprod = self.prod_tree_dict_OT[self.product_selected]
        self.root_node_inbound_byprod  = self.prod_tree_dict_IN[self.product_selected]
        # Check if the necessary data is loaded
        #if self.root_node_outbound is None or self.nodes_outbound is None:
        if self.root_node_outbound_byprod is None:
            print("Error: PSI Plan data4multi-product is not loaded.")
            tk.messagebox.showerror("Error", "PSI Plan data4multi-product is not loaded.")
            return
        # Implement forward planning logic here
        print("Supply planning with Decoupling points")
        #@250730 STOP
        ## Restore PSI data from a backup file
        #self.root_node_outbound = self.psi_restore_from_file('psi_backup.pkl')
        #@250730 Temporary ADD
        self.decouple_node_selected = []
        if self.decouple_node_selected == []:
            # Search nodes_decouple_all[-2], that is "DAD" nodes
            nodes_decouple_all = make_nodes_decouple_all(self.root_node_outbound_byprod)
            print("nodes_decouple_all by_product", self.product_selected, nodes_decouple_all)
            # [-3] will be "DAD" node, the point of Delivery and Distribution
            decouple_node_names = nodes_decouple_all[-3] # this is "DADxxx"
            print("decouple_node_names = nodes_decouple_all[-3] ", self.product_selected, decouple_node_names)
            # sampl image of nodes_decouple_all
            # nodes_decouple_all by_product JPN_Koshihikari [['CS_JPN'], ['RT_JPN'], ['WS2JPN'], ['WS1Kosihikari'], ['DADKosihikari'], ['supply_point'], ['root']]
        else:
            decouple_node_names = self.decouple_node_selected
        print("push_pull_all_psi2i_decouple4supply5")
        print("self.root_node_outbound_byprod.name", self.root_node_outbound_byprod.name)
        print("decouple_node_names", decouple_node_names)
        # Perform supply planning logic
        push_pull_all_psi2i_decouple4supply5(
            self.root_node_outbound_byprod, decouple_node_names
        )
        # Evaluate the results
        #self.update_evaluation_results()
        self.update_evaluation_results4multi_product()
        #@250218 STOP
        ## Cash OUT/IN
        #self.cash_flow_print()
        # Update the network visualization
        self.decouple_node_selected = decouple_node_names
        self.view_nx_matlib4opt()
        # Update the PSI area
        self.root.after(1000, self.show_psi_by_product("outbound", "supply", self.product_selected))
        #self.root.after(1000, self.show_psi("outbound", "supply"))
    def supply_planning(self):
        # Check if the necessary data is loaded
        if self.root_node_outbound is None or self.nodes_outbound is None:
            print("Error: PSI Plan data is not loaded. Please load the data first.")
            tk.messagebox.showerror("Error", "PSI Plan data is NOT loaded. please File Open parameter directory first.")
            return
        # Implement forward planning logic here
        print("Supply planning with Decoupling points")
        # Restore PSI data from a backup file
        self.root_node_outbound = self.psi_restore_from_file('psi_backup.pkl')
        if self.decouple_node_selected == []:
            # Search nodes_decouple_all[-2], that is "DAD" nodes
            nodes_decouple_all = make_nodes_decouple_all(self.root_node_outbound    )
            print("nodes_decouple_all", nodes_decouple_all)
            # [-2] will be "DAD" node, the point of Delivery and Distribution
            decouple_node_names = nodes_decouple_all[-2]
        else:
            decouple_node_names = self.decouple_node_selected
        # Perform supply planning logic
        push_pull_all_psi2i_decouple4supply5(
            self.root_node_outbound, decouple_node_names
        )
        # Evaluate the results
        self.update_evaluation_results()
        #@250218 STOP
        ## Cash OUT/IN
        #self.cash_flow_print()
        # Update the network visualization
        self.decouple_node_selected = decouple_node_names
        self.view_nx_matlib4opt()
        # Update the PSI area
        self.root.after(1000, self.show_psi("outbound", "supply"))
    #def eval_buffer_stock(self):
    #    pass
    def eval_buffer_stock(self):
        # Check if the necessary data is loaded
        if self.root_node_outbound is None or self.nodes_outbound is None:
            print("Error: PSI Plan data is not loaded. Please load the data first.")
            tk.messagebox.showerror("Error", "PSI Plan data is NOT loaded. please File Open parameter directory first.")
            return
        print("eval_buffer_stock with Decoupling points")
        # This backup is in "demand leveling"
        ## PSI計画の初期状態をバックアップ
        #self.psi_backup_to_file(self.root_node_outbound, 'psi_backup.pkl')
        nodes_decouple_all = make_nodes_decouple_all(self.root_node_outbound)
        print("nodes_decouple_all", nodes_decouple_all)
        for i, decouple_node_names in enumerate(nodes_decouple_all):
            print("nodes_decouple_all", nodes_decouple_all)
            # PSI計画の状態をリストア
            self.root_node_outbound = self.psi_restore_from_file('psi_backup.pkl')
            push_pull_all_psi2i_decouple4supply5(self.root_node_outbound, decouple_node_names)
            self.update_evaluation_results()
            print("decouple_node_names", decouple_node_names)
            print("self.total_revenue", self.total_revenue)
            print("self.total_profit", self.total_profit)
            self.decouple_node_dic[i] = [self.total_revenue, self.total_profit, decouple_node_names]
            ## network area
            #self.view_nx_matlib()
            ##@241207 TEST
            #self.root.after(1000, self.show_psi("outbound", "supply"))
        self.display_decoupling_patterns()
        # PSI area => move to selected_node in window
    def optimize_network(self):
        # Check if the necessary data is loaded
        if self.root_node_outbound is None or self.nodes_outbound is None:
            print("Error: PSI Plan data is not loaded. Please load the data first.")
            tk.messagebox.showerror("Error", "PSI Plan data is NOT loaded. please File Open parameter directory first.")
            return
        print("optimizing start")
    #@ STOP
    #def optimize_and_view_nx_matlib(self):
        G = nx.DiGraph()    # base display field
        Gdm_structure = nx.DiGraph()  # optimise for demand side
        #Gdm = nx.DiGraph()  # optimise for demand side
        Gsp = nx.DiGraph()  # optimise for supply side
        self.G = G
        self.Gdm_structure = Gdm_structure
        self.Gsp = Gsp
        root_node_outbound = self.root_node_outbound
        nodes_outbound = self.nodes_outbound
        root_node_inbound = self.root_node_inbound
        nodes_inbound = self.nodes_inbound
        pos_E2E, G, Gdm_structure, Gsp = self.show_network_E2E_matplotlib(
        #pos_E2E, Gdm_structure, Gsp = show_network_E2E_matplotlib(
        #pos_E2E, flowDict_dm, flowDict_sp, Gdm_structure, Gsp = show_network_E2E_matplotlib(
            root_node_outbound, nodes_outbound,
            root_node_inbound, nodes_inbound,
            G, Gdm_structure, Gsp
        )
        # **************************************************
        # optimizing here
        # **************************************************
        G_opt = Gdm_structure.copy()
        # 最適化パラメータをリセット
        self.reset_optimization_params(G_opt)
        #@241229 ADD
        self.reset_optimized_path(G_opt)
        # 新しい最適化パラメータを設定
        self.set_optimization_params(G_opt)
        flowDict_opt = self.flowDict_opt
        print("optimizing here flowDict_opt", flowDict_opt)
        # 最適化を実行
        # fllowing set should be done here
        #self.flowDict_opt = flowDict_opt
        #self.flowCost_opt = flowCost_opt
        self.run_optimization(G_opt)
        print("1st run_optimization self.flowDict_opt", self.flowDict_opt)
        # flowCost_opt = self.flowCost_opt # direct input
        G_result = G_opt.copy()
        G_view = G_result.copy()
        self.add_optimized_path(G_view, self.flowDict_opt)
        #@241205 STOP **** flowDict_optを使ったGのE2Eの表示系に任せる
        ## 前回の最適化pathをリセット
        self.reset_optimized_path(G_result)
        #
        ## 新しい最適化pathを追加
        G_result = G_opt.copy()
        self.add_optimized_path(G_result, self.flowDict_opt)
        # 最適化pathの表示（オプション）
        #print("Iteration", i + 1)
        print("Optimized Path:", self.flowDict_opt)
        print("Optimized Cost:", self.flowCost_opt)
        # make optimized tree and PSI planning and show it
        flowDict_opt = self.flowDict_opt
        optimized_nodes = {} # 初期化
        optimized_nodes = self.create_optimized_tree(flowDict_opt)
        if not optimized_nodes:
            error_message = "error: optimization with NOT enough supply"
            print(error_message)
            self.show_error_message(error_message)  # 画面にエラーメッセージを表示する関数
            return
        print("optimized_nodes", optimized_nodes)
        optimized_root = optimized_nodes['supply_point']
        self.optimized_root = optimized_root
        #@241227 MEMO
        # 最適化されたnodeの有無でPSI表示をON/OFFしているが、これに加えて
        # ここでは、最適化nodeは存在し、、年間の値が0の時、
        # 年間供給量を月次に按分して供給するなどの処理を追加する
        # *********************************
        # making limited_supply_nodes
        # *********************************
        leaf_nodes_out       = self.leaf_nodes_out  # all leaf_nodes
        optimized_nodes_list = []              # leaf_node on targetted market
        limited_supply_nodes = []              # leaf_node Removed from target
        # 1. optimized_nodes辞書からキー項目をリストoptimized_nodes_listに抽出
        optimized_nodes_list = list(optimized_nodes.keys())
        # 2. leaf_nodes_outからoptimized_nodes_listの要素を排除して
        # limited_supply_nodesを生成
        limited_supply_nodes = [node for node in leaf_nodes_out if node not in optimized_nodes_list]
        # 結果を表示
        print("optimized_nodes_list:", optimized_nodes_list)
        print("limited_supply_nodes:", limited_supply_nodes)
# 最適化の結果をPSIに反映する方法
# 1. 入力ファイルS_month_data.csvをdataframeに読込み
# 2. limited_supply_nodesの各要素node nameに該当するS_month_dataのSの値を
#    すべて0 clearする。
# 3. 結果を"S_month_optimized.csv"として保存する
# 4. S_month_optimized.csvを入力として、load_data_opt_filesからPSI planする
        # limited_supply_nodesのリスト
        #limited_supply_nodes = ['MUC_N', 'MUC_D', 'MUC_I', 'SHA_I', 'NYC_D', 'NYC_I', 'LAX_D', 'LAX_I']
        # 入力CSVファイル名
        input_csv = 'S_month_data.csv'
        # デバッグ用コード追加
        print(f"self.directory: {self.directory}")
        print(f"input_csv: {input_csv}")
        if self.directory is None or input_csv is None:
            raise ValueError("self.directory または input_csv が None になっています。適切な値を設定してください。")
        input_csv_path = os.path.join(self.directory, input_csv)
        # 出力CSVファイル名
        output_csv = 'S_month_optimized.csv'
        output_csv_path = os.path.join(self.directory, output_csv)
        # S_month.csvにoptimized_demandをセットする
        # optimized leaf_node以外を0 clearする
        #@ STOP
        # 最適化にもとづく供給配分 ここでは簡易的にon-offしているのみ
        # 本来であれば、最適化の供給配分を詳細に行うべき所
        #self.clear_s_values(limited_supply_nodes, input_csv_path, output_csv_path)
        input_csv = 'S_month_data.csv'
        output_csv = 'S_month_optimized.csv'
        input_csv_path = os.path.join(self.directory, input_csv)
        output_csv_path = os.path.join(self.directory, output_csv)
        self.clear_s_values(self.flowDict_opt, input_csv_path, output_csv_path)
        ## **************************************
        ## input_csv = 'S_month_optimized.csv' load_files & planning
        ## **************************************
        #
        self.load_data_files4opt()     # loading with 'S_month_optimized.csv'
        #
        self.plan_through_engines4opt()
        # **************************************
        # いままでの評価と描画系
        # **************************************
        # *********************
        # evaluation@241220
        # *********************
        #@241225 memo "root_node_out_opt"のtreeにはcs_xxxxがセットされていない
        self.update_evaluation_results4optimize()
        # *********************
        # network graph
        # *********************
        # STAY ORIGINAL PLAN
        # selfのhandle nameは、root_node_outboundで、root_node_out_optではない
        #
        # グラフ描画関数を呼び出し  最適ルートを赤線で表示
        #
        # title revenue, profit, profit_ratio
        self.draw_network4opt(G, Gdm_structure, Gsp, pos_E2E, self.flowDict_opt)
        #self.draw_network4opt(G, Gdm, Gsp, pos_E2E, flowDict_dm, flowDict_sp, flowDict_opt)
        # *********************
        # PSI graph
        # *********************
        self.root.after(1000, self.show_psi_graph4opt)
        #self.root.after(1000, self.show_psi_graph)
        #@ ADD
        # パラメータの初期化と更新を呼び出し
        self.updated_parameters()
        #@ STOP
        #self.updated_parameters4opt()
    def Inbound_DmBw(self):
        connect_outbound2inbound(self.root_node_outbound, self.root_node_inbound)
        calc_all_psiS2P2childS_preorder(self.root_node_inbound)
        #@250120 eval and view
        self.update_evaluation_results()
        #@241212 add
        self.decouple_node_selected = []
        self.view_nx_matlib()
        self.root.after(1000, self.show_psi("inbound", "demand"))
        #self.root.after(1000, self.show_psi("outbound", "demand"))
        pass
    def Inbound_SpFw(self):
        #@240907 demand2supply
        # copy demand layer to supply layer # メモリーを消費するので要修正
        self.node_psi_dict_In4Sp = psi_dict_copy(
                                 self.node_psi_dict_In4Dm, # in demand  .copy()
                                 self.node_psi_dict_In4Sp   # in supply
                              )
        # In4Dmの辞書をself.psi4supply = node_psi_dict_In4Dm[self.name]でre_connect
        def re_connect_suppy_dict2psi(node, node_psi_dict):
            node.psi4supply = node_psi_dict[node.name]
            for child in node.children:
                re_connect_suppy_dict2psi(child, node_psi_dict)
        re_connect_suppy_dict2psi(self.root_node_inbound, self.node_psi_dict_In4Sp)
        calc_all_psi2i4supply_post(self.root_node_inbound)
        #@250120 eval and view
        self.update_evaluation_results()
        #@241212 add
        self.decouple_node_selected = []
        self.view_nx_matlib()
        self.root.after(1000, self.show_psi("inbound", "supply"))
        #self.root.after(1000, self.show_psi("outbound", "demand"))
        pass
# **** 19 call_backs END*****
# **** Start of SUB_MODULE for Optimization ****
    def _load_tree_structure(self, load_directory):
        with open(f"{load_directory}/root_node_outbound.pkl", 'rb') as f:
            self.root_node_outbound = pickle.load(f)
            print(f"root_node_outbound loaded: {self.root_node_outbound}")
        with open(f"{load_directory}/root_node_inbound.pkl", 'rb') as f:
            self.root_node_inbound = pickle.load(f)
            print(f"root_node_inbound loaded: {self.root_node_inbound}")
        if os.path.exists(f"{load_directory}/root_node_out_opt.pkl"):
            with open(f"{load_directory}/root_node_out_opt.pkl", 'rb') as f:
                self.root_node_out_opt = pickle.load(f)
                print(f"root_node_out_opt loaded: {self.root_node_out_opt}")
        else:
            self.flowDict_opt = {}  # NO optimize
            pass
    def reset_optimization_params(self, G):
        for u, v in G.edges():
            G[u][v]['capacity'] = 0
            G[u][v]['weight'] = 0
        for node in G.nodes():
            G.nodes[node]['demand'] = 0
    def reset_optimized_path(self, G):
        for u, v in G.edges():
            if 'flow' in G[u][v]:
                del G[u][v]['flow']
    def run_optimization(self, G):
        #flow_dict = nx.min_cost_flow(G)
        #cost = nx.cost_of_flow(G, flow_dict)
        #return flow_dict, cost
        # ************************************
        # optimize network
        # ************************************
        try:
            flowCost_opt, flowDict_opt = nx.network_simplex(G)
        except Exception as e:
            print("Error during optimization:", e)
            return
        self.flowCost_opt = flowCost_opt
        self.flowDict_opt = flowDict_opt
        print("flowDict_opt", flowDict_opt)
        print("flowCost_opt", flowCost_opt)
        print("end optimization")
    def add_optimized_path(self, G, flow_dict):
        for u in flow_dict:
            for v, flow in flow_dict[u].items():
                if flow > 0:
                    G[u][v]['flow'] = flow
    # 画面にエラーメッセージを表示する関数
    def show_error_message(self, message):
        error_window = tk.Toplevel(self.root)
        error_window.title("Error")
        tk.Label(error_window, text=message, fg="red").pack()
        tk.Button(error_window, text="OK", command=error_window.destroy).pack()
    # オリジナルノードからコピーする処理
    def copy_node(self, node_name):
        original_node = self.nodes_outbound[node_name]  #オリジナルノードを取得
        copied_node = copy.deepcopy(original_node)  # deepcopyを使ってコピー
        return copied_node
    def create_optimized_tree(self, flowDict_opt):
        # Optimized Treeの生成
        optimized_nodes = {}
        for from_node, flows in flowDict_opt.items():
            if from_node == 'sales_office': # 末端の'sales_office'はtreeの外
                pass
            else:
                for to_node, flow in flows.items():
                    if to_node == 'sales_office': # 末端の'sales_office'はtreeの外
                        pass
                    else:
                        if flow > 0:
                            if from_node not in optimized_nodes:
                                optimized_nodes[from_node] = self.copy_node(from_node)
                            if to_node not in optimized_nodes:
                                optimized_nodes[to_node] = self.copy_node(to_node)
                                optimized_nodes[to_node].parent =optimized_nodes[from_node]
        return optimized_nodes
    def set_optimization_params(self, G):
        print("optimization start")
        #Gdm = self.Gdm
        nodes_outbound = self.nodes_outbound
        root_node_outbound = self.root_node_outbound
        print("root_node_outbound.name", root_node_outbound.name)
        # Total Supply Planの取得
        total_supply_plan = int( self.total_supply_plan )
        #total_supply_plan = int(self.tsp_entry.get())
        print("setting capacity")
        max_capacity = 1000000  # 設定可能な最大キャパシティ（適切な値を設定）
        scale_factor_capacity = 1  # キャパシティをスケールするための因子
        scale_factor_demand   = 1  # スケーリング因子
        for edge in G.edges():
            from_node, to_node = edge
            # if node is leaf_node
            #@250103 STOP
            #if from_node in self.leaf_nodes_out and to_node == 'sales_office':
            #@250103 RUN
            if to_node in self.leaf_nodes_out:
                #@250103 RUN
                # ********************************************
                # scale_factor_capacity
                #@241220 TAX100... demand curve... Price_Up and Demand_Down
                # ********************************************
                capacity = int(nodes_outbound[to_node].nx_capacity * scale_factor_capacity)
                #@ STOP
                ## ********************************************
                ## scale_factor_capacity
                ##@241220 TAX100... demand curve... Price_Up and Demand_Down
                ## ********************************************
                #capacity = int(nodes_outbound[from_node].lot_counts_all * scale_factor_capacity)
                G.edges[edge]['capacity'] = capacity
            else:
                G.edges[edge]['capacity'] = max_capacity  # 最大キャパシティを設定
            print("G.edges[edge]['capacity']", edge, G.edges[edge]['capacity'])
        #@250102 MARK
        print("setting weight")
        for edge in G.edges():
            from_node, to_node = edge
            #@ RUN
            G.edges[edge]['weight'] = int(nodes_outbound[from_node].nx_weight)
            print("weight = nx_weight = cs_cost_total+TAX", nodes_outbound[from_node].name, int(nodes_outbound[from_node].nx_weight) )
            #@ STOP
            #G.edges[edge]['weight'] = int(nodes_outbound[from_node].cs_cost_total)
            #print("weight = cs_cost_total", nodes_outbound[from_node].name, int(nodes_outbound[from_node].cs_cost_total) )
        print("setting source and sink")
        # Total Supply Planの取得
        total_supply_plan = int( self.total_supply_plan )
        print("source:supply_point:-total_supply_plan", -total_supply_plan * scale_factor_demand)
        print("sink  :sales_office:total_supply_plan", total_supply_plan * scale_factor_demand)
        # scale = 1
        G.nodes['supply_point']['demand'] = -total_supply_plan * scale_factor_demand
        G.nodes['sales_office']['demand'] = total_supply_plan * scale_factor_demand
        print("optimizing supply chain network")
        for node in G.nodes():
            if node != 'supply_point' and node != 'sales_office':
                G.nodes[node]['demand'] = 0  # 他のノードのデマンドは0に設定
#        # ************************************
#        # optimize network
#        # ************************************
#        try:
#
#            flowCost_opt, flowDict_opt = nx.network_simplex(G)
#
#        except Exception as e:
#            print("Error during optimization:", e)
#            return
#
#        self.flowCost_opt = flowCost_opt
#        self.flowDict_opt = flowDict_opt
#
#        print("flowDict_opt", flowDict_opt)
#        print("flowCost_opt", flowCost_opt)
#
#        print("end optimization")
    # ******************************
    # engines helper エンジン起動→評価→再描画 @250921
    # ******************************
    def _get_roots(self):
        prod = getattr(self, "product_selected", None) or getattr(self.env, "product_selected", None)
        def get_roots(self, product_name: str):
            r_ot = self.prod_tree_dict_OT.get(product_name)
            r_in = self.prod_tree_dict_IN.get(product_name, r_ot)
            return (r_ot, r_in)
        out_root, in_root = self.psi.get_roots(prod)
        #out_root, in_root = self.psi.get_roots_for_product(prod)
        #out_root, in_root = self.env.get_roots_for_product(prod)
        return prod, out_root, in_root


    def _run_engine_gui(self, mode: str, layer: str):

        prod, out_root, in_root = self._get_roots()
        
        if not (out_root or in_root):
            print("[WARN] roots not ready"); return
        
        root = out_root if mode.startswith("outbound") else in_root
        
        kwargs = {}
        
        if "MOM" in mode:
            kwargs["mom_name"] = self.var_mom.get().strip()
        
        if "BUFFER" in mode:
            kwargs["buffer_name"] = self.var_buf.get().strip()
        
        if mode == "outbound_forward_push_DAD_to_buffer":
            kwargs.setdefault("dad_name", "DAD")
        
        ##@250923 UPDATE
        #out_rt, in_rt = run_engine(out_root, in_root, self.decouple_node_selected, mode=mode, layer=layer, **kwargs)
        # decouple の選択は GUI が決める。engine に渡すだけ
        
        out_rt, in_rt = run_engine(
            out_root, in_root, self.decouple_node_selected,
            mode=mode, layer=layer,
            dad_name=self.var_dad.get().strip() if hasattr(self, "var_dad") else "DAD",
            buffer_name=self.var_buf.get().strip() if hasattr(self, "var_buf") else "BUFFER",
        )
        
        self.root_node_outbound = out_rt
        self.root_node_inbound  = in_rt
        
        try:
            eval_supply_chain_cost(self.root_node_outbound)
            eval_supply_chain_cost(self.root_node_inbound)
        
        except Exception as e:
            print("[WARN] eval_supply_chain_cost:", e)
        # 再描画（既存の描画関数名に合わせて調整）
        try:
            self.view_nx_matlib4opt()
        except Exception as e:
            print("[WARN] network redraw:", e)
        # 旧：
        # self.show_psi_by_product("outbound", "demand", prod)
        # self.show_psi_by_product("outbound", "supply", prod)
        # self.show_psi_by_product("inbound",  "demand", prod)
        # self.show_psi_by_product("inbound",  "supply", prod)
        # 新：俯瞰 1 枚（基本は supply）
        try:
            #self.show_psi_overview(prod, layer="supply", skip_empty=True)
            #self.show_psi_overview(prod, primary_layer="supply", fallback_to_demand=True)
            self.show_psi_overview(prod, primary_layer="supply",
                        fallback_to_demand=True, skip_empty=True)
        except Exception as e:
            print("[WARN] psi overview:", e)




    def _run_full_pipeline(self):
        seq = [
            ("outbound_backward_leaf_to_MOM", "demand"),
            ("inbound_MOM_leveling_vs_capacity", "demand"),
            ("inbound_backward_MOM_to_leaf", "demand"),
            ("inbound_forward_leaf_to_MOM", "supply"),
            ("outbound_forward_push_DAD_to_buffer", "supply"),
            ("outbound_backward_pull_buffer_to_leaf", "supply"),
        ]
        for mode, layer in seq:
            self._run_engine_gui(mode, layer)


    def plan_through_engines4opt(self):
    #@RENAME
    # nodes_out_opt     : nodes_out_opt
    # root_node_out_opt : root_node_out_opt
        print("planning with OPTIMIZED S")
        # Demand planning
        calc_all_psi2i4demand(self.root_node_out_opt)
        # Demand LEVELing on shipping yard / with pre_production week
        year_st = self.plan_year_st
        year_end = year_st + self.plan_range - 1
        pre_prod_week = self.pre_proc_LT
        demand_leveling_on_ship(self.root_node_out_opt, pre_prod_week, year_st, year_end)
        # root_node_out_optのsupplyの"PSI"を生成している
        self.root_node_out_opt.calcS2P_4supply()  #mother plantのconfirm S=> P
        self.root_node_out_opt.calcPS2I4supply()  #mother plantのPS=>I
        # ***************************************
        # その3　都度のparent searchを実行 setPS_on_ship2node
        # ***************************************
        feedback_psi_lists(self.root_node_out_opt, self.nodes_out_opt)
        #@241208 STOP
        ## Supply planning
        #print("Supply planning with Decoupling points")
        #nodes_decouple_all = make_nodes_decouple_all(self.root_node_out_opt)
        #print("nodes_decouple_all", nodes_decouple_all)
        #
        #for i, decouple_node_names in enumerate(nodes_decouple_all):
        #    decouple_flag = "OFF"
        #    if i == 0:
        decouple_node_names = self.decouple_node_selected
        push_pull_all_psi2i_decouple4supply5(self.root_node_out_opt, decouple_node_names)
# **** End of Optimization ****
    def load_tree_structure(self):
        try:
            file_path = filedialog.askopenfilename(title="Select Tree Structure File")
            if not file_path:
                return
            # Placeholder for loading tree structure
            self.tree_structure = nx.DiGraph()
            self.tree_structure.add_edge("Root", "Child1")
            self.tree_structure.add_edge("Root", "Child2")
            messagebox.showinfo("Success", "Tree structure loaded successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load tree structure: {e}")
    def view_nx_matlib4opt_WO_capa(self):
        G = nx.DiGraph()
        Gdm_structure = nx.DiGraph()
        Gsp = nx.DiGraph()
        self.G = G
        self.Gdm_structure = Gdm_structure
        self.Gsp = Gsp
        pos_E2E, G, Gdm, Gsp = self.show_network_E2E_matplotlib_WO_capa(
            self.root_node_outbound, self.nodes_outbound,
            self.root_node_inbound, self.nodes_inbound,
            G, Gdm_structure, Gsp
        )
        self.pos_E2E = pos_E2E
        #self.draw_network4opt(G, Gdm, Gsp, pos_E2E)
        # グラフ描画関数を呼び出し  最適ルートを赤線で表示
        print("load_from_directory self.flowDict_opt", self.flowDict_opt)
        self.draw_network4opt(G, Gdm_structure, Gsp, pos_E2E, self.flowDict_opt)
    def draw_network4opt(self, G, Gdm, Gsp, pos_E2E, flowDict_opt):
        self.ax_network.clear()  # 図をクリア
        # タイトル設定
        total_revenue = round(self.total_revenue)
        total_profit = round(self.total_profit)
        profit_ratio = round((total_profit / total_revenue) * 100, 1) if total_revenue != 0 else 0
        self.ax_network.set_title(
            f'PySI Optimized Supply Chain Network\nREVENUE: {total_revenue:,} | PROFIT: {total_profit:,} | PROFIT_RATIO: {profit_ratio}%',
            fontsize=10
        )
        self.ax_network.axis('off')
        # ノードの形状と色
        node_shapes = ['v' if node in self.decouple_node_selected else 'o' for node in G.nodes()]
        node_colors = ['brown' if node in self.decouple_node_selected else 'lightblue' for node in G.nodes()]
        # ノード描画
        for node, shape, color in zip(G.nodes(), node_shapes, node_colors):
            nx.draw_networkx_nodes(G, pos_E2E, nodelist=[node], node_size=50, node_color=color, node_shape=shape, ax=self.ax_network)
        # エッジ描画
        for edge in G.edges():
            if edge[0] == "procurement_office" or edge[1] == "sales_office":
                edge_color = 'lightgrey'
            elif edge in Gdm.edges():
                edge_color = 'blue'
            elif edge in Gsp.edges():
                edge_color = 'green'
            else:
                edge_color = 'lightgrey'
            nx.draw_networkx_edges(G, pos_E2E, edgelist=[edge], edge_color=edge_color, arrows=False, ax=self.ax_network, width=0.5)
        # 最適化パス（赤線）
        for from_node, flows in flowDict_opt.items():
            for to_node, flow in flows.items():
                if flow > 0:
                    nx.draw_networkx_edges(self.G, pos_E2E, edgelist=[(from_node, to_node)], ax=self.ax_network, edge_color='red', arrows=False, width=0.5)
        # ノードラベル
        node_labels = {node: f"{node}" for node in G.nodes()}
        nx.draw_networkx_labels(G, pos_E2E, labels=node_labels, font_size=10, ax=self.ax_network)
        # キャンバス更新
        self.canvas_network.draw()
        #@STOP
        #plt.close(self.fig_network)  # メモリ解放のため閉じる
        self.canvas_network.mpl_connect('button_press_event', self.on_plot_click)
    def make_highlight_flow(self, prod_tree_OT, prod_tree_IN):
        """
        指定された product の tree 構造 (outbound + inbound) の root PlanNode から、
        描画用の flow エッジ情報を抽出する。
        戻り値: dict[from_node][to_node] = flow
        """
        highlight_flow = {}
        def walk_tree(plan_node):
            for child in plan_node.children:
                from_node = plan_node.name
                to_node = child.name
                if from_node not in highlight_flow:
                    highlight_flow[from_node] = {}
                highlight_flow[from_node][to_node] = 1.0
                walk_tree(child)
        # root PlanNode から再帰的にたどる
        if prod_tree_OT is not None:
            print("highlight: outbound root =", prod_tree_OT.name)
            walk_tree(prod_tree_OT)
        if prod_tree_IN is not None:
            print("highlight: inbound root =", prod_tree_IN.name)
            walk_tree(prod_tree_IN)
        return highlight_flow
    def draw_network4multi_prod(self, G, Gdm, Gsp, pos_E2E, highlight_flow):
        #@250826 STOP
        #self._ensure_network_axes()  # ← 保険
        #ax = self.ax_network
        #
        #self.ax_network.clear()  # 図をクリア
        #
        ## タイトル設定
        #total_revenue = round(self.total_revenue)
        #total_profit = round(self.total_profit)
        #profit_ratio = round((total_profit / total_revenue) * 100, 1) if total_revenue != 0 else 0
        #self.ax_network.set_title(
        #    f'PySI Optimized Supply Chain Network\nREVENUE: {total_revenue:,} | PROFIT: {total_profit:,} | PROFIT_RATIO: {profit_ratio}%',
        #    fontsize=10
        #)
        #self.ax_network.axis('off')
        #@250826 ADD
        self._ensure_network_axes()
        ax = self.ax_network
        ax.clear()
        # 安全なタイトル設定（ゼロ初期化でも落ちない）
        self._set_network_title()
        ax.axis('off')
        # ここが落ちていたのでガード
        decouple_set = set(getattr(self, "decouple_node_selected", []) or [])
        # （例）ノード形状の決定で使用している箇所を安全化
        node_shapes = ['v' if node in decouple_set else 'o' for node in G.nodes()]
        # …以降の描画処理はそのままでOK
        #@250826 MEMO 実値でタイトルを出したい場合
        # どこかで集計が終わったタイミング（例：update_evaluation_results() やエンジン実行後）
        #self.total_revenue = calc_revenue_somehow(...)  # 実際の合計売上
        #self.total_profit  = calc_profit_somehow(...)   # 実際の合計利益
        ## ネットワーク再描画 or タイトルだけ更新
        #self._set_network_title()
        #if hasattr(self, "canvas_network"):
        #    self.canvas_network.draw_idle()
        # ノードの形状と色
        node_shapes = ['v' if node in self.decouple_node_selected else 'o' for node in G.nodes()]
        node_colors = ['brown' if node in self.decouple_node_selected else 'lightblue' for node in G.nodes()]
        # ノード描画
        for node, shape, color in zip(G.nodes(), node_shapes, node_colors):
            nx.draw_networkx_nodes(G, pos_E2E, nodelist=[node], node_size=50, node_color=color, node_shape=shape, ax=self.ax_network)
        # エッジ描画
        for edge in G.edges():
            if edge[0] == "procurement_office" or edge[1] == "sales_office":
                edge_color = 'lightgrey'
            elif edge in Gdm.edges():
                edge_color = 'blue'
            elif edge in Gsp.edges():
                edge_color = 'green'
            else:
                edge_color = 'lightgrey'
            nx.draw_networkx_edges(G, pos_E2E, edgelist=[edge], edge_color=edge_color, arrows=False, ax=self.ax_network, width=0.5)
        #@STOP
        ## 最適化パス（赤線）
        #for from_node, flows in flowDict_opt.items():
        #    for to_node, flow in flows.items():
        #        if flow > 0:
        #            nx.draw_networkx_edges(self.G, pos_E2E, edgelist=[(from_node, to_node)], ax=self.ax_network, edge_color='red', arrows=False, width=0.5)
        #@ STOP 描画関数の外に出す
        ## red line 描画用 flow 構造に変換
        #highlight_flow = self.make_highlight_flow(prod_tree_OT, prod_tree_IN)
        # flow に従って赤線を描画
        for from_node, flows in highlight_flow.items():
            for to_node, flow in flows.items():
                if flow > 0:
                    nx.draw_networkx_edges(
                        self.G,
                        pos_E2E,
                        edgelist=[(from_node, to_node)],
                        ax=self.ax_network,
                        edge_color='red',
                        arrows=False,
                        width=1.0
                    )
        # ノードラベル
        node_labels = {node: f"{node}" for node in G.nodes()}
        nx.draw_networkx_labels(G, pos_E2E, labels=node_labels, font_size=10, ax=self.ax_network)
        # キャンバス更新
        self.canvas_network.draw()
        #@STOP
        #plt.close(self.fig_network)  # メモリ解放のため閉じる
        self.canvas_network.mpl_connect('button_press_event', self.on_plot_click)
    def show_info_graph(self, node_info, select_node):
        # 既存のウィンドウを再利用または作成
        if self.info_window is None or not tk.Toplevel.winfo_exists(self.info_window):
            self.info_window = tk.Toplevel(self.root)
            self.info_window.title("Node Information")
            self.info_frame = tk.Frame(self.info_window)
            self.info_frame.pack()
            self.info_label = tk.Label(self.info_frame, text="", justify='left', font=("Arial", 10), padx=10)
            self.info_label.grid(row=0, column=1, sticky='nw')
        else:
            # 既存のキャンバスをクリア
            for widget in self.info_frame.grid_slaves(row=0, column=0):
                widget.destroy()
        #@250729 ADD
        plan_node = select_node.sku_dict[self.product_selected]
        # 円グラフデータ
        labels = ['Profit', 'SG&A', 'Tax Portion', 'Logistics', 'Warehouse', 'Materials']
        values = [
                plan_node.eval_cs_profit,
                plan_node.eval_cs_SGA_total,
                plan_node.eval_cs_tax_portion,
                plan_node.eval_cs_logistics_costs,
                plan_node.eval_cs_warehouse_cost,
                plan_node.eval_cs_direct_materials_costs,
        ]
        colors = ['blue', 'orange', 'green', 'red', 'purple', 'brown']
        filtered = [(l, v, c) for l, v, c in zip(labels, values, colors) if v > 0]
        if not filtered:
            filtered = [('No Data', 1, 'gray')]
        labels, values, colors = zip(*filtered)
        # 新しい円グラフ
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90, colors=colors)
        ax.set_title(select_node.name, fontsize=9)
        print("DEBUG: plan_node.eval_cs_warehouse_cost =", plan_node.eval_cs_warehouse_cost)
        print("DEBUG: plan_node.sku.warehouse_cost =", plan_node.sku.warehouse_cost)
        # キャンバスを更新
        self.info_canvas = FigureCanvasTkAgg(fig, master=self.info_frame)
        self.info_canvas.get_tk_widget().grid(row=0, column=0)
        self.info_canvas.draw()
        self.info_label.config(text=node_info)
        # 古いFigureを閉じる
        plt.close(fig)
        gc.collect()  # ガベージコレクションを明示的に実行
    def on_plot_click(self, event):
        if event.xdata is None or event.ydata is None:
            return
        # 最も近いノードを検索
        min_dist = float('inf')
        closest_node = None
        for node, (nx_pos, ny_pos) in self.pos_E2E.items():
            dist = np.sqrt((event.xdata - nx_pos) ** 2 + (event.ydata - ny_pos) ** 2)
            if dist < min_dist:
                min_dist = dist
                closest_node = node
        if closest_node and min_dist < 0.5:
            # ノード情報の取得
            select_node = None
            if closest_node in self.nodes_outbound and self.nodes_outbound[closest_node]:
                select_node = self.nodes_outbound[closest_node]
            elif closest_node in self.nodes_inbound and self.nodes_inbound[closest_node]:
                select_node = self.nodes_inbound[closest_node]
            else:
                print("Error: Node not found or value is None")
                return
            #@250801 ADD
            self.select_node = select_node
            plan_node = select_node.sku_dict[self.product_selected]
            print("select_node plan_node =", select_node.name, plan_node.name)
            # ノード情報文字列の作成
            revenue      = round(plan_node.eval_cs_price_sales_shipped)
            profit       = round(plan_node.eval_cs_profit)
            profit_ratio = round((profit / revenue) * 100, 1) if revenue != 0 else 0
            node_info = (
                f" name: {select_node.name}\n"
                f" leadtime: {    plan_node.leadtime}\n"
                f" demand  : {    plan_node.nx_demand}\n"
                f" weight  : {    plan_node.nx_weight}\n"
                f" capacity: {    plan_node.nx_capacity }\n\n"
                f" Evaluation\n"
                f" decoupling_total_I: {    plan_node.decoupling_total_I }\n"
                f" lot_counts_all    : {    plan_node.lot_counts_all     }\n\n"
                f" Settings for cost-profit evaluation parameter\n"
                f" LT_boat            : {    plan_node.LT_boat             }\n"
                f" SS_days            : {    plan_node.SS_days             }\n"
                f" HS_code            : {    plan_node.HS_code             }\n"
                #@250803 UPDATE
                f" tariff_rate: {    plan_node.tariff_rate*100 }%\n"
                f" tariff_cost: {    plan_node.tariff_cost  }\n"
                #f" customs_tariff_rate: {    plan_node.customs_tariff_rate*100 }%\n"
                #f" tariff_on_price    : {    plan_node.tariff_on_price     }\n"
                f" price_elasticity   : {    plan_node.price_elasticity    }\n\n"
                f" Business Performance\n"
                f" offering_price_TOBE: {    plan_node.offering_price_TOBE  }\n"
                f" offering_price_ASIS: {    plan_node.offering_price_ASIS  }\n"
                f" profit_ratio: {profit_ratio     }%\n"
                f" revenue     : {revenue:,}\n"
                f" profit      : {profit:,}\n\n"
                f" Cost_Structure\n"
                #f" SGA_total   : {round(    plan_node.eval_cs_SGA_total):,}\n"
                #f" Custom_tax  : {round(    plan_node.eval_cs_tax_portion):,}\n"
                #f" Logi_costs  : {round(    plan_node.eval_cs_logistics_costs):,}\n"
                #f" WH_cost     : {round(    plan_node.eval_cs_warehouse_cost):,}\n"
                #f" Direct_MTRL : {round(    plan_node.eval_cs_direct_materials_costs):,}\n"
                f" SGA_total   : {plan_node.eval_cs_SGA_total:.2f}\n"
                f" Custom_tax  : {plan_node.eval_cs_tax_portion:.2f}\n"
                f" Logi_costs  : {plan_node.eval_cs_logistics_costs:.2f}\n"
                f" WH_cost     : {plan_node.eval_cs_warehouse_cost:.2f}\n"
                f" Direct_MTRL : {plan_node.eval_cs_direct_materials_costs:.2f}\n"
            )
            print( "testing list(node.sku_dict.values())[0] ")
            print("select_node.name", select_node.name)
            print("select_node.sku_dict", select_node.sku_dict)
            for produst_node_item in list(select_node.sku_dict.items()):
                print("produst_node_item in list(node.sku_dict.items())", produst_node_item )
            for key, value in select_node.sku_dict.items():
                print("select_node.sku_dict key:peoduct_name value:plan_node.name", key, value.name )
                print("value:plan_node.psi4demand", key, value.psi4demand )
            print("node_info", node_info)
            # 情報ウィンドウを表示
            self.print_cost_sku()
            self.print_cost_node_cs()
            self.print_cost_node_eval_cs()
            self.show_info_graph(node_info, select_node)
    def draw_network4opt_STOP250727(self, G, Gdm, Gsp, pos_E2E, flowDict_opt):
        # 安全に初期化（すでに存在していればスキップ）
        if not hasattr(self, 'annotation_artist'):
            self.annotation_artist = None
        if not hasattr(self, 'last_highlight_node'):
            self.last_highlight_node = None
        if not hasattr(self, 'last_clicked_node'):
            self.last_clicked_node = None
        ## 既存の軸をクリア
        #self.ax_network.clear()
    #def draw_network(self, G, Gdm, Gsp, pos_E2E):
        self.ax_network.clear()  # 図をクリア
        print("draw_network4opt: self.total_revenue", self.total_revenue)
        print("draw_network4opt: self.total_profit", self.total_profit)
        # 評価結果の更新
        ttl_revenue = self.total_revenue
        ttl_profit = self.total_profit
        ttl_profit_ratio = (ttl_profit / ttl_revenue) if ttl_revenue != 0 else 0
        # 四捨五入して表示
        total_revenue = round(ttl_revenue)
        total_profit = round(ttl_profit)
        profit_ratio = round(ttl_profit_ratio * 100, 1)  # パーセント表示
        #ax.set_title(f'Node: {node_name} | REVENUE: {revenue:,} | PROFIT: {profit:,} | PROFIT_RATIO: {profit_ratio}%', fontsize=8)
        # タイトルを設定
        self.ax_network.set_title(f'PySI Optimized Supply Chain Network\nREVENUE: {total_revenue:,} | PROFIT: {total_profit:,} | PROFIT_RATIO: {profit_ratio}%', fontsize=10)
        print("ax_network.set_title: total_revenue", total_revenue)
        print("ax_network.set_title: total_profit", total_profit)
#".format(total_revenue, total_profit))
        self.ax_network.axis('off')
        # *************************
        # contents of network draw START
        # *************************
        # ノードの形状と色を定義
        node_shapes = ['v' if node in self.decouple_node_selected else 'o' for node in G.nodes()]
        node_colors = ['brown' if node in self.decouple_node_selected else 'lightblue' for node in G.nodes()]
        # ノードの描画
        for node, shape, color in zip(G.nodes(), node_shapes, node_colors):
            nx.draw_networkx_nodes(G, pos_E2E, nodelist=[node], node_size=50, node_color=color, node_shape=shape, ax=self.ax_network)
        # エッジの描画
        for edge in G.edges():
            if edge[0] == "procurement_office" or edge[1] == "sales_office":
                edge_color = 'lightgrey'  # "procurement_office"または"sales_office"に接続するエッジはlightgrey
            elif edge in Gdm.edges():
                edge_color = 'blue'  # outbound（Gdm）のエッジは青
            elif edge in Gsp.edges():
                edge_color = 'green'  # inbound（Gsp）のエッジは緑
            else:
                edge_color = 'lightgrey'  # その他はlightgrey
            nx.draw_networkx_edges(G, pos_E2E, edgelist=[edge], edge_color=edge_color, arrows=False, ax=self.ax_network, width=0.5)
        # 最適化pathの赤線表示
        for from_node, flows in flowDict_opt.items():
            for to_node, flow in flows.items():
                if flow > 0:
                    # "G"の上に描画
                    nx.draw_networkx_edges(self.G, self.pos_E2E, edgelist=[(from_node, to_node)], ax=self.ax_network, edge_color='red', arrows=False, width=0.5)
        # ノードラベルの描画
        node_labels = {node: f"{node}" for node in G.nodes()}
        nx.draw_networkx_labels(G, pos_E2E, labels=node_labels, font_size=10, ax=self.ax_network)
        # *************************
        # contents of network draw END
        # *************************
        # ***************************
        # title and axis
        # ***************************
        #plt.title("Supply Chain Network end2end")
        #@ STOOOOOOOP
        #plt.title("Optimized Supply Chain Network")
        #self.ax_network.axis('off')  # 軸を非表示にする
        # *******************
        #@250319 STOP
        # *******************
        ## キャンバスを更新
        self.canvas_network.draw()
        # 🔴 `on_plot_click` 関数の定義（ここに追加）
        #info_window = None  # ノード情報ウィンドウの参照を保持
        # 🔴 `self.info_window` をクラス変数として定義
        self.info_window = None  # ノード情報ウィンドウの参照を保持
        def on_plot_click_STOP250727(event):
            """ クリックしたノードの情報を表示する関数 """
            #global info_window
            clicked_x, clicked_y = event.xdata, event.ydata
            print("clicked_x, clicked_y", clicked_x, clicked_y)
            if clicked_x is None or clicked_y is None:
                return  # クリックがグラフ外の場合は無視
            # クリック位置に最も近いノードを検索
            min_dist = float('inf')
            closest_node = None
            for node, (nx_pos, ny_pos) in pos_E2E.items():
                dist = np.sqrt((clicked_x - nx_pos) ** 2 + (clicked_y - ny_pos) ** 2)
                if dist < min_dist:
                    min_dist = dist
                    closest_node = node
            if closest_node and min_dist < 0.5:  # 誤認識を防ぐための閾値
            #if closest_node and min_dist < 0.1:  # 誤認識を防ぐための閾値
                node_info = f"Node: {closest_node}\nDegree: {G.degree[closest_node]}"
                print("closest_node", closest_node)
                # node情報の取り出し
                if closest_node in self.nodes_outbound:
                    if self.nodes_outbound[closest_node] is not None:
                        select_node = self.nodes_outbound[closest_node]
                    else:
                        print("error: nodes_outbound value is None")
                elif closest_node in self.nodes_inbound:
                    if self.nodes_inbound[closest_node] is not None:
                        select_node = self.nodes_inbound[closest_node]
                    else:
                        print("error: nodes_inbound value is None")
                else:
                    print("error: closest_node not found in nodes_outbound or nodes_inbound")
                # ***************************
                # on_node_click
                # ***************************
                def on_node_click(gui_node, product_name):
                    sku = gui_node.sku_dict.get(product_name)
                    if sku and sku.psi_node_ref:
                        plan_node = sku.psi_node_ref
                        # 🧠 表示項目の例（簡易版）
                        print(f"[{product_name}] @ Node: {gui_node.name}")
                        print("PSI Demand:", plan_node.sku.psi4demand)
                        print("PSI Supply:", plan_node.sku.psi4supply)
                        #print("Cost:", plan_node.sku.cost)
                        print("Revenue:", plan_node.sku.revenue)
                        print("Profit:", plan_node.sku.profit)
                        # GUIに表示したければ、後続で pop-up, graph などに渡す
                # 🔁 Multi Product対応：SKUごとに処理
                for product_name in select_node.sku_dict:
                    on_node_click(select_node, product_name)
                #node_info = f' name: {select_node.name}\n leadtime: {select_node.leadtime}\n demand  : {select_node.nx_demand}\n weight  : {select_node.nx_weight}\n capacity: {select_node.nx_capacity }\n \n Evaluation\n decoupling_total_I: {select_node.decoupling_total_I }\n lot_counts_all    : {select_node.lot_counts_all     }\n \n Settings for cost-profit evaluation parameter}\n LT_boat            : {select_node.LT_boat             }\n SS_days            : {select_node.SS_days             }\n HS_code            : {select_node.HS_code             }\n customs_tariff_rate: {select_node.customs_tariff_rate }\n tariff_on_price    : {select_node.tariff_on_price     }\n price_elasticity   : {select_node.price_elasticity    }\n \n Business Perfirmance\n profit_ratio: {select_node.eval_profit_ratio     }%\n revenue     : {select_node.eval_revenue:,}\n profit      : {select_node.eval_profit:,}\n \n Cost_Structure\n PO_cost     : {select_node.eval_PO_cost        }\n P_cost      : {select_node.eval_P_cost         }\n WH_cost     : {select_node.eval_WH_cost        }\n SGMC        : {select_node.eval_SGMC           }\n Dist_Cost   : {select_node.eval_Dist_Cost      }'
                revenue = round(select_node.eval_cs_price_sales_shipped)
                profit = round(select_node.eval_cs_profit)
                # PROFIT_RATIOを計算して四捨五入
                profit_ratio = round((profit / revenue) * 100, 1) if revenue != 0 else 0
                SGA_total   = round(select_node.eval_cs_SGA_total)
                tax_portion = round(select_node.eval_cs_tax_portion)
                logi_costs  = round(select_node.eval_cs_logistics_costs)
                WH_cost     = round(select_node.eval_cs_warehouse_cost)
                Direct_MTRL = round(select_node.eval_cs_direct_materials_costs)
                node_info = (
    f" name: {select_node.name}\n"
    f" leadtime: {select_node.leadtime}\n"
    f" demand  : {select_node.nx_demand}\n"
    f" weight  : {select_node.nx_weight}\n"
    f" capacity: {select_node.nx_capacity }\n\n"
    f" Evaluation\n"
    f" decoupling_total_I: {select_node.decoupling_total_I }\n"
    f" lot_counts_all    : {select_node.lot_counts_all     }\n\n"
    f" Settings for cost-profit evaluation parameter\n"
    f" LT_boat            : {select_node.LT_boat             }\n"
    f" SS_days            : {select_node.SS_days             }\n"
    f" HS_code            : {select_node.HS_code             }\n"
    f" customs_tariff_rate: {select_node.customs_tariff_rate*100 }%\n"
    f" tariff_on_price    : {select_node.tariff_on_price     }\n"
    f" price_elasticity   : {select_node.price_elasticity    }\n\n"
    f" Business Performance\n"
    f" offering_price_TOBE: {    plan_node.offering_price_TOBE  }\n"
    f" offering_price_ASIS: {    plan_node.offering_price_ASIS  }\n"
    f" profit_ratio: {profit_ratio     }%\n"
    f" revenue     : {revenue:,}\n"
    f" profit      : {profit:,}\n\n"
    #f" profit_ratio: {select_node.eval_cs_profit_ratio     }%\n"
    #f" revenue     : {select_node.eval_cs_revenue:,}\n"
    #f" profit      : {select_node.eval_cs_profit:,}\n\n"
    #f" Tariff_ratio: {select_node.eval_cs_custom_tax}%\n" # これは意味なし
    f" Cost_Structure\n"
    f" SGA_total   : {SGA_total:,}\n"
    f" Custom_tax  : {tax_portion:,}\n"
    f" Logi_costs  : {logi_costs:,}\n"
    f" WH_cost     : {WH_cost:,}\n"
    f" Direct_MTRL : {Direct_MTRL:,}\n"
)
    #f" PO_cost     : {select_node.eval_cs_PO_cost        }\n"
    #f" P_cost      : {select_node.eval_cs_P_cost         }\n"
    #f" WH_cost     : {select_node.eval_cs_WH_cost        }\n"
    #f" SGMC        : {select_node.eval_cs_SGMC           }\n"
    #f" Dist_Cost   : {select_node.eval_cs_Dist_Cost      }"
                ax = self.ax_network
                #@250727 STOP
                ## 🔴【修正1】 既存のラベルをクリア
                #for text in ax.texts:
                #    text.remove()
                #
                ## `node_info` をネットワーク・グラフの中央下部に固定表示
                ##fixed_x, fixed_y = 0.5, 0.1  # Y座標を調整
                #fixed_x, fixed_y = 0.5, 0  # Y座標を調整
                #
                #ax.text(fixed_x, fixed_y, node_info, fontsize=10, color="red",
                #        transform=ax.transAxes, verticalalignment='bottom')
                #
                #
                #
                #
                ### `node_info` をネットワーク・グラフの固定領域に表示（中央下部
                ##fixed_x, fixed_y = 0.5, -0.2  # グラフの中央下部に表示する座標（調整可能）
                ##ax.text(fixed_x, fixed_y, node_info, fontsize=10, color="red",
                ##        transform=ax.transAxes, verticalalignment='top')
                #
                #
                ## `closest_node` をクリックしたノードの近くに表示
                #ax.text(pos_E2E[closest_node][0], pos_E2E[closest_node][1], closest_node, fontsize=10, color="red")
                #@ STOP
                ## ノードの横に情報を表示
                #ax.text(pos_E2E[closest_node][0], pos_E2E[closest_node][1], node_info, fontsize=10, color="red")
                #
                #ax.text(pos_E2E[closest_node][0], pos_E2E[closest_node][1], closest_node, fontsize=10, color="red")
                # *************************
                # contents of network draw START
                # *************************
                # ノードの形状と色を定義
                node_shapes = ['v' if node in self.decouple_node_selected else 'o' for node in G.nodes()]
                node_colors = ['brown' if node in self.decouple_node_selected else 'lightblue' for node in G.nodes()]
                # ノードの描画
                for node, shape, color in zip(G.nodes(), node_shapes, node_colors):
                        nx.draw_networkx_nodes(G, pos_E2E, nodelist=[node], node_size=50, node_color=color, node_shape=shape, ax=self.ax_network)
                # エッジの描画
                for edge in G.edges():
                        if edge[0] == "procurement_office" or edge[1] == "sales_office":
                                edge_color = 'lightgrey'  # "procurement_office"または"sales_office"に接続するエッジはlightgrey
                        elif edge in Gdm.edges():
                                edge_color = 'blue'  # outbound（Gdm）のエッジは青
                        elif edge in Gsp.edges():
                                edge_color = 'green'  # inbound（Gsp）のエッジは緑
                        else:
                                edge_color = 'lightgrey'  # その他はlightgrey
                        nx.draw_networkx_edges(G, pos_E2E, edgelist=[edge], edge_color=edge_color, arrows=False, ax=self.ax_network, width=0.5)
                # 最適化pathの赤線表示
                for from_node, flows in flowDict_opt.items():
                        for to_node, flow in flows.items():
                                if flow > 0:
                                        # "G"の上に描画
                                        nx.draw_networkx_edges(self.G, self.pos_E2E, edgelist=[(from_node, to_node)], ax=self.ax_network, edge_color='red', arrows=False, width=0.5)
                # ノードラベルの描画
                node_labels = {node: f"{node}" for node in G.nodes()}
                nx.draw_networkx_labels(G, pos_E2E, labels=node_labels, font_size=10, ax=self.ax_network)
                # *************************
                # contents of network draw END
                # *************************
                #canvas.draw()  # 再描画
                self.canvas_network.draw()  # 再描画
                # 🔴【修正2】 既存のウィンドウを閉じる
                if self.info_window is not None:
                    self.info_window.destroy()
                # 新しい情報ウィンドウを作成
                show_info_graph(node_info, select_node)
                #self.show_info_graph(node_info, select_node)
                #show_info_graph(node_info)
        def show_info_graph_STOP250727_1550(self, node_info, select_node):
            # 既存のウィンドウを再利用または作成
            if self.info_window is None or not tk.Toplevel.winfo_exists(self.info_window):
                self.info_window = tk.Toplevel(self.root)
                self.info_window.title("Node Information")
                self.info_frame = tk.Frame(self.info_window)
                self.info_frame.pack()
                self.info_label = tk.Label(self.info_frame, text="", justify='left', font=("Arial", 10), padx=10)
                self.info_label.grid(row=0, column=1, sticky='nw')
            else:
                # 既存のキャンバスをクリア
                for widget in self.info_frame.grid_slaves(row=0, column=0):
                    widget.destroy()
            # 円グラフデータ
            labels = ['Profit', 'SG&A', 'Tax Portion', 'Logistics', 'Warehouse', 'Materials']
            values = [
                select_node.eval_cs_profit,
                select_node.eval_cs_SGA_total,
                select_node.eval_cs_tax_portion,
                select_node.eval_cs_logistics_costs,
                select_node.eval_cs_warehouse_cost,
                select_node.eval_cs_direct_materials_costs,
            ]
            colors = ['blue', 'orange', 'green', 'red', 'purple', 'brown']
            filtered = [(l, v, c) for l, v, c in zip(labels, values, colors) if v > 0]
            if not filtered:
                filtered = [('No Data', 1, 'gray')]
            labels, values, colors = zip(*filtered)
            # 新しい円グラフ
            fig, ax = plt.subplots(figsize=(4, 3))
            ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90, colors=colors)
            ax.set_title(select_node.name, fontsize=9)
            # キャンバスを更新
            self.info_canvas = FigureCanvasTkAgg(fig, master=self.info_frame)
            self.info_canvas.get_tk_widget().grid(row=0, column=0)
            self.info_canvas.draw()
            self.info_label.config(text=node_info)
            # 古いFigureを閉じる
            plt.close(fig)
            gc.collect()  # ガベージコレクションを明示的に実行
        def show_info_graph_STOP250727(node_info, select_node):
            """ ノード情報を表示する Tkinter ウィンドウ + 円グラフ """
            if self.info_window is None or not tk.Toplevel.winfo_exists(self.info_window):
                self.info_window = tk.Toplevel(self.root)
                self.info_window.title("Node Information")
                self.info_frame = tk.Frame(self.info_window)
                self.info_frame.pack()
                self.info_label = tk.Label(self.info_frame, text="", justify='left', font=("Arial",10), padx=10)
                self.info_label.grid(row=0, column=1, sticky='nw')
            else:
                # 再利用のため前回のキャンバスがあれば破棄
                for widget in self.info_frame.grid_slaves(row=0, column=0):
                    widget.destroy()
            # Pie chart 再描画
            labels = ['Profit', 'SG&A', 'Tax Portion', 'Logistics', 'Warehouse', 'Materials']
            values = [
                select_node.eval_cs_profit,
                select_node.eval_cs_SGA_total,
                select_node.eval_cs_tax_portion,
                select_node.eval_cs_logistics_costs,
                select_node.eval_cs_warehouse_cost,
                select_node.eval_cs_direct_materials_costs,
            ]
            colors = ['blue', 'orange', 'green', 'red', 'purple', 'brown']
            filtered = [(l, v, c) for l, v, c in zip(labels, values, colors) if v > 0]
            if not filtered:
                filtered = [('No Data', 1, 'gray')]
            labels, values, colors = zip(*filtered)
            fig, ax = plt.subplots(figsize=(4, 3))
            ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90, colors=colors)
            ax.set_title(select_node.name, fontsize=9)
            canvas = FigureCanvasTkAgg(fig, master=self.info_frame)
            canvas.get_tk_widget().grid(row=0, column=0)
            canvas.draw()
            self.info_label.config(text=node_info)
        # 🔴 `mpl_connect` でクリックイベントを登録（ここに追加）
        #canvas.mpl_connect('button_press_event', on_plot_click)
        self.canvas_network.mpl_connect('button_press_event', on_plot_click)
        #@STOP
        ## Tkinter メインループ開始
        #self.root.mainloop()
        # 既存描画コードまま...
        # self.ax_network.clear()
        # ノード／エッジ描画
        # self.canvas_network.draw()
        # annotation_artist 初期化
        if self.annotation_artist:
            self.annotation_artist.remove()
        self.annotation_artist = None
    def view_nx_matlib(self):
        G = nx.DiGraph()
        Gdm_structure = nx.DiGraph()
        Gsp = nx.DiGraph()
        print(f"view_nx_matlib before show_network_E2E_matplotlib self.decouple_node_selected: {self.decouple_node_selected}")
        pos_E2E, G, Gdm_structure, Gsp = self.show_network_E2E_matplotlib(
            self.root_node_outbound, self.nodes_outbound,
            self.root_node_inbound, self.nodes_inbound,
            G, Gdm_structure, Gsp
        )
        self.pos_E2E = pos_E2E
        print(f"view_nx_matlib after show_network_E2E_matplotlib self.decouple_node_selected: {self.decouple_node_selected}")
        self.G = G
        self.Gdm_structure = Gdm_structure
        self.Gsp = Gsp
        self.draw_network(self.G, self.Gdm_structure, self.Gsp, self.pos_E2E)
    def draw_network(self, G, Gdm, Gsp, pos_E2E):
        self.ax_network.clear()  # 図をクリア
        # 評価結果の更新
        ttl_revenue = self.total_revenue
        ttl_profit = self.total_profit
        ttl_profit_ratio = (ttl_profit / ttl_revenue) if ttl_revenue != 0 else 0
        # 四捨五入して表示
        total_revenue = round(ttl_revenue)
        total_profit = round(ttl_profit)
        profit_ratio = round(ttl_profit_ratio * 100, 1)  # パーセント表示
        # タイトルを設定
        self.ax_network.set_title(f'PySI\nOptimized Supply Chain Network\nREVENUE: {total_revenue:,} | PROFIT: {total_profit:,} | PROFIT_RATIO: {profit_ratio}%', fontsize=10)
        self.ax_network.axis('off')
        print("draw_network self.decouple_node_selected", self.decouple_node_selected)
        print("draw_network G nodes", list(G.nodes()))
        print("draw_network G edges", list(G.edges()))
        # Node描画
        node_shapes = ['v' if node in self.decouple_node_selected else 'o' for node in G.nodes()]
        node_colors = ['brown' if node in self.decouple_node_selected else 'lightblue' for node in G.nodes()]
        for node, shape, color in zip(G.nodes(), node_shapes, node_colors):
            nx.draw_networkx_nodes(G, pos_E2E, nodelist=[node], node_size=50, node_color=color, node_shape=shape, ax=self.ax_network)
        # Edge描画
        for edge in G.edges():
            edge_color = 'lightgrey' if edge[0] == "procurement_office" or edge[1] == "sales_office" else 'blue' if edge in Gdm.edges() else 'green' if edge in Gsp.edges() else 'gray'
            nx.draw_networkx_edges(G, pos_E2E, edgelist=[edge], edge_color=edge_color, arrows=False, ax=self.ax_network, width=0.5)
        # Labels描画
        node_labels = {node: node for node in G.nodes()}
        nx.draw_networkx_labels(G, pos_E2E, labels=node_labels, font_size=10, ax=self.ax_network) #@250702 fantsize 6=>10
        #@ STOP
        ## キャンバスの再描画
        #self.canvas_network.draw()
        # キャンバスの再描画
        # 描画処理を待機キューに入れて部分的な描画を実行
        self.canvas_network.draw_idle()
    def display_decoupling_patterns(self):
        subroot = tk.Toplevel(self.root)
        subroot.title("Decoupling Stock Buffer Patterns")
        frame = ttk.Frame(subroot)
        frame.pack(fill='both', expand=True)
        tree = ttk.Treeview(frame, columns=('Revenue', 'Profit', 'Nodes'), show='headings')
        tree.heading('Revenue', text='Revenue')
        tree.heading('Profit', text='Profit')
        tree.heading('Nodes', text='Nodes')
        tree.pack(fill='both', expand=True)
        style = ttk.Style()
        # カラムヘッダを中央揃えにする
        style.configure('Treeview.Heading', anchor='center')
        style.configure('Treeview', rowheight=25)  # 行の高さを設定
        def format_number(value):
            return f"{round(value):,}"
        for i, (revenue, profit, nodes) in self.decouple_node_dic.items():
            formatted_revenue = format_number(revenue)
            formatted_profit = format_number(profit)
            tree.insert('', 'end', values=(formatted_revenue, formatted_profit, ', '.join(nodes)))
        # 列を右寄せに設定する関数
        def adjust_column(tree, col):
            tree.column(col, anchor='e')
        # Revenue と Profit の列を右寄せに設定
        adjust_column(tree, 'Revenue')
        adjust_column(tree, 'Profit')
        selected_pattern = None
        def on_select_pattern(event):
            nonlocal selected_pattern
            item = tree.selection()[0]
            selected_pattern = tree.item(item, 'values')
        tree.bind('<<TreeviewSelect>>', on_select_pattern)
        def on_confirm():
            if selected_pattern:
                self.decouple_node_selected = selected_pattern[2].split(', ')
                print("decouple_node_selected", self.decouple_node_selected)
                self.execute_selected_pattern()
                subroot.destroy()  # サブウィンドウを閉じる
        confirm_button = ttk.Button(subroot, text="SELECT buffering stock", command=on_confirm)
        confirm_button.pack()
        subroot.protocol("WM_DELETE_WINDOW", on_confirm)
    def execute_selected_pattern(self):
        decouple_node_names = self.decouple_node_selected
        # PSI計画の状態をリストア
        self.root_node_outbound = self.psi_restore_from_file('psi_backup.pkl')
        print("exe engine decouple_node_selected", self.decouple_node_selected)
        push_pull_all_psi2i_decouple4supply5(self.root_node_outbound, decouple_node_names)
        self.update_evaluation_results()
        self.view_nx_matlib()
        self.root.after(1000, self.show_psi("outbound", "supply"))
    def load4execute_selected_pattern(self):
        # 1. Load元となるdirectoryの問い合わせ
        load_directory = filedialog.askdirectory()
        if not load_directory:
            return  # ユーザーがキャンセルした場合
        ## 2. 初期処理のcsv fileのコピー
        #for filename in os.listdir(load_directory):
        #    if filename.endswith('.csv'):
        #        full_file_name = os.path.join(load_directory, filename)
        #        if os.path.isfile(full_file_name):
        #            shutil.copy(full_file_name, self.directory)
        # 3. Tree構造の読み込み
        with open(os.path.join(load_directory, 'root_node_outbound.pkl'), 'rb') as f:
            self.root_node_outbound = pickle.load(f)
            print(f"root_node_outbound loaded: {self.root_node_outbound.name}")
        #
        #with open(os.path.join(load_directory, 'root_node_inbound.pkl'), 'rb') as f:
        #    self.root_node_inbound = pickle.load(f)
        #    print(f"root_node_inbound loaded: {self.root_node_inbound}")
        # 4. PSIPlannerAppのデータ・インスタンスの読み込み
        with open(os.path.join(load_directory, 'psi_planner_app.pkl'), 'rb') as f:
            loaded_attributes = pickle.load(f)
            self.__dict__.update(loaded_attributes)
            print(f"loaded_attributes: {loaded_attributes}")
        ## 5. nodes_outboundとnodes_inboundを再生成
        #self.nodes_outbound = self.regenerate_nodes(self.root_node_outbound)
        #self.nodes_inbound = self.regenerate_nodes(self.root_node_inbound)
        # network area
        print("load_from_directory self.decouple_node_selected", self.decouple_node_selected)
        #decouple_node_names = self.decouple_node_selected
        decouple_node_names = self.decouple_node_selected
        ## PSI計画の状態をリストア
        #self.root_node_outbound = self.psi_restore_from_file('psi_backup.pkl')
        print("exe engine decouple_node_selected", self.decouple_node_selected)
        push_pull_all_psi2i_decouple4supply5(self.root_node_outbound, decouple_node_names)
        self.update_evaluation_results()
        #@241212 Gdm_structureにupdated
        self.draw_network(G, Gdm_structure, Gsp, pos_E2E)
        ## 追加: キャンバスを再描画
        #self.canvas_network.draw()
        #
        #self.view_nx_matlib()
        self.root.after(1000, self.show_psi("outbound", "supply"))
# ******************************************
# clear_s_values
# ******************************************
#
#複数年のデータに対応するために、node_name と year をキーにして各ノードのデータを処理。
#
#説明
#leaf_nodeの特定方法の修正：
#
#flow_dict 内で各ノードに sales_office が含まれているかどうかで leaf_nodes を特定します。
#
#rule-1, rule-2, rule-3 の適用：
#
#rule-1: flow_dict に存在しないノードの月次Sの値を0に設定。
#
#rule-2: flow_dict に存在し、sales_office に繋がるノードの値が0である場合、月次S#の値を0に設定。
#
#rule-3: flow_dict に存在し、sales_office に繋がるノードの値が0以外である場合、月次Sの値をプロポーションに応じて分配。
#
#proportionsの計算と値の丸め：
#
#各月のproportionを計算し、それを使って丸めた値を求めます。
#
#rounded_values に丸めた値を格納し、合計が期待する供給量と一致しない場合は、
#最大の値を持つ月で調整します。
#
#年間total_supplyが0の場合の処理：
#年間total_supplyが0の場合は、月次Sの値をすべて0に設定します。
    def clear_s_values(self, flow_dict, input_csv, output_csv):
        # 1. 入力ファイルS_month_data.csvをデータフレームに読み込み
        df = pd.read_csv(input_csv)
        # leaf_nodeを特定
        leaf_nodes = [node for node, connections in flow_dict.items() if 'sales_office' in connections]
        # 2. rule-1, rule-2, rule-3を適用してデータを修正する
        for index, row in df.iterrows():
            node_name = row['node_name']
            year = row['year']
            if node_name in flow_dict:
                # ノードがflow_dictに存在する場合
                if node_name in leaf_nodes:
                    # rule-2: ノードの値が0の場合、月次Sの値をすべて0に設定
                    if flow_dict[node_name]['sales_office'] == 0:
                        df.loc[(df['node_name'] == node_name) & (df['year'] == year),
                               ['m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm8', 'm9', 'm10', 'm11', 'm12']] = 0
                    else:
                        # rule-3: ノードの値が0以外の場合、月次Sのproportionに応じて分配
                        total_supply = sum(df.loc[(df['node_name'] == node_name) & (df['year'] == year),
                                                  ['m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm8', 'm9', 'm10', 'm11', 'm12']].values.flatten())
                        if total_supply != 0:
                            proportions = df.loc[(df['node_name'] == node_name) & (df['year'] == year),
                                                 ['m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm8', 'm9', 'm10', 'm11', 'm12']].values.flatten() / total_supply
                            rounded_values = [round(proportion * flow_dict[node_name]['sales_office']) for proportion in proportions]
                            difference = flow_dict[node_name]['sales_office'] - sum(rounded_values)
                            if difference != 0:
                                max_index = rounded_values.index(max(rounded_values))
                                rounded_values[max_index] += difference
                            df.loc[(df['node_name'] == node_name) & (df['year'] == year),
                                   ['m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm8', 'm9', 'm10', 'm11', 'm12']] = rounded_values
                        else:
                            # 供給量がゼロの場合、元データを保持（エラーチェック）
                            df.loc[(df['node_name'] == node_name) & (df['year'] == year),
                                   ['m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm8', 'm9', 'm10', 'm11', 'm12']] = [0] * 12
            else:
                # rule-1: ノードがflow_dictに存在しない場合、月次Sの値をすべて0に設定
                df.loc[index, ['m1', 'm2', 'm3', 'm4', 'm5', 'm6', 'm7', 'm8', 'm9', 'm10', 'm11', 'm12']] = 0
        # 3. 結果を"S_month_data_optimized.csv"として保存する
        df.to_csv(output_csv, index=False)
        print(f"Optimized data saved to {output_csv}")
    def eval_supply_chain_cost4opt(self, node_opt):
        # change from "out_opt" to "outbound"
        node = self.nodes_outbound[node_opt.name]
        # *********************
        # counting Purchase Order
        # *********************
        # psi_listのPOは、psi_list[w][3]の中のlot_idのロット数=リスト長
        # lot_counts is "out_opt"side
        node_opt.set_lot_counts()
        #@ STOP
        #node.set_lot_counts()
        # output:
        #    self.lot_counts_all = sum(self.lot_counts)
        # change lot_counts from "out_opt"side to "outbound"side
        node.lot_counts_all = node_opt.lot_counts_all
        # *********************
        # EvalPlanSIP()の中でnode instanceに以下をセットする
        # self.profit, self.revenue, self.profit_ratio
        # *********************
        # by weekの計画状態xxx[w]の変化を評価して、self.eval_xxxにセット
        total_revenue, total_profit = node.EvalPlanSIP_cost()
        #@241225 ADD
        node.total_revenue     = total_revenue
        node.total_profit      = total_profit
        node_opt.total_revenue = total_revenue
        node_opt.total_profit  = total_profit
        self.total_revenue += total_revenue
        self.total_profit  += total_profit
        #@241118 "eval_" is 1st def /  "eval_cs_" is 2nd def
        # print(
        #    "Eval node profit revenue profit_ratio",
        #    node.name,
        #    node.eval_profit,
        #    node.eval_revenue,
        #    node.eval_profit_ratio,
        # )
        for child in node.children:
            self.eval_supply_chain_cost4opt(child)
#@250218 STOP
#    def cash_flow_print(self):
#
#        #self.total_revenue, self.total_profit = eval_supply_chain_cost(self.root_node_outbound)
#
#        self.total_revenue, self.total_profit = eval_supply_chain_cash(self.root_node_outbound)
    def update_evaluation_results(self):
        # Evaluation on PSI
        self.total_revenue = 0
        self.total_profit  = 0
        self.profit_ratio  = 0
        # ***********************
        # This is a simple Evaluation process with "cost table"
        # ***********************
#@241120 STOP
#        self.eval_plan()
#
#    def eval_plan(self):
        # 在庫係数の計算
        # I_cost_coeff = I_total_qty_init / I_total_qty_planned
        #
        # 計画された在庫コストの算定
        # I_cost_planned = I_cost_init * I_cost_coeff
        # by node evaluation Revenue / Cost / Profit
        # "eval_xxx" = "lot_counts" X "cs_xxx" that is from cost_table
        # Inventory cost has 係数 = I_total on Demand/ I_total on Supply
        #self.total_revenue = 0
        #self.total_profit  = 0
        #eval_supply_chain_cost(self.root_node_outbound)
        #self.eval_supply_chain_cost(self.root_node_outbound)
        #eval_supply_chain_cost(self.root_node_inbound)
        #self.eval_supply_chain_cost(self.root_node_inbound)
        #@ CONTEXT グローバル変数 STOP
        ## サプライチェーン全体のコストを評価
        #eval_supply_chain_cost(self.root_node_outbound, self)
        #eval_supply_chain_cost(self.root_node_inbound, self)
        # サプライチェーンの評価を開始
        # tree.py に配置して、node に対して：
        # set_lot_counts() を呼び出し、ロット数を設定
        # EvalPlanSIP_cost() で revenue と profit を計算
        # 子ノード (children) に対して再帰的に eval_supply_chain_cost() をcall
        self.total_revenue, self.total_profit = eval_supply_chain_cost(self.root_node_outbound)
        ttl_revenue = self.total_revenue
        ttl_profit  = self.total_profit
        if ttl_revenue == 0:
            ttl_profit_ratio = 0
        else:
            ttl_profit_ratio = ttl_profit / ttl_revenue
        # 四捨五入して表示
        total_revenue = round(ttl_revenue)
        total_profit = round(ttl_profit)
        profit_ratio = round(ttl_profit_ratio*100, 1) # パーセント表示
        print("total_revenue", total_revenue)
        print("total_profit", total_profit)
        print("profit_ratio", profit_ratio)
#total_revenue 343587
#total_profit 32205
#profit_ratio 9.4
        self.total_revenue_entry.config(state='normal')
        self.total_revenue_entry.delete(0, tk.END)
        self.total_revenue_entry.insert(0, f"{total_revenue:,}")
        #self.total_revenue_entry.insert(0, str(kpi_results["total_revenue"]))
        self.total_revenue_entry.config(state='readonly')
        self.total_profit_entry.config(state='normal')
        self.total_profit_entry.delete(0, tk.END)
        self.total_profit_entry.insert(0, f"{total_profit:,}")
        #self.total_profit_entry.insert(0, str(kpi_results["total_profit"]))
        self.total_profit_entry.config(state='readonly')
        self.profit_ratio_entry.config(state='normal')
        self.profit_ratio_entry.delete(0, tk.END)
        self.profit_ratio_entry.insert(0, f"{profit_ratio}%")
        self.profit_ratio_entry.config(state='readonly')
        # 画面を再描画
        self.total_revenue_entry.update_idletasks()
        self.total_profit_entry.update_idletasks()
        self.profit_ratio_entry.update_idletasks()
    def update_evaluation_results4multi_product(self):
        print("Evaluation started")
        #@250730 ADD Focus on Product Selected
        # root_node is "supply_point"
        self.root_node_outbound_byprod = self.prod_tree_dict_OT[self.product_selected]
        self.root_node_inbound_byprod  = self.prod_tree_dict_IN[self.product_selected]
        # Evaluation on PSI
        self.total_revenue = 0
        self.total_profit  = 0
        self.profit_ratio  = 0
        # ***********************
        # This is a simple Evaluation process with "cost table"
        # ***********************
#@241120 STOP
#        self.eval_plan()
#
#    def eval_plan(self):
        # 在庫係数の計算
        # I_cost_coeff = I_total_qty_init / I_total_qty_planned
        #
        # 計画された在庫コストの算定
        # I_cost_planned = I_cost_init * I_cost_coeff
        # by node evaluation Revenue / Cost / Profit
        # "eval_xxx" = "lot_counts" X "cs_xxx" that is from cost_table
        # Inventory cost has 係数 = I_total on Demand/ I_total on Supply
        #self.total_revenue = 0
        #self.total_profit  = 0
        #eval_supply_chain_cost(self.root_node_outbound)
        #self.eval_supply_chain_cost(self.root_node_outbound)
        #eval_supply_chain_cost(self.root_node_inbound)
        #self.eval_supply_chain_cost(self.root_node_inbound)
        #@ CONTEXT グローバル変数 STOP
        ## サプライチェーン全体のコストを評価
        #eval_supply_chain_cost(self.root_node_outbound, self)
        #eval_supply_chain_cost(self.root_node_inbound, self)
        # サプライチェーンの評価を開始
        # tree.py に配置して、node に対して：
        # set_lot_counts() を呼び出し、ロット数を設定
        # EvalPlanSIP_cost() で revenue と profit を計算
        # 子ノード (children) に対して再帰的に eval_supply_chain_cost() をcall
        self.total_revenue, self.total_profit = eval_supply_chain_cost(self.root_node_outbound_byprod)
        ttl_revenue = self.total_revenue
        ttl_profit  = self.total_profit
        if ttl_revenue == 0:
            ttl_profit_ratio = 0
        else:
            ttl_profit_ratio = ttl_profit / ttl_revenue
        # 四捨五入して表示
        total_revenue = round(ttl_revenue)
        total_profit = round(ttl_profit)
        profit_ratio = round(ttl_profit_ratio*100, 1) # パーセント表示
        print("total_revenue", total_revenue)
        print("total_profit", total_profit)
        print("profit_ratio", profit_ratio)
#total_revenue 343587
#total_profit 32205
#profit_ratio 9.4
        self.total_revenue_entry.config(state='normal')
        self.total_revenue_entry.delete(0, tk.END)
        self.total_revenue_entry.insert(0, f"{total_revenue:,}")
        #self.total_revenue_entry.insert(0, str(kpi_results["total_revenue"]))
        self.total_revenue_entry.config(state='readonly')
        self.total_profit_entry.config(state='normal')
        self.total_profit_entry.delete(0, tk.END)
        self.total_profit_entry.insert(0, f"{total_profit:,}")
        #self.total_profit_entry.insert(0, str(kpi_results["total_profit"]))
        self.total_profit_entry.config(state='readonly')
        self.profit_ratio_entry.config(state='normal')
        self.profit_ratio_entry.delete(0, tk.END)
        self.profit_ratio_entry.insert(0, f"{profit_ratio}%")
        self.profit_ratio_entry.config(state='readonly')
        # 画面を再描画
        self.total_revenue_entry.update_idletasks()
        self.total_profit_entry.update_idletasks()
        self.profit_ratio_entry.update_idletasks()
    def update_evaluation_results4optimize(self):
        # Evaluation on PSI
        self.total_revenue = 0
        self.total_profit  = 0
        self.profit_ratio  = 0
        # ***********************
        # This is a simple Evaluation process with "cost table"
        # ***********************
        # 在庫係数の計算
        # I_cost_coeff = I_total_qty_init / I_total_qty_planned
        #
        # 計画された在庫コストの算定
        # I_cost_planned = I_cost_init * I_cost_coeff
        # by node evaluation Revenue / Cost / Profit
        # "eval_xxx" = "lot_counts" X "cs_xxx" that is from cost_table
        # Inventory cost has 係数 = I_total on Demand/ I_total on Supply
        #self.total_revenue = 0
        #self.total_profit  = 0
        #@241225 memo "root_node_out_opt"のtreeにはcs_xxxxがセットされていない
        # cs_xxxxのあるnode = self.nodes_outbound[node_opt.name]に変換して参照
        #@241225 be checkek
        # ***************************
        # change ROOT HANDLE
        # ***************************
        self.eval_supply_chain_cost4opt(self.root_node_out_opt)
        print("self.root_node_out_opt.name", self.root_node_out_opt.name)
        #self.eval_supply_chain_cost(self.root_node_outbound)
        #self.eval_supply_chain_cost(self.root_node_inbound)
        ttl_revenue = self.total_revenue
        ttl_profit  = self.total_profit
        print("def update_evaluation_results4optimize")
        print("self.total_revenue", self.total_revenue)
        print("self.total_profit" , self.total_profit)
        if ttl_revenue == 0:
            ttl_profit_ratio = 0
        else:
            ttl_profit_ratio = ttl_profit / ttl_revenue
        # 四捨五入して表示
        total_revenue = round(ttl_revenue)
        total_profit = round(ttl_profit)
        profit_ratio = round(ttl_profit_ratio*100, 1) # パーセント表示
        print("total_revenue", total_revenue)
        print("total_profit", total_profit)
        print("profit_ratio", profit_ratio)
#total_revenue 343587
#total_profit 32205
#profit_ratio 9.4
        self.total_revenue_entry.config(state='normal')
        self.total_revenue_entry.delete(0, tk.END)
        self.total_revenue_entry.insert(0, f"{total_revenue:,}")
        #self.total_revenue_entry.insert(0, str(kpi_results["total_revenue"]))
        self.total_revenue_entry.config(state='readonly')
        self.total_profit_entry.config(state='normal')
        self.total_profit_entry.delete(0, tk.END)
        self.total_profit_entry.insert(0, f"{total_profit:,}")
        #self.total_profit_entry.insert(0, str(kpi_results["total_profit"]))
        self.total_profit_entry.config(state='readonly')
        self.profit_ratio_entry.config(state='normal')
        self.profit_ratio_entry.delete(0, tk.END)
        self.profit_ratio_entry.insert(0, f"{profit_ratio}%")
        self.profit_ratio_entry.config(state='readonly')
        # 画面を再描画
        self.total_revenue_entry.update_idletasks()
        self.total_profit_entry.update_idletasks()
        self.profit_ratio_entry.update_idletasks()
# ******************************************
# visualize graph
# ******************************************
    def view_nx_matlib_stop_draw(self):
        G = nx.DiGraph()
        Gdm_structure = nx.DiGraph()
        Gsp = nx.DiGraph()
        print(f"view_nx_matlib before show_network_E2E_matplotlib self.decouple_node_selected: {self.decouple_node_selected}")
        pos_E2E, G, Gdm_structure, Gsp = self.show_network_E2E_matplotlib(
            self.root_node_outbound, self.nodes_outbound,
            self.root_node_inbound, self.nodes_inbound,
            G, Gdm_structure, Gsp
        )
        self.pos_E2E = pos_E2E
        print(f"view_nx_matlib after show_network_E2E_matplotlib self.decouple_node_selected: {self.decouple_node_selected}")
        self.G = G
        self.Gdm_structure = Gdm_structure
        self.Gsp = Gsp
        #@250106 STOP draw
        #self.draw_network(self.G, self.Gdm_structure, self.Gsp, self.pos_E2E)
    def initialize_graphs(self):
        self.G = nx.DiGraph()
        self.Gdm_structure = nx.DiGraph()
        self.Gsp = nx.DiGraph()
    # ***************************
    # make network with NetworkX
    # ***************************
    def show_network_E2E_matplotlib_WO_capa(self,
            root_node_outbound, nodes_outbound,
            root_node_inbound, nodes_inbound,
            G, Gdm, Gsp):
        # Original code's logic to process and set up the network
        root_node_name_out = root_node_outbound.name
        root_node_name_in  = root_node_inbound.name
        #@STOP
        #total_demand =0
        #total_demand = set_leaf_demand(root_node_outbound, total_demand)
        #total_demand = self.set_leaf_demand(root_node_outbound, total_demand)
        total_demand =100
        print("average_total_demand", total_demand)
        print("root_node_outbound.nx_demand", root_node_outbound.nx_demand)
        root_node_outbound.nx_demand = total_demand
        root_node_inbound.nx_demand = total_demand
        G_add_nodes_from_tree(root_node_outbound, G)
        #self.G_add_nodes_from_tree(root_node_outbound, G)
        G_add_nodes_from_tree_skip_root(root_node_inbound, root_node_name_in, G)
        #self.G_add_nodes_from_tree_skip_root(root_node_inbound, root_node_name_in, G)
        G.add_node("sales_office", demand=total_demand)
        G.add_node(root_node_outbound.name, demand=0)
        G.add_node("procurement_office", demand=(-1 * total_demand))
        G_add_edge_from_tree(root_node_outbound, G)
        #self.G_add_edge_from_tree(root_node_outbound, G)
        supplyers_capacity = root_node_inbound.nx_demand * 2
        G_add_edge_from_inbound_tree(root_node_inbound, supplyers_capacity, G)
        #self.G_add_edge_from_inbound_tree(root_node_inbound, supplyers_capacity, G)
        G_add_nodes_from_tree(root_node_outbound, Gdm)
        #self.G_add_nodes_from_tree(root_node_outbound, Gdm)
        Gdm.add_node(root_node_outbound.name, demand = (-1 * total_demand))
        Gdm.add_node("sales_office", demand = total_demand)
        Gdm_add_edge_sc2nx_outbound(root_node_outbound, Gdm)
        #self.Gdm_add_edge_sc2nx_outbound(root_node_outbound, Gdm)
        G_add_nodes_from_tree(root_node_inbound, Gsp)
        #self.G_add_nodes_from_tree(root_node_inbound, Gsp)
        Gsp.add_node("procurement_office", demand = (-1 * total_demand))
        Gsp.add_node(root_node_inbound.name, demand = total_demand)
        Gsp_add_edge_sc2nx_inbound(root_node_inbound, Gsp)
        #self.Gsp_add_edge_sc2nx_inbound(root_node_inbound, Gsp)
        pos_E2E = make_E2E_positions(
            root_node_outbound=self.root_node_outbound,
            root_node_inbound=self.root_node_inbound,
            dx=1.0, dy=1.0, office_margin=1.0
        )
        #@250913 STOP
        #pos_E2E = make_E2E_positions(root_node_outbound, root_node_inbound)
        ##pos_E2E = self.make_E2E_positions(root_node_outbound, root_node_inbound)
        #@250913 STOP
        #pos_E2E = tune_hammock(pos_E2E, nodes_outbound, nodes_inbound)
        ##pos_E2E = self.tune_hammock(pos_E2E, nodes_outbound, nodes_inbound)
        return pos_E2E, G, Gdm, Gsp
    def show_network_E2E_matplotlib(self,
            root_node_outbound, nodes_outbound,
            root_node_inbound, nodes_inbound,
            G, Gdm, Gsp):
        # Original code's logic to process and set up the network
        root_node_name_out = root_node_outbound.name
        root_node_name_in  = root_node_inbound.name
        total_demand =0
        total_demand = set_leaf_demand(root_node_outbound, total_demand)
        #total_demand = self.set_leaf_demand(root_node_outbound, total_demand)
        print("average_total_demand", total_demand)
        print("root_node_outbound.nx_demand", root_node_outbound.nx_demand)
        root_node_outbound.nx_demand = total_demand
        root_node_inbound.nx_demand = total_demand
        G_add_nodes_from_tree(root_node_outbound, G)
        #self.G_add_nodes_from_tree(root_node_outbound, G)
        G_add_nodes_from_tree_skip_root(root_node_inbound, root_node_name_in, G)
        #self.G_add_nodes_from_tree_skip_root(root_node_inbound, root_node_name_in, G)
        G.add_node("sales_office", demand=total_demand)
        G.add_node(root_node_outbound.name, demand=0)
        G.add_node("procurement_office", demand=(-1 * total_demand))
        G_add_edge_from_tree(root_node_outbound, G)
        #self.G_add_edge_from_tree(root_node_outbound, G)
        supplyers_capacity = root_node_inbound.nx_demand * 2
        G_add_edge_from_inbound_tree(root_node_inbound, supplyers_capacity, G)
        #self.G_add_edge_from_inbound_tree(root_node_inbound, supplyers_capacity, G)
        G_add_nodes_from_tree(root_node_outbound, Gdm)
        #self.G_add_nodes_from_tree(root_node_outbound, Gdm)
        Gdm.add_node(root_node_outbound.name, demand = (-1 * total_demand))
        Gdm.add_node("sales_office", demand = total_demand)
        Gdm_add_edge_sc2nx_outbound(root_node_outbound, Gdm)
        #self.Gdm_add_edge_sc2nx_outbound(root_node_outbound, Gdm)
        G_add_nodes_from_tree(root_node_inbound, Gsp)
        #self.G_add_nodes_from_tree(root_node_inbound, Gsp)
        Gsp.add_node("procurement_office", demand = (-1 * total_demand))
        Gsp.add_node(root_node_inbound.name, demand = total_demand)
        Gsp_add_edge_sc2nx_inbound(root_node_inbound, Gsp)
        #self.Gsp_add_edge_sc2nx_inbound(root_node_inbound, Gsp)
        pos_E2E = make_E2E_positions(
            root_node_outbound=self.root_node_outbound,
            root_node_inbound=self.root_node_inbound,
            dx=1.0, dy=1.0, office_margin=1.0
        )
    # **********************************************
    #@250913 ADD for DEBUG
    # **********************************************
    #    in_names  = self._names_in_tree_safe(self.root_node_inbound)
    #    out_names = self._names_in_tree_safe(self.root_node_outbound)
    #    self._print_layout_ranges("IN ", in_names,  pos_E2E)
    #    self._print_layout_ranges("OUT", out_names, pos_E2E)
        #@250913 STOP
        #pos_E2E = make_E2E_positions(root_node_outbound, root_node_inbound)
        ##pos_E2E = self.make_E2E_positions(root_node_outbound, root_node_inbound)
        #@250913 STOP
        #pos_E2E = tune_hammock(pos_E2E, nodes_outbound, nodes_inbound)
        ##pos_E2E = self.tune_hammock(pos_E2E, nodes_outbound, nodes_inbound)
        return pos_E2E, G, Gdm, Gsp
    # **** helper ****
    # **********************************************
    #@250913 ADD for DEBUG
    # **********************************************
    def _names_in_tree_safe(self, root):
        if not root:
            return set()
        st = [root]; seen = set(); names = set()
        while st:
            p = st.pop()
            if id(p) in seen:
                continue
            seen.add(id(p))
            nm = getattr(p, "name", "")
            if nm:
                names.add(nm)
            for c in getattr(p, "children", []) or []:
                st.append(c)
        return names
    def _print_layout_ranges(self, tag, names, pos):
        xs = [pos[n][0] for n in names if n in pos]
        if xs:
            print(f"[LAYOUT] {tag}: minX={min(xs):.2f}, maxX={max(xs):.2f}, n={len(xs)}")
    def show_network_E2E_matplotlib_with_self(self):
        root_node_outbound = self.root_node_outbound
        nodes_outbound = self.nodes_outbound
        root_node_inbound = self.root_node_inbound
        nodes_inbound = self.nodes_inbound
        return self.show_network_E2E_matplotlib(
            root_node_outbound, nodes_outbound,
            root_node_inbound, nodes_inbound,
            self.G, self.Gdm_structure, self.Gsp
        )
# ******************************************
# optimize network graph
# ******************************************
    def optimize(self, G_opt):
        self.reset_optimization_params(G_opt)
        self.set_optimization_params(G_opt)
        self.run_optimization(G_opt)
        print("run_optimization self.flowDict_opt", self.flowDict_opt)
        self.reset_optimized_path(G_opt)
        self.add_optimized_path(G_opt, self.flowDict_opt)
        print("Optimized Path:", self.flowDict_opt)
        print("Optimized Cost:", self.flowCost_opt)
    def load_data_files4opt(self):
    #@RENAME
    # nodes_outbound     : nodes_out_opt
    # root_node_outbound : root_node_out_opt
        # setting directory from "plan"
        directory = self.directory
        #@ STOP
        #directory = filedialog.askdirectory(title="Select Data Directory")
        if directory:
            # ***********************
            # Lot sizeを取得して変換
            # ***********************
            #try:
            #    self.lot_size = int(self.lot_size_entry.get())
            #except ValueError:
            #    print("Invalid lot size input. Using default value.")
            # Lot size, Plan Year Start, and Plan Rangeを取得して変換
            try:
                self.lot_size = int(self.lot_size_entry.get())
                self.plan_year_st = int(self.plan_year_entry.get())
                self.plan_range = int(self.plan_range_entry.get())
            except ValueError:
                print("Invalid input for lot size, plan year start, or plan range. Using default values.")
            self.outbound_data = []
            self.inbound_data = []
            print("os.listdir(directory)",os.listdir(directory))
            data_file_list = os.listdir(directory)
            # save directory
            self.directory = directory
            # ************************
            # read "profile_tree_outbound.csv"
            # build tree_outbound
            # ************************
            if "profile_tree_outbound.csv" in data_file_list:
                filename = "profile_tree_outbound.csv"
                file_path = os.path.join(directory, filename)
                #filepath = os.path.join(directory, filename)
                #load_outbound(outbound_tree_file)
                # ***************************
                # set file name for "profile tree"
                # ***************************
                #outbound_tree_file = "profile_tree_outbound.csv"
                #inbound_tree_file = "profile_tree_inbound.csv"
                # ***************************
                # create supply chain tree for "out"bound + optimization
                # ***************************
                # because of the python interpreter performance point of view,
                # this "create tree" code be placed in here, main process
            #@240830
            # "nodes_xxxx" is dictionary to get "node pointer" from "node name"
                nodes_out_opt = {}
                nodes_out_opt, root_node_name_out = create_tree_set_attribute(file_path)
                print("root_node_name_out",root_node_name_out)
                root_node_out_opt = nodes_out_opt[root_node_name_out]
                def make_leaf_nodes(node, list):
                    if node.children == []: # leaf_nodeの場合
                        list.append(node.name)
                    else:
                        pass
                    for child in node.children:
                        make_leaf_nodes(child, list)
                    return list
                leaf_nodes_opt = []
                leaf_nodes_opt = make_leaf_nodes(root_node_out_opt, leaf_nodes_opt)
                # making balance for nodes
                # ********************************
                # set outbound tree handle
                # ********************************
                self.nodes_out_opt = nodes_out_opt
                self.root_node_out_opt = root_node_out_opt
                print("leaf_nodes_opt", leaf_nodes_opt)
                self.leaf_nodes_opt = leaf_nodes_opt
                # ********************************
                # tree wideth/depth count and adjust
                # ********************************
                set_positions(root_node_out_opt)
                # root_node_out_opt = nodes_out_opt['JPN']      # for test, direct define
                # root_node_out_opt = nodes_out_opt['JPN_OUT']  # for test, direct define
                # setting parent on its child
                set_parent_all(root_node_out_opt)
                print_parent_all(root_node_out_opt)
            else:
                print("error: profile_tree_outbound.csv is missed")
                pass
            # ************************
            # read "profile_tree_inbound.csv"
            # build tree_inbound
            # ************************
            if "profile_tree_inbound.csv" in data_file_list:
                filename = "profile_tree_inbound.csv"
                file_path = os.path.join(directory, filename)
                # ***************************
                # create supply chain tree for "in"bound
                # ***************************
                nodes_inbound = {}
                nodes_inbound, root_node_name_in = create_tree_set_attribute(file_path)
                root_node_inbound = nodes_inbound[root_node_name_in]
                # ********************************
                # set inbound tree handle
                # ********************************
                self.nodes_inbound = nodes_inbound
                self.root_node_inbound = root_node_inbound
                # ********************************
                # tree wideth/depth count and adjust
                # ********************************
                set_positions(root_node_inbound)
                # setting parent on its child
                set_parent_all(root_node_inbound)
                print_parent_all(root_node_inbound)
            else:
                print("error: profile_tree_inbound.csv is missed")
                pass
            # ************************
            # read "node_cost_table_outbound.csv"
            # read_set_cost
            # ************************
            if "node_cost_table_outbound.csv" in data_file_list:
                filename = "node_cost_table_outbound.csv"
                file_path = os.path.join(directory, filename)
                read_set_cost(file_path, nodes_out_opt)
            else:
                print("error: node_cost_table_outbound.csv is missed")
                pass
            # ************************
            # read "node_cost_table_inbound.csv"
            # read_set_cost
            # ************************
            if "node_cost_table_inbound.csv" in data_file_list:
                filename = "node_cost_table_inbound.csv"
                file_path = os.path.join(directory, filename)
                read_set_cost(file_path, nodes_inbound)
            else:
                print("error: node_cost_table_inbound.csv is missed")
                pass
            # ***************************
            # make price chain table
            # ***************************
            # すべてのパスを見つける
            paths = find_paths(root_node_out_opt)
            # 各リストをタプルに変換してsetに変換し、重複を排除
            unique_paths = list(set(tuple(x) for x in paths))
            # タプルをリストに戻す
            unique_paths = [list(x) for x in unique_paths]
            print("")
            print("")
            for path in unique_paths:
                print(path)
            sorted_paths = sorted(paths, key=len)
            print("")
            print("")
            for path in sorted_paths:
                print(path)
            #@241224 MARK4OPT_SAVE
            # ************************
            # read "S_month_optimized.csv"
            # trans_month2week2lot_id_list
            # ************************
            if "S_month_optimized.csv" in data_file_list:
            #if "S_month_data.csv" in data_file_list:
                filename = "S_month_optimized.csv"
                in_file_path = os.path.join(directory, filename)
                print("self.lot_size",self.lot_size)
                # 使用例
                #in_file = "S_month_data.csv"
                df_weekly, plan_range, plan_year_st = process_monthly_demand(in_file_path, self.lot_size)
                #df_weekly, plan_range, plan_year_st = trans_month2week2lot_id_list(in_file_path, self.lot_size)
                print("plan_year_st",plan_year_st)
                print("plan_range",plan_range)
                # update plan_year_st plan_range
                self.plan_year_st = plan_year_st  # S_monthで更新
                self.plan_range   = plan_range    # S_monthで更新
                # Update the GUI fields
                self.plan_year_entry.delete(0, tk.END)
                self.plan_year_entry.insert(0, str(self.plan_year_st))
                self.plan_range_entry.delete(0, tk.END)
                self.plan_range_entry.insert(0, str(self.plan_range))
                out_file = "S_iso_week_data_opt.csv"
                out_file_path = os.path.join(directory, out_file)
                df_weekly.to_csv(out_file_path, index=False)
                df_capa_year = make_capa_year_month(in_file_path)
                #@241112 test
                year_st = df_capa_year["year"].min()
                year_end = df_capa_year["year"].max()
                print("year_st, year_end",year_st, year_end)
            else:
                print("error: S_month_optimized.csv is missed")
                pass
            #@241124 ココは、初期のEVAL処理用パラメータ。現在は使用していない
            # planning parameterをNode method(=self.)でセットする。
            # plan_range, lot_counts, cash_in, cash_out用のparameterをセット
            root_node_out_opt.set_plan_range_lot_counts(plan_range, plan_year_st)
            root_node_inbound.set_plan_range_lot_counts(plan_range, plan_year_st)
            # ***************************
            # an image of data
            #
            # for node_val in node_yyyyww_value:
            #   #print( node_val )
            #
            ##['SHA_N', 22.580645161290324, 22.580645161290324, 22.580645161290324, 22.5    80645161290324, 26.22914349276974, 28.96551724137931, 28.96551724137931, 28.    96551724137931, 31.067853170189103, 33.87096774193549, 33.87096774193549, 33    .87096774193549, 33.87096774193549, 30.33333333333333, 30.33333333333333, 30    .33333333333333, 30.33333333333333, 31.247311827956988, 31.612903225806452,
            # node_yyyyww_key [['CAN', 'CAN202401', 'CAN202402', 'CAN202403', 'CAN20240    4', 'CAN202405', 'CAN202406', 'CAN202407', 'CAN202408', 'CAN202409', 'CAN202    410', 'CAN202411', 'CAN202412', 'CAN202413', 'CAN202414', 'CAN202415', 'CAN2    02416', 'CAN202417', 'CAN202418', 'CAN202419',
            # ********************************
            # make_node_psi_dict
            # ********************************
            # 1. treeを生成して、nodes[node_name]辞書で、各nodeのinstanceを操作        する
            # 2. 週次S yyyywwの値valueを月次Sから変換、
            #    週次のlotの数Slotとlot_keyを生成、
            # 3. ロット単位=lot_idとするリストSlot_id_listを生成しながらpsi_list        生成
            # 4. node_psi_dict=[node1: psi_list1,,,]を生成、treeのnode.psi4deman        dに接続する
            S_week = []
            # *************************************************
            # node_psi辞書を初期セットする
            # initialise node_psi_dict
            # *************************************************
            node_psi_dict = {}  # 変数 node_psi辞書
            # ***************************
            # outbound psi_dic
            # ***************************
            node_psi_dict_Ot4Dm = {}  # node_psi辞書Outbound4Demand plan
            node_psi_dict_Ot4Sp = {}  # node_psi辞書Outbound4Supply plan
            # coupling psi
            node_psi_dict_Ot4Cl = {}  # node_psi辞書Outbound4Couple plan
            # accume psi
            node_psi_dict_Ot4Ac = {}  # node_psi辞書Outbound4Accume plan
            # ***************************
            # inbound psi_dic
            # ***************************
            self.node_psi_dict_In4Dm = {}  # node_psi辞書Inbound4demand plan
            self.node_psi_dict_In4Sp = {}  # node_psi辞書Inbound4supply plan
            # coupling psi
            node_psi_dict_In4Cl = {}  # node_psi辞書Inbound4couple plan
            # accume psi
            node_psi_dict_In4Ac = {}  # node_psi辞書Inbound4accume plan
            # ***************************
            # rootからtree nodeをpreorder順に検索 node_psi辞書に空リストをセット        する
            # psi_list = [[[] for j in range(4)] for w in range(53 * plan_range)        ]
            # ***************************
            node_psi_dict_Ot4Dm = make_psi_space_dict(
        root_node_out_opt, node_psi_dict_Ot4Dm, plan_range
            )
            node_psi_dict_Ot4Sp = make_psi_space_dict(
                root_node_out_opt, node_psi_dict_Ot4Sp, plan_range
            )
            node_psi_dict_Ot4Cl = make_psi_space_dict(
                root_node_out_opt, node_psi_dict_Ot4Cl, plan_range
            )
            node_psi_dict_Ot4Ac = make_psi_space_dict(
                root_node_out_opt, node_psi_dict_Ot4Ac, plan_range
            )
            self.node_psi_dict_In4Dm = make_psi_space_dict(
                root_node_inbound, self.node_psi_dict_In4Dm, plan_range
            )
            self.node_psi_dict_In4Sp = make_psi_space_dict(
                root_node_inbound, self.node_psi_dict_In4Sp, plan_range
            )
            node_psi_dict_In4Cl = make_psi_space_dict(
                root_node_inbound, node_psi_dict_In4Cl, plan_range
            )
            node_psi_dict_In4Ac = make_psi_space_dict(
                root_node_inbound, node_psi_dict_In4Ac, plan_range
            )
            # ***********************************
            # set_dict2tree
            # ***********************************
            # rootからtreeをpreorder順に検索
            # node_psi辞書内のpsi_list pointerをNodeのnode objectにsetattr()で接        続
            set_dict2tree_psi(root_node_out_opt, "psi4demand", node_psi_dict_Ot4Dm)
            set_dict2tree_psi(root_node_out_opt, "psi4supply", node_psi_dict_Ot4Sp)
            set_dict2tree_psi(root_node_out_opt, "psi4couple", node_psi_dict_Ot4Cl)
            set_dict2tree_psi(root_node_out_opt, "psi4accume", node_psi_dict_Ot4Ac)
            set_dict2tree_psi(root_node_inbound, "psi4demand", self.node_psi_dict_In4Dm)
            set_dict2tree_psi(root_node_inbound, "psi4supply", self.node_psi_dict_In4Sp)
            set_dict2tree_psi(root_node_inbound, "psi4couple", node_psi_dict_In4Cl)
            set_dict2tree_psi(root_node_inbound, "psi4accume", node_psi_dict_In4Ac)
            #@241224 MARK4OPT_SAVE
            #
            # ココで、root_node_out_optのPSIがsetされ、planning engineに渡る
            #
            # ************************************
            # setting S on PSI
            # ************************************
            # Weekly Lot: CPU:Common Planning UnitをPSI spaceにセットする
            set_df_Slots2psi4demand(root_node_out_opt, df_weekly)
            #@241124 adding for "global market potential"
            # ************************************
            # counting all lots
            # ************************************
            #print("check lots on psi4demand[w][0] ")
            ## count lot on all nodes  from  node.psi4demand[w][0]
            #lot_num = count_lot_all_nodes(root_node_out_opt)
            # year_st
            # year_end
            # **************************************
            # count_lots_on_S_psi4demand
            # **************************************
            # psi4demand[w][0]の配置されたSのlots数を年別にcountしてlist化
            def count_lots_on_S_psi4demand(node, S_list):
                if node.children == []:
                    for w_psi in node.psi4demand:
                        S_list.append(w_psi[0])
                for child in node.children:
                    count_lots_on_S_psi4demand(child, S_list)
                return S_list
            S_list = []
            year_lots_list4S = []
            S_list = count_lots_on_S_psi4demand(root_node_out_opt, S_list)
            plan_year_st = year_st
            #for yyyy in range(plan_year_st, plan_year_st + plan_range + 1):
            for yyyy in range(int(plan_year_st), int(plan_year_st + plan_range + 1)):
                year_lots4S = count_lots_yyyy(S_list, str(yyyy))
                year_lots_list4S.append(year_lots4S)
            #@241205 STOP NOT change "global_market_potential" at 2nd loading
            ## 値をインスタンス変数に保存
            #self.global_market_potential = year_lots_list4S[1]
            print("NOT change #market_potential# at 2nd loading")
            print("self.market_potential", self.market_potential)
        for filename in os.listdir(directory):
            if filename.endswith(".csv"):
                filepath = os.path.join(directory, filename)
                print(f"Loading file: {filename}")
                if "outbound" in filename.lower():
                    self.outbound_data.append(pd.read_csv(filepath))
                elif "inbound" in filename.lower():
                    self.inbound_data.append(pd.read_csv(filepath))
        print("Outbound files loaded.")
        print("Inbound files loaded.")
        #@ STOP optimize processでは初期loadのcost_stracture設定で完了している
        #base_leaf = self.nodes_outbound[self.base_leaf_name]
        #
        #root_price = set_price_leaf2root(base_leaf,self.root_node_out_opt,100)
        #print("root_price", root_price)
        #set_value_chain_outbound(root_price, self.root_node_out_opt)
        self.view_nx_matlib()
        self.root.after(1000, self.show_psi_graph)
        #@241222@ STOP RUN
        # パラメータの初期化と更新を呼び出し
        self.initialize_parameters()
        def count_lots_on_S_psi4demand(node, S_list):
            # leaf_node末端市場の判定
            if node.children == []:  # 子nodeがないleaf nodeの場合
                # psi_listからS_listを生成する
                for w_psi in node.psi4demand:  # weeklyのSをS_listに集計
                    S_list.append(w_psi[0])
            else:
                pass
            for child in node.children:
                count_lots_on_S_psi4demand(child, S_list)
            return S_list
        S_list = []
        year_lots_list4S = []
        # treeを生成した直後なので、root_node_out_optが使える
        S_list = count_lots_on_S_psi4demand(root_node_out_opt, S_list)
            # 開始年を取得する
        plan_year_st = year_st  # 開始年のセット in main()要修正
        #for yyyy in range(plan_year_st, plan_year_st + plan_range + 1):
        for yyyy in range(int(plan_year_st), int(plan_year_st + plan_range + 1)):
            year_lots4S = count_lots_yyyy(S_list, str(yyyy))
            year_lots_list4S.append(year_lots4S)
            #        # 結果を出力
            #       #print(yyyy, " year carrying lots:", year_lots)
            #
            #    # 結果を出力
            #   #print(" year_lots_list:", year_lots_list)
            # an image of sample data
            #
            # 2023  year carrying lots: 0
            # 2024  year carrying lots: 2919
            # 2025  year carrying lots: 2914
            # 2026  year carrying lots: 2986
            # 2027  year carrying lots: 2942
            # 2028  year carrying lots: 2913
            # 2029  year carrying lots: 0
            #
            # year_lots_list4S: [0, 2919, 2914, 2986, 2942, 2913, 0]
            #@241124 CHECK
        #@241205 STOP NOT change "market_potential" at 2nd loading
        ## 値をインスタンス変数に保存
        #self.market_potential = year_lots_list4S[1]
        #print("year_lots_list4S", year_lots_list4S)
        #self.global_market_potential = year_lots_list4S[1]
        #print("self.global_market_potential", self.global_market_potential)
        for filename in os.listdir(directory):
            if filename.endswith(".csv"):
                filepath = os.path.join(directory, filename)
                print(f"Loading file: {filename}")
                if "outbound" in filename.lower():
                    self.outbound_data.append(pd.read_csv(filepath))
                elif "inbound" in filename.lower():
                    self.inbound_data.append(pd.read_csv(filepath))
        print("Outbound files loaded.")
        print("Inbound files loaded.")
    # *************************
    # PSI graph
    # *************************
    def show_psi_by_product(self, bound, layer, product_name):
        self._ensure_plan_window()
        self._ensure_psi_area()      # ← これを追加
        print("making by product PSI graph data...")
        week_start = 1
        week_end = self.plan_range * 53
        psi_data = []
        if bound not in ["outbound", "inbound"]:
            print("error: outbound or inbound must be defined for PSI layer")
            return
        if layer not in ["demand", "supply"]:
            print("error: demand or supply must be defined for PSI layer")
            return
        # prod ツリー辞書の存在ガード
        if not hasattr(self, "prod_tree_dict_OT"):
            print("[WARN] prod_tree_dict_OT is missing; abort PSI drawing.")
            return
        if not hasattr(self, "prod_tree_dict_IN"):
            print("[INFO] prod_tree_dict_IN missing -> fallback to OT.")
            self.prod_tree_dict_IN = self.prod_tree_dict_OT
        # .get() で KeyError を回避しつつ、INはOTにフォールバック
        prod_root_node_OT = self.prod_tree_dict_OT.get(product_name)
        prod_root_node_IN = self.prod_tree_dict_IN.get(product_name, prod_root_node_OT)
        if prod_root_node_OT is None:
            print(f"[WARN] No product root found for '{product_name}'. Abort PSI drawing.")
            return
        def traverse_nodes(node):
            if node is None:
                return
            for child in getattr(node, "children", []) or []:
                traverse_nodes(child)
            collect_psi_data(node, layer, week_start, week_end, psi_data)
        if bound == "outbound":
            traverse_nodes(prod_root_node_OT)
        else:
            traverse_nodes(prod_root_node_IN)
        # データが空なら描画スキップ（安全）
        if not psi_data:
            print(f"[INFO] show_psi_by_product: psi_data empty for product={product_name}, bound={bound}, layer={layer}")
            return
        cal = Calendar445(
            start_year=self.plan_year_st,
            plan_range=self.plan_range,
            use_13_months=True,
            holiday_country="JP"
        )
        max_year = self.plan_year_st + self.plan_range - 1
        week_to_yymm_all = cal.get_week_labels()
        week_to_yymm = {w: y for w, y in week_to_yymm_all.items() if int(str(y)[:2]) <= max_year % 100}
        month_end_weeks = [w for w in cal.get_month_end_weeks() if w in week_to_yymm]
        holiday_weeks = [w for w in cal.get_holiday_weeks() if w in week_to_yymm]
        print("week_to_yymm", week_to_yymm)
        week_span = week_end - week_start + 1
        fig_width = max(6, min(week_span * 0.08, 9))
        fig, axs = plt.subplots(len(psi_data), 1, figsize=(fig_width, len(psi_data) * 1.5))
        if len(psi_data) == 1:
            axs = [axs]
        # PlanNode辞書（overlayで使う場合のみ参照）
        nodes_prod_out = getattr(self, "nodes_prod_outbound", {})
        nodes_prod_in  = getattr(self, "nodes_prod_inbound",  {})
        for ax, (node_name, revenue, profit, profit_ratio, line_plot_data_2I, bar_plot_data_3P, bar_plot_data_0S) in zip(axs, psi_data):
            ax2 = ax.twinx()
            ax.bar(line_plot_data_2I.index, line_plot_data_2I.values, color='r', alpha=0.6)
            ax.bar(bar_plot_data_3P.index, bar_plot_data_3P.values, color='g', alpha=0.6)
            ax2.plot(bar_plot_data_0S.index, bar_plot_data_0S.values, color='b')
            # 価格オーバーレイ（PlanNodeの世界を使う前提）
            node_for_overlay = None
            if bound == "outbound":
                if isinstance(nodes_prod_out, dict):
                    node_for_overlay = nodes_prod_out.get(node_name)
            else:
                if isinstance(nodes_prod_in, dict):
                    node_for_overlay = nodes_prod_in.get(node_name)
            if node_for_overlay is not None:
                # product_name を self.product_selected ではなく、引数の product_name を渡す方が自然
                self.overlay_price_on_axes(ax, node_for_overlay, product_name)
            ax.set_ylabel('I&P Lots', fontsize=10)
            ax2.set_ylabel('S Lots', fontsize=10)
            ax.set_title(f'Node: {node_name} | REVENUE: {revenue:,} | PROFIT: {profit:,} | PROFIT_RATIO: {profit_ratio}%', fontsize=10)
            ax.set_xlim(week_start, week_end)
            ax.set_xticks(list(week_to_yymm.keys()))
            ax.set_xticklabels(list(week_to_yymm.values()), rotation=45, fontsize=8)
            for week in month_end_weeks:
                ax.axvspan(week - 0.5, week + 0.5, color='gray', alpha=0.1)
        fig.tight_layout(pad=0.5)
        print("making PSI figure and widget...")
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        canvas_psi = FigureCanvasTkAgg(fig, master=self.scrollable_frame)
        canvas_psi.draw()
        canvas_psi.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        # PSI描画後のshow_psiの末尾で
        self.scrollable_frame.update_idletasks()
        self.canvas_psi.configure(scrollregion=self.canvas_psi.bbox("all"))
# 描画完了 → サイズ決定 → bbox 更新という順序が必要
#
#update_idletasks() がなければ、まだウィジェットのサイズが未定のまま bbox を取得#しても正しくならない
#
#canvas_psi.get_tk_widget().pack(...) の後で update_idletasks() を呼ぶのがベスト#タイミング
#  Tkinter + Matplotlib の組み合わせでは：
# update_idletasks() の呼び出しタイミング
# scrollregion 設定
# <Configure> イベントの扱い
# …が意外とデリケートなポイント
    def overlay_price_on_axes(self, ax, node, product_name: str, weeks=None):
        """
        PSIの棒グラフ(ax)に、単価/原価ラインをオーバーレイする。
        - 単価: offering_price_TOBE があれば優先、なければ ASIS
        - 原価: unit_cost_dm + unit_cost_tariff（存在すれば）
        """
        import numpy as np
        W = 0
        if hasattr(node, "psi4demand") and isinstance(node.psi4demand, list):
            W = len(node.psi4demand)
        if weeks is None:
            weeks = np.arange(W) if W else np.arange(0, 52)
        # 価格（定数ライン）
        unit_price = getattr(node, "offering_price_TOBE", None)
        if unit_price is None:
            unit_price = getattr(node, "offering_price_ASIS", None)
        # 原価（定数ライン）
        dm = getattr(node, "unit_cost_dm", None)
        tr = getattr(node, "unit_cost_tariff", None)
        unit_cost = None
        if (dm is not None) or (tr is not None):
            unit_cost = (dm or 0.0) + (tr or 0.0)
        if (unit_price is None) and (unit_cost is None):
            return  # オーバーレイ情報無し
        ax2 = ax.twinx()
        handles = []; labels = []
        if unit_price is not None:
            h1, = ax2.plot(weeks, [unit_price]*len(weeks), color="#1f77b4", linewidth=2.0, label="Unit Price")
            handles.append(h1); labels.append("Unit Price")
        if unit_cost is not None:
            h2, = ax2.plot(weeks, [unit_cost]*len(weeks), color="#FF7F0E", linewidth=1.8, linestyle="--", label="Unit Cost")
            handles.append(h2); labels.append("Unit Cost")
        ax2.set_ylabel("Price")
        # 既存凡例と結合（重なりを避けて右上へ）
        h0, l0 = ax.get_legend_handles_labels()
        ax.legend(h0+handles, l0+labels, loc="upper right", fontsize=8, frameon=True)
    # --- 1) 世界地図ビュー -------------------------------------------
    def _iter_parent_child(self, root):
        """PlanNodeツリーから(parent, child)のタプルを列挙（製品エッジ抽出に使用）。"""
        if root is None:
            return
        stack = [root]
        while stack:
            n = stack.pop()
            for c in getattr(n, "children", []) or []:
                yield (n, c)
                stack.append(c)
    def show_psi_graph(self):
        print("making PSI graph data...")
        self._ensure_plan_window()
        #@STOP
        #self._ensure_psi_area()      # ← これを追加
        week_start = 1
        week_end = self.plan_range * 53
        psi_data = []
        def traverse_nodes(node):
            for child in node.children:
                traverse_nodes(child)
            collect_psi_data(node, "demand", week_start, week_end, psi_data)
        # ***************************
        # ROOT HANDLE
        # ***************************
        traverse_nodes(self.root_node_outbound)
        fig, axs = plt.subplots(len(psi_data), 1, figsize=(5, len(psi_data) * 1))  # figsizeの高さをさらに短く設定
        if len(psi_data) == 1:
            axs = [axs]
        for ax, (node_name, revenue, profit, profit_ratio, line_plot_data_2I, bar_plot_data_3P, bar_plot_data_0S) in zip(axs, psi_data):
            ax2 = ax.twinx()
            ax.bar(line_plot_data_2I.index, line_plot_data_2I.values, color='r', alpha=0.6)
            ax.bar(bar_plot_data_3P.index, bar_plot_data_3P.values, color='g', alpha=0.6)
            ax2.plot(bar_plot_data_0S.index, bar_plot_data_0S.values, color='b')
            ax.set_ylabel('I&P Lots', fontsize=8)
            ax2.set_ylabel('S Lots', fontsize=8)
            ax.set_title(f'Node: {node_name} | REVENUE: {revenue:,} | PROFIT: {profit:,} | PROFIT_RATIO: {profit_ratio}%', fontsize=8)
            # Y軸の整数設定
            ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
            ax2.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        fig.tight_layout(pad=0.5)
        print("making PSI figure and widget...")
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        canvas_psi = FigureCanvasTkAgg(fig, master=self.scrollable_frame)
        canvas_psi.draw()
        canvas_psi.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    def show_psi_overview(self, product_name: str,
                        primary_layer: str = "supply",
                        fallback_to_demand: bool = True,
                        skip_empty: bool = True):
        """
        レイアウト:
        上段: Outbound（leaf→DAD）= post-order（root除外）
        下段: Inbound（MOM→leaf）  = pre-order（MOM起点、root除外）
        表示レイヤ:
        primary_layer("supply"/"demand") が空なら fallback_to_demand=True で demand にフォールバック
        """
        import tkinter as tk
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        # PSI表示の“器”が未作成なら、右のPSIカラムに必ず作る
        try:
            parent_for_psi = getattr(self, "frame_psi", None) or getattr(self, "right_psi", None) or self.root
            if not getattr(self, "canvas_psi", None) or not getattr(self, "scrollable_frame", None):
                self._ensure_psi_area(parent_for_psi)
        except Exception:
            pass
        # 古い PSI 図だけを掃除（キャンバス自体は再利用）
        try:
            if getattr(self, 'scrollable_frame', None):
                for w in list(self.scrollable_frame.winfo_children()):
                    try:
                        w.destroy()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            if getattr(self, "_psi_canvas", None):
                self._psi_canvas.get_tk_widget().destroy()
                self._psi_canvas = None
            if getattr(self, "_psi_fig", None):
                self._psi_fig.clf(); plt.close(self._psi_fig)
                self._psi_fig = None
        except Exception:
            pass
        # ---- 週軸 ----
        week_start = 1
        week_end   = int(getattr(self, "plan_range", 3)) * 53
        # ---- ルート取得 ----
        out_root = (getattr(self, "prod_tree_dict_OT", {}) or {}).get(product_name)
        in_root  = (getattr(self, "prod_tree_dict_IN", {}) or {}).get(product_name)
        if not out_root or not in_root:
            print(f"[WARN] show_psi_overview: roots not found for product={product_name}")
            return
        # ---- 便利関数 ----
        def _depth(n):
            d = 0
            while getattr(n, 'parent', None):
                n = n.parent; d += 1
            return d
        def _iter_postorder(root):
            st = [(root, False)]
            while st:
                n, done = st.pop()
                if not n:
                    continue
                if done:
                    yield n
                else:
                    st.append((n, True))
                    for c in getattr(n, 'children', []) or []:
                        st.append((c, False))
        def _iter_preorder(node):
            st = [node]
            while st:
                n = st.pop()
                if n:
                    yield n
                    ch = getattr(n, 'children', []) or []
                    for c in reversed(ch):
                        st.append(c)
        def _layer_psi(node):
            # primary_layer優先、必要なら demand にフォールバック
            if primary_layer == "supply":
                psi = getattr(node, "psi4supply", None)
                if (not psi) and fallback_to_demand:
                    return getattr(node, "psi4demand", None), "demand(fallback)"
                return psi, "supply"
            else:
                return getattr(node, "psi4demand", None), "demand"
        def _has_data(psi_layer):
            if not psi_layer:
                return False
            # S / I / P のどれかに1つでも lot があれば “あり”
            upto = min(len(psi_layer)-1, week_end)
            for w in range(week_start, upto+1):
                week = psi_layer[w]
                if week[0] or week[2] or week[3]:
                    return True
            return False
        def _series_from_psi(psi_layer, w0, w1):
            import pandas as pd
            if not psi_layer:
                return pd.Series([], dtype=int), pd.Series([], dtype=int), pd.Series([], dtype=int)
            w1 = min(w1, len(psi_layer)-1)
            S = [len(psi_layer[w][0]) for w in range(w0, w1+1)]
            I = [len(psi_layer[w][2]) for w in range(w0, w1+1)]
            P = [len(psi_layer[w][3]) for w in range(w0, w1+1)]
            idx = list(range(w0, w1+1))
            return pd.Series(I, index=idx), pd.Series(P, index=idx), pd.Series(S, index=idx)
        # ---- 並べるノード列 ----
        # Outbound: 葉が上（深い順）、root(out_root)は除外
        out_nodes = [n for n in _iter_postorder(out_root) if getattr(n, 'parent', None) is not None]
        out_nodes.sort(key=_depth, reverse=True)
        # --- Inbound の起点（MOM*）を厳密に探索：root→supply_point→MOMxxx（複数可）---
        def _name(n):
            return str(getattr(n, "name", "") or "")
        def _is_mom(n):
            return _name(n).upper().startswith("MOM")  # 接頭辞判定（== "MOM" は不可）
        def _is_supply_point(n):
            return _name(n).lower() == "supply_point"
        # 1) supply_point を特定（in_root 自体か、その直下にいる想定）
        sp = None
        if _is_supply_point(in_root):
            sp = in_root
        else:
            for c in getattr(in_root, "children", []) or []:
                if _is_supply_point(c):
                    sp = c
                    break
        # 最後の保険（見つからない特殊データでも落とさない）
        if sp is None:
            sp = in_root
        # 2) supply_point の子から MOM* を全取得（複数想定）
        moms = [c for c in (getattr(sp, "children", []) or []) if _is_mom(c)]
        # 3) それでも 0 件なら、旧来の位置（in_root 直下）も一応スキャン
        if not moms:
            moms = [c for c in (getattr(in_root, "children", []) or []) if _is_mom(c)]
        # 4) それでも無ければ、最初の子を起点に（見栄え用フォールバック）
        if not moms and getattr(sp, "children", None):
            moms = [sp.children[0]]
        # 5) Inbound 可視化用ノード列を構築（各 MOM サブツリーを pre-order で連結）
        in_nodes = []
        seen = set()
        for m in moms:
            for n in _iter_preorder(m):
                # in_root / supply_point は描かない。MOM から下を表示
                key = id(n)
                if n is not sp and n is not in_root and key not in seen:
                    in_nodes.append(n)
                    seen.add(key)
        # 空ノードを省くオプション
        if skip_empty:
            out_nodes = [n for n in out_nodes if _has_data(_layer_psi(n)[0])]
            in_nodes  = [n for n in in_nodes  if _has_data(_layer_psi(n)[0])]
        # ---- Calendar & 軸 ----
        cal = Calendar445(start_year=self.plan_year_st, plan_range=self.plan_range,
                        use_13_months=True, holiday_country="JP")
        week_to_yymm_all = cal.get_week_labels()
        max_year = self.plan_year_st + self.plan_range - 1
        week_to_yymm = {w: y for w, y in week_to_yymm_all.items()
                        if int(str(y)[:2]) <= (max_year % 100)}
        month_end_weeks = [w for w in cal.get_month_end_weeks() if w in week_to_yymm]
        # ---- Figure ----
        nrows = (0 if len(out_nodes)==0 else len(out_nodes)+1) + (0 if len(in_nodes)==0 else len(in_nodes)+1)
        nrows = nrows or 2
        fig_w = max(10, min((week_end - week_start + 1) * 0.06, 20))  # 横は広め（2〜3年想定）
        fig_h = max(5.5, 1.0 * nrows)
        fig = plt.figure(figsize=(fig_w, fig_h), constrained_layout=True)
        from matplotlib.gridspec import GridSpec
        gs = GridSpec(nrows=nrows, ncols=1, figure=fig)
        row = 0
        if out_nodes:
            axh = fig.add_subplot(gs[row]); row += 1
            axh.axis('off')
            axh.text(0, 0.5, f"Outbound (leaf→DAD)  [primary: {primary_layer}]",
                    fontsize=11, fontweight='bold', va='center')
            for n in out_nodes:
                ax = fig.add_subplot(gs[row]); row += 1
                psi, _ = _layer_psi(n)
                if not psi:
                    continue
                I, P, S = _series_from_psi(psi, week_start, week_end)
                ax2 = ax.twinx()
                ax.bar(I.index, I.values, color='#d95f02', alpha=0.65)
                ax.bar(P.index, P.values, color='#1b9e77', alpha=0.65)
                ax2.plot(S.index, S.values, color='#377eb8', linewidth=1.1)
                ax.set_xlim(week_start, week_end)
                ax.set_xticks(list(week_to_yymm.keys()))
                ax.set_xticklabels(list(week_to_yymm.values()), rotation=45, fontsize=8)
                for w in month_end_weeks:
                    ax.axvspan(w - 0.5, w + 0.5, color='gray', alpha=0.08)
                ax.set_ylabel('I&P Lots', fontsize=9)
                ax2.set_ylabel('S Lots', fontsize=9)
                # タイトルは潰れやすいので y 軸ラベルへノード名を表示
                ax.set_title("")
                ax.set_ylabel(n.name, rotation=0, ha='right', va='center', labelpad=35, fontsize=9)
        if in_nodes:
            axh = fig.add_subplot(gs[row]); row += 1
            axh.axis('off')
            axh.text(0, 0.5, f"Inbound (MOM→leaf)  [primary: {primary_layer}]",
                    fontsize=11, fontweight='bold', va='center')
            for n in in_nodes:
                ax = fig.add_subplot(gs[row]); row += 1
                psi, _ = _layer_psi(n)
                if not psi:
                    continue
                I, P, S = _series_from_psi(psi, week_start, week_end)
                ax2 = ax.twinx()
                ax.bar(I.index, I.values, color='#d95f02', alpha=0.65)
                ax.bar(P.index, P.values, color='#1b9e77', alpha=0.65)
                ax2.plot(S.index, S.values, color='#377eb8', linewidth=1.1)
                ax.set_xlim(week_start, week_end)
                ax.set_xticks(list(week_to_yymm.keys()))
                ax.set_xticklabels(list(week_to_yymm.values()), rotation=45, fontsize=8)
                for w in month_end_weeks:
                    ax.axvspan(w - 0.5, w + 0.5, color='gray', alpha=0.08)
                ax.set_ylabel('I&P Lots', fontsize=9)
                ax2.set_ylabel('S Lots', fontsize=9)
                ax.set_title("")
                ax.set_ylabel(n.name, rotation=0, ha='right', va='center', labelpad=35, fontsize=9)
        # ========= Tk へ貼り付け（self.scrollable_frame 配下が超重要） =========
        self._psi_fig = fig
        self._psi_canvas = FigureCanvasTkAgg(fig, master=self.scrollable_frame)
        self._psi_canvas.draw()
        self._psi_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        # スクロール領域更新
        try:
            self.scrollable_frame.update_idletasks()
            self.canvas_psi.configure(scrollregion=self.canvas_psi.bbox("all"))
        except Exception:
            pass
    # ============================================
    # End of show_psi_overview
    # ============================================
    # ================================
    # World Map view: helpers
    # ================================
    def _get_physical_nodes(self):
        """
        物理ノード辞書を返す。優先度:
        1) self.global_nodes があればそれ
        2) networkx Graph G のノード名を self.nodes_outbound / inbound から引く
        3) 最後に {name: SimpleNamespace(name=name)} のダミー化
        """
        from types import SimpleNamespace
        if isinstance(getattr(self, "global_nodes", None), dict) and self.global_nodes:
            return self.global_nodes
        mapping = {}
        G = getattr(self, "G", None)
        cand1 = getattr(self, "nodes_outbound", {}) if isinstance(getattr(self, "nodes_outbound", None), dict) else {}
        cand2 = getattr(self, "nodes_inbound", {})  if isinstance(getattr(self, "nodes_inbound",  None), dict)  else {}
        if G is not None:
            for nm in G.nodes():
                node = cand1.get(nm) or cand2.get(nm)
                if node is None:
                    node = SimpleNamespace(name=nm, lat=None, lon=None, role="SITE")
                mapping[nm] = node
        return mapping
    def _collect_highlight_edges(self, product_name: str):
        """
        製品ツリーから (u_name, v_name) の物理辺集合を作る。
        PlanNode名==物理Node名 を前提。異なるなら PlanNode 側に node_name を持たせてここで解決。
        """
        edges = set()
        root = getattr(self, "prod_tree_dict_OT", {}).get(product_name)
        if not root:
            return edges
        stack = [root]
        while stack:
            n = stack.pop()
            for c in getattr(n, "children", []) or []:
                u = getattr(n, "name", None) or getattr(n, "node_name", None)
                v = getattr(c, "name", None) or getattr(c, "node_name", None)
                if u and v:
                    edges.add((u, v))
                stack.append(c)
        return edges
    def _ensure_geo_positions(self, phys_nodes: dict, G):
        """
        多数のノードに lat/lon が無い場合、既存のネットワーク座標(self.pos_E2E など)や spring_layout
        を使って擬似的に世界座標へマップして node.lat/node.lon に保存する。
        - 経度: -170..+170 に線形スケール
        - 緯度:  -60.. +60 に線形スケール（見やすさ優先）
        """
        import numpy as np
        import networkx as nx
        # 現在の pos を取得（無ければ spring_layout）
        pos = getattr(self, "pos_E2E", None)
        if not pos or len(pos) < max(1, int(0.3 * len(phys_nodes))):
            # spring_layout でざっくり配置
            pos = nx.spring_layout(G, seed=42, k=None, iterations=100)
        # pos を配列に
        xs = np.array([pos.get(nm, (0.0, 0.0))[0] for nm in phys_nodes.keys()], dtype=float)
        ys = np.array([pos.get(nm, (0.0, 0.0))[1] for nm in phys_nodes.keys()], dtype=float)
        # min==max を避ける
        def _scale(arr, lo, hi):
            a, b = float(arr.min()), float(arr.max())
            if abs(b - a) < 1e-9:
                return np.full_like(arr, (lo + hi) / 2.0)
            return lo + (arr - a) * (hi - lo) / (b - a)
        lons = _scale(xs, -170.0, 170.0)
        lats = _scale(ys,  -60.0,  60.0)
        # 未設定のノードだけ書き込む（既に lat/lon が入っていれば尊重）
        for (nm, node), lo, la in zip(phys_nodes.items(), lons, lats):
            if getattr(node, "lat", None) in (None, "", "None"):
                setattr(node, "lat", float(la))
            if getattr(node, "lon", None) in (None, "", "None"):
                setattr(node, "lon", float(lo))
    # ================================
    # World Map: main renderer
    # ================================
    def _toggle_worldmap_fit(self):
        """Viewメニューの 'Fit to data' トグル反映 → 再描画"""
        try:
            self.world_map_fit = bool(self.world_map_fit_var.get())
        except Exception:
            self.world_map_fit = True
        # 現在選択中の製品（無ければ None）
        product = getattr(self, "product_selected", None)
        self.show_world_map(product)
    def _toggle_worldmap_fit(self):
        """
        チェック状態を切り替えて、必要なら World Map を再表示＋Fit
        """
        self.world_map_fit = not self.world_map_fit
        # 地図未描画なら先に描く（この時点で self._map_pos が更新される）
        if not hasattr(self, "_map_ax") or self._map_ax is None:
            self.show_world_map(self.product_selected)
            return  # show_world_map内でfitされるので終了
        # 既に地図表示中なら、明示的にfitをかける
        pos = getattr(self, "_map_pos", {})
        if pos:
            lons = [lon for lon, _ in pos.values()]
            lats = [lat for _, lat in pos.values()]
            self._fit_lonlat(lons, lats, edges=None)
    # ======== Map interactions ========
    def _install_map_interactions(self):
        """右ドラッグのパンだけを canvas に接続する。"""
        canvas = getattr(self, "_map_canvas", None)
        if canvas is None:
            return
        # 以前のパン用接続を解除
        for cid in getattr(self, "_map_pan_cids", []):
            try:
                canvas.mpl_disconnect(cid)
            except Exception:
                pass
        self._map_pan_cids = []
        # 状態初期化
        self._map_panning = False
        self._map_pan_last = None
        # ★ パンだけ接続（scroll/key は接続しない）
        self._map_pan_cids = [
            canvas.mpl_connect("button_press_event",   self._on_map_button),
            canvas.mpl_connect("motion_notify_event",  self._on_map_motion),
            canvas.mpl_connect("button_release_event", self._on_map_release),
        ]
    def _clear_map_highlights(self):
        """注釈・ハイライトを消す"""
        for art in getattr(self, "_map_highlight_artists", []):
            try: art.remove()
            except Exception: pass
        self._map_highlight_artists = []
        ann = getattr(self, "_map_anno_artist", None)
        if ann is not None:
            try: ann.remove()
            except Exception: pass
            self._map_anno_artist = None
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    def _clear_map_highlights(self):
        """注釈・ハイライトを消す"""
        for art in getattr(self, "_map_highlight_artists", []):
            try: art.remove()
            except Exception: pass
        self._map_highlight_artists = []
        ann = getattr(self, "_map_anno_artist", None)
        if ann is not None:
            try: ann.remove()
            except Exception: pass
            self._map_anno_artist = None
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    def _on_map_press(self, event):
        """
        [新規] マウスボタンが押された時の処理
        - 左クリック: ノード選択
        - 右クリック: パン操作の開始
        """
        ax = getattr(self, "_map_ax", None)
        if ax is None or event.inaxes is not ax or event.xdata is None:
            return
        if event.button == 1: # 左クリック
            self._on_map_click(event)
        elif event.button == 3: # 右クリック
            self._map_pan_state['dragging'] = True
            # [理由] パンは投影座標系(xdata, ydata)で行う
            self._map_pan_state['last_pos'] = (event.xdata, event.ydata)
    def _on_map_click(self, event):
        """左クリック：最寄りノードに注釈 + ハイライト"""
        ax = getattr(self, "_map_ax", None)
        if ax is None or event.inaxes is not ax:
            return
        pair = self._event_lonlat(event)
        if not pair:
            self._clear_map_highlights()
            return
        x, y = pair
        pos = getattr(self, "_map_pos", {})
        if not pos:
            return
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        data_crs = getattr(self, "_map_data_crs", None)
        if used_cartopy and data_crs:
            xmin, xmax, ymin, ymax = ax.get_extent(crs=data_crs)
        else:
            xmin, xmax = ax.get_xlim(); ymin, ymax = ax.get_ylim()
        thr = 0.01 * ((xmax - xmin) + (ymax - ymin))  # 1%程度の箱で当たりを取る
        hit, best = None, 1e9
        for name, (lon, lat) in pos.items():
            d = abs(lon - x) + abs(lat - y)
            if d < best:
                hit, best = name, d
        if hit is None or best > thr:
            self._clear_map_highlights()
            return
        # 既存の注釈/ハイライトを消す
        self._clear_map_highlights()
        # 注釈テキスト
        node = getattr(self, "_map_nodes", {}).get(hit)
        info = hit
        if node is not None:
            rows = []
            for k in ("lat", "lon", "node_type", "capacity", "cost_coeff", "revenue_coeff"):
                if hasattr(node, k):
                    rows.append(f"{k}: {getattr(node, k)}")
            if rows:
                info = hit + "\n" + "\n".join(rows)
        if used_cartopy and data_crs:
            anno = ax.annotate(
                info, xy=pos[hit], xytext=(6, 6), textcoords="offset points",
                fontsize=9, bbox=dict(boxstyle="round", fc="w", ec="#333", alpha=0.9),
                transform=data_crs, zorder=10
            )
            ring, = ax.plot([pos[hit][0]], [pos[hit][1]], "o",
                            ms=18, mfc="none", mec="red", mew=2,
                            alpha=0.7, transform=data_crs, zorder=9)
        else:
            anno = ax.annotate(
                info, xy=pos[hit], xytext=(6, 6), textcoords="offset points",
                fontsize=9, bbox=dict(boxstyle="round", fc="w", ec="#333", alpha=0.9),
                zorder=10
            )
            ring, = ax.plot([pos[hit][0]], [pos[hit][1]], "o",
                            ms=18, mfc="none", mec="red", mew=2, alpha=0.7, zorder=9)
        self._map_anno_artist = anno
        self._map_highlight_artists = [ring, anno]
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    def _on_map_click(self, event):
        """左クリック：最寄りノードに注釈 + ハイライト"""
        ax = getattr(self, "_map_ax", None)
        if ax is None or event.inaxes is not ax:
            return
        pair = self._event_lonlat(event)
        if not pair:
            self._clear_map_highlights()
            return
        x, y = pair
        pos = getattr(self, "_map_pos", {})
        if not pos:
            return
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        data_crs = getattr(self, "_map_data_crs", None)
        if used_cartopy and data_crs:
            xmin, xmax, ymin, ymax = ax.get_extent(crs=data_crs)
        else:
            xmin, xmax = ax.get_xlim(); ymin, ymax = ax.get_ylim()
        thr = 0.01 * ((xmax - xmin) + (ymax - ymin))  # 1%程度の箱で当たりを取る
        hit, best = None, 1e9
        for name, (lon, lat) in pos.items():
            d = abs(lon - x) + abs(lat - y)
            if d < best:
                hit, best = name, d
        if hit is None or best > thr:
            self._clear_map_highlights()
            return
        # 既存の注釈/ハイライトを消す
        self._clear_map_highlights()
        # ★クリック地点を次回ズームのピボットとして保存（標準 lon/lat）
        #   Cartopy/非Cartopyどちらでも pos は (lon, lat)
        try:
            self._map_last_pivot_lonlat = pos[hit]
        except Exception:
            pass
        # 注釈テキスト
        node = getattr(self, "_map_nodes", {}).get(hit)
        info = hit
        if node is not None:
            rows = []
            for k in ("lat", "lon", "node_type", "capacity", "cost_coeff", "revenue_coeff"):
                if hasattr(node, k):
                    rows.append(f"{k}: {getattr(node, k)}")
            if rows:
                info = hit + "\n" + "\n".join(rows)
        if used_cartopy and data_crs:
            anno = ax.annotate(
                info, xy=pos[hit], xytext=(6, 6), textcoords="offset points",
                fontsize=9, bbox=dict(boxstyle="round", fc="w", ec="#333", alpha=0.9),
                transform=data_crs, zorder=10
            )
            ring, = ax.plot([pos[hit][0]], [pos[hit][1]], "o",
                            ms=18, mfc="none", mec="red", mew=2,
                            alpha=0.7, transform=data_crs, zorder=9)
        else:
            anno = ax.annotate(
                info, xy=pos[hit], xytext=(6, 6), textcoords="offset points",
                fontsize=9, bbox=dict(boxstyle="round", fc="w", ec="#333", alpha=0.9),
                zorder=10
            )
            ring, = ax.plot([pos[hit][0]], [pos[hit][1]], "o",
                            ms=18, mfc="none", mec="red", mew=2, alpha=0.7, zorder=9)
        self._map_anno_artist = anno
        self._map_highlight_artists = [ring, anno]
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    def _on_map_click(self, event):
        """左クリック：最寄りノードに注釈 + ハイライト（既存のコードを流用）"""
        ax = getattr(self, "_map_ax", None)
        if ax is None or event.inaxes is not ax:
            return
        pair = self._event_lonlat(event)
        if not pair:
            self._clear_map_highlights()
            return
        x, y = pair
        pos = getattr(self, "_map_pos", {})
        if not pos: return
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        data_crs = getattr(self, "_map_data_crs", None)
        if used_cartopy and data_crs:
            xmin, xmax, ymin, ymax = ax.get_extent(crs=data_crs)
        else:
            xmin, xmax = ax.get_xlim(); ymin, ymax = ax.get_ylim()
        thr = 0.01 * ((xmax - xmin) + (ymax - ymin)) # 1%程度の箱で当たりを取る
        hit, best = None, 1e9
        for name, (lon, lat) in pos.items():
            d = abs(lon - x) + abs(lat - y)
            if d < best:
                hit, best = name, d
        if hit is None or best > thr:
            self._clear_map_highlights()
            return
        self._clear_map_highlights()
        # 注釈テキスト
        node = getattr(self, "_map_nodes", {}).get(hit)
        info = hit
        if node is not None:
            rows = []
            for k in ("lat", "lon", "node_type", "capacity", "cost_coeff", "revenue_coeff"):
                if hasattr(node, k): rows.append(f"{k}: {getattr(node, k)}")
            if rows: info = hit + "\n" + "\n".join(rows)
        # 描画
        if used_cartopy and data_crs:
            anno = ax.annotate(info, xy=pos[hit], xytext=(6, 6), textcoords="offset points",
                             fontsize=9, bbox=dict(boxstyle="round", fc="w", ec="#333", alpha=0.9),
                             transform=data_crs, zorder=10)
            ring, = ax.plot([pos[hit][0]], [pos[hit][1]], "o", ms=18, mfc="none", mec="red", mew=2,
                             alpha=0.7, transform=data_crs, zorder=9)
        else:
            anno = ax.annotate(info, xy=pos[hit], xytext=(6, 6), textcoords="offset points",
                             fontsize=9, bbox=dict(boxstyle="round", fc="w", ec="#333", alpha=0.9),
                             zorder=10)
            ring, = ax.plot([pos[hit][0]], [pos[hit][1]], "o", ms=18, mfc="none", mec="red", mew=2, alpha=0.7, zorder=9)
        self._map_anno_artist = anno
        self._map_highlight_artists = [ring, anno]
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    def _on_map_scroll_1st(self, event):
        """マウスホイール：カーソル位置を中心にズーム。
        Cartopy ではピクセル空間で拡大縮小してから lon/lat に戻すので縦が潰れません。
        """
        ax = getattr(self, "_map_ax", None)
        if ax is None or event.inaxes is not ax:
            return
        # 拡大/縮小係数
        base = 1.2
        if   event.button == "up":   scale = 1.0 / base   # 拡大
        elif event.button == "down": scale = base         # 縮小
        else:
            return
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        # ---- 通常の Matplotlib Axes ----
        if not used_cartopy:
            if event.xdata is None or event.ydata is None:
                return
            cx, cy = float(event.xdata), float(event.ydata)
            xmin, xmax = ax.get_xlim();  ymin, ymax = ax.get_ylim()
            w = (xmax - xmin) * scale
            h = (ymax - ymin) * scale
            ax.set_xlim(cx - w/2.0, cx + w/2.0)
            ax.set_ylim(cy - h/2.0, cy + h/2.0)
            if hasattr(self, "canvas_network"): self.canvas_network.draw_idle()
            return
        # ---- Cartopy GeoAxes：ピクセル空間で拡大縮小 ----
        import numpy as np
        import cartopy.crs as ccrs
        data_crs = getattr(self, "_map_data_crs", ccrs.PlateCarree())
        map_crs  = ax.projection
        # ピボット（画面ピクセル座標）
        if event.x is None or event.y is None:
            pivot_px = getattr(self, "_map_last_pivot_px", None)
            if pivot_px is None:  # 直近が無ければ中止
                return
            px, py = pivot_px
        else:
            px, py = float(event.x), float(event.y)
            self._map_last_pivot_px = (px, py)
        # 現在の表示範囲（lon/lat）
        xmin_lon, xmax_lon, ymin_lat, ymax_lat = ax.get_extent(crs=data_crs)
        # 現在の extent の 4 隅を map 座標 → 画面ピクセルへ
        lons = np.array([xmin_lon, xmax_lon, xmin_lon, xmax_lon])
        lats = np.array([ymin_lat, ymin_lat, ymax_lat, ymax_lat])
        pts_map = map_crs.transform_points(data_crs, lons, lats)[:, :2]          # (x_map, y_map)
        pts_px  = ax.transData.transform(pts_map)                                 # → (x_px, y_px)
        # ピクセル空間でピボット中心にスケーリング
        v = pts_px - np.array([px, py])      # ピボットからのベクトル
        pts_px_new = np.array([px, py]) + v * scale
        # 画面ピクセル → map 座標 → lon/lat へ逆変換
        pts_map_new = ax.transData.inverted().transform(pts_px_new)
        pts_ll_new  = data_crs.transform_points(map_crs,
                                                pts_map_new[:, 0], pts_map_new[:, 1])
        xs = pts_ll_new[:, 0];  ys = pts_ll_new[:, 1]
        xmin_new, xmax_new = float(xs.min()), float(xs.max())
        ymin_new, ymax_new = float(ys.min()), float(ys.max())
        # 若干の安全クリップ
        ymin_new = max(-89.9, ymin_new); ymax_new = min(89.9, ymax_new)
        # 新しい範囲をセット（lon/lat）
        ax.set_extent([xmin_new, xmax_new, ymin_new, ymax_new], crs=data_crs)
        # LOD 切替関数があれば呼ぶ（任意）
        if hasattr(self, "_set_basemap_lod_from_extent"):
            try: self._set_basemap_lod_from_extent()
            except Exception: pass
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    def _on_map_scroll_2nd(self, event):
        """ホイール：カーソル位置を中心にズーム（lon/lat 上で幅を計算して set_extent）"""
        ax = getattr(self, "_map_ax", None)
        if ax is None or event.inaxes is not ax:
            return
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        base = 1.2
        if   event.button == "up":   scale = 1.0 / base   # 拡大
        elif event.button == "down": scale = base         # 縮小
        else:
            return
        if used_cartopy:
            import cartopy.crs as ccrs
            data_crs = getattr(self, "_map_data_crs", None) or ccrs.PlateCarree()
            # ピボット（lon/lat）
            pair = self._event_lonlat(event)
            if pair:
                cx, cy = pair
                self._map_last_pivot_ll = (cx, cy)
            else:
                cx, cy = getattr(self, "_map_last_pivot_ll", (0.0, 0.0))
            # 現在の表示範囲（lon/lat）
            xmin, xmax, ymin, ymax = ax.get_extent(crs=data_crs)
            # 経度幅は 0..360 のモジュロで評価（全世界=360°）
            span_lon = (xmax - xmin) % 360.0
            if span_lon < 1e-6:
                span_lon = 360.0
            span_lat = ymax - ymin
            if span_lat <= 0:
                span_lat = 180.0  # 念のため
            # 新しい幅・高さ（最小1°を確保）
            new_lon = max(span_lon * scale, 1.0)
            new_lat = max(span_lat * scale, 1.0)
            # 緯度ピボットは少しだけクランプ
            cy = max(min(cy, 85.0), -85.0)
            # ピボット中心で新しい矩形（lon/lat）
            xmin_new = cx - new_lon / 2.0
            xmax_new = cx + new_lon / 2.0
            ymin_new = cy - new_lat / 2.0
            ymax_new = cy + new_lat / 2.0
            # 緯度が[-90,90]を超えたら平行移動で補正
            if ymin_new < -90:
                d = -90 - ymin_new
                ymin_new += d; ymax_new += d
            if ymax_new > 90:
                d = 90 - ymax_new
                ymin_new += d; ymax_new += d
            # lon は wrap 不要でも OK（Cartopy が解釈）だが、PlateCarree を明示
            ax.set_extent([xmin_new, xmax_new, ymin_new, ymax_new], crs=data_crs)
        else:
            # 通常 Axes
            if event.xdata is None or event.ydata is None:
                return
            cx, cy = float(event.xdata), float(event.ydata)
            xmin, xmax = ax.get_xlim();  ymin, ymax = ax.get_ylim()
            width  = max((xmax - xmin) * scale, 1e-6)
            height = max((ymax - ymin) * scale, 1e-6)
            ax.set_xlim(cx - width/2.0,  cx + width/2.0)
            ax.set_ylim(cy - height/2.0, cy + height/2.0)
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    def _on_map_scroll_3rd(self, event):
        """ホイール：カーソル位置を中心にズーム（投影座標で一貫処理）"""
        ax = getattr(self, "_map_ax", None)
        if ax is None or event.inaxes is not ax:
            return
        base = 1.2
        if   event.button == "up":   scale = 1.0 / base   # 拡大
        elif event.button == "down": scale = base         # 縮小
        else:
            return
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        if used_cartopy:
            # ---- GeoAxes: 投影（map_crs）で完結 ----
            map_crs = ax.projection
            # ピボット（マウス位置）を map 座標で取得
            if event.xdata is not None and event.ydata is not None:
                cx, cy = float(event.xdata), float(event.ydata)
                self._map_last_pivot_map = (cx, cy)
            else:
                # ホイールが Axes 外で回された等の保険
                pivot = getattr(self, "_map_last_pivot_map", None)
                if pivot is None:
                    return
                cx, cy = pivot
            # 現在の表示範囲（map 座標）
            xmin, xmax, ymin, ymax = ax.get_extent(crs=map_crs)
            width  = xmax - xmin
            height = ymax - ymin
            # 新しい幅・高さ（極端に小さくならないよう下限を設定）
            width2  = max(width  * scale, 1e-6)
            height2 = max(height * scale, 1e-6)
            # ピボット中心で新しい範囲を設定（map 座標のまま）
            ax.set_extent([cx - width2/2.0, cx + width2/2.0,
                        cy - height2/2.0, cy + height2/2.0],
                        crs=map_crs)
        else:
            # ---- 通常 Axes ----
            if event.xdata is None or event.ydata is None:
                return
            cx, cy = float(event.xdata), float(event.ydata)
            xmin, xmax = ax.get_xlim()
            ymin, ymax = ax.get_ylim()
            width  = xmax - xmin
            height = ymax - ymin
            width2  = max(width  * scale, 1e-6)
            height2 = max(height * scale, 1e-6)
            ax.set_xlim(cx - width2/2.0, cx + width2/2.0)
            ax.set_ylim(cy - height2/2.0, cy + height2/2.0)
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    def _on_map_scroll_4th(self, event):
        """ホイール：カーソル位置を中心にズーム（投影座標で一貫処理 & 経度窓を正規化）"""
        ax = getattr(self, "_map_ax", None)
        if ax is None or event.inaxes is not ax:
            return
        base = 1.2
        if   event.button == "up":   scale = 1.0 / base   # 拡大
        elif event.button == "down": scale = base         # 縮小
        else:
            return
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        if used_cartopy:
            import cartopy.crs as ccrs
            map_crs = ax.projection
            # ピボット座標（map_crs）
            if event.xdata is not None and event.ydata is not None:
                cx, cy = float(event.xdata), float(event.ydata)
                self._map_last_pivot_map = (cx, cy)
            else:
                pivot = getattr(self, "_map_last_pivot_map", None)
                if pivot is None:
                    return
                cx, cy = pivot
            # 現在の可視範囲（map_crs）
            xmin, xmax, ymin, ymax = ax.get_extent(crs=map_crs)
            width  = xmax - xmin
            height = ymax - ymin
            width2  = max(width  * scale, 1e-6)
            height2 = max(height * scale, 1e-6)
            # ---- 経度窓の正規化（[-180,180]に同時に収まるよう中心を±360°回す）----
            half = width2 / 2.0
            mid  = cx
            # map_crs=PlateCarree(central_longitude=180) の経度有効域
            LMIN, LMAX = -180.0, 180.0
            # 中央をずらして [mid-half, mid+half] が同時に域内に入るように調整
            # （width2 <= 360° を前提。初回ズーム後は必ず満たす）
            while (mid - half) < LMIN:
                mid += 360.0
            while (mid + half) > LMAX:
                mid -= 360.0
            xmin_new = mid - half
            xmax_new = mid + half
            # ---- 緯度は安全側にクリップ（極近傍の特異を避ける）----
            half_y = height2 / 2.0
            ymin_new = max(-89.9, cy - half_y)
            ymax_new = min( 89.9, cy + half_y)
            ax.set_extent([xmin_new, xmax_new, ymin_new, ymax_new], crs=map_crs)
        else:
            # 通常 Axes
            if event.xdata is None or event.ydata is None:
                return
            cx, cy = float(event.xdata), float(event.ydata)
            xmin, xmax = ax.get_xlim()
            ymin, ymax = ax.get_ylim()
            width  = xmax - xmin
            height = ymax - ymin
            width2  = max(width  * scale, 1e-6)
            height2 = max(height * scale, 1e-6)
            ax.set_xlim(cx - width2/2.0, cx + width2/2.0)
            ax.set_ylim(cy - height2/2.0, cy + height2/2.0)
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    def _on_map_scroll_5th(self, event):
        """ホイール：カーソル位置を中心にズーム（標準 lon/lat で計算→extent 設定）"""
        ax = getattr(self, "_map_ax", None)
        if ax is None or event.inaxes is not ax:
            return
        base = 1.2
        if   event.button == "up":   scale = 1.0 / base   # 拡大
        elif event.button == "down": scale = base         # 縮小
        else:
            return
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        if used_cartopy:
            import numpy as np
            import cartopy.crs as ccrs
            map_crs  = ax.projection
            data_crs = getattr(self, "_map_data_crs", ccrs.PlateCarree())  # ← 標準 lon/lat
            # --- ピボット位置を 標準 lon/lat に変換 ---
            if event.xdata is not None and event.ydata is not None:
                pts = data_crs.transform_points(map_crs,
                                                np.asarray([event.xdata]),
                                                np.asarray([event.ydata]))
                lon, lat = float(pts[0, 0]), float(pts[0, 1])
                self._map_last_pivot_lonlat = (lon, lat)
            else:
                if not hasattr(self, "_map_last_pivot_lonlat"):
                    return
                lon, lat = self._map_last_pivot_lonlat
            # --- 現在の表示範囲（標準 lon/lat） ---
            xmin, xmax, ymin, ymax = ax.get_extent(crs=data_crs)
            width  = xmax - xmin
            height = ymax - ymin
            # 初回は width ≈ 360。1ステップ後は <360 になる
            width2  = max(width  * scale, 1e-6)
            height2 = max(height * scale, 1e-6)
            # --- 経度窓の正規化：[-180,180] に同時に収める ---
            if width2 >= 360.0:
                xmin_new, xmax_new = -180.0, 180.0
            else:
                half = width2 / 2.0
                mid  = lon
                while (mid - half) < -180.0:
                    mid += 360.0
                while (mid + half) >  180.0:
                    mid -= 360.0
                xmin_new = mid - half
                xmax_new = mid + half
            # --- 緯度は安全側にクリップ（極付近の特異を避ける） ---
            half_y   = height2 / 2.0
            ymin_new = max(-89.9, lat - half_y)
            ymax_new = min( 89.9, lat + half_y)
            ax.set_extent([xmin_new, xmax_new, ymin_new, ymax_new], crs=data_crs)
        else:
            # 通常 Axes
            if event.xdata is None or event.ydata is None:
                return
            cx, cy = float(event.xdata), float(event.ydata)
            xmin, xmax = ax.get_xlim()
            ymin, ymax = ax.get_ylim()
            width  = xmax - xmin
            height = ymax - ymin
            width2  = max(width  * scale, 1e-6)
            height2 = max(height * scale, 1e-6)
            ax.set_xlim(cx - width2/2.0, cx + width2/2.0)
            ax.set_ylim(cy - height2/2.0, cy + height2/2.0)
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    def _on_map_scroll_6th(self, event):
        """ホイール：カーソル位置を中心にズーム（lon/lat で一貫処理・日付変更線対応）"""
        ax = getattr(self, "_map_ax", None)
        if ax is None or event.inaxes is not ax:
            return
        # 拡大縮小倍率
        base = 1.2
        if   event.button == "up":   scale = 1.0 / base   # 拡大
        elif event.button == "down": scale = base         # 縮小
        else:
            return
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        if used_cartopy:
            import numpy as np
            import cartopy.crs as ccrs
            data_crs = getattr(self, "_map_data_crs", ccrs.PlateCarree())
            map_crs  = ax.projection
            # --- helpers ---------------------------------------------------------
            def wrap180(lon: float) -> float:
                # [-180, 180) に正規化
                return ((lon + 180.0) % 360.0) - 180.0
            def unwrap_to_ref(lon: float, ref: float) -> float:
                # ref を中心に連続軸へ移す（west<east を保証するため）
                x = lon
                while x - ref < -180.0:
                    x += 360.0
                while x - ref >  180.0:
                    x -= 360.0
                return x
            # ---------------------------------------------------------------------
            # ピボット（lon/lat）。イベント座標が無ければ直前のピボット → さらに無ければ現在範囲の中心
            if event.xdata is not None and event.ydata is not None:
                pts = data_crs.transform_points(
                    map_crs,
                    np.asarray([event.xdata], dtype=float),
                    np.asarray([event.ydata], dtype=float),
                )
                cx
    def _on_map_scroll_7th(self, event):
        """ホイール：カーソル位置（lon/lat）を中心に安定ズーム"""
        ax = getattr(self, "_map_ax", None)
        if ax is None or event.inaxes is not ax:
            return
        # 方向
        base = 1.25
        if   event.button == "up":   scale = 1.0 / base  # 拡大
        elif event.button == "down": scale = base        # 縮小
        else:
            return
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        if used_cartopy:
            try:
                import numpy as np
                import cartopy.crs as ccrs
            except Exception:
                # cartopy が無ければ通常軸として処理
                used_cartopy = False
        if used_cartopy:
            # ---- すべて「データの CRS = PlateCarree(0°)」で扱う ----
            data_crs = getattr(self, "_map_data_crs", None) or ccrs.PlateCarree()
            map_crs  = ax.projection
            # ピボット（lon/lat）
            if event.xdata is not None and event.ydata is not None:
                # map_crs -> data_crs へ変換
                pts = data_crs.transform_points(
                    map_crs, np.asarray([event.xdata]), np.asarray([event.ydata])
                )
                cx, cy = float(pts[0, 0]), float(pts[0, 1])
                self._map_last_pivot_lonlat = (cx, cy)
            else:
                # 直近ピボットが無ければズーム不可
                cx, cy = getattr(self, "_map_last_pivot_lonlat", (None, None))
                if cx is None:
                    return
            # 現在の表示範囲（lon/lat）
            xmin, xmax, ymin, ymax = ax.get_extent(crs=data_crs)
            # 180°ラップに強い計算：ピボットを原点にシフトしてから拡大縮小
            def wrap180(v):
                return ((v + 180.0) % 360.0) - 180.0
            # ピボット中心系（経度だけシフト）
            xmin_s = wrap180(xmin - cx)
            xmax_s = wrap180(xmax - cx)
            if xmax_s <= xmin_s:
                xmax_s += 360.0  # 区間を正方向に
            width_s  = (xmax_s - xmin_s) * scale
            height   = (ymax - ymin)      * scale
            # 最小幅・最小高さ（つぶれ防止）
            min_w = max((xmax_s - xmin_s) * 0.02, 1.0)
            min_h = max((ymax - ymin)     * 0.02, 1.0)
            width_s  = max(width_s,  min_w)
            height   = max(height,   min_h)
            # 新しいシフト系の範囲（ピボット中心）
            xmin_s_new = -width_s / 2.0
            xmax_s_new =  width_s / 2.0
            ymin_new   =  cy - height / 2.0
            ymax_new   =  cy + height / 2.0
            # 緯度のクランプ（極域の特異点回避）
            ymin_new = max(-89.0, ymin_new)
            ymax_new = min( 89.0, ymax_new)
            # 元の座標へ戻す（経度だけ戻す）
            xmin_new = wrap180(xmin_s_new + cx)
            xmax_new = wrap180(xmax_s_new + cx)
            # Cartopy に連続区間を渡すため、必要なら +360 で単調増加にする
            if (xmax_new - xmin_new) <= 0:
                xmax_new += 360.0
            ax.set_extent([xmin_new, xmax_new, ymin_new, ymax_new], crs=data_crs)
        else:
            # ---- 通常の Matplotlib Axes ----
            if event.xdata is None or event.ydata is None:
                return
            cx, cy = float(event.xdata), float(event.ydata)
            xmin, xmax = ax.get_xlim()
            ymin, ymax = ax.get_ylim()
            width  = (xmax - xmin) * scale
            height = (ymax - ymin) * scale
            ax.set_xlim(cx - width / 2.0, cx + width / 2.0)
            ax.set_ylim(cy - height / 2.0, cy + height / 2.0)
        # 再描画 & （使っていれば）LOD 切り替え
        try:
            if hasattr(self, "canvas_network"):
                self.canvas_network.draw_idle()
            if hasattr(self, "_set_basemap_lod_from_extent"):
                self._set_basemap_lod_from_extent()
        except Exception:
            pass
    def _on_map_scroll(self, event):
        """
        [修正] ホイール：カーソル位置を中心にズーム（投影座標で一貫処理）
        [理由] この方法が最も安定しており、地図の歪みを防ぎます。
        """
        ax = getattr(self, "_map_ax", None)
        if ax is None or event.inaxes is not ax or event.xdata is None:
            return
        # 拡大・縮小係数
        base_scale = 1.2
        if event.button == 'up':
            scale_factor = 1 / base_scale
        elif event.button == 'down':
            scale_factor = base_scale
        else:
            return
        # ピボット（カーソル位置）
        cx, cy = event.xdata, event.ydata
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        if used_cartopy:
            # Cartopy GeoAxes: 投影座標系（map_crs）で処理
            map_crs = ax.projection
            xmin, xmax, ymin, ymax = ax.get_extent(crs=map_crs)
        else:
            # 通常の Matplotlib Axes
            xmin, xmax = ax.get_xlim()
            ymin, ymax = ax.get_ylim()
        # ピボットからの相対位置をスケーリング
        new_xmin = cx + (xmin - cx) * scale_factor
        new_xmax = cx + (xmax - cx) * scale_factor
        new_ymin = cy + (ymin - cy) * scale_factor
        new_ymax = cy + (ymax - cy) * scale_factor
        # 新しい表示範囲を設定
        if used_cartopy:
            ax.set_extent([new_xmin, new_xmax, new_ymin, new_ymax], crs=map_crs)
        else:
            ax.set_xlim(new_xmin, new_xmax)
            ax.set_ylim(new_ymin, new_ymax)
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    def _on_map_key(self, event):
        """f=選択品目にフィット, a=全ノード, w=世界全体, esc=ハイライト消し"""
        if event.key == "escape":
            self._clear_map_highlights()
            return
        ax = getattr(self, "_map_ax", None)
        if ax is None:
            return
        used_cartopy    = getattr(self, "_map_used_cartopy", False)
        pos             = getattr(self, "_map_pos", {})
        highlight_edges = getattr(self, "_map_high_edges", [])
        def _wrap180(lon: float) -> float:
            # 180°中心の [-180, 180) に正規化
            return ((lon - 180.0 + 180.0) % 360.0) - 180.0
        # lon/lat の配列から extent を設定
        def _fit_lonlat(lons, lats):
            if not lons or not lats:
                return
            xs = [_wrap180(x) for x in lons]
            ys = list(lats)
            xmin, xmax = min(xs), max(xs)
            ymin, ymax = min(ys), max(ys)
            # 余白 & 最小幅（見やすさ）
            lon_pad = max(5.0, (xmax - xmin) * 0.08)
            lat_pad = max(3.0, (ymax - ymin) * 0.10)
            if (xmax - xmin) < 10.0:
                cx = 0.5 * (xmin + xmax)
                xmin, xmax = cx - 5.0, cx + 5.0
            if (ymax - ymin) < 6.0:
                cy = 0.5 * (ymin + ymax)
                ymin, ymax = cy - 3.0, cy + 3.0
            if used_cartopy:
                # ★ ここが重要：PlateCarree(central_longitude=180) の座標系で指定
                ax.set_extent([xmin - lon_pad, xmax + lon_pad,
                            ymin - lat_pad,  ymax + lat_pad],
                            crs=ax.projection)
            else:
                ax.set_xlim(xmin - lon_pad, xmax + lon_pad)
                ax.set_ylim(ymin - lat_pad,  ymax + lat_pad)
        # ---- キー別動作 ----
        if event.key == "a":
            if pos:
                lons = [x for x, _ in pos.values()]
                lats = [y for _, y in pos.values()]
                self._fit_lonlat(lons, lats)
        elif event.key == "w":
            if used_cartopy:
                ax.set_global()
            else:
                ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
        elif event.key == "f":
            nodes = set()
            for u, v in highlight_edges:
                if u in pos: nodes.add(u)
                if v in pos: nodes.add(v)
            if nodes:
                lons = [pos[n][0] for n in nodes if n in pos]
                lats = [pos[n][1] for n in nodes if n in pos]
                self._fit_lonlat(lons, lats)
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    def _on_map_key(self, event):
        """[修正] f=選択品目, a=全ノード, w=世界全体, esc=ハイライト消し"""
        if event.key == "escape":
            self._clear_map_highlights()
            return
        ax = getattr(self, "_map_ax", None)
        if ax is None: return
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        pos = getattr(self, "_map_pos", {})
        highlight_edges = getattr(self, "_map_high_edges", [])
        # lon/lat の配列から extent を設定するヘルパー関数
        def _fit_lonlat(lons, lats):
            if not hasattr(self, "_map_data_crs") or not lons or not lats:
                return
            # 経度を-180..180の範囲に正規化して範囲を計算
            # 注意: 日付変更線をまたぐ場合に大きな範囲になることがあるが、ここでは単純なmin/maxで対応
            # より厳密な対応が必要な場合は、経度の中心値を計算し、そこからの差で範囲を決める
            import numpy as np
            norm_lons = [((lon + 180) % 360) - 180 for lon in lons]
            xmin, xmax = np.min(norm_lons), np.max(norm_lons)
            ymin, ymax = np.min(lats), np.max(lats)
            # 日付変更線をまたいでいるかチェック
            if (xmax - xmin) > 180:
                # またいでいる場合、正の値と負の値を分けて考える
                pos_lons = [l for l in norm_lons if l >= 0]
                neg_lons = [l for l in norm_lons if l < 0]
                if pos_lons and neg_lons:
                    # [東側..180] と [-180..西側] のどちらが狭いかで判断
                    # この実装では、単純に全ノードを含む矩形を表示
                    # ユーザー体験を向上させるには、中央経度を動かすなどの工夫が必要
                    pass # 今回は単純なmin/maxのままとする
            # 余白を設定
            width = xmax - xmin
            height = ymax - ymin
            pad_x = max(width * 0.1, 5)
            pad_y = max(height * 0.1, 5)
            # 新しい範囲
            extent = [
                xmin - pad_x, xmax + pad_x,
                ymin - pad_y, ymax + pad_y
            ]
            if used_cartopy:
                # [修正] 座標系を正しくデータCRS(PlateCarree)に指定する
                data_crs = getattr(self, "_map_data_crs")
                ax.set_extent(extent, crs=data_crs)
            else:
                ax.set_xlim(extent[0], extent[1])
                ax.set_ylim(extent[2], extent[3])
        # ---- キー別動作 ----
        if event.key == "a": # 全ノードにフィット
            if pos:
                lons = [p[0] for p in pos.values()]
                lats = [p[1] for p in pos.values()]
                self._fit_lonlat(lons, lats)
        elif event.key == "w": # 世界全体表示
            if used_cartopy:
                ax.set_global()
            else:
                ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
        elif event.key == "f": # 選択中の製品にフィット
            nodes = set(u for u, v in highlight_edges) | set(v for u, v in highlight_edges)
            if nodes:
                lons = [pos[n][0] for n in nodes if n in pos]
                lats = [pos[n][1] for n in nodes if n in pos]
                if lons and lats:
                    self._fit_lonlat(lons, lats)
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
# [修正] _on_map_key を日付変更線に対応させる
    def _on_map_key(self, event):
        """[修正] f=選択品目, a=全ノード, w=世界全体, esc=ハイライト消し"""
        if event.key == "escape":
            self._clear_map_highlights()
            return
        ax = getattr(self, "_map_ax", None)
        if ax is None: return
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        pos = getattr(self, "_map_pos", {})
        highlight_edges = getattr(self, "_map_high_edges", [])
        # [修正] ======== 日付変更線に対応したヘルパー関数 ========
        def _fit_lonlat(lons, lats):
            """
            [理由] 複数の経度を内包する最短の範囲を計算し、ビューをフィットさせる。
                  日付変更線をまたぐ場合（例：日本と米国）でも正しく動作する。
            """
            if not hasattr(self, "_map_data_crs") or not lons or not lats:
                return
            import numpy as np
            # --- 緯度範囲の計算 (これは単純なmin/maxでOK) ---
            lat_min, lat_max = np.min(lats), np.max(lats)
            # --- 経度範囲の計算（日付変更線対応） ---
            # 1. 全ての経度から最適な「中央経度」を計算する
            #    角度を単位円上のベクトルに変換し、その平均ベクトルの角度を求めることで、
            #    日付変更線をまたいでも安定した中央値が得られる。
            lon_rad = np.deg2rad(lons)
            x = np.cos(lon_rad)
            y = np.sin(lon_rad)
            central_lon = np.rad2deg(np.arctan2(np.mean(y), np.mean(x)))
            # 2. 全ての経度を、計算した中央経度を基準に [-180, 180) の範囲に再マッピングする
            #    これにより、日付変更線による数値の分断がなくなり、単純なmin/maxで範囲を求められる。
            remapped_lons = [(((lon - central_lon + 180) % 360) - 180) for lon in lons]
            # 3. 再マッピングした座標で範囲を求め、元の中心に戻す
            lon_min_remap = np.min(remapped_lons)
            lon_max_remap = np.max(remapped_lons)
            lon_min = lon_min_remap + central_lon
            lon_max = lon_max_remap + central_lon
            # --- 余白の計算と範囲の確定 ---
            width = lon_max - lon_min
            height = lat_max - lat_min
            # 範囲が狭すぎる場合に最小幅を確保
            if width < 10:
                center = (lon_min + lon_max) / 2
                lon_min, lon_max = center - 5, center + 5
            if height < 10:
                center = (lat_min + lat_max) / 2
                lat_min, lat_max = center - 5, center + 5
            pad_x = width * 0.1
            pad_y = height * 0.1
            extent = [
                lon_min - pad_x, lon_max + pad_x,
                lat_min - pad_y, lat_max + pad_y
            ]
            # --- 表示範囲の設定 ---
            if used_cartopy:
                data_crs = getattr(self, "_map_data_crs")
                ax.set_extent(extent, crs=data_crs)
            else:
                ax.set_xlim(extent[0], extent[1])
                ax.set_ylim(extent[2], extent[3])
        # =======================================================
        # ---- キー別動作 (ここは変更なし) ----
        if event.key == "a":
            if pos:
                lons = [p[0] for p in pos.values()]
                lats = [p[1] for p in pos.values()]
                self._fit_lonlat(lons, lats)
        elif event.key == "w":
            if used_cartopy:
                ax.set_global()
            else:
                ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
        elif event.key == "f":
            nodes = set(u for u, v in highlight_edges) | set(v for u, v in highlight_edges)
            if nodes:
                lons = [pos[n][0] for n in nodes if n in pos]
                lats = [pos[n][1] for n in nodes if n in pos]
                if lons and lats:
                    self._fit_lonlat(lons, lats)
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    # --- optional: Tk のカーソルを変える小ヘルパ ---
    def _set_map_cursor(self, name=None):
        try:
            w = self.canvas_network.get_tk_widget()
            w.configure(cursor=("fleur" if name == "pan" else ""))
        except Exception:
            pass
# [最終修正] _on_map_key を「緯度優先フィット」ロジックに対応
    def _on_map_key(self, event):
        """[修正] f=選択品目, a=全ノード, w=世界全体, esc=ハイライト消し"""
        if event.key == "escape":
            self._clear_map_highlights()
            return
        ax = getattr(self, "_map_ax", None)
        if ax is None: return
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        pos = getattr(self, "_map_pos", {})
        highlight_edges = getattr(self, "_map_high_edges", [])
        # [修正] ======== 緯度優先フィットに対応したヘルパー関数 ========
        def _fit_lonlat(lons, lats):
            """
            [理由] 緯度方向を Axes の上下にフィットさせ、経度方向はアスペクト比を
                  維持するように範囲を調整する。
            """
            if not hasattr(self, "_map_data_crs") or not lons or not lats:
                return
            import numpy as np
            import cartopy.crs as ccrs
            # === Step 1: 表示したいデータの地理的中心と範囲を計算 ===
            # (前回の修正と同じロジックで日付変更線を考慮)
            lon_rad = np.deg2rad(lons)
            central_lon = np.rad2deg(np.arctan2(np.mean(np.sin(lon_rad)), np.mean(np.cos(lon_rad))))
            remapped_lons = [(((lon - central_lon + 180) % 360) - 180) for lon in lons]
            data_lon_min = np.min(remapped_lons) + central_lon
            data_lon_max = np.max(remapped_lons) + central_lon
            data_lat_min, data_lat_max = np.min(lats), np.max(lats)
            # データ範囲が点や線の場合に最小領域を確保
            if np.isclose(data_lon_min, data_lon_max): data_lon_max += 1.0
            if np.isclose(data_lat_min, data_lat_max): data_lat_max += 1.0
            # === Step 2: 地図 Axes の物理的なアスペクト比を取得 ===
            # (これにより、表示枠の形状がわかる)
            try:
                # FigureCanvasが描画済みの場合
                bbox = ax.get_window_extent()
                axes_aspect_ratio = bbox.width / bbox.height
            except Exception:
                # 未描画の場合のフォールバック
                axes_aspect_ratio = 4 / 3 # デフォルト値
            # === Step 3: 緯度フィットに必要な経度範囲を逆算 ===
            data_crs = getattr(self, "_map_data_crs", ccrs.PlateCarree())
            map_crs = ax.projection
            # データの緯度範囲と経度中心を、地図の投影座標系に変換
            pts_proj = map_crs.transform_points(
                data_crs,
                np.array([central_lon, central_lon]),
                np.array([data_lat_min, data_lat_max])
            )
            # 投影座標系でのY方向(縦)の幅
            proj_y_span = abs(pts_proj[1, 1] - pts_proj[0, 1])
            # 投影座標系でのX方向(横)の中心
            proj_x_center = pts_proj[0, 0]
            # 投影座標系で、Axesのアスペクト比を維持するために必要なX方向の幅を計算
            proj_x_span = proj_y_span * axes_aspect_ratio
            # 新しい投影座標系の範囲を計算
            proj_x_min = proj_x_center - proj_x_span / 2
            proj_x_max = proj_x_center + proj_x_span / 2
            proj_y_min = min(pts_proj[0, 1], pts_proj[1, 1])
            proj_y_max = max(pts_proj[0, 1], pts_proj[1, 1])
            # === Step 4: 新しい範囲を緯度経度に戻し、set_extentに渡す ===
            # 投影座標系の四隅を、緯度経度座標系に逆変換
            new_bounds_proj = np.array([
                [proj_x_min, proj_y_min],
                [proj_x_max, proj_y_max]
            ])
            new_bounds_lonlat = data_crs.transform_points(map_crs,
                new_bounds_proj[:, 0], new_bounds_proj[:, 1]
            )
            final_lon_min = new_bounds_lonlat[0, 0]
            final_lon_max = new_bounds_lonlat[1, 0]
            final_lat_min = new_bounds_lonlat[0, 1]
            final_lat_max = new_bounds_lonlat[1, 1]
            # パディング（少し余白を追加）
            lat_padding = (final_lat_max - final_lat_min) * 0.05
            extent = [
                final_lon_min, final_lon_max,
                final_lat_min - lat_padding, final_lat_max + lat_padding
            ]
            if used_cartopy:
                ax.set_extent(extent, crs=data_crs)
            else:
                # 非cartopyの場合の簡易ロジック
                ax.set_ylim(extent[2], extent[3])
                ax.set_xlim(extent[0], extent[1])
                ax.set_aspect('equal', adjustable='box')
        # =======================================================
        # ---- キー別動作 (変更なし) ----
        if event.key == "a":
            if pos:
                self._fit_lonlat([p[0] for p in pos.values()], [p[1] for p in pos.values()])
        elif event.key == "w":
            if used_cartopy: ax.set_global()
            else: ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
        elif event.key == "f":
            nodes = set(u for u, v in highlight_edges) | set(v for u, v in highlight_edges)
            if nodes:
                lons = [pos[n][0] for n in nodes if n in pos]
                lats = [pos[n][1] for n in nodes if n in pos]
                if lons and lats: self._fit_lonlat(lons, lats)
        # 最後に再描画をかけてレイアウトを更新
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
# [最終修正 ver.2] _on_map_key を「水平フォーカス調整」に対応
    def _on_map_key(self, event):
        """[修正] f=選択品目, a=全ノード, w=世界全体, esc=ハイライト消し"""
        if event.key == "escape":
            self._clear_map_highlights()
            return
        ax = getattr(self, "_map_ax", None)
        if ax is None: return
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        pos = getattr(self, "_map_pos", {})
        highlight_edges = getattr(self, "_map_high_edges", [])
        # [修正] ======== 水平フォーカス調整に対応したヘルパー関数 ========
        def _fit_lonlat(lons, lats, edges=None):
            """
            [理由] 緯度フィットを維持しつつ、水平方向のフォーカスを調整する。
                  edgesが与えられればfrom nodeを、なければ左端のノードを優先する。
            """
            if not hasattr(self, "_map_data_crs") or not lons or not lats:
                return
            import numpy as np
            import cartopy.crs as ccrs
            # === Step 1: 表示したいデータの地理的範囲を計算 ===
            lon_rad = np.deg2rad(lons)
            central_lon = np.rad2deg(np.arctan2(np.mean(np.sin(lon_rad)), np.mean(np.cos(lon_rad))))
            remapped_lons = [(((lon - central_lon + 180) % 360) - 180) for lon in lons]
            data_lon_min_remap = np.min(remapped_lons)
            data_lon_max_remap = np.max(remapped_lons)
            data_lon_min = data_lon_min_remap + central_lon
            data_lon_max = data_lon_max_remap + central_lon
            data_lat_min, data_lat_max = np.min(lats), np.max(lats)
            if np.isclose(data_lon_min, data_lon_max): data_lon_max += 1.0
            if np.isclose(data_lat_min, data_lat_max): data_lat_max += 1.0
            # === Step 2: [新規] フォーカスすべき経度(focal_lon)を決定 ===
            focal_lon = None
            # "f"キーで呼ばれた場合 (edgesあり) -> from nodeを優先
            if edges:
                from_nodes = {u for u, v in edges}
                from_lons = [pos[n][0] for n in from_nodes if n in pos]
                if from_lons:
                    # from node群の中心経度を計算
                    from_lon_rad = np.deg2rad(from_lons)
                    focal_lon = np.rad2deg(np.arctan2(np.mean(np.sin(from_lon_rad)), np.mean(np.cos(from_lon_rad))))
            # from nodeがない場合 -> 左端のノードを優先
            if focal_lon is None:
                # 経度を再マッピングした際の最小値が左端のノード
                # remapped_lons と lons は同じ順序なので、argminで元の経度を探す
                leftmost_idx = np.argmin(remapped_lons)
                focal_lon = lons[leftmost_idx]
            # === Step 3: 地図 Axes のアスペクト比を取得 ===
            try:
                bbox = ax.get_window_extent()
                axes_aspect_ratio = bbox.width / bbox.height
            except Exception:
                axes_aspect_ratio = 4 / 3
            # === Step 4: 緯度フィットと水平フォーカスを両立する表示範囲を計算 ===
            data_crs = getattr(self, "_map_data_crs", ccrs.PlateCarree())
            map_crs = ax.projection
            # データの緯度範囲と、focal_lonを投影座標系に変換
            pts_proj = map_crs.transform_points(
                data_crs,
                np.array([focal_lon, focal_lon]),
                np.array([data_lat_min, data_lat_max])
            )
            proj_y_span = abs(pts_proj[1, 1] - pts_proj[0, 1])
            proj_focal_x = pts_proj[0, 0] # 投影座標系でのフォーカス点のX座標
            # 必要な投影X方向の幅を計算
            proj_x_span = proj_y_span * axes_aspect_ratio
            # [修正] フォーカス点を画面の左から1/4の位置にするための新しいX範囲を計算
            proj_x_min = proj_focal_x - (proj_x_span * 0.25)
            proj_x_max = proj_focal_x + (proj_x_span * 0.75)
            # Y範囲はデータの緯度範囲から決定
            proj_y_min = min(pts_proj[0, 1], pts_proj[1, 1])
            proj_y_max = max(pts_proj[0, 1], pts_proj[1, 1])
            # === Step 5: 新しい範囲を緯度経度に戻し、set_extentに渡す ===
            new_bounds_proj = np.array([[proj_x_min, proj_y_min], [proj_x_max, proj_y_max]])
            new_bounds_lonlat = data_crs.transform_points(map_crs,
                new_bounds_proj[:, 0], new_bounds_proj[:, 1]
            )
            extent_lon_min, extent_lat_min = new_bounds_lonlat[0, 0], new_bounds_lonlat[0, 1]
            extent_lon_max, extent_lat_max = new_bounds_lonlat[1, 0], new_bounds_lonlat[1, 1]
            lat_padding = (extent_lat_max - extent_lat_min) * 0.05
            extent = [extent_lon_min, extent_lon_max, extent_lat_min - lat_padding, extent_lat_max + lat_padding]
            if used_cartopy:
                ax.set_extent(extent, crs=data_crs)
            else:
                ax.set_ylim(extent[2], extent[3])
                ax.set_xlim(extent[0], extent[1])
                ax.set_aspect('equal', adjustable='box')
        # =======================================================
# [修正] ======== 水平フォーカス調整（5%）に対応したヘルパー関数 ========
        def _fit_lonlat(lons, lats, edges=None):
            """
            [理由] 緯度フィットを維持しつつ、水平方向のフォーカスを調整する。
                  edgesが与えられればfrom nodeを、なければ左端のノードを優先する。
            """
            if not hasattr(self, "_map_data_crs") or not lons or not lats:
                return
            import numpy as np
            import cartopy.crs as ccrs
            # === Step 1: 表示したいデータの地理的範囲を計算 ===
            lon_rad = np.deg2rad(lons)
            central_lon = np.rad2deg(np.arctan2(np.mean(np.sin(lon_rad)), np.mean(np.cos(lon_rad))))
            remapped_lons = [(((lon - central_lon + 180) % 360) - 180) for lon in lons]
            data_lon_min_remap = np.min(remapped_lons)
            data_lon_max_remap = np.max(remapped_lons)
            data_lon_min = data_lon_min_remap + central_lon
            data_lon_max = data_lon_max_remap + central_lon
            data_lat_min, data_lat_max = np.min(lats), np.max(lats)
            if np.isclose(data_lon_min, data_lon_max): data_lon_max += 1.0
            if np.isclose(data_lat_min, data_lat_max): data_lat_max += 1.0
            # === Step 2: フォーカスすべき経度(focal_lon)を決定 ===
            focal_lon = None
            if edges:
                from_nodes = {u for u, v in edges}
                from_lons = [pos[n][0] for n in from_nodes if n in pos]
                if from_lons:
                    from_lon_rad = np.deg2rad(from_lons)
                    focal_lon = np.rad2deg(np.arctan2(np.mean(np.sin(from_lon_rad)), np.mean(np.cos(from_lon_rad))))
            if focal_lon is None:
                leftmost_idx = np.argmin(remapped_lons)
                focal_lon = lons[leftmost_idx]
            # === Step 3: 地図 Axes のアスペクト比を取得 ===
            try:
                bbox = ax.get_window_extent()
                axes_aspect_ratio = bbox.width / bbox.height
            except Exception:
                axes_aspect_ratio = 4 / 3
            # === Step 4: 緯度フィットと水平フォーカスを両立する表示範囲を計算 ===
            data_crs = getattr(self, "_map_data_crs", ccrs.PlateCarree())
            map_crs = ax.projection
            pts_proj = map_crs.transform_points(
                data_crs,
                np.array([focal_lon, focal_lon]),
                np.array([data_lat_min, data_lat_max])
            )
            proj_y_span = abs(pts_proj[1, 1] - pts_proj[0, 1])
            proj_focal_x = pts_proj[0, 0]
            proj_x_span = proj_y_span * axes_aspect_ratio
            # [修正] フォーカス点を画面の左から5%の位置に変更
            proj_x_min = proj_focal_x - (proj_x_span * 0.05)
            proj_x_max = proj_focal_x + (proj_x_span * 0.95)
            proj_y_min = min(pts_proj[0, 1], pts_proj[1, 1])
            proj_y_max = max(pts_proj[0, 1], pts_proj[1, 1])
            # === Step 5: 新しい範囲を緯度経度に戻し、set_extentに渡す ===
            new_bounds_proj = np.array([[proj_x_min, proj_y_min], [proj_x_max, proj_y_max]])
            new_bounds_lonlat = data_crs.transform_points(map_crs,
                new_bounds_proj[:, 0], new_bounds_proj[:, 1]
            )
            extent_lon_min, extent_lat_min = new_bounds_lonlat[0, 0], new_bounds_lonlat[0, 1]
            extent_lon_max, extent_lat_max = new_bounds_lonlat[1, 0], new_bounds_lonlat[1, 1]
            lat_padding = (extent_lat_max - extent_lat_min) * 0.05
            extent = [extent_lon_min, extent_lon_max, extent_lat_min - lat_padding, extent_lat_max + lat_padding]
            if used_cartopy:
                ax.set_extent(extent, crs=data_crs)
            else:
                ax.set_ylim(extent[2], extent[3])
                ax.set_xlim(extent[0], extent[1])
                ax.set_aspect('equal', adjustable='box')
        # ---- キー別動作 (呼び出し方を修正) ----
        if event.key == "a":
            if pos:
                all_lons = [p[0] for p in pos.values()]
                all_lats = [p[1] for p in pos.values()]
                # "a" (All) の場合はedgesを渡さない
                self._fit_lonlat(all_lons, all_lats, edges=None)
        elif event.key == "w":
            if used_cartopy: ax.set_global()
            else: ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
        elif event.key == "f":
            nodes = set(u for u, v in highlight_edges) | set(v for u, v in highlight_edges)
            if nodes:
                lons = [pos[n][0] for n in nodes if n in pos]
                lats = [pos[n][1] for n in nodes if n in pos]
                if lons and lats:
                    # "f" (Fit) の場合は highlight_edges を渡して from node を判断させる
                    self._fit_lonlat(lons, lats, edges=highlight_edges)
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    def _fit_lonlat(self, lons, lats, edges=None):
        """
        緯度（縦）を枠いっぱいにフィット。
        水平のフォーカスは:
        1) edges があれば from ノード群の中で、
        2) それ以外は全ノードの中で、
        東経を 0..360 に正規化した値が最小の経度を「左端」として採用。
        その左端が 画面の左 5% に来るように投影座標で extent を決める。
        """
        import numpy as np
        import cartopy.crs as ccrs
        ax = getattr(self, "_map_ax", None)
        if ax is None or not lons or not lats:
            return
        def min_east_positive(lon_list):
            if not lon_list:
                return None
            arr = np.asarray(lon_list, dtype=float)
            arr360 = (arr + 360.0) % 360.0
            i = int(np.argmin(arr360))
            return float(arr[i])
        pos = getattr(self, "_map_pos", {})
        focal_candidates = []
        if edges:
            from_nodes = {u for (u, _v) in edges}
            focal_candidates = [pos[n][0] for n in from_nodes if n in pos]
        focal_lon = min_east_positive(focal_candidates) or min_east_positive(lons)
        lat_min = float(np.min(lats))
        lat_max = float(np.max(lats))
        if not np.isfinite(lat_min) or not np.isfinite(lat_max):
            return
        if np.isclose(lat_min, lat_max):
            lat_max = lat_min + 1.0
        lat_min = max(-89.0, lat_min)
        lat_max = min(89.0, lat_max)
        try:
            bbox = ax.get_window_extent()
            axes_aspect = float(bbox.width) / float(bbox.height)
        except Exception:
            axes_aspect = 4.0 / 3.0
        data_crs = getattr(self, "_map_data_crs", ccrs.PlateCarree())
        map_crs = ax.projection
        pts = map_crs.transform_points(
            data_crs,
            np.array([focal_lon, focal_lon], dtype=float),
            np.array([lat_min, lat_max], dtype=float)
        )
        proj_y0, proj_y1 = float(min(pts[0, 1], pts[1, 1])), float(max(pts[0, 1], pts[1, 1]))
        proj_y_span = proj_y1 - proj_y0
        proj_x_span = proj_y_span * axes_aspect
        proj_focal_x = float(pts[0, 0])
        LEFT_FRAC = 0.05
        proj_x0 = proj_focal_x - proj_x_span * LEFT_FRAC
        proj_x1 = proj_focal_x + proj_x_span * (1.0 - LEFT_FRAC)
        pad_y = proj_y_span * 0.05
        proj_y0 -= pad_y
        proj_y1 += pad_y
        ax.set_extent([proj_x0, proj_x1, proj_y0, proj_y1], crs=map_crs)
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    # --- マウス押下：右ボタンならパン開始、左は既存のクリック処理へ委譲 ---
    # 右ボタンだけでパンを開始（左はここでは処理しない）
    def _on_map_button(self, event):
        """右クリックでパン開始。左クリックはここでは扱わない（別ハンドラが処理）。"""
        ax = getattr(self, "_map_ax", None)
        if ax is None or event.inaxes is not ax:
            return
        # 右クリックのみパン開始
        if event.button == 3:
            if event.xdata is None or event.ydata is None:
                return
            self._map_panning = True
            self._map_pan_last = (float(event.xdata), float(event.ydata))
            # スクロール時のピボットにも使えるようピクセル座標も保持
            try:
                self._map_last_pivot_px = (float(event.x), float(event.y))
            except Exception:
                pass
            self._set_map_cursor("pan")
            return
        # 左クリックなどは何もしない（_on_map_click が fig.canvas に接続済み）
    def _on_map_button(self, event):
        """右クリックでパン開始。左クリックはここでは扱わない（別ハンドラが処理）。"""
        ax = getattr(self, "_map_ax", None)
        if ax is None or event.inaxes is not ax:
            return
        # 右クリックのみパン開始
        if event.button == 3:
            if event.xdata is None or event.ydata is None:
                return
            # パン状態・直近位置（投影座標=map座標）を保存
            self._map_panning = True
            self._map_pan_last = (float(event.xdata), float(event.ydata))
            # スクロール時のピボット（投影座標 / ピクセル座標）も保持
            try:
                self._map_last_pivot_map = (float(event.xdata), float(event.ydata))
            except Exception:
                pass
            try:
                self._map_last_pivot_px = (float(event.x), float(event.y))
            except Exception:
                pass
            # ★ 右ドラッグ開始時の位置も lon/lat（データCRS）で保存
            try:
                if getattr(self, "_map_used_cartopy", False):
                    import numpy as np
                    import cartopy.crs as ccrs
                    map_crs  = ax.projection
                    data_crs = getattr(self, "_map_data_crs", ccrs.PlateCarree())
                    pts = data_crs.transform_points(
                        map_crs,
                        np.asarray([event.xdata], dtype=float),
                        np.asarray([event.ydata], dtype=float),
                    )
                    self._map_last_pivot_lonlat = (float(pts[0, 0]), float(pts[0, 1]))
                else:
                    # Cartopy未使用のときは x/y がそのまま lon/lat
                    self._map_last_pivot_lonlat = (float(event.xdata), float(event.ydata))
            except Exception:
                pass
            self._set_map_cursor("pan")
            return
        # 左クリックなどは何もしない（_on_map_click が fig.canvas に接続済み）
        return
    # --- 移動中：右ドラッグでビューポートを平行移動 ---
    def _on_map_motion(self, event):
        if not getattr(self, "_map_panning", False):
            return
        ax = getattr(self, "_map_ax", None)
        if ax is None or event.inaxes is not ax:
            return
        if event.xdata is None or event.ydata is None:
            return
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        x, y = float(event.xdata), float(event.ydata)
        lx, ly = getattr(self, "_map_pan_last", (x, y))
        dx, dy = x - lx, y - ly
        if used_cartopy:
            map_crs = ax.projection
            xmin, xmax, ymin, ymax = ax.get_extent(crs=map_crs)
            # マウスの移動と同じ向きに地図が動くよう、ビューを逆向きにシフト
            ax.set_extent([xmin - dx, xmax - dx, ymin - dy, ymax - dy], crs=map_crs)
        else:
            xmin, xmax = ax.get_xlim()
            ymin, ymax = ax.get_ylim()
            ax.set_xlim(xmin - dx, xmax - dx)
            ax.set_ylim(ymin - dy, ymax - dy)
        self._map_pan_last = (x, y)
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    # --- ボタン離し：パン終了 ---
    def _on_map_release(self, event):
        if getattr(self, "_map_panning", False):
            self._map_panning = False
            self._set_map_cursor(None)
    def _on_map_motion(self, event):
        """
        [新規] マウス移動時の処理
        - 右ドラッグ中: 地図をパン（平行移動）させる
        """
        ax = getattr(self, "_map_ax", None)
        if not self._map_pan_state.get('dragging') or event.inaxes is not ax or event.xdata is None:
            return
        last_x, last_y = self._map_pan_state['last_pos']
        dx = event.xdata - last_x
        dy = event.ydata - last_y
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        if used_cartopy:
            map_crs = ax.projection
            xmin, xmax, ymin, ymax = ax.get_extent(crs=map_crs)
            ax.set_extent([xmin - dx, xmax - dx, ymin - dy, ymax - dy], crs=map_crs)
        else: # 通常のAxes
            xmin, xmax = ax.get_xlim()
            ymin, ymax = ax.get_ylim()
            ax.set_xlim(xmin - dx, xmax - dx)
            ax.set_ylim(ymin - dy, ymax - dy)
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    def _on_map_release(self, event):
        """
        [新規] マウスボタンが離された時の処理
        - 右クリック: パン操作の終了
        """
        if event.button == 3: # 右クリック
            self._map_pan_state['dragging'] = False
            self._map_pan_state['last_pos'] = None
    #@250918 ADD for putting INBOUND nodes on Worlld Map
    def _inject_node_geo_coords(self):
        """
        node.lat / node.lon に DB から緯度経度をセットする。
        - IN / OUT 両方の Node に対応
        - DB には SqlPlanEnv.geo_lookup() でアクセス
        """
        env = getattr(self, "psi", None)
        if not env or not hasattr(env, "geo_lookup"):
            print("[WARN] _inject_node_geo_coords: geo_lookup() not available")
            return
        geo = env.geo_lookup()
        seen = set()
        def _inject(nodes_dict):
            for n in (nodes_dict or {}).values():
                if id(n) in seen:
                    continue
                seen.add(id(n))
                if hasattr(n, "name") and n.name in geo:
                    n.lat, n.lon = geo[n.name]
                for c in getattr(n, "children", []):
                    if id(c) not in seen and hasattr(c, "name") and c.name in geo:
                        c.lat, c.lon = geo[c.name]
                        seen.add(id(c))
        # outbound/inbound 両方に注入
        _inject(getattr(self, "nodes_outbound", {}))
        _inject(getattr(self, "nodes_inbound", {}))
        # または prod_tree_dict_OT / IN も走査対象にするなら：
        if env and hasattr(env, "prod_tree_dict_OT"):
            for _prod, root in env.prod_tree_dict_OT.items():
                self._walk_and_inject_geo(root, geo)
        if env and hasattr(env, "prod_tree_dict_IN"):
            for _prod, root in env.prod_tree_dict_IN.items():
                self._walk_and_inject_geo(root, geo)
    def _walk_and_inject_geo(self, root, geo):
        seen = set()
        def dfs(n):
            if not n or id(n) in seen: return
            seen.add(id(n))
            if getattr(n, "name", None) in geo:
                n.lat, n.lon = geo[n.name]
            for c in getattr(n, "children", []):
                dfs(c)
        dfs(root)
    def show_world_map(self, product_name=None):
        """
        世界地図ビュー（太平洋中心）。選択製品の OUT=青 / IN=緑 を色分け。
        位置情報は DB(node_geo) のみ参照。
        """
        # --- Axes / Figure ---
        self._ensure_network_axes()
        ax = getattr(self, "ax_network", None)
        if ax is None:
            print("[WORLD-MAP] no axes")
            return
        fig = ax.figure
        # --- ノード集合（OUT/IN の両方） ---
        env = getattr(self, "psi", None)
        nodes_all = {}
        if env:
            if getattr(env, "prod_tree_dict_OT", None):
                for _prod, _root in env.prod_tree_dict_OT.items():
                    for n in self._walk_nodes(_root): nodes_all[n.name] = n
            if getattr(env, "prod_tree_dict_IN", None):
                for _prod, _root in env.prod_tree_dict_IN.items():
                    for n in self._walk_nodes(_root): nodes_all[n.name] = n
        if not nodes_all:
            nodes_all = (getattr(self, "nodes_outbound", {}) or {}) | \
                        (getattr(self, "nodes_inbound",  {}) or {})
        # --- DB から geo を取得（必須） ---
        GEO = {}
        if hasattr(env, "geo_lookup"):
            GEO = env.geo_lookup()
        else:
            print("[WORLD-MAP] SqlPlanEnv.geo_lookup() が見つかりません。")
            GEO = {}
        # --- 背景（Cartopy, 太平洋中心） ---
        ax.clear(); ax.set_title("Global Supply Chain Map", fontsize=12)
        used_cartopy = False; data_crs = None
        try:
            import cartopy.crs as ccrs
            import cartopy.feature as cfeature
            from cartopy.io import shapereader as shpreader
            fig = ax.figure; ax.remove()
            proj_map = ccrs.PlateCarree(central_longitude=180)
            ax = fig.add_subplot(111, projection=proj_map)
            self.ax_network = ax
            ax.add_feature(cfeature.OCEAN.with_scale('110m'),  facecolor="#e6f2ff")
            ax.add_feature(cfeature.LAND .with_scale('110m'),  facecolor="#f6f6f6")
            ax.add_feature(cfeature.COASTLINE.with_scale('110m'), linewidth=0.4, edgecolor="#555")
            ax.add_feature(cfeature.BORDERS .with_scale('110m'), linewidth=0.4, edgecolor="#777")
            ax.set_global()
            gl = ax.gridlines(draw_labels=True, linewidth=0.2, color='gray', alpha=0.5, linestyle='--')
            gl.top_labels = gl.right_labels = False
            used_cartopy = True
            data_crs = ccrs.PlateCarree()
        except Exception:
            ax.set_xlim(-180, 180); ax.set_ylim(-90, 90); ax.set_facecolor("#e6f2ff")
        # --- ノード描画 ---
        pos = {}
        hub = {"sales_office", "procurement_office", "supply_point"}
        missing_geo = []
        for name, node in nodes_all.items():
            geo = GEO.get(name)
            if not geo:
                missing_geo.append(name); continue
            lat, lon = float(geo[0]), float(geo[1])
            x, y = lon, lat
            pos[name] = (x, y)
            color = "#1f77b4" if name not in hub else "#444444"
            ms = 15 if name not in hub else 30
            if used_cartopy:
                ax.plot(x, y, "o", ms=max(ms,12), mfc=color, alpha=0.15, mec="none", transform=data_crs, zorder=3)
                ax.plot(x, y, "o", ms=7, mfc=color, mec="white", mew=0.8, transform=data_crs, zorder=4)
                ax.text(x, y, f" {name}", fontsize=8, va="bottom", transform=data_crs, zorder=4)
            else:
                ax.plot(x, y, "o", ms=max(ms,12), mfc=color, alpha=0.15, mec="none", zorder=3)
                ax.plot(x, y, "o", ms=7, mfc=color, mec="white", mew=0.8, zorder=4)
                ax.text(x, y, f" {name}", fontsize=8, va="bottom", zorder=4)
        if missing_geo:
            print(f"[WORLD-MAP] missing geo in DB for nodes (first 20): {missing_geo[:20]}")
        # --- エッジ収集 ---
        all_edges = set()
        G = getattr(self, "G", None)
        if G is not None and hasattr(G, "edges"):
            all_edges = set(G.edges())
        else:
            if env and getattr(env, "prod_tree_dict_OT", None):
                for _prod, _root in env.prod_tree_dict_OT.items():
                    for p, c in self._iter_parent_child(_root):
                        all_edges.add((getattr(p, "name", ""), getattr(c, "name", "")))
            if env and getattr(env, "prod_tree_dict_IN", None):
                for _prod, _root in env.prod_tree_dict_IN.items():
                    for p, c in self._iter_parent_child(_root):
                        all_edges.add((getattr(p, "name", ""), getattr(c, "name", "")))
        # --- 選択品目の OUT/IN を分けてハイライト ---
        highlight_edges_ot, highlight_edges_in = set(), set()
        selected_names = set()
        if product_name and env:
            root_ot = getattr(env, "prod_tree_dict_OT", {}).get(product_name) if getattr(env, "prod_tree_dict_OT", None) else None
            if root_ot:
                for p, c in self._iter_parent_child(root_ot):
                    highlight_edges_ot.add((getattr(p, "name", ""), getattr(c, "name", "")))
                for n in self._walk_nodes(root_ot):
                    if n.name: selected_names.add(n.name)
            root_in = getattr(env, "prod_tree_dict_IN", {}).get(product_name) if getattr(env, "prod_tree_dict_IN", None) else None
            if root_in:
                for p, c in self._iter_parent_child(root_in):
                    highlight_edges_in.add((getattr(p, "name", ""), getattr(c, "name", "")))
                for n in self._walk_nodes(root_in):
                    if n.name: selected_names.add(n.name)
        try:
            import cartopy.crs as ccrs
        except Exception:
            ccrs = None
        def _seg(u, v, color, lw, arrow=False, z=3):
            if u not in pos or v not in pos: return
            x1, y1 = pos[u]; x2, y2 = pos[v]
            if used_cartopy and ccrs:
                ax.plot([x1, x2], [y1, y2], color=color, lw=lw, alpha=0.8, transform=ccrs.Geodetic(), zorder=z)
                if arrow:
                    ax.plot(x2, y2, marker='>', color=color, ms=6, transform=data_crs, zorder=z+1)
            else:
                ax.plot([x1, x2], [y1, y2], color=color, lw=lw, alpha=0.8, zorder=z)
                if arrow:
                    ax.plot(x2, y2, marker='>', color=color, ms=6, zorder=z+1)
        for (u, v) in all_edges:           _seg(u, v, "#cccccc", 1.0, arrow=False, z=3)      # 全体
        for (u, v) in highlight_edges_ot:  _seg(u, v, "royalblue", 2.2, arrow=True,  z=5)    # OUT
        for (u, v) in highlight_edges_in:  _seg(v, u, "seagreen",  2.2, arrow=True,  z=5)    # IN は反転
        # --- 自動フィット（選択品目ノード） ---
        def _wrap_lon(lon, center=180.0): return ((lon - center + 180.0) % 360.0) - 180.0
        fit = bool(getattr(self, "world_map_fit", True))
        if hasattr(self, "world_map_fit_var"):
            try: fit = bool(self.world_map_fit_var.get())
            except Exception: pass
        if pos:
            fit_keys = [k for k in selected_names if k in pos] or list(pos.keys())
            xs = [pos[k][0] for k in fit_keys]; ys = [pos[k][1] for k in fit_keys]
            ymin, ymax = min(ys), max(ys)
            xs_wrapped = [_wrap_lon(x, center=180.0) for x in xs]
            xmin_c, xmax_c = min(xs_wrapped), max(xs_wrapped)
            lon_pad = max(5.0, (xmax_c - xmin_c) * 0.08)
            lat_pad = max(3.0, (ymax - ymin) * 0.10)
            if fit:
                if used_cartopy:
                    ax.set_extent([xmin_c - lon_pad, xmax_c + lon_pad, ymin - lat_pad, ymax + lat_pad],
                                crs=ax.projection)
                else:
                    ax.set_xlim(xmin_c - lon_pad, xmax_c + lon_pad)
                    ax.set_ylim(ymin   - lat_pad, ymax   + lat_pad)
            else:
                ax.set_global() if used_cartopy else (ax.set_xlim(-180, 180), ax.set_ylim(-90, 90))
        # --- 凡例 & 描画 ---
        ax.plot([], [], color="#cccccc", lw=1.2, label="All edges")
        ax.plot([], [], color="royalblue", lw=2.2, label="Outbound (product)")
        ax.plot([], [], color="seagreen",  lw=2.2, label="Inbound (product)")
        ax.legend(loc="lower left", fontsize=8)
        #@STOP
        ## イベント等は既存の実装を踏襲（省略）
        #if hasattr(self, "canvas_network"): self.canvas_network.draw_idle()
        # =========================
        # 状態保存 & イベント再接続
        # =========================
        try:
            if hasattr(self, "_map_cids") and hasattr(self, "_map_canvas"):
                for cid in self._map_cids:
                    self._map_canvas.mpl_disconnect(cid)
        except Exception:
            pass
        self._map_ax           = ax
        self._map_pos          = pos
        self._map_nodes        = nodes_all
        self._map_all_edges    = list(all_edges)
        # ハイライトは OUT/IN をマージして保存（必要なら別属性で分けてもOK）
        self._map_high_edges   = list(highlight_edges_ot | highlight_edges_in)
        self._map_used_cartopy = used_cartopy
        self._map_data_crs     = data_crs
        # イベントは Figure 側の canvas に接続
        canvas = fig.canvas
        self._map_canvas = canvas
        self._map_cids = [
            canvas.mpl_connect("scroll_event",       self._on_map_scroll),
            canvas.mpl_connect("button_press_event", self._on_map_click),
            canvas.mpl_connect("key_press_event",    self._on_map_key),
        ]
        try:
            self.canvas_network.get_tk_widget().focus_set()
        except Exception:
            pass
        # 既存の view 補助（そのまま）
        pts  = self._collect_geo_points()
        mode = "fit" if getattr(self, "world_map_mode", "global") == "fit" else "global"
        self._apply_world_limits(ax, pts, mode)
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
        # 右ドラッグなど
        self._install_map_interactions()
        # === 自動Fit: 起動直後のViewメニュー呼び出し対応 ===
        if self.world_map_fit and hasattr(self, "_map_pos"):
            pos = self._map_pos
            if pos:
                lons = [lon for lon, _ in pos.values()]
                lats = [lat for _, lat in pos.values()]
                self._fit_lonlat(lons, lats, edges=None)
    def _install_map_interactions(self):
        """
        [修正] 投影座標系で動作する安定したパンとズームを接続する
        """
        canvas = getattr(self, "_map_canvas", None)
        if canvas is None:
            return
        # 以前の接続をすべて解除
        for cid in getattr(self, "_map_pan_zoom_cids", []):
            try:
                canvas.mpl_disconnect(cid)
            except Exception:
                pass
        # 状態変数を初期化
        self._map_pan_state = {'dragging': False, 'last_pos': None}
        # 新しいイベントハンドラを接続
        self._map_pan_zoom_cids = [
            canvas.mpl_connect("button_press_event", self._on_map_press),
            canvas.mpl_connect("button_release_event", self._on_map_release),
            canvas.mpl_connect("motion_notify_event", self._on_map_motion),
            canvas.mpl_connect("scroll_event", self._on_map_scroll),
            canvas.mpl_connect("key_press_event", self._on_map_key),
        ]
    def _event_lonlat(self, event):
        """イベント位置を (lon, lat) に変換。Axes 外や変換失敗は None を返す。"""
        ax = getattr(self, "_map_ax", None)
        if ax is None or event.inaxes is not ax:
            return None
        if event.xdata is None or event.ydata is None:
            return None
        used_cartopy = getattr(self, "_map_used_cartopy", False)
        if not used_cartopy:
            return float(event.xdata), float(event.ydata)
        try:
            import cartopy.crs as ccrs, numpy as np
            data_crs = getattr(self, "_map_data_crs", ccrs.PlateCarree())
            map_crs  = ax.projection
            pts = data_crs.transform_points(
                map_crs, np.asarray([event.xdata]), np.asarray([event.ydata])
            )
            return float(pts[0, 0]), float(pts[0, 1])
        except Exception:
            return None
    # ================================
    # View 切替（メニューから呼ぶ）
    # ================================
    def show_network_graph(self):
        """通常のNetworkビューに戻す"""
        self.view_nx_matlib4opt()   # 既存の描画関数をそのまま呼ぶ
        if hasattr(self, "canvas_network"):
            self.canvas_network.draw_idle()
    def show_network_view(self):
        """既存の by-product ネットワーク表示へ戻す。"""
        self._view_mode = "network"
        # 既存の描画関数を再利用
        if hasattr(self, "view_nx_matlib4opt"):
            self.view_nx_matlib4opt()
        # 右側PSIも選択製品で再描画
        prod = getattr(self, "product_selected", None)
        if prod:
            try:
                self.show_psi_by_product("outbound", "demand", prod)
            except Exception:
                # 旧APIなら self.show_psi(...)
                self.show_psi("outbound", "demand")
    def show_world_map_view(self):
        """現在選択中の製品を赤ハイライトして世界地図を表示。"""
        prod = getattr(self, "product_selected", None)
        self.show_world_map(product_name=prod)
    # ================================
    # --- helper: いま選択中の製品を安全に取得 ---
    def _current_product(self):
        try:
            v = self.cb_product.get()
            if v:
                self.product_selected = v
        except Exception:
            pass
        if getattr(self, "product_selected", None):
            return self.product_selected
        lst = getattr(self, "product_name_list", []) or []
        return lst[0] if lst else None
    # --- 現在のビューだけを再描画（ネットワーク or ワールドマップ） ---
    def _redraw_current_view(self, product=None):
        product = product or self._current_product()
        if self.view_mode == "network":
            try:
                if hasattr(self, "view_nx_matlib4opt"):
                    print( "view_nx_matlib4opt is RUN" )
                    self.view_nx_matlib4opt()              # 計画系ネットワーク（by product）
                else:
                    #self.show_network_by_product(product)
                    print( "show_network_graph is RUN" )
                    self.show_network_graph(product)
            except Exception as e:
                print(f"[INFO] network view skipped: {e}")
        elif self.view_mode in ("worldmap", "worldmap_fit"):
            try:
                # 物理系は「全ノード＋選択製品のエッジを赤でハイライト」
                #self.show_world_map(product_name=product)
                self._show_worldmap_global()
                if self.view_mode == "worldmap_fit":
                    #self._fit_world_map_to_data()
                    self._show_worldmap_fit()
            except Exception as e:
                print(f"[INFO] world map view skipped: {e}")
        # 右側のPSIサブプロットは常に選択製品で更新
        if product:
            #self.show_psi_by_product("outbound", "demand", product)
            try:
                #self.show_psi_overview(prod, primary_layer="supply", fallback_to_demand=True)
                self.show_psi_overview(product, primary_layer="supply",
                            fallback_to_demand=True, skip_empty=True)
            except Exception as e:
                print("[WARN] psi overview (on change):", e)
    def _fit_world_map_to_data(self):
        # 既に show_world_map 側で after_idle しているなら不要。保険で用意。
        try:
            pos = getattr(self, "_map_pos", {}) or {}
            if pos:
                lons = [lon for lon, _ in pos.values()]
                lats = [lat for _, lat in pos.values()]
                self._fit_lonlat(lons, lats, edges=None)
        except Exception:
            pass
    # --- メニューからの切替 ---
    def _switch_view(self, mode: str):
        self.view_mode = mode
        self._redraw_current_view(self._current_product())
    #@241225 marked revenueとprofitは、node classにインスタンスあり
    def show_psi_graph4opt(self):
        print("making PSI graph data...")
        self._ensure_plan_window()
        #@STOP
        #self._ensure_psi_area()      # ← これを追加
        week_start = 1
        week_end = self.plan_range * 53
        psi_data = []
        nodes_outbound = self.nodes_outbound  # node辞書{}
        def traverse_nodes(node_opt):
            for child in node_opt.children:
                print("show_psi_graph4opt child.name", child.name)
                traverse_nodes(child)
            node_out = nodes_outbound[node_opt.name]
            collect_psi_data_opt(node_opt, node_out, "supply", week_start, week_end, psi_data)
        # ***************************
        # change ROOT HANDLE
        # ***************************
        traverse_nodes(self.root_node_out_opt)
        fig, axs = plt.subplots(len(psi_data), 1, figsize=(5, len(psi_data) * 1))  # figsizeの高さをさらに短く設定
        if len(psi_data) == 1:
            axs = [axs]
        for ax, (node_name, revenue, profit, profit_ratio, line_plot_data_2I, bar_plot_data_3P, bar_plot_data_0S) in zip(axs, psi_data):
            ax2 = ax.twinx()
            ax.bar(line_plot_data_2I.index, line_plot_data_2I.values, color='r', alpha=0.6)
            ax.bar(bar_plot_data_3P.index, bar_plot_data_3P.values, color='g', alpha=0.6)
            ax2.plot(bar_plot_data_0S.index, bar_plot_data_0S.values, color='b')
            ax.set_ylabel('I&P Lots', fontsize=8)
            ax2.set_ylabel('S Lots', fontsize=8)
            ax.set_title(f'Node: {node_name} | REVENUE: {revenue:,} | PROFIT: {profit:,} | PROFIT_RATIO: {profit_ratio}%', fontsize=8)
            # Y軸の整数設定
            ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
            ax2.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        fig.tight_layout(pad=0.5)
        print("making PSI figure and widget...")
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        canvas_psi = FigureCanvasTkAgg(fig, master=self.scrollable_frame)
        canvas_psi.draw()
        canvas_psi.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    # ==================================================================
    # ファイル: pysi/gui/app.py など（NetworkX描画をしているところ）
    #import networkx as nx
    # ==================================================================
    def view_nx_matlib4opt(self):
        self._ensure_network_axes()  # ← 既存
        ax = self.ax_network
        ax.clear()
    # ==================================================================
        def _iter_parent_child_local(root):
            """root から (parent.name, child.name) を列挙（製品ごと）"""
            if not root:
                return
            st = [root]
            seen = set()
            while st:
                p = st.pop()
                if id(p) in seen:
                    continue
                seen.add(id(p))
                for c in getattr(p, "children", []) or []:
                    yield (getattr(p, "name", ""), getattr(c, "name", ""))
                    st.append(c)
        def _edges_for_product_local(prod_root):
            return [(u, v) for (u, v) in _iter_parent_child_local(prod_root)]
        def _edges_all_products_local(prod_tree_dict_OT):
            E = set()
            for _prod, root in (prod_tree_dict_OT or {}).items():
                for e in _edges_for_product_local(root):
                    E.add(e)
            return list(E)
    # ==================================================================
        # 既存: E2Eグラフ/座標を構築（ここで pos_E2E を作る）
        G = nx.DiGraph()
        Gdm_structure = nx.DiGraph()
        Gsp = nx.DiGraph()
        self.G = G; self.Gdm_structure = Gdm_structure; self.Gsp = Gsp
        pos_E2E, G, Gdm, Gsp = self.show_network_E2E_matplotlib(
            self.root_node_outbound, self.nodes_outbound,
            self.root_node_inbound,  self.nodes_inbound,
            G, Gdm_structure, Gsp
        )
        self.pos_E2E = pos_E2E  # ← “ハンモック座標”を以後も使う
        # ========== ここから描画 ==========
        # ① ノード集合（pos_E2E に存在するものに限定）
        pos = {n: (float(x), float(y)) for n, (x, y) in (pos_E2E or {}).items()}
        nodes_in_pos = list(pos.keys())
        # ② 全製品のエッジ（薄いグレー）
        edges_all = _edges_all_products_local(getattr(self, "prod_tree_dict_OT", {}))
        edges_all = [(u, v) for (u, v) in edges_all if (u in pos and v in pos)]
        # ③ 選択製品のエッジ（赤）
        selected = getattr(self, "product_selected", None)
        root_sel = (getattr(self, "prod_tree_dict_OT", {}) or {}).get(selected)
        edges_sel = _edges_for_product_local(root_sel)
        edges_sel = [(u, v) for (u, v) in edges_sel if (u in pos and v in pos)]
        # --- 描画（※ spring_layout 等は使わず、pos_E2E をそのまま利用） ---
        # ノード
        nx.draw_networkx_nodes(
            G, pos,
            nodelist=nodes_in_pos,
            node_size=26, node_color="#1f77b4",
            edgecolors="white", linewidths=0.6, ax=ax
        )
        # 全エッジ（グレー）
        if edges_all:
            nx.draw_networkx_edges(
                G, pos, edgelist=edges_all,
                width=1.0, edge_color="#cfcfcf", arrows=False, ax=ax
            )
        # 選択製品（赤で上書き）
        if edges_sel:
            nx.draw_networkx_edges(
                G, pos, edgelist=edges_sel,
                width=2.2, edge_color="crimson", arrows=False, ax=ax
            )
        # ラベル
        nx.draw_networkx_labels(
            G, pos, labels={n: n for n in nodes_in_pos},
            font_size=8, font_color="#222", ax=ax
        )
        # タイトル／凡例
        ax.set_axis_off()
        ax.set_title(
            "PySI Optimized Supply Chain Network\n"
            f"Selected: {selected or '-'}",
            fontsize=11
        )
        from matplotlib.lines import Line2D  # ← mlines 未定義エラー対策
        h_all = Line2D([], [], color="#cfcfcf", lw=2, label="All edges")
        h_sel = Line2D([], [], color="crimson", lw=2, label=f"{selected} edges")
        ax.legend(handles=[h_all, h_sel], loc="lower right", fontsize=8)
        # クリックなどのイベントは既存のハンドラを再接続
        try:
            self.canvas_network.draw_idle()
        except Exception:
            pass
        # クリック用初期化（既存）
        self.last_clicked_node = None
        self.annotation_artist = None
        self.canvas_network.mpl_connect('button_press_event', self.on_network_click)
    # ==================================================================
    # Network Graph Helper
    # ==================================================================
    # ---- edges(全製品)とレイアウトのキャッシュ ----
    def _walk_prod_tree(self, root):
        if not root:
            return
        st=[root]; seen=set()
        while st:
            p=st.pop()
            if id(p) in seen:
                continue
            seen.add(id(p))
            for c in getattr(p, "children", []) or []:
                yield getattr(p, "name", ""), getattr(c, "name", "")
                st.append(c)
    def _edges_for_product(self, root):
        return list(self._walk_prod_tree(root))
    def _edges_all_products(self):
        # prod_tree_dict_OT が同一ならキャッシュを返す
        key = id(getattr(self, "prod_tree_dict_OT", {}))
        if getattr(self, "_edges_all_cache_key", None) == key and getattr(self, "_edges_all_cache", None):
            return self._edges_all_cache
        E=set()
        for _prod, root in (getattr(self, "prod_tree_dict_OT", {}) or {}).items():
            for e in self._edges_for_product(root):
                E.add(e)
        self._edges_all_cache = list(E)
        self._edges_all_cache_key = key
        # レイアウトも同時に無効化
        self._pos_all_cache = None
        self._pos_all_cache_sig = None
        return self._edges_all_cache
    def _invalidate_edges_cache(self):
        self._edges_all_cache = None
        self._edges_all_cache_key = None
        self._pos_all_cache = None
        self._pos_all_cache_sig = None
    def _get_pos_all_union(self):
        """
        全製品エッジの和集合から“ハンモック風”の軽量レイアウトを作りキャッシュ。
        spring_layout は使わず、層(深さ)×順番で安定配置する。
        """
        import networkx as nx
        from collections import defaultdict, deque
        E = self._edges_all_products()
        sig = (len(E),)  # 簡易シグネチャ
        if getattr(self, "_pos_all_cache_sig", None) == sig and getattr(self, "_pos_all_cache", None):
            return self._pos_all_cache
        G = nx.DiGraph(); G.add_edges_from(E)
        nodes = list(G.nodes())
        if not nodes:
            self._pos_all_cache = {}
            self._pos_all_cache_sig = sig
            return {}
        # ルート候補（親なし）。無ければ 'supply_point' を優先、さらに無ければ任意の1つ
        roots = [n for n in nodes if G.in_degree(n)==0]
        if not roots:
            roots = ["supply_point"] if "supply_point" in G else [nodes[0]]
        # BFSで深さ（列= x）を決める。複数ルートがあれば最小深さ。
        depth = {}
        for r in roots:
            dq=deque([(r,0)])
            while dq:
                n,d = dq.popleft()
                if d < depth.get(n, 10**9):
                    depth[n]=d
                    for _u,v in G.out_edges(n):
                        dq.append((v,d+1))
        for n in nodes:
            depth.setdefault(n, 0)
        # 同じ深さの中で整列（行= y）。左右中央寄せのために±オフセット。
        by_d = defaultdict(list)
        for n,d in depth.items(): by_d[d].append(n)
        pos = {}
        for d, arr in by_d.items():
            arr_sorted = sorted(arr)
            mid = (len(arr_sorted)-1)/2.0
            for i,n in enumerate(arr_sorted):
                pos[n] = (float(d), float(-(i - mid)))  # x=深さ, y=整列（上がマイナス）
        self._pos_all_cache = pos
        self._pos_all_cache_sig = sig
        return pos
    # ---- debug: dump all product trees ---------------------------------
    def dump_all_product_trees(self, resolved=False, summary_only=False, max_paths_per_side=5):
        """
        全製品について、IN/OUT の root と配下をダンプ。
        resolved=True なら get_roots_for_product() を使って補正後の root を表示。
        summary_only=True なら件数サマリのみ。
        """
        def _nm(n): return getattr(n, "name", None) or "None"
        def _collect(root):
            """root から到達できる (names_set, leaf_paths(list[list[str]]), first_children_names) を返す"""
            names, paths = set(), []
            first_children = [getattr(c, "name", "") for c in (getattr(root, "children", []) or [])]
            if not root:
                return names, paths, first_children
            stack = [(root, [_nm(root)], {id(root)})]  # (node, path_names, seen_ids_on_path)
            while stack:
                node, path, seen = stack.pop()
                names.add(_nm(node))
                children = getattr(node, "children", []) or []
                if not children:
                    paths.append(path)
                    continue
                for c in children:
                    if id(c) in seen:
                        continue  # cycle guard
                    s2 = set(seen); s2.add(id(c))
                    stack.append((c, path + [_nm(c)], s2))
            return names, paths, first_children
        # 対象製品集合（product_name_list が空でも辞書の key から拾う）
        prods = list(self.product_name_list or [])
        keys_ot = set((self.prod_tree_dict_OT or {}).keys())
        keys_in = set((self.prod_tree_dict_IN or {}).keys())
        for k in sorted(keys_ot | keys_in):
            if k not in prods: prods.append(k)
        if not prods:
            print("[DUMP] no products.")
            return
        print(f"[DUMP] products={len(prods)} resolved={resolved} summary_only={summary_only}")
        for p in prods:
            # root の取り出し
            if resolved and hasattr(self, "get_roots_for_product"):
                out_root, in_root = self.get_roots_for_product(p)
            else:
                out_root = (self.prod_tree_dict_OT or {}).get(p)
                in_root  = (self.prod_tree_dict_IN or {}).get(p)
            out_names, out_paths, out_kids = _collect(out_root)
            in_names,  in_paths,  in_kids  = _collect(in_root)
            identical = (out_names == in_names) and bool(out_names)
            print("\n============================================================")
            print(f"[PRODUCT] {p}")
            print(f"  OUT root={_nm(out_root)} | IN root={_nm(in_root)}")
            print(f"  OUT: nodes={len(out_names):3d} leaves={len(out_paths):3d} kids={out_kids}")
            print(f"  IN : nodes={len(in_names):3d} leaves={len(in_paths):3d} kids={in_kids}")
            print(f"  overlap={len(out_names & in_names):3d} | identical={identical}")
            if summary_only:
                continue
            # パスの一部を表示（長すぎ回避）
            def _show_paths(side, paths):
                n = len(paths)
                for i, path in enumerate(paths[:max_paths_per_side], 1):
                    print(f"    {side} path#{i}: " + " -> ".join(path))
                if n > max_paths_per_side:
                    print(f"    {side} ... (+{n - max_paths_per_side} more)")
            _show_paths("OUT", out_paths)
            _show_paths("IN ", in_paths)
    #@250911ADD_250916UPDATING
    def view_nx_matlib4opt(self):
        self._ensure_network_axes()
        ax = self.ax_network
        ax.clear()
        # ---------- helpers (ローカル) ----------
        def _iter_parent_child_local(root):
            if not root:
                return
            st, seen = [root], set()
            while st:
                p = st.pop()
                if id(p) in seen:
                    continue
                seen.add(id(p))
                for c in getattr(p, "children", []) or []:
                    yield (getattr(p, "name", ""), getattr(c, "name", ""))
                    st.append(c)
        def _edges_for_product_local(prod_root):
            return [(u, v) for (u, v) in _iter_parent_child_local(prod_root)]
        # ---------- 既存：ハンモック座標を構築 ----------
        G = nx.DiGraph(); Gdm_structure = nx.DiGraph(); Gsp = nx.DiGraph()
        self.G, self.Gdm_structure, self.Gsp = G, Gdm_structure, Gsp
        #@250916 MEMO use this by product_name tree_root
        # by product select view
        #self.prod_tree_dict_IN = {}
        #self.prod_tree_dict_OT = {}
        #@ ORIGINAL
        #pos_E2E, G, Gdm, Gsp = self.show_network_E2E_matplotlib(
        #    self.root_node_outbound, self.nodes_outbound,
        #    self.root_node_inbound,  self.nodes_inbound,
        #    G, Gdm_structure, Gsp
        #)
        # 選択製品
        selected = getattr(self, "product_selected", None) or (
            self.product_name_list[0] if getattr(self, "product_name_list", None) else None
        )
        if not selected:
            print("[INFO] skip network: no product selected")
            self.canvas_network.draw_idle()
            return
        # ← ここが肝：辞書から “その製品の root” を取り出す
        out_root = (self.prod_tree_dict_OT or {}).get(selected)
        in_root  = (self.prod_tree_dict_IN or {}).get(selected)
        # ******************************************************************
        # ==== debug helpers: root から leaf までのパス＆到達ノードを出力 ====
        def print_all_node_name_from_root2leaf(root, tag=""):
            """root から辿れる全ノード名と、root→leaf の全パスを print。
            戻り値: 到達ノード名の set
            """
            def _nm(n):
                return getattr(n, "name", "")
            if not root:
                print(f"[TREE {tag}] root=None (skip)")
                return set()
            names = set()
            leaf_paths = []
            # stack: (node, path_names, seen_ids_on_path)
            stack = [(root, [_nm(root)], {id(root)})]
            while stack:
                node, path_names, seen_ids = stack.pop()
                names.add(_nm(node))
                children = getattr(node, "children", []) or []
                if not children:
                    # leaf
                    leaf_paths.append(path_names)
                    continue
                for c in children:
                    if id(c) in seen_ids:
                        # cycle guard
                        continue
                    new_seen = set(seen_ids); new_seen.add(id(c))
                    stack.append((c, path_names + [_nm(c)], new_seen))
            print(f"[TREE {tag}] root={_nm(root)} | nodes={len(names)} | leaves={len(leaf_paths)}")
            print(f"[TREE {tag}] nodes: {sorted([n for n in names if n])}")
            for i, p in enumerate(leaf_paths, 1):
                print(f"[TREE {tag}] path#{i}: " + " -> ".join(p))
            return names
        def debug_dump_roots(out_root, in_root):
            """OUT/IN の到達集合と重なりを出す総合ダンプ"""
            out_names = print_all_node_name_from_root2leaf(out_root, tag="OUT")
            in_names  = print_all_node_name_from_root2leaf(in_root,  tag="IN")
            overlap = sorted(out_names & in_names)
            print(f"[TREE] overlap_count={len(overlap)}")
            if overlap:
                print(f"[TREE] overlap: {overlap[:80]}" + (" ..." if len(overlap) > 80 else ""))
        # ******************************************************************
        # ==== ここで中身を確認 ====
        # debug_dump_roots(out_root, in_root)
        # もしくは個別に
        print_all_node_name_from_root2leaf(out_root, tag="OUT")
        print_all_node_name_from_root2leaf(in_root,  tag="IN")
        self.dump_all_product_trees(resolved=False, summary_only=False, max_paths_per_side=5)
        if not (out_root and in_root):
            print(f"[INFO] skip network: missing in/out trees for {selected}"
                f" (out={bool(out_root)}, in={bool(in_root)})")
            self.canvas_network.draw_idle()
            return
        print("[WIRE] selected=", selected,
            "| OUT root=", getattr(out_root, "name", None),
            "| IN root=",  getattr(in_root,  "name", None))
        # 渡すのは dict ではなく root ノード
        pos_E2E, G, Gdm, Gsp = self.show_network_E2E_matplotlib(
            out_root, None,
            in_root,  None,
            G, Gdm_structure, Gsp
        )
        print("pos_E2E test@250916_1624", pos_E2E)
        self.pos_E2E = pos_E2E
        #def _names_in_tree(root_check):
        #    return {getattr(n,'name','') for n in _iter_nodes_preorder(root_check)} if root else set()
        #
        #in_names  = _names_in_tree(self.root_node_inbound)
        #out_names = _names_in_tree(self.root_node_outbound)
        #
        #def _xr(tag, names, pos):
        #    xs = [pos[n][0] for n in names if n in pos]
        #    if xs:
        #        print(f"[LAYOUT] {tag}: minX={min(xs):.2f}, maxX={max(xs):.2f}, n={len(xs)}")
        #_xr("IN ", in_names,  pos_E2E)
        #_xr("OUT", out_names, pos_E2E)
        # **********************************************
        # ---------- 描画 ----------
        pos = {n: (float(x), float(y)) for n, (x, y) in (pos_E2E or {}).items()}
        nodes_in_pos = list(pos.keys())
        # 選択製品の OUT/IN ルート取得
        selected = getattr(self, "product_selected", None)
        root_ot = (getattr(self, "prod_tree_dict_OT", {}) or {}).get(selected)
        root_in = (getattr(self, "prod_tree_dict_IN", {}) or {}).get(selected)
        # 製品ごとのエッジ列（座標が取れるものだけ）
        edges_sel_ot = [(u, v) for (u, v) in _edges_for_product_local(root_ot) if (u in pos and v in pos)]
        edges_sel_in = [(u, v) for (u, v) in _edges_for_product_local(root_in) if (u in pos and v in pos)]
        # ノード
        nx.draw_networkx_nodes(
            G, pos, nodelist=nodes_in_pos,
            node_size=26, node_color="#dddddd",  # ノードは目立たせない薄色に
            edgecolors="white", linewidths=0.6, ax=ax
        )
        # === 調整1: 矢印を付ける / 調整2: 容量で太さを変える ===
        import math
        def _cap_to_width(cap):
            """capacity値→線幅（1.6〜4.0）にマップ。0以下は細く。"""
            try:
                c = float(cap or 0.0)
            except Exception:
                c = 0.0
            if c <= 0:
                return 1.6
            # logスケールで圧縮（cap=10付近でほぼ上限）
            return 1.6 + 2.4 * min(1.0, math.log1p(c) / math.log1p(10.0))
        # OUT（青）
        if edges_sel_ot:
            widths_ot = [
                _cap_to_width(G[u][v].get('capacity', 0.0)) if G.has_edge(u, v) else 2.2
                for (u, v) in edges_sel_ot
            ]
            try:
                nx.draw_networkx_edges(
                    G, pos, edgelist=edges_sel_ot,
                    width=widths_ot, edge_color="royalblue",
                    arrows=True, arrowstyle='-|>', arrowsize=12,
                    min_source_margin=6, min_target_margin=6,
                    ax=ax
                )
            except TypeError:
                # 古いnetworkx/matplotlib環境向けのフォールバック（margin指定なし）
                nx.draw_networkx_edges(
                    G, pos, edgelist=edges_sel_ot,
                    width=widths_ot, edge_color="royalblue",
                    arrows=True, arrowstyle='-|>', arrowsize=12,
                    ax=ax
                )
        # IN（緑）
        if edges_sel_in:
            widths_in = [
                _cap_to_width(G[u][v].get('capacity', 0.0)) if G.has_edge(u, v) else 2.2
                for (u, v) in edges_sel_in
            ]
            try:
                nx.draw_networkx_edges(
                    G, pos, edgelist=edges_sel_in,
                    width=widths_in, edge_color="seagreen",
                    arrows=True, arrowstyle='-|>', arrowsize=12,
                    min_source_margin=6, min_target_margin=6,
                    ax=ax
                )
            except TypeError:
                nx.draw_networkx_edges(
                    G, pos, edgelist=edges_sel_in,
                    width=widths_in, edge_color="seagreen",
                    arrows=True, arrowstyle='-|>', arrowsize=12,
                    ax=ax
                )
        # === 調整3: ラベルを少しだけ上にオフセットして描く ===
        for n, (x, y) in pos.items():
            ax.text(x, y + 0.06, n, fontsize=8, ha='center', va='bottom', color="#222")
        # ---------- 端点オフィスへの灰色コネクタ ----------
        def _extreme_nodes(edges, side="right"):
            if not edges:
                return []
            xs = {}
            for u, v in edges:
                if u in pos: xs[u] = pos[u][0]
                if v in pos: xs[v] = pos[v][0]
            if not xs:
                return []
            extreme = max(xs.values()) if side == "right" else min(xs.values())
            tol = 1e-6
            return [n for n, x in xs.items() if abs(x - extreme) <= tol]
        # OUT側（右端）→ sales_office
        if "sales_office" in pos and edges_sel_ot:
            rights = _extreme_nodes(edges_sel_ot, side="right")
            if rights:
                nx.draw_networkx_edges(
                    G, pos, edgelist=[(n, "sales_office") for n in rights if n in pos],
                    width=1.2, style="dashed", edge_color="#bbbbbb", arrows=False, ax=ax
                )
        # IN側（左端）→ procurement_office
        if "procurement_office" in pos and edges_sel_in:
            lefts = _extreme_nodes(edges_sel_in, side="left")
            if lefts:
                nx.draw_networkx_edges(
                    G, pos, edgelist=[("procurement_office", n) for n in lefts if n in pos],
                    width=1.2, style="dashed", edge_color="#bbbbbb", arrows=False, ax=ax
                )
        # タイトル/凡例
        ax.set_axis_off()
        ax.set_title("PySI Optimized Supply Chain Network\n"
                    f"Selected: {selected or '-'}", fontsize=11)
        from matplotlib.lines import Line2D
        h_out = Line2D([], [], color="royalblue", lw=2, label="Outbound edges")
        h_in  = Line2D([], [], color="seagreen",  lw=2, label="Inbound edges")
        h_con = Line2D([], [], color="#bbbbbb",   lw=1.2, ls="--", label="office connectors")
        ax.legend(handles=[h_out, h_in, h_con], loc="lower right", fontsize=8)
        # 描画
        try:
            self.canvas_network.draw_idle()
        except Exception:
            pass
        # クリック初期化
        self.last_clicked_node = None
        self.annotation_artist = None
        if not hasattr(self, "_network_click_cid") or self._network_click_cid is None:
            self._network_click_cid = self.canvas_network.mpl_connect(
                'button_press_event', self.on_network_click
            )
    def view_nx_matlib4opt(self):
        self._ensure_network_axes()
        ax = self.ax_network
        ax.clear()
        # ---------- helpers (ローカル) ----------
        def _iter_parent_child_local(root):
            if not root:
                return
            st, seen = [root], set()
            while st:
                p = st.pop()
                if id(p) in seen:
                    continue
                seen.add(id(p))
                for c in getattr(p, "children", []) or []:
                    yield (getattr(p, "name", ""), getattr(c, "name", ""))
                    st.append(c)
        def _edges_for_product_local(prod_root):
            return [(u, v) for (u, v) in _iter_parent_child_local(prod_root)]
        # ---------- 既存：ハンモック座標を構築 ----------
        G = nx.DiGraph(); Gdm_structure = nx.DiGraph(); Gsp = nx.DiGraph()
        self.G, self.Gdm_structure, self.Gsp = G, Gdm_structure, Gsp
        # 選択製品
        selected = getattr(self, "product_selected", None) or (
            self.product_name_list[0] if getattr(self, "product_name_list", None) else None
        )
        if not selected:
            print("[INFO] skip network: no product selected")
            self.canvas_network.draw_idle()
            return
        # ← ここが肝：辞書から “その製品の root” を取り出す
        out_root = (self.prod_tree_dict_OT or {}).get(selected)
        in_root  = (self.prod_tree_dict_IN or {}).get(selected)
        # ==== debug helpers: root から leaf までのパス＆到達ノードを出力 ====
        def print_all_node_name_from_root2leaf(root, tag=""):
            def _nm(n): return getattr(n, "name", "")
            if not root:
                print(f"[TREE {tag}] root=None (skip)")
                return set()
            names = set()
            leaf_paths = []
            stack = [(root, [_nm(root)], {id(root)})]
            while stack:
                node, path_names, seen_ids = stack.pop()
                names.add(_nm(node))
                children = getattr(node, "children", []) or []
                if not children:
                    leaf_paths.append(path_names); continue
                for c in children:
                    if id(c) in seen_ids:  # cycle guard
                        continue
                    new_seen = set(seen_ids); new_seen.add(id(c))
                    stack.append((c, path_names + [_nm(c)], new_seen))
            print(f"[TREE {tag}] root={_nm(root)} | nodes={len(names)} | leaves={len(leaf_paths)}")
            print(f"[TREE {tag}] nodes: {sorted([n for n in names if n])}")
            for i, p in enumerate(leaf_paths, 1):
                print(f"[TREE {tag}] path#{i}: " + " -> ".join(p))
            return names
        print_all_node_name_from_root2leaf(out_root, tag="OUT")
        print_all_node_name_from_root2leaf(in_root,  tag="IN")
        self.dump_all_product_trees(resolved=False, summary_only=False, max_paths_per_side=5)
        if not (out_root and in_root):
            print(f"[INFO] skip network: missing in/out trees for {selected}"
                f" (out={bool(out_root)}, in={bool(in_root)})")
            self.canvas_network.draw_idle()
            return
        print("[WIRE] selected=", selected,
            "| OUT root=", getattr(out_root, "name", None),
            "| IN root=",  getattr(in_root,  "name", None))
        # 渡すのは dict ではなく root ノード
        pos_E2E, G, Gdm, Gsp = self.show_network_E2E_matplotlib(
            out_root, None,
            in_root,  None,
            G, Gdm_structure, Gsp
        )
        print("pos_E2E test@250916_1624", pos_E2E)
        self.pos_E2E = pos_E2E
        # ---------- 描画 ----------
        pos = {n: (float(x), float(y)) for n, (x, y) in (pos_E2E or {}).items()}
        nodes_in_pos = list(pos.keys())
        # 選択製品の OUT/IN ルート取得
        selected = getattr(self, "product_selected", None)
        root_ot = (getattr(self, "prod_tree_dict_OT", {}) or {}).get(selected)
        root_in = (getattr(self, "prod_tree_dict_IN", {}) or {}).get(selected)
        # 製品ごとのエッジ列（座標が取れるものだけ）
        edges_sel_ot = [(u, v) for (u, v) in _edges_for_product_local(root_ot) if (u in pos and v in pos)]
        edges_sel_in = [(u, v) for (u, v) in _edges_for_product_local(root_in) if (u in pos and v in pos)]
        # ---------- ノード描画 ----------
        # supply_point は“本部”として別スタイルに
        nodes_non_sp = [n for n in nodes_in_pos if n != "supply_point"]
        nx.draw_networkx_nodes(
            G, pos, nodelist=nodes_non_sp,
            node_size=26, node_color="#dddddd",
            edgecolors="white", linewidths=0.6, ax=ax
        )
        if "supply_point" in pos:
            nx.draw_networkx_nodes(
                G, pos, nodelist=["supply_point"],
                node_size=36, node_shape="s",      # 四角で描画
                node_color="#f5f5f5", edgecolors="#888",
                linewidths=0.8, ax=ax
            )
        # ---------- 本線（OUT/IN） ----------
        # IN は「leaf -> root」向きに見せるため、描画時だけ向きを反転
        edges_sel_in_dir = [(v, u) for (u, v) in edges_sel_in]
        # OUT（青）
        if edges_sel_ot:
            nx.draw_networkx_edges(
                G, pos, edgelist=edges_sel_ot,
                width=2.2, edge_color="royalblue",
                arrows=True, arrowstyle='-|>', arrowsize=12,
                connectionstyle="arc3", ax=ax
            )
        # IN（緑）
        if edges_sel_in_dir:
            nx.draw_networkx_edges(
                G, pos, edgelist=edges_sel_in_dir,
                width=2.2, edge_color="seagreen",
                arrows=True, arrowstyle='-|>', arrowsize=12,
                connectionstyle="arc3", ax=ax
            )
        # ---------- ラベル ----------
        #@250918 STOP
        #import matplotlib.patheffects as pe
        #labels = {n: n for n in nodes_in_pos}
        #_txt = nx.draw_networkx_labels(G, pos, labels=labels,
        #                            font_size=8, font_color="#222", ax=ax)
        #for t in _txt.values():
        #    t.set_path_effects([
        #        pe.Stroke(linewidth=2.5, foreground="white", alpha=0.9),
        #        pe.Normal()
        #    ])
        # ---------- ラベル（少し上にオフセット） ----------
        import matplotlib.patheffects as pe
        def _shift_pos_y(pos_dict: dict[str, tuple[float, float]], dy: float = 0.12):
            """各ノードの描画位置を少し上にずらす"""
            return {n: (x, y + dy) for n, (x, y) in pos_dict.items()}
        LABEL_DY = 0.08  # ← ここを 0.08〜0.18 で調整すると見やすさが変わります
        labels  = {n: n for n in nodes_in_pos}
        pos_lbl = _shift_pos_y(pos, dy=LABEL_DY)
        _txt = nx.draw_networkx_labels(
            G, pos_lbl, labels=labels,
            font_size=8, font_color="#222",
            verticalalignment='bottom',  # va='bottom' でもOK
            horizontalalignment='center',
            #clip_on=True,
            clip_on=False,  # ← ここを False に変更
            ax=ax
        )
        print("250918 testing check")
        # 白フチを付けて読みやすく
        for t in _txt.values():
            t.set_path_effects([
                pe.Stroke(linewidth=2.6, foreground="white", alpha=0.9),
                pe.Normal()
            ])
        # ---------- 事務所への灰色コネクタ（“全 leaf” と接続） ----------
        def _leaf_nodes(edges):
            """与えられた edgelist から葉ノード集合を返す（親に出ないノード）"""
            parents = {u for (u, v) in edges}
            nodes   = set()
            for u, v in edges:
                nodes.add(u); nodes.add(v)
            return [n for n in nodes if n not in parents]
        # 必要ならオフィス座標を用意（無ければ自動で左右に配置）
        def _ensure_office_pos(pos_dict):
            xs = [xy[0] for xy in pos_dict.values()] or [0.0]
            x_min, x_max = min(xs), max(xs)
            y0 = 0.0
            if "sales_office" not in pos_dict:
                pos_dict["sales_office"] = (x_max + 0.6, y0)
            if "procurement_office" not in pos_dict:
                pos_dict["procurement_office"] = (x_min - 0.6, y0)
            return pos_dict
        pos = _ensure_office_pos(pos)
        # officeノードも薄く描いておく（なくても線は引けるが見やすさ向上）
        office_nodes = [n for n in ("sales_office", "procurement_office") if n in pos]
        if office_nodes:
            nx.draw_networkx_nodes(
                G, pos, nodelist=office_nodes,
                node_size=22, node_color="#eeeeee",
                edgecolors="#999", linewidths=0.6, ax=ax
            )
        # OUT: 右側の “全 leaf” を sales_office へ
        if edges_sel_ot:
            ot_leaves = [n for n in _leaf_nodes(edges_sel_ot) if n in pos]
            if ot_leaves:
                nx.draw_networkx_edges(
                    G, pos,
                    edgelist=[(n, "sales_office") for n in ot_leaves],
                    width=1.2, style="dashed", edge_color="#bbbbbb",
                    arrows=False, ax=ax
                )
        # IN: 左側の “全 leaf” を procurement_office から接続
        if edges_sel_in:
            in_leaves = [n for n in _leaf_nodes(edges_sel_in) if n in pos]
            if in_leaves:
                nx.draw_networkx_edges(
                    G, pos,
                    edgelist=[("procurement_office", n) for n in in_leaves],
                    width=1.2, style="dashed", edge_color="#bbbbbb",
                    arrows=False, ax=ax
                )
        # ---------- タイトル/凡例 ----------
        ax.set_axis_off()
        ax.set_title("PySI Optimized Supply Chain Network\n"
                    f"Selected: {selected or '-'}", fontsize=11)
        from matplotlib.lines import Line2D
        h_out = Line2D([], [], color="royalblue", lw=2, label="Outbound edges")
        h_in  = Line2D([], [], color="seagreen",  lw=2, label="Inbound edges")
        h_con = Line2D([], [], color="#bbbbbb",   lw=1.2, ls="--", label="office connectors")
        ax.legend(handles=[h_out, h_in, h_con], loc="lower right", fontsize=8)
        # 描画
        try:
            self.canvas_network.draw_idle()
        except Exception:
            pass
        # クリック初期化
        self.last_clicked_node = None
        self.annotation_artist = None
        if not hasattr(self, "_network_click_cid") or self._network_click_cid is None:
            self._network_click_cid = self.canvas_network.mpl_connect(
                'button_press_event', self.on_network_click
            )
    def view_nx_matlib4opt(self):
        self._ensure_network_axes()
        ax = self.ax_network
        ax.clear()
        # ---------- helpers (ローカル) ----------
        def _iter_parent_child_local(root):
            if not root:
                return
            st, seen = [root], set()
            while st:
                p = st.pop()
                if id(p) in seen:
                    continue
                seen.add(id(p))
                for c in getattr(p, "children", []) or []:
                    yield (getattr(p, "name", ""), getattr(c, "name", ""))
                    st.append(c)
        def _edges_for_product_local(prod_root):
            return [(u, v) for (u, v) in _iter_parent_child_local(prod_root)]
        # ---------- 既存：ハンモック座標を構築 ----------
        G = nx.DiGraph(); Gdm_structure = nx.DiGraph(); Gsp = nx.DiGraph()
        self.G, self.Gdm_structure, self.Gsp = G, Gdm_structure, Gsp
        # 選択製品
        selected = getattr(self, "product_selected", None) or (
            self.product_name_list[0] if getattr(self, "product_name_list", None) else None
        )
        if not selected:
            print("[INFO] skip network: no product selected")
            self.canvas_network.draw_idle()
            return
        # 辞書から “その製品の root” を取り出す
        out_root = (self.prod_tree_dict_OT or {}).get(selected)
        in_root  = (self.prod_tree_dict_IN or {}).get(selected)
        # ==== debug helpers: root→leaf のパス/到達ノードを出力 ====
        def print_all_node_name_from_root2leaf(root, tag=""):
            def _nm(n): return getattr(n, "name", "")
            if not root:
                print(f"[TREE {tag}] root=None (skip)")
                return set()
            names = set()
            leaf_paths = []
            stack = [(root, [_nm(root)], {id(root)})]
            while stack:
                node, path_names, seen_ids = stack.pop()
                names.add(_nm(node))
                children = getattr(node, "children", []) or []
                if not children:
                    leaf_paths.append(path_names); continue
                for c in children:
                    if id(c) in seen_ids:  # cycle guard
                        continue
                    new_seen = set(seen_ids); new_seen.add(id(c))
                    stack.append((c, path_names + [_nm(c)], new_seen))
            print(f"[TREE {tag}] root={_nm(root)} | nodes={len(names)} | leaves={len(leaf_paths)}")
            print(f"[TREE {tag}] nodes: {sorted([n for n in names if n])}")
            for i, p in enumerate(leaf_paths, 1):
                print(f"[TREE {tag}] path#{i}: " + " -> ".join(p))
            return names
        print_all_node_name_from_root2leaf(out_root, tag="OUT")
        print_all_node_name_from_root2leaf(in_root,  tag="IN")
        self.dump_all_product_trees(resolved=False, summary_only=False, max_paths_per_side=5)
        if not (out_root and in_root):
            print(f"[INFO] skip network: missing in/out trees for {selected}"
                f" (out={bool(out_root)}, in={bool(in_root)})")
            self.canvas_network.draw_idle()
            return
        print("[WIRE] selected=", selected,
            "| OUT root=", getattr(out_root, "name", None),
            "| IN root=",  getattr(in_root,  "name", None))
        # 渡すのは dict ではなく root ノード
        pos_E2E, G, Gdm, Gsp = self.show_network_E2E_matplotlib(
            out_root, None,
            in_root,  None,
            G, Gdm_structure, Gsp
        )
        print("pos_E2E test@250916_1624", pos_E2E)
        self.pos_E2E = pos_E2E
        # ---------- 描画 ----------
        pos = {n: (float(x), float(y)) for n, (x, y) in (pos_E2E or {}).items()}
        nodes_in_pos = list(pos.keys())
        # 選択製品の OUT/IN ルート取得
        selected = getattr(self, "product_selected", None)
        root_ot = (getattr(self, "prod_tree_dict_OT", {}) or {}).get(selected)
        root_in = (getattr(self, "prod_tree_dict_IN", {}) or {}).get(selected)
        # 製品ごとのエッジ列（座標が取れるものだけ）
        edges_sel_ot = [(u, v) for (u, v) in _edges_for_product_local(root_ot) if (u in pos and v in pos)]
        edges_sel_in = [(u, v) for (u, v) in _edges_for_product_local(root_in) if (u in pos and v in pos)]
        # ---------- ノード描画 ----------
        # supply_point は“本部”として別スタイルに
        nodes_non_sp = [n for n in nodes_in_pos if n != "supply_point"]
        nx.draw_networkx_nodes(
            G, pos, nodelist=nodes_non_sp,
            node_size=26, node_color="#dddddd",
            edgecolors="white", linewidths=0.6, ax=ax
        )
        if "supply_point" in pos:
            nx.draw_networkx_nodes(
                G, pos, nodelist=["supply_point"],
                node_size=36, node_shape="s",      # 四角で描画
                node_color="#f5f5f5", edgecolors="#888",
                linewidths=0.8, ax=ax
            )
        # ---------- 本線（OUT/IN） ----------
        # IN は「leaf -> root」向きに見せるため、描画時だけ向きを反転
        edges_sel_in_dir = [(v, u) for (u, v) in edges_sel_in]
        # OUT（青）
        if edges_sel_ot:
            nx.draw_networkx_edges(
                G, pos, edgelist=edges_sel_ot,
                width=2.2, edge_color="royalblue",
                arrows=True, arrowstyle='-|>', arrowsize=12,
                connectionstyle="arc3", ax=ax
            )
        # IN（緑）
        if edges_sel_in_dir:
            nx.draw_networkx_edges(
                G, pos, edgelist=edges_sel_in_dir,
                width=2.2, edge_color="seagreen",
                arrows=True, arrowstyle='-|>', arrowsize=12,
                connectionstyle="arc3", ax=ax
            )
        # ========================= ここが追加点 =========================
        # 直線（一列）レイアウトでもラベルが見切れないよう、縦方向に余白を確保
        ys = [y for (_, y) in pos.values()] or [0.0]
        ymin, ymax = min(ys), max(ys)
        if (ymax - ymin) < 1e-6:
            # ほぼ水平一列 → 上下に pad を固定値で追加（データ座標）
            pad = 0.25  # 0.25〜0.5 で調整可
            ax.set_ylim(ymin - pad, ymax + pad)
        else:
            # 多少でも高さがあれば軽めのマージン
            ax.margins(y=0.10)
        # ===============================================================
        # ---------- ラベル（少し上にオフセット） ----------
        import matplotlib.patheffects as pe
        def _shift_pos_y(pos_dict: dict[str, tuple[float, float]], dy: float = 0.12):
            """各ノードの描画位置を少し上にずらす"""
            return {n: (x, y + dy) for n, (x, y) in pos_dict.items()}
        LABEL_DY = 0.08  # 0.08〜0.18 で微調整
        labels  = {n: n for n in nodes_in_pos}
        pos_lbl = _shift_pos_y(pos, dy=LABEL_DY)
        _txt = nx.draw_networkx_labels(
            G, pos_lbl, labels=labels,
            font_size=8, font_color="#222",
            verticalalignment='bottom',
            horizontalalignment='center',
            clip_on=False,   # 余白を入れているのでクリップ不要
            ax=ax
        )
        for t in _txt.values():
            t.set_path_effects([
                pe.Stroke(linewidth=2.6, foreground="white", alpha=0.9),
                pe.Normal()
            ])
        # ---------- 事務所への灰色コネクタ（“全 leaf” と接続） ----------
        def _leaf_nodes(edges):
            """与えられた edgelist から葉ノード集合を返す（親に出ないノード）"""
            parents = {u for (u, v) in edges}
            nodes   = set()
            for u, v in edges:
                nodes.add(u); nodes.add(v)
            return [n for n in nodes if n not in parents]
        # 必要ならオフィス座標を用意（無ければ自動で左右に配置）
        def _ensure_office_pos(pos_dict):
            xs = [xy[0] for xy in pos_dict.values()] or [0.0]
            x_min, x_max = min(xs), max(xs)
            y0 = 0.0
            if "sales_office" not in pos_dict:
                pos_dict["sales_office"] = (x_max + 0.6, y0)
            if "procurement_office" not in pos_dict:
                pos_dict["procurement_office"] = (x_min - 0.6, y0)
            return pos_dict
        pos = _ensure_office_pos(pos)
        # officeノードも薄く描いておく
        office_nodes = [n for n in ("sales_office", "procurement_office") if n in pos]
        if office_nodes:
            nx.draw_networkx_nodes(
                G, pos, nodelist=office_nodes,
                node_size=22, node_color="#eeeeee",
                edgecolors="#999", linewidths=0.6, ax=ax
            )
        # OUT: 右側の “全 leaf” を sales_office へ
        if edges_sel_ot:
            ot_leaves = [n for n in _leaf_nodes(edges_sel_ot) if n in pos]
            if ot_leaves:
                nx.draw_networkx_edges(
                    G, pos,
                    edgelist=[(n, "sales_office") for n in ot_leaves],
                    width=1.2, style="dashed", edge_color="#bbbbbb",
                    arrows=False, ax=ax
                )
        # IN: 左側の “全 leaf” を procurement_office から接続
        if edges_sel_in:
            in_leaves = [n for n in _leaf_nodes(edges_sel_in) if n in pos]
            if in_leaves:
                nx.draw_networkx_edges(
                    G, pos,
                    edgelist=[("procurement_office", n) for n in in_leaves],
                    width=1.2, style="dashed", edge_color="#bbbbbb",
                    arrows=False, ax=ax
                )
        # ---------- タイトル/凡例 ----------
        ax.set_axis_off()
        ax.set_title("PySI Optimized Supply Chain Network\n"
                    f"Selected: {selected or '-'}", fontsize=11)
        from matplotlib.lines import Line2D
        h_out = Line2D([], [], color="royalblue", lw=2, label="Outbound edges")
        h_in  = Line2D([], [], color="seagreen",  lw=2, label="Inbound edges")
        h_con = Line2D([], [], color="#bbbbbb",   lw=1.2, ls="--", label="office connectors")
        ax.legend(handles=[h_out, h_in, h_con], loc="lower right", fontsize=8)
        # 描画
        try:
            self.canvas_network.draw_idle()
        except Exception:
            pass
        # クリック初期化
        self.last_clicked_node = None
        self.annotation_artist = None
        if not hasattr(self, "_network_click_cid") or self._network_click_cid is None:
            self._network_click_cid = self.canvas_network.mpl_connect(
                'button_press_event', self.on_network_click
            )
    def view_nx_matlib4opt(self):
        self._ensure_network_axes()
        ax = self.ax_network
        ax.clear()
        # ---------- helpers (ローカル) ----------
        def _iter_parent_child_local(root):
            if not root:
                return
            st, seen = [root], set()
            while st:
                p = st.pop()
                if id(p) in seen:
                    continue
                seen.add(id(p))
                for c in getattr(p, "children", []) or []:
                    yield (getattr(p, "name", ""), getattr(c, "name", ""))
                    st.append(c)
        def _edges_for_product_local(prod_root):
            return [(u, v) for (u, v) in _iter_parent_child_local(prod_root)]
        # ---------- 既存：ハンモック座標を構築 ----------
        G = nx.DiGraph(); Gdm_structure = nx.DiGraph(); Gsp = nx.DiGraph()
        self.G, self.Gdm_structure, self.Gsp = G, Gdm_structure, Gsp
        # 選択製品
        selected = getattr(self, "product_selected", None) or (
            self.product_name_list[0] if getattr(self, "product_name_list", None) else None
        )
        if not selected:
            print("[INFO] skip network: no product selected")
            self.canvas_network.draw_idle()
            return
        # 辞書から “その製品の root” を取り出す
        out_root = (self.prod_tree_dict_OT or {}).get(selected)
        in_root  = (self.prod_tree_dict_IN or {}).get(selected)
        # ==== debug helpers: root→leaf のパス/到達ノードを出力 ====
        def print_all_node_name_from_root2leaf(root, tag=""):
            def _nm(n): return getattr(n, "name", "")
            if not root:
                print(f"[TREE {tag}] root=None (skip)")
                return set()
            names = set()
            leaf_paths = []
            stack = [(root, [_nm(root)], {id(root)})]
            while stack:
                node, path_names, seen_ids = stack.pop()
                names.add(_nm(node))
                children = getattr(node, "children", []) or []
                if not children:
                    leaf_paths.append(path_names); continue
                for c in children:
                    if id(c) in seen_ids:  # cycle guard
                        continue
                    new_seen = set(seen_ids); new_seen.add(id(c))
                    stack.append((c, path_names + [_nm(c)], new_seen))
            print(f"[TREE {tag}] root={_nm(root)} | nodes={len(names)} | leaves={len(leaf_paths)}")
            print(f"[TREE {tag}] nodes: {sorted([n for n in names if n])}")
            for i, p in enumerate(leaf_paths, 1):
                print(f"[TREE {tag}] path#{i}: " + " -> ".join(p))
            return names
        print_all_node_name_from_root2leaf(out_root, tag="OUT")
        print_all_node_name_from_root2leaf(in_root,  tag="IN")
        self.dump_all_product_trees(resolved=False, summary_only=False, max_paths_per_side=5)
        if not (out_root and in_root):
            print(f"[INFO] skip network: missing in/out trees for {selected}"
                f" (out={bool(out_root)}, in={bool(in_root)})")
            self.canvas_network.draw_idle()
            return
        print("[WIRE] selected=", selected,
            "| OUT root=", getattr(out_root, "name", None),
            "| IN root=",  getattr(in_root,  "name", None))
        # 渡すのは dict ではなく root ノード
        pos_E2E, G, Gdm, Gsp = self.show_network_E2E_matplotlib(
            out_root, None,
            in_root,  None,
            G, Gdm_structure, Gsp
        )
        print("pos_E2E test@250916_1624", pos_E2E)
        self.pos_E2E = pos_E2E
        # ---------- 描画 ----------
        pos = {n: (float(x), float(y)) for n, (x, y) in (pos_E2E or {}).items()}
        nodes_in_pos = list(pos.keys())
        # 選択製品の OUT/IN ルート取得
        selected = getattr(self, "product_selected", None)
        root_ot = (getattr(self, "prod_tree_dict_OT", {}) or {}).get(selected)
        root_in = (getattr(self, "prod_tree_dict_IN", {}) or {}).get(selected)
        # 製品ごとのエッジ列（座標が取れるものだけ）
        edges_sel_ot = [(u, v) for (u, v) in _edges_for_product_local(root_ot) if (u in pos and v in pos)]
        edges_sel_in = [(u, v) for (u, v) in _edges_for_product_local(root_in) if (u in pos and v in pos)]
        # ---------- ノード描画 ----------
        # supply_point は“本部”として別スタイルに
        nodes_non_sp = [n for n in nodes_in_pos if n != "supply_point"]
        nx.draw_networkx_nodes(
            G, pos, nodelist=nodes_non_sp,
            node_size=26, node_color="#dddddd",
            edgecolors="white", linewidths=0.6, ax=ax
        )
        if "supply_point" in pos:
            nx.draw_networkx_nodes(
                G, pos, nodelist=["supply_point"],
                node_size=36, node_shape="s",      # 四角で描画
                node_color="#f5f5f5", edgecolors="#888",
                linewidths=0.8, ax=ax
            )
        # ---------- 本線（OUT/IN） ----------
        # IN は「leaf -> root」向きに見せるため、描画時だけ向きを反転
        edges_sel_in_dir = [(v, u) for (u, v) in edges_sel_in]
        # OUT（青）
        if edges_sel_ot:
            nx.draw_networkx_edges(
                G, pos, edgelist=edges_sel_ot,
                width=2.2, edge_color="royalblue",
                arrows=True, arrowstyle='-|>', arrowsize=12,
                connectionstyle="arc3", ax=ax
            )
        # IN（緑）
        if edges_sel_in_dir:
            nx.draw_networkx_edges(
                G, pos, edgelist=edges_sel_in_dir,
                width=2.2, edge_color="seagreen",
                arrows=True, arrowstyle='-|>', arrowsize=12,
                connectionstyle="arc3", ax=ax
            )
        # ---------- 直線（一列）でもラベル用の縦余白を確保 ----------
        ys = [y for (_, y) in pos.values()] or [0.0]
        ymin, ymax = min(ys), max(ys)
        if (ymax - ymin) < 1e-6:
            pad = 0.35  # 0.25〜0.5 で調整可
            ax.set_ylim(ymin - pad, ymax + pad)
        else:
            ax.margins(y=0.10)
        # ---------- ラベル（ポイント単位オフセット＋複数行対応） ----------
        import matplotlib.patheffects as pe
        import textwrap
        import matplotlib.transforms as mtransforms
        # （任意）ノード名→表示文字列を作る関数：今は名前だけ。将来は改行で情報追加
        def _label_for(n: str) -> str:
            # 例）メタ情報が取れるなら：
            # meta = getattr(self, "node_meta", {}).get(n, {})
            # return f"{n}\nLT:{meta.get('leadtime',1)} wk  Lot:{meta.get('lot_size',1)}"
            return textwrap.fill(n, width=18)  # 長い名前は折り返し
        labels = {n: _label_for(n) for n in nodes_in_pos}
        # 画面上方向へ“ポイント（表示座標）”でオフセット
        DY_PT = 8  # 6〜12 でお好み
        text_trans = mtransforms.offset_copy(ax.transData, fig=ax.figure, x=0, y=DY_PT, units='points')
        # networkx のラベル描画を使わず、自前で描く（transform を差し替えるため）
        for n, (x, y) in pos.items():
            t = ax.text(
                x, y, labels.get(n, n),
                transform=text_trans,
                ha='center', va='bottom',
                fontsize=8, color="#222",
                linespacing=1.1, multialignment='center',
                clip_on=False,
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.0, edgecolor="none")  # 枠を出したければ alpha を上げる
            )
            t.set_path_effects([
                pe.Stroke(linewidth=2.6, foreground="white", alpha=0.9),
                pe.Normal()
            ])
        # ---------- 事務所への灰色コネクタ（“全 leaf” と接続） ----------
        def _leaf_nodes(edges):
            """与えられた edgelist から葉ノード集合を返す（親に出ないノード）"""
            parents = {u for (u, v) in edges}
            nodes   = set()
            for u, v in edges:
                nodes.add(u); nodes.add(v)
            return [n for n in nodes if n not in parents]
        # 必要ならオフィス座標を用意（無ければ自動で左右に配置）
        def _ensure_office_pos(pos_dict):
            xs = [xy[0] for xy in pos_dict.values()] or [0.0]
            x_min, x_max = min(xs), max(xs)
            y0 = 0.0
            if "sales_office" not in pos_dict:
                pos_dict["sales_office"] = (x_max + 0.6, y0)
            if "procurement_office" not in pos_dict:
                pos_dict["procurement_office"] = (x_min - 0.6, y0)
            return pos_dict
        pos = _ensure_office_pos(pos)
        # officeノードも薄く描いておく
        office_nodes = [n for n in ("sales_office", "procurement_office") if n in pos]
        if office_nodes:
            nx.draw_networkx_nodes(
                G, pos, nodelist=office_nodes,
                node_size=22, node_color="#eeeeee",
                edgecolors="#999", linewidths=0.6, ax=ax
            )
        # OUT: 右側の “全 leaf” を sales_office へ
        if edges_sel_ot:
            ot_leaves = [n for n in _leaf_nodes(edges_sel_ot) if n in pos]
            if ot_leaves:
                nx.draw_networkx_edges(
                    G, pos,
                    edgelist=[(n, "sales_office") for n in ot_leaves],
                    width=1.2, style="dashed", edge_color="#bbbbbb",
                    arrows=False, ax=ax
                )
        # IN: 左側の “全 leaf” を procurement_office から接続
        if edges_sel_in:
            in_leaves = [n for n in _leaf_nodes(edges_sel_in) if n in pos]
            if in_leaves:
                nx.draw_networkx_edges(
                    G, pos,
                    edgelist=[("procurement_office", n) for n in in_leaves],
                    width=1.2, style="dashed", edge_color="#bbbbbb",
                    arrows=False, ax=ax
                )
        # ---------- タイトル/凡例 ----------
        ax.set_axis_off()
        ax.set_title("PySI Optimized Supply Chain Network\n"
                    f"Selected: {selected or '-'}", fontsize=11)
        from matplotlib.lines import Line2D
        h_out = Line2D([], [], color="royalblue", lw=2, label="Outbound edges")
        h_in  = Line2D([], [], color="seagreen",  lw=2, label="Inbound edges")
        h_con = Line2D([], [], color="#bbbbbb",   lw=1.2, ls="--", label="office connectors")
        ax.legend(handles=[h_out, h_in, h_con], loc="lower right", fontsize=8)
        # 描画
        try:
            self.canvas_network.draw_idle()
        except Exception:
            pass
        # クリック初期化
        self.last_clicked_node = None
        self.annotation_artist = None
        if not hasattr(self, "_network_click_cid") or self._network_click_cid is None:
            self._network_click_cid = self.canvas_network.mpl_connect(
                'button_press_event', self.on_network_click
            )
    # ==================================================================
    # Safety Gard for World Map Helper
    # ==================================================================
    def _safe_float(self, v):
        try:
            s = str(v).strip()
            if not s:
                return None
            return float(s)
        except Exception:
            return None
    def _collect_geo_points(self):
        """node_geo由来のlon/latが入っているノードだけ抽出"""
        pts = []
        # 物理ノードのリスト／辞書、プロジェクトの実体に合わせてどれか使う
        nodes = []
        if hasattr(self, "nodes_all") and self.nodes_all:
            nodes = self.nodes_all
        elif hasattr(self, "node_dict_by_name") and self.node_dict_by_name:
            nodes = self.node_dict_by_name.values()
        else:
            # 最低限、IN/OUTの集合で代替
            nodes = list(getattr(self, "nodes_outbound", []) or []) + \
                    list(getattr(self, "nodes_inbound", []) or [])
        for n in nodes:
            lon = self._safe_float(getattr(n, "lon", None))
            lat = self._safe_float(getattr(n, "lat", None))
            if lon is None or lat is None:
                continue  # (0,0)落下を防ぐ
            name = getattr(n, "name", getattr(n, "node_name", ""))
            pts.append((lon, lat, name))
        return pts
    def _apply_world_limits(self, ax, pts=None, mode="global"):
        """地図の表示範囲とアスペクトを安定化"""
        ax.set_aspect("equal", adjustable="box")
        if mode == "global" or not pts:
            ax.set_xlim(-180, 180)
            ax.set_ylim(-90, 90)
            return
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        dx = max(3.0, (xmax - xmin) * 0.10)
        dy = max(2.0, (ymax - ymin) * 0.10)
        ax.set_xlim(max(-180, xmin - dx), min(180, xmax + dx))
        ax.set_ylim(max(-90,  ymin - dy), min(90,  ymax + dy))
    # ==================================================================
    # Network Graph Helper
    # ==================================================================
    # ---- edges(全製品)とレイアウトのキャッシュ ----
    def _walk_prod_tree(self, root):
        """PlanNode ツリーを DFS/BFS 風に辿って (parent, child) を列挙"""
        if not root:
            return
        st = [root]
        seen = set()
        while st:
            p = st.pop()
            if id(p) in seen:
                continue
            seen.add(id(p))
            for c in getattr(p, "children", []) or []:
                yield getattr(p, "name", ""), getattr(c, "name", "")
                st.append(c)
    def _edges_for_product(self, root):
        """選択製品のエッジ列挙"""
        return list(self._walk_prod_tree(root))
    def _edges_all_products(self):
        """
        全製品のエッジ（和集合）を返す。
        prod_tree_dict_OT が同一の間はキャッシュを使う。
        """
        key = id(getattr(self, "prod_tree_dict_OT", {}))
        if getattr(self, "_edges_all_cache_key", None) == key and getattr(self, "_edges_all_cache", None):
            return self._edges_all_cache
        E = set()
        for _prod, root in (getattr(self, "prod_tree_dict_OT", {}) or {}).items():
            for e in self._edges_for_product(root):
                E.add(e)
        self._edges_all_cache = list(E)
        self._edges_all_cache_key = key
        # レイアウトも同時に無効化（次回 _get_pos_all_union で再計算）
        self._pos_all_cache = None
        self._pos_all_cache_sig = None
        return self._edges_all_cache
    def _invalidate_edges_cache(self):
        """ツリーを差し替えたときに呼ぶと安全"""
        self._edges_all_cache = None
        self._edges_all_cache_key = None
        self._pos_all_cache = None
        self._pos_all_cache_sig = None
    def _get_pos_all_union(self):
        """
        全製品エッジの和集合から“ハンモック風”の軽量レイアウトを生成（キャッシュ）。
        spring_layout は使わず、層(深さ=x)×行(整列=y)で安定配置。
        """
        import networkx as nx
        from collections import defaultdict, deque
        E = self._edges_all_products()
        sig = (len(E),)  # 簡易シグネチャ
        if getattr(self, "_pos_all_cache_sig", None) == sig and getattr(self, "_pos_all_cache", None):
            return self._pos_all_cache
        G = nx.DiGraph()
        G.add_edges_from(E)
        nodes = list(G.nodes())
        if not nodes:
            self._pos_all_cache = {}
            self._pos_all_cache_sig = sig
            return {}
        # ルート候補（親なし）。無ければ 'supply_point' を優先、さらに無ければ任意の1つ
        roots = [n for n in nodes if G.in_degree(n) == 0]
        if not roots:
            roots = ["supply_point"] if "supply_point" in G else [nodes[0]]
        # BFS で深さ（列=x）を決める（複数ルートがあれば最小深さ）
        depth = {}
        for r in roots:
            dq = deque([(r, 0)])
            while dq:
                n, d = dq.popleft()
                if d < depth.get(n, 10**9):
                    depth[n] = d
                    for _u, v in G.out_edges(n):
                        dq.append((v, d + 1))
        for n in nodes:
            depth.setdefault(n, 0)
        # 同じ深さの中で整列（行=y）。中央寄せっぽく配置
        by_d = defaultdict(list)
        for n, d in depth.items():
            by_d[d].append(n)
        pos = {}
        for d, arr in by_d.items():
            arr_sorted = sorted(arr)
            mid = (len(arr_sorted) - 1) / 2.0
            for i, n in enumerate(arr_sorted):
                pos[n] = (float(d), float(-(i - mid)))  # x=深さ, y=整列（上がマイナス）
        self._pos_all_cache = pos
        self._pos_all_cache_sig = sig
        return pos
# *********************************************************************
# *********************************************************************
    def draw_network4opt_ADD250727(self, G, Gdm, Gsp, pos_E2E, flowDict_opt):
        # 安全に初期化（すでに存在していればスキップ）
        if not hasattr(self, 'annotation_artist'):
            self.annotation_artist = None
        if not hasattr(self, 'last_highlight_node'):
            self.last_highlight_node = None
        if not hasattr(self, 'last_clicked_node'):
            self.last_clicked_node = None
        ## 既存の軸をクリア
        #self.ax_network.clear()
    #def draw_network(self, G, Gdm, Gsp, pos_E2E):
        self.ax_network.clear()  # 図をクリア
        print("draw_network4opt: self.total_revenue", self.total_revenue)
        print("draw_network4opt: self.total_profit", self.total_profit)
        # 評価結果の更新
        ttl_revenue = self.total_revenue
        ttl_profit = self.total_profit
        ttl_profit_ratio = (ttl_profit / ttl_revenue) if ttl_revenue != 0 else 0
        # 四捨五入して表示
        total_revenue = round(ttl_revenue)
        total_profit = round(ttl_profit)
        profit_ratio = round(ttl_profit_ratio * 100, 1)  # パーセント表示
        #ax.set_title(f'Node: {node_name} | REVENUE: {revenue:,} | PROFIT: {profit:,} | PROFIT_RATIO: {profit_ratio}%', fontsize=8)
        # タイトルを設定
        self.ax_network.set_title(f'PySI Optimized Supply Chain Network\nREVENUE: {total_revenue:,} | PROFIT: {total_profit:,} | PROFIT_RATIO: {profit_ratio}%', fontsize=10)
        print("ax_network.set_title: total_revenue", total_revenue)
        print("ax_network.set_title: total_profit", total_profit)
#".format(total_revenue, total_profit))
        self.ax_network.axis('off')
        # *************************
        # contents of network draw START
        # *************************
        # ノードの形状と色を定義
        node_shapes = ['v' if node in self.decouple_node_selected else 'o' for node in G.nodes()]
        node_colors = ['brown' if node in self.decouple_node_selected else 'lightblue' for node in G.nodes()]
        # ノードの描画
        for node, shape, color in zip(G.nodes(), node_shapes, node_colors):
            nx.draw_networkx_nodes(G, pos_E2E, nodelist=[node], node_size=50, node_color=color, node_shape=shape, ax=self.ax_network)
        # エッジの描画
        for edge in G.edges():
            if edge[0] == "procurement_office" or edge[1] == "sales_office":
                edge_color = 'lightgrey'  # "procurement_office"または"sales_office"に接続するエッジはlightgrey
            elif edge in Gdm.edges():
                edge_color = 'blue'  # outbound（Gdm）のエッジは青
            elif edge in Gsp.edges():
                edge_color = 'green'  # inbound（Gsp）のエッジは緑
            else:
                edge_color = 'lightgrey'  # その他はlightgrey
            nx.draw_networkx_edges(G, pos_E2E, edgelist=[edge], edge_color=edge_color, arrows=False, ax=self.ax_network, width=0.5)
        # 最適化pathの赤線表示
        for from_node, flows in flowDict_opt.items():
            for to_node, flow in flows.items():
                if flow > 0:
                    # "G"の上に描画
                    nx.draw_networkx_edges(self.G, self.pos_E2E, edgelist=[(from_node, to_node)], ax=self.ax_network, edge_color='red', arrows=False, width=0.5)
        # ノードラベルの描画
        node_labels = {node: f"{node}" for node in G.nodes()}
        nx.draw_networkx_labels(G, pos_E2E, labels=node_labels, font_size=10, ax=self.ax_network)
        # *************************
        # contents of network draw END
        # *************************
        # ***************************
        # title and axis
        # ***************************
        #plt.title("Supply Chain Network end2end")
        #@ STOOOOOOOP
        #plt.title("Optimized Supply Chain Network")
        #self.ax_network.axis('off')  # 軸を非表示にする
        # *******************
        #@250319 STOP
        # *******************
        ## キャンバスを更新
        self.canvas_network.draw()
        # 🔴 `on_plot_click` 関数の定義（ここに追加）
        #info_window = None  # ノード情報ウィンドウの参照を保持
        # 🔴 `self.info_window` をクラス変数として定義
        self.info_window = None  # ノード情報ウィンドウの参照を保持
        def on_plot_click(event):
            """ クリックしたノードの情報を表示する関数 """
            #global info_window
            clicked_x, clicked_y = event.xdata, event.ydata
            print("clicked_x, clicked_y", clicked_x, clicked_y)
            if clicked_x is None or clicked_y is None:
                return  # クリックがグラフ外の場合は無視
            # クリック位置に最も近いノードを検索
            min_dist = float('inf')
            closest_node = None
            for node, (nx_pos, ny_pos) in pos_E2E.items():
                dist = np.sqrt((clicked_x - nx_pos) ** 2 + (clicked_y - ny_pos) ** 2)
                if dist < min_dist:
                    min_dist = dist
                    closest_node = node
            if closest_node and min_dist < 0.5:  # 誤認識を防ぐための閾値
            #if closest_node and min_dist < 0.1:  # 誤認識を防ぐための閾値
                node_info = f"Node: {closest_node}\nDegree: {G.degree[closest_node]}"
                print("closest_node", closest_node)
                # node情報の取り出し
                if closest_node in self.nodes_outbound:
                    if self.nodes_outbound[closest_node] is not None:
                        select_node = self.nodes_outbound[closest_node]
                    else:
                        print("error: nodes_outbound value is None")
                elif closest_node in self.nodes_inbound:
                    if self.nodes_inbound[closest_node] is not None:
                        select_node = self.nodes_inbound[closest_node]
                    else:
                        print("error: nodes_inbound value is None")
                else:
                    print("error: closest_node not found in nodes_outbound or nodes_inbound")
                # ***************************
                # on_node_click
                # ***************************
                def on_node_click(gui_node, product_name):
                    sku = gui_node.sku_dict.get(product_name)
                    if sku and sku.psi_node_ref:
                        plan_node = sku.psi_node_ref
                        # 🧠 表示項目の例（簡易版）
                        print(f"[{product_name}] @ Node: {gui_node.name}")
                        print("PSI Demand:", plan_node.sku.psi4demand)
                        print("PSI Supply:", plan_node.sku.psi4supply)
                        #print("Cost:", plan_node.sku.cost)
                        print("Revenue:", plan_node.sku.revenue)
                        print("Profit:", plan_node.sku.profit)
                        # GUIに表示したければ、後続で pop-up, graph などに渡す
                # 🔁 Multi Product対応：SKUごとに処理
                for product_name in select_node.sku_dict:
                    on_node_click(select_node, product_name)
                #node_info = f' name: {select_node.name}\n leadtime: {select_node.leadtime}\n demand  : {select_node.nx_demand}\n weight  : {select_node.nx_weight}\n capacity: {select_node.nx_capacity }\n \n Evaluation\n decoupling_total_I: {select_node.decoupling_total_I }\n lot_counts_all    : {select_node.lot_counts_all     }\n \n Settings for cost-profit evaluation parameter}\n LT_boat            : {select_node.LT_boat             }\n SS_days            : {select_node.SS_days             }\n HS_code            : {select_node.HS_code             }\n customs_tariff_rate: {select_node.customs_tariff_rate }\n tariff_on_price    : {select_node.tariff_on_price     }\n price_elasticity   : {select_node.price_elasticity    }\n \n Business Perfirmance\n profit_ratio: {select_node.eval_profit_ratio     }%\n revenue     : {select_node.eval_revenue:,}\n profit      : {select_node.eval_profit:,}\n \n Cost_Structure\n PO_cost     : {select_node.eval_PO_cost        }\n P_cost      : {select_node.eval_P_cost         }\n WH_cost     : {select_node.eval_WH_cost        }\n SGMC        : {select_node.eval_SGMC           }\n Dist_Cost   : {select_node.eval_Dist_Cost      }'
                revenue = round(select_node.eval_cs_price_sales_shipped)
                profit = round(select_node.eval_cs_profit)
                # PROFIT_RATIOを計算して四捨五入
                profit_ratio = round((profit / revenue) * 100, 1) if revenue != 0 else 0
                SGA_total   = round(select_node.eval_cs_SGA_total)
                tax_portion = round(select_node.eval_cs_tax_portion)
                logi_costs  = round(select_node.eval_cs_logistics_costs)
                WH_cost     = round(select_node.eval_cs_warehouse_cost)
                Direct_MTRL = round(select_node.eval_cs_direct_materials_costs)
                node_info = (
    f" name: {select_node.name}\n"
    f" leadtime: {select_node.leadtime}\n"
    f" demand  : {select_node.nx_demand}\n"
    f" weight  : {select_node.nx_weight}\n"
    f" capacity: {select_node.nx_capacity }\n\n"
    f" Evaluation\n"
    f" decoupling_total_I: {select_node.decoupling_total_I }\n"
    f" lot_counts_all    : {select_node.lot_counts_all     }\n\n"
    f" Settings for cost-profit evaluation parameter\n"
    f" LT_boat            : {select_node.LT_boat             }\n"
    f" SS_days            : {select_node.SS_days             }\n"
    f" HS_code            : {select_node.HS_code             }\n"
    f" customs_tariff_rate: {select_node.customs_tariff_rate*100 }%\n"
    f" tariff_on_price    : {select_node.tariff_on_price     }\n"
    f" price_elasticity   : {select_node.price_elasticity    }\n\n"
    f" Business Performance\n"
    f" offering_price_TOBE: {    plan_node.offering_price_TOBE  }\n"
    f" offering_price_ASIS: {    plan_node.offering_price_ASIS  }\n"
    f" profit_ratio: {profit_ratio     }%\n"
    f" revenue     : {revenue:,}\n"
    f" profit      : {profit:,}\n\n"
    #f" profit_ratio: {select_node.eval_cs_profit_ratio     }%\n"
    #f" revenue     : {select_node.eval_cs_revenue:,}\n"
    #f" profit      : {select_node.eval_cs_profit:,}\n\n"
    #f" Tariff_ratio: {select_node.eval_cs_custom_tax}%\n" # これは意味なし
    f" Cost_Structure\n"
    f" SGA_total   : {SGA_total:,}\n"
    f" Custom_tax  : {tax_portion:,}\n"
    f" Logi_costs  : {logi_costs:,}\n"
    f" WH_cost     : {WH_cost:,}\n"
    f" Direct_MTRL : {Direct_MTRL:,}\n"
)
    #f" PO_cost     : {select_node.eval_cs_PO_cost        }\n"
    #f" P_cost      : {select_node.eval_cs_P_cost         }\n"
    #f" WH_cost     : {select_node.eval_cs_WH_cost        }\n"
    #f" SGMC        : {select_node.eval_cs_SGMC           }\n"
    #f" Dist_Cost   : {select_node.eval_cs_Dist_Cost      }"
                ax = self.ax_network
                # 🔴【修正1】 既存のラベルをクリア
                for text in ax.texts:
                    text.remove()
                # `node_info` をネットワーク・グラフの中央下部に固定表示
                #fixed_x, fixed_y = 0.5, 0.1  # Y座標を調整
                fixed_x, fixed_y = 0.5, 0  # Y座標を調整
                ax.text(fixed_x, fixed_y, node_info, fontsize=10, color="red",
                        transform=ax.transAxes, verticalalignment='bottom')
                ## `node_info` をネットワーク・グラフの固定領域に表示（中央下部
                #fixed_x, fixed_y = 0.5, -0.2  # グラフの中央下部に表示する座標（調整可能）
                #ax.text(fixed_x, fixed_y, node_info, fontsize=10, color="red",
                #        transform=ax.transAxes, verticalalignment='top')
                # `closest_node` をクリックしたノードの近くに表示
                ax.text(pos_E2E[closest_node][0], pos_E2E[closest_node][1], closest_node, fontsize=10, color="red")
                #@ STOP
                ## ノードの横に情報を表示
                #ax.text(pos_E2E[closest_node][0], pos_E2E[closest_node][1], node_info, fontsize=10, color="red")
                #
                #ax.text(pos_E2E[closest_node][0], pos_E2E[closest_node][1], closest_node, fontsize=10, color="red")
                # *************************
                # contents of network draw START
                # *************************
                # ノードの形状と色を定義
                node_shapes = ['v' if node in self.decouple_node_selected else 'o' for node in G.nodes()]
                node_colors = ['brown' if node in self.decouple_node_selected else 'lightblue' for node in G.nodes()]
                # ノードの描画
                for node, shape, color in zip(G.nodes(), node_shapes, node_colors):
                        nx.draw_networkx_nodes(G, pos_E2E, nodelist=[node], node_size=50, node_color=color, node_shape=shape, ax=self.ax_network)
                # エッジの描画
                for edge in G.edges():
                        if edge[0] == "procurement_office" or edge[1] == "sales_office":
                                edge_color = 'lightgrey'  # "procurement_office"または"sales_office"に接続するエッジはlightgrey
                        elif edge in Gdm.edges():
                                edge_color = 'blue'  # outbound（Gdm）のエッジは青
                        elif edge in Gsp.edges():
                                edge_color = 'green'  # inbound（Gsp）のエッジは緑
                        else:
                                edge_color = 'lightgrey'  # その他はlightgrey
                        nx.draw_networkx_edges(G, pos_E2E, edgelist=[edge], edge_color=edge_color, arrows=False, ax=self.ax_network, width=0.5)
                # 最適化pathの赤線表示
                for from_node, flows in flowDict_opt.items():
                        for to_node, flow in flows.items():
                                if flow > 0:
                                        # "G"の上に描画
                                        nx.draw_networkx_edges(self.G, self.pos_E2E, edgelist=[(from_node, to_node)], ax=self.ax_network, edge_color='red', arrows=False, width=0.5)
                # ノードラベルの描画
                node_labels = {node: f"{node}" for node in G.nodes()}
                nx.draw_networkx_labels(G, pos_E2E, labels=node_labels, font_size=10, ax=self.ax_network)
                # *************************
                # contents of network draw END
                # *************************
                #canvas.draw()  # 再描画
                self.canvas_network.draw()  # 再描画
                # 🔴【修正2】 既存のウィンドウを閉じる
                if self.info_window is not None:
                    self.info_window.destroy()
                # 新しい情報ウィンドウを作成
                show_info_graph(node_info, select_node)
                #self.show_info_graph(node_info, select_node)
                #show_info_graph(node_info)
        def show_info_graph(node_info, select_node):
                """ ノード情報を表示する Tkinter ウィンドウ + 円グラフ """
                if self.info_window is not None:
                        self.info_window.destroy()
                self.info_window = tk.Toplevel(self.root)
                self.info_window.title("Node Information")
                labels = ['Profit', 'SG&A', 'Tax Portion', 'Logistics', 'Warehouse', 'Materials']
                values = [
                        select_node.eval_cs_profit,
                        select_node.eval_cs_SGA_total,
                        select_node.eval_cs_tax_portion,
                        select_node.eval_cs_logistics_costs,
                        select_node.eval_cs_warehouse_cost,
                        select_node.eval_cs_direct_materials_costs,
                ]
                colors = ['blue', 'orange', 'green', 'red', 'purple', 'brown']  # 各項目の固定色
                # 売上（収益）から非ゼロ構成のみ抽出
                filtered = [(label, val, color) for label, val, color in zip(labels, values, colors) if val > 0]
                if not filtered:
                        filtered = [('No Data', 1, 'gray')]
                labels, values, colors = zip(*filtered)
                fig, ax = plt.subplots(figsize=(5, 4))
                ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90, colors=colors)
                ax.set_title(select_node.name, fontsize=9)  # `node_info` ではなく `node_name` をタイトルに設定
                #ax.set_title(node_info, fontsize=9)  # `node_info` ではなく `node_name` をタイトルに設定
                # Tkinter の Frame に Matplotlib のグラフと node_info を配置
                frame = tk.Frame(self.info_window)
                frame.pack()
                canvas = FigureCanvasTkAgg(fig, frame)
                canvas.get_tk_widget().grid(row=0, column=0)
                canvas.draw()
                # node_info を右横に表示
                info_label = tk.Label(frame, text=node_info, justify='left', padx=10, font=("Arial", 10), fg='darkblue')
                info_label.grid(row=0, column=1, sticky='nw')
                #info_label = tk.Label(frame, text=node_info, justify='left', padx=10, font=("Arial", 10))
                #info_label.grid(row=0, column=1, sticky='nw')
                #canvas = FigureCanvasTkAgg(fig, self.info_window)
                #canvas.get_tk_widget().pack()
                #canvas.draw()
        # 🔴 `mpl_connect` でクリックイベントを登録（ここに追加）
        #canvas.mpl_connect('button_press_event', on_plot_click)
        self.canvas_network.mpl_connect('button_press_event', on_plot_click)
        #@STOP
        ## Tkinter メインループ開始
        #self.root.mainloop()
        # 既存描画コードまま...
        # self.ax_network.clear()
        # ノード／エッジ描画
        # self.canvas_network.draw()
        # annotation_artist 初期化
        if self.annotation_artist:
            self.annotation_artist.remove()
        self.annotation_artist = None
    def _update_info_window(self, node_name, select_node):
        # info_window 存在チェック
        if self.info_window and tk.Toplevel.winfo_exists(self.info_window):
            # 再利用のため destroy せず既存ウィンドウを更新する方法も可
            self.info_window.destroy()
        # show_info_graph を呼び出し
        self.show_info_graph(node_name, select_node)
#@250916 ADD
    # ===== PSIPlannerApp クラス内に追加 =====
    def _name2node_from_roots(self, out_root, in_root):
        """OUT/IN の root から name->Node マップを作る（後勝ちで上書き）。"""
        def _walk(n):
            st = [n]; seen = set()
            while st:
                x = st.pop()
                if id(x) in seen: continue
                seen.add(id(x))
                yield x
                for c in getattr(x, "children", []) or []:
                    st.append(c)
        m = {}
        for r in (out_root, in_root):
            if not r: continue
            for n in _walk(r):
                nm = getattr(n, "name", "")
                if nm: m[nm] = n
        return m
    # **********************
    # show_offering_price_board
    # **********************
    # **** helper ****
    def _resolve_db_path(self) -> str | None:
        """
        よく使われる属性や既定場所から DB パスを推測して確定する。
        見つかれば self.db_path に保存して返す。
        """
        candidates: list[str] = []
        # 既存フィールド候補（あなたのアプリで使っていそうな名前を網羅）
        for name in ("db_path", "DB_path", "sqlite_path", "DBfile"):
            v = getattr(self, name, None)
            if isinstance(v, str) and v.strip():
                candidates.append(v)
        # Tk の StringVar 等も拾う
        for name in ("DB_path_var",):
            v = getattr(self, name, None)
            try:
                s = v.get()
                if isinstance(s, str) and s.strip():
                    candidates.append(s)
            except Exception:
                pass
        # 既定の相対パスも試す
        candidates += [
            os.path.join(os.getcwd(), "var", "psi.sqlite"),
            os.path.join(os.path.dirname(__file__), "..", "var", "psi.sqlite"),
            os.path.join(os.path.dirname(__file__), "..", "..", "var", "psi.sqlite"),
        ]
        # ファイルが存在する最初のものを採用
        for p in candidates:
            if p and os.path.isfile(p):
                self.db_path = os.path.abspath(p)
                return self.db_path
        # 見つからなかった
        print("[offering_price] DB path not resolved. tried:", candidates)
        return None
    
    def show_offering_price_board(self, products=None, tobe_mode="root_scale"):
        """
        製品ごとに全ノードの offering_price(ASIS/TOBE) を棒グラフで表示。
        - products: None -> 全製品, "selected" -> GUIの選択製品のみ, あるいは製品名のリスト
        - tobe_mode: 'root_scale' なら、TOBE未設定ノードも root比で補完
        """
        #@STOP
        #db_path = getattr(self, "db_path", None) or getattr(self, "DB_path", None)
        db_path = self._resolve_db_path()
        
        
        if not db_path:
            from tkinter import messagebox
            messagebox.showerror("Error", "DB path not found.")
            return
        
        # データ組み立て
        #df = build_offering_price_frame(db_path, prefer_calc_as_is=True, tobe_mode=tobe_mode)
        
        #dbp = get_db_path_from(self.psi if hasattr(self, "psi") else self)
        df = build_offering_price_frame(
            db_path=db_path,
            scenario_id=self.active_scenario_id,   # ← ここがポイント
            prefer_calc_as_is=True,
            tobe_mode="root_scale",
        )
        
        
        
        # プロダクト選択
        if products == "selected":
            prod = getattr(self, "product_selected", None)
            if not prod:
                from tkinter import messagebox
                messagebox.showwarning("Warning", "No product selected. Showing all.")
                products = None
            else:
                products = [prod]
        elif products is None:
            products = sorted(df["product_name"].unique().tolist())
        elif isinstance(products, str):
            products = [products]
        # Figure 作成
        fig = plot_offering_price_grid(df, products=products, ncols=2, height_per_row=3.0, width=12.0)
        # Toplevel へ埋め込み
        import tkinter as tk
        if getattr(self, "price_window", None) and self.price_window.winfo_exists():
            self.price_window.destroy()
        self.price_window = tk.Toplevel(self.root)
        self.price_window.title("Offering Price Propagation")
        canvas = FigureCanvasTkAgg(fig, master=self.price_window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self._price_canvas = canvas
        self._price_fig = fig





    # **********************
    # PIE graph NEW
    # **********************
    # ==========================================
    # Cost pie helpers (DB優先 / 暫定フォールバック)
    # ==========================================
    def _cost_palette(self):
        # ラベル→色（大小文字・別名も吸収）
        return {
            "Direct Materials":       "#1f77b4",
            "Direct materials":       "#1f77b4",   # alias（フォールバックで出やすい）
            "Materials":              "#1f77b4",   # alias
            "Tariff":                 "#d62728",
            "Logistics":              "#2ca02c",
            "Warehouse":              "#17becf",
            "Marketing":              "#ff7f0e",
            "Sales Admin":            "#bcbd22",
            "Prod Indirect Labor":    "#9467bd",
            "Prod Indirect Others":   "#8c564b",
            "Direct Labor":           "#7f7f7f",
            "Depreciation":           "#e377c2",
            "Mfg Overhead":           "#aec7e8",
            "Profit":                 "#2c3e50",
            # フォールバック旧キー
            "Processing":             "#9467bd",
            "Overhead":               "#8c564b",
        }
    def _canon_label(self, lbl: str) -> str:
        # ラベル正規化（表示も色も安定）
        m = {
            "direct materials": "Direct Materials",
            "materials":        "Direct Materials",
            "direct material":  "Direct Materials",
        }
        key = (lbl or "").strip().lower()
        return m.get(key, lbl)
    def _get_cost_row(self, product_name: str, node_name: str):
        """
        self.cost_df から対象行（Series）を返す。無ければ None。
        大小文字・前後空白の差異を吸収。見つからない場合は候補をログ。
        """
        def _norm_key(s: str) -> str:
            return (s or "").strip().upper()
        cdf = getattr(self, "cost_df", None)
        if cdf is None:
            print("[pie] cost_df is None (build_cost_df_from_sql not executed yet?)")
            return None
        try:
            pm = cdf["product_name"].astype(str).str.strip()
            nm = cdf["node_name"].astype(str).str.strip()
            hit = cdf[ (pm.str.upper()==_norm_key(product_name)) & (nm.str.upper()==_norm_key(node_name)) ]
            if not hit.empty:
                return hit.iloc[0]
            # 見つからなければ候補をログ
            avail_nodes = cdf.loc[pm.str.upper()==_norm_key(product_name), "node_name"].unique().tolist()
            print(f"[pie] row not found: product={product_name}, node={node_name}. candidates={avail_nodes}")
        except Exception as e:
            print(f"[pie] lookup error: {e}")
        return None
    def _collect_cost_components_fallback(self, node):
        """
        旧：Node属性から暫定で拾う（self.cost_df が無い/行が無い時のみ使用）
        ラベルは正規化して返す（色と表示安定化のため）。
        """
        pairs = [
            ("Direct materials", getattr(node, "unit_cost_dm", None)),
            ("Tariff",           getattr(node, "unit_cost_tariff", None)),
            ("Processing",       getattr(node, "unit_cost_proc", None)),
            ("Logistics",        getattr(node, "unit_cost_logistics", None)),
            ("Overhead",         getattr(node, "unit_cost_oh", None)),
        ]
        comps = []
        for k, v in pairs:
            if v is None:
                continue
            fv = float(v)
            if fv > 0.0:
                comps.append((self._canon_label(k), fv))
        return comps
    def _collect_cost_components(self, product_name: str, node_name: str, node=None):
        """
        DB優先でコスト辞書を構築。無ければ node 属性からフォールバック。
        戻り値: (labels, values[0..1], total_money)
        """
        row = self._get_cost_row(product_name, node_name)
        if row is not None:
            cost_dict = build_cost_pie_dict(row)              # money辞書
            ratios, total = pie_normalize(cost_dict, mode="ratio")
            # 0の項目は非表示（必要ならここを変えて全表示に）
            labels = [self._canon_label(k) for k, v in ratios.items() if v > 0]
            values = [ratios[k] for k in ratios if self._canon_label(k) in labels]
            return labels, values, float(total)
        # ---- フォールバック ----
        comps = self._collect_cost_components_fallback(node)
        if not comps:
            return [], [], 0.0
        labels, money = zip(*comps)
        money = [max(0.0, float(x)) for x in money]
        total = sum(money)
        values = [m/total for m in money] if total > 0 else [0.0 for _ in money]
        return list(labels), list(values), float(total)
    def show_node_cost_pie(self, node):
        """選択ノードのコスト円グラフを Toplevel に表示（DBが無い場合はフォールバック）。"""
        if node is None:
            return
        product = getattr(self, "product_selected", None)
        node_name = getattr(node, "name", None) or getattr(node, "node_name", None)
        labels, values, total = self._collect_cost_components(product, node_name, node=node)
        title = f"Cost Structure : {node_name}"
        # 既存 info_window を閉じる（再利用しない）
        if getattr(self, "info_window", None) and self.info_window.winfo_exists():
            self.info_window.destroy()
        self.info_window = tk.Toplevel(self.root)
        self.info_window.title(title)
        fig = Figure(figsize=(3.8, 3.8), dpi=110)
        ax = fig.add_subplot(111)
        if not labels or sum(values) <= 0.0:
            tk.Label(self.info_window, text="No cost data for this node").pack(padx=16, pady=16)
            return
        # 1要素でも確実に見えるように色を決定
        palette = self._cost_palette()
        colors = [palette.get(lbl, "#999999") for lbl in labels]
        # 割合と金額を両方表示
        def _fmt(pct):
            val = pct * total / 100.0
            return f"{pct:.0f}%\n({val:,.0f})" if total >= 10 else f"{pct:.0f}%\n({val:.2g})"
        wedges, texts, autotexts = ax.pie(
            values,
            labels=labels,
            autopct=_fmt,
            startangle=90,
            counterclock=False,
            pctdistance=0.72,
            labeldistance=1.05,
            colors=colors,
            wedgeprops=dict(linewidth=0.8, edgecolor="white")
        )
        ax.set_aspect('equal')
        ax.set_title(title, fontsize=10, pad=10)
        # 中央に合計（money）表示
        ax.text(0, 0, f"Total\n{total:,.0f}", ha="center", va="center", fontsize=10, color="#333")
        canvas = FigureCanvasTkAgg(fig, master=self.info_window)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self._cost_canvas = canvas
        self._cost_fig = fig
    def on_network_click(self, event):
        """ネットワーク図クリック: 最寄りノードを特定してコスト円グラフを表示。"""
        if event.inaxes is None or event.inaxes != getattr(self, "ax_network", None):
            return
        if event.xdata is None or event.ydata is None:
            return
        pos = getattr(self, "pos_E2E", {}) or {}
        if not pos:
            return
        cx, cy = float(event.xdata), float(event.ydata)
        closest = min(pos.items(), key=lambda kv: (kv[1][0] - cx) ** 2 + (kv[1][1] - cy) ** 2)
        name, (nx_, ny_) = closest
        dist2 = (nx_ - cx) ** 2 + (ny_ - cy) ** 2
        if dist2 > 0.20 ** 2:
            return
        selected = getattr(self, "product_selected", None)
        out_root = (getattr(self, "prod_tree_dict_OT", {}) or {}).get(selected)
        in_root  = (getattr(self, "prod_tree_dict_IN", {}) or {}).get(selected)
        name2node = self._name2node_from_roots(out_root, in_root)
        node = name2node.get(name)
        self.show_node_cost_pie(node)