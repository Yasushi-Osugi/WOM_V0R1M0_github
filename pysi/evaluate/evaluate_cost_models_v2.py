# evaluate_cost_models_v2.py
# --------------------------------------------
# 概要：Multi-Product対応の価格・コスト構造逆伝播／順伝播ロジック
# --------------------------------------------
import csv
import os
import tkinter as tk
from tkinter import filedialog, messagebox
# --------------------------------------------
# Utils
# --------------------------------------------
def get_tariff_rate(product_name, from_node, to_node, tariff_table):
    key = (product_name.strip(), from_node.strip(), to_node.strip())
    return tariff_table.get(key, 0.0)
# --------------------------------------------
# 下流 -> 上流へ価格逆算（LeafからRootへ）
# --------------------------------------------
def evaluate_price_TOBE(leaf_node, product_name, tariff_table):
    node = leaf_node
    print(f"[TOBE Init] Leaf {node.name} offering_price = {node.offering_price_TOBE:.2f}")
    while node.parent:
        #child = node
        #node = node.parent
        parent = node.parent
        #child_price = child.offering_price_TOBE
        node_price = node.offering_price_TOBE
        # 関税率を取得
        #tariff_rate = get_tariff_rate(product_name, node.name, child.name, tariff_table)
        tariff_rate = get_tariff_rate(product_name, parent.name, node.name, tariff_table)
        #node.cs_tariff_rate = tariff_rate
        node.tariff_rate = tariff_rate
        # その他のコスト合計
        # "cs_xxx"はprice=100とする比率で表現されている
        other_costs = (
            node.cs_logistics_costs +
            node.cs_warehouse_cost +
            node.cs_fixed_cost +
            node.cs_profit
        )
        # offering_priceを関税込みで割り戻す
        #node.offering_price_TOBE = (child_price - other_costs) / (1 + tariff_rate)
        #parent.offering_price_TOBE = (node_price - other_costs) / (1 + tariff_rate)
        parent.offering_price_TOBE = node_price * ( 1 - other_costs/100 ) / (1 + tariff_rate)
        # 関税コストを改めて算出
        #node.cs_tariff_cost = tariff_rate * node.offering_price_TOBE
        node.tariff_cost = tariff_rate * node.offering_price_TOBE
        print(f"[TOBE] {parent.name} -> {node.name} : offering_price = {node.offering_price_TOBE:.2f}")
        node = parent
# --------------------------------------------
# 上流 -> 下流へ価格展開（RootからLeafへ）
# --------------------------------------------
def evaluate_price_ASIS(root_node, product_name, tariff_table):
    queue = [root_node]
    print(f"[ASIS Init] Root {root_node.name} offering_price = {root_node.offering_price_ASIS:.2f}")
    while queue:
        node = queue.pop(0)
        for child in node.children:
            # 関税率を取得
            tariff_rate = get_tariff_rate(product_name, node.name, child.name, tariff_table)
            #child.cs_tariff_rate = tariff_rate
            child.tariff_rate = tariff_rate
            # 原材料費 = 親ノード価格 × (1 + 関税率)
            #child.cs_material_cost = node.offering_price_ASIS * (1 + tariff_rate)
            child.direct_materials_costs = node.offering_price_ASIS * (1 + tariff_rate)
            # その他コスト + 利益を加味して子ノードの販売価格ASISを算出
            # "cs_xxx"はprice=100とする比率で表現されている
            child.offering_price_ASIS = (
                child.direct_materials_costs +    # purchase(=materials) + tariff
                node.offering_price_ASIS * (      # Cost Stracture without purchase
                child.cs_logistics_costs +
                child.cs_warehouse_cost +
                child.cs_fixed_cost +
                child.cs_profit ) / 100
            )
            #child.offering_price_ASIS = (
            #    child.cs_material_cost +
            #    child.cs_logistics_costs +
            #    child.cs_warehouse_cost +
            #    child.cs_fixed_cost +
            #    child.cs_profit
            #)
            # 関税コストも計算
            #child.cs_tariff_cost = tariff_rate * node.offering_price_ASIS
            child.tariff_cost = tariff_rate * node.offering_price_ASIS
            print(f"[ASIS] {node.name} -> {child.name} : offering_price = {child.offering_price_ASIS:.2f}")
            queue.append(child)
def evaluate_outbound_price_v2(leaf_node, product_name, tariff_table):
    node = leaf_node
    while node.parent:
        parent = node.parent
        downstream_price = parent.price_sales_shipped # 仕入価格
        tariff_rate = get_tariff_rate(product_name, parent.name, node.name, tariff_table)
        tariff_cost = tariff_rate * downstream_price # 関税コスト
        node.cs_tax_portion = tariff_cost
        #@250803
        print("node, tariff_rate", node.name, tariff_rate)
        print("node, tariff_cost", node.name, tariff_cost)
        #node.cs_tariff_rate = tariff_rate
        #node.cs_tariff_cost = tariff_cost
        node.tariff_rate = tariff_rate
        node.tariff_cost = tariff_cost
        node.cs_price_sales_shipped = downstream_price + ( tariff_cost
            + node.cs_logistics_costs
            + node.cs_warehouse_cost
            + node.cs_fixed_cost
            # + node.cs_direct_materials_costs
            # + node.other_cost
            + node.cs_profit
            )
        #node.price = downstream_price - (
        #    node.transport_cost + node.storage_cost + tariff_cost +
        #    node.fixed_cost + node.other_cost
        #)
        #sku = parent.sku
        #downstream_price = node.sku.price
        #tariff_rate = get_tariff_rate(product_name, parent.name, node.name, tariff_table)
        #tariff_cost = tariff_rate * downstream_price
        #sku.tariff_cost = tariff_cost
        #sku.price = downstream_price - (
        #    sku.transport_cost + sku.storage_cost + tariff_cost +
        #    sku.fixed_cost + sku.other_cost
        #)
        print(f"[OutPrice] {parent.name} <- {node.name} : price = {node.cs_price_sales_shipped:.2f}")
        #print(f"[OutPrice] {parent.name} <- {node.name} : price = {sku.price:.2f}")
        node = parent
# 全Leafに対して実行
#@STOP
#def evaluate_outbound_price_all_v2(leaf_nodes, product_name, tariff_table):
#    for leaf in leaf_nodes:
#        #evaluate_outbound_price_v2(leaf, product_name, tariff_table)
#        evaluate_price_TOBE(leaf, product_name, tariff_table)
# ******************************************
#@250807 STOP TOBE Re-Write from"SKU"to"PlanNode"
# ******************************************
# --------------------------------------------
# 上流 -> 下流へコスト構成展開（RootからLeafへ）
# --------------------------------------------
def evaluate_inbound_cost(root_node, product_name, tariff_table):
    def propagate(node):
        sku = node.sku
        if node.parent:
            sku.purchase_price = node.parent.sku.price
            tariff_rate = get_tariff_rate(product_name, node.parent.name, node.name, tariff_table)
            sku.tariff_cost = tariff_rate * sku.purchase_price
        else:
            sku.purchase_price = 0
            sku.tariff_cost = 0
        sku.total_cost = (
            sku.purchase_price + sku.transport_cost + sku.storage_cost +
            sku.tariff_cost + sku.fixed_cost + sku.other_cost
        )
        if not sku.price or sku.price <= 0:
            margin_rate = getattr(sku, "profit_margin", 0.05)
            sku.price = sku.total_cost * (1 + margin_rate)
        sku.profit = sku.price - sku.total_cost
        sku.SGA_total = sku.total_cost * 0.02  # 仮設定
        for child in node.children:
            propagate(child)
    propagate(root_node)
# --------------------------------------------
# Leaf探索
# --------------------------------------------
def find_leaf_nodes(root_node):
    result = []
    def dfs(node):
        if not node.children:
            result.append(node)
        for child in node.children:
            dfs(child)
    dfs(root_node)
    return result
# --------------------------------------------
# 関税テーブル読み込み
# --------------------------------------------
def load_tariff_table_from_csv(filepath):
    tariff_table = {}
    with open(filepath, newline='', encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["product_name"].strip(), row["from_node"].strip(), row["to_node"].strip())
            tariff_table[key] = float(row["tariff_rate"])
    return tariff_table
# --------------------------------------------
# 各製品について伝播実行
# --------------------------------------------
def run_price_and_cost_propagation(product_tree_dict, tariff_table):
    for product_name, tree in product_tree_dict.items():
        leaf_nodes = find_leaf_nodes(tree)
        #leaf_nodes = find_leaf_nodes(tree.root_node_outbound)
        #@250801 treeのままでOK、OUT/INの分岐は入口のproduct_tree_dict_OT/_INで区別している
        # 本来はOT/INで最初から処理を分けるべき処理
        for leaf in leaf_nodes:
            evaluate_price_TOBE(leaf, product_name, tariff_table)
        #@TOBE ReWrite with "PlanNode" based data
        #evaluate_inbound_cost(tree.root_node_inbound, product_name, tariff_table)
        # tree is root_node of DADxxx
        evaluate_price_ASIS(tree, product_name, tariff_table)
# --------------------------------------------
# 結果出力（CSV）
# --------------------------------------------
def export_node_prices_and_costs(product_tree_dict, output_dir):
    output_path = os.path.join(output_dir, "price_cost_output.csv")
    with open(output_path, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            "product_name", "node_name", "price", "total_cost", "purchase_price",
            "tariff_cost", "transport_cost", "storage_cost", "fixed_cost", "other_cost",
            "profit", "SGA_total"
        ])
        for product_name, tree in product_tree_dict.items():
            def traverse(node):
                sku = node.sku
                writer.writerow([
                    product_name, node.name, sku.price, sku.total_cost, sku.purchase_price,
                    getattr(sku, "tariff_cost", 0), sku.transport_cost, sku.storage_cost,
                    sku.fixed_cost, getattr(sku, "other_cost", 0),
                    getattr(sku, "profit", 0), getattr(sku, "SGA_total", 0)
                ])
                for child in node.children:
                    traverse(child)
            traverse(tree)
            #@STOP
            #traverse(tree.root_node_inbound)
            #traverse(tree.root_node_outbound)
# --------------------------------------------
# GUI連携用初期実行
# --------------------------------------------
def gui_run_initial_propagation(product_tree_dict, data_dir):
    try:
        tariff_csv = os.path.join(data_dir, "tariff_table.csv")
        tariff_table = load_tariff_table_from_csv(tariff_csv) if os.path.exists(tariff_csv) else {}
        run_price_and_cost_propagation(product_tree_dict, tariff_table)
        print("[Info] 初期コスト伝播完了")
    except Exception as e:
        print("[Error] 初期コスト伝播失敗:", str(e))
# --------------------------------------------
# PlanNode属性にコスト構造値をコピー
# --------------------------------------------
def propagate_cost_to_plan_nodes(product_tree_dict):
    for product_name, tree in product_tree_dict.items():
        def traverse(node):
            node.eval_cs_price_sales_shipped = getattr(node, "cs_price_sales_shipped", 0)
            node.eval_cs_profit = getattr(node, "cs_profit", 0)
            node.eval_cs_SGA_total = getattr(node, "cs_SGA_total", 0)
            node.eval_cs_tax_portion = getattr(node, "cs_tax_portion", 0)
            node.eval_cs_logistics_costs = getattr(node, "cs_logistics_costs", 0)
            node.eval_cs_warehouse_cost = getattr(node, "cs_warehouse_cost", 0)
            node.eval_cs_direct_materials_costs = getattr(node, "cs_direct_materials_costs", 0)
            #sku = node.sku
            #node.eval_cs_price_sales_shipped = getattr(sku, "price", 0)
            #node.eval_cs_profit = getattr(sku, "profit", 0)
            #node.eval_cs_SGA_total = getattr(sku, "SGA_total", 0)
            #node.eval_cs_tax_portion = getattr(sku, "tariff_cost", 0)
            #node.eval_cs_logistics_costs = getattr(sku, "transport_cost", 0)
            #node.eval_cs_warehouse_cost = getattr(sku, "storage_cost", 0)
            #node.eval_cs_direct_materials_costs = getattr(sku, "purchase_price", 0)
            for child in node.children:
                traverse(child)
        traverse(tree)
        #@STOP
        #traverse(tree.root_node_inbound)
        #traverse(tree.root_node_outbound)
# **********************************
# price_setting.py
# **********************************
# TOBE価格（市場価格）をLeafノードにセット
def load_tobe_prices(filepath):
    tobe_price_dict = {}
    with open(filepath, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row['leaf_node_name'].strip(), row['product_name'].strip())
            tobe_price_dict[key] = float(row['offering_price_TOBE'])
    return tobe_price_dict
def assign_tobe_prices_to_leaf_nodes(product_tree_dict, tobe_price_dict):
    for product_name, tree in product_tree_dict.items():
        leaf_nodes = find_leaf_nodes(tree)
        for leaf in leaf_nodes:
            key = (leaf.name.strip(), product_name.strip())
            if key in tobe_price_dict:
                leaf.offering_price_TOBE = tobe_price_dict[key]
                #leaf.cs_offering_price = tobe_price_dict[key]
                print(f"[Assign TOBE] {leaf.name} - {product_name} = {leaf.offering_price_TOBE}")
                #print(f"[Assign TOBE] {leaf.name} - {product_name} = {leaf.cs_offering_price}")
            else:
                print(f"[Warning] No TOBE price found for {key}")
#ASIS価格（出荷価格）をRootノードにセット
def load_asis_prices(filepath):
    asis_price_dict = {}
    with open(filepath, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row['product_name'].strip(), row['DAD_node_name'].strip())
            asis_price_dict[key] = float(row['offering_price_ASIS'])
    return asis_price_dict
def assign_asis_prices_to_root_nodes(product_tree_dict, asis_price_dict):
    for product_name, tree in product_tree_dict.items():
        root = tree  # または tree.root_node_inbound
        for dad_node in asis_price_dict:
            if dad_node[0] == product_name:
                root.offering_price_ASIS = asis_price_dict[dad_node]
                #root.sku.price = asis_price_dict[dad_node]
                print(f"[Assign ASIS] {root.name} - {product_name} = {root.offering_price_ASIS}")
                #print(f"[Assign ASIS] {root.name} - {product_name} = {root.sku.price}")
