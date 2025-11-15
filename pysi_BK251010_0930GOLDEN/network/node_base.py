#node_base.py
import math
#@250713 for def load_sku_cost_master(...)
import pandas as pd
# network/tree.py
from typing import List, Dict, Optional, Callable, Any
from collections import defaultdict
from pysi.utils.file_io import read_tree_file
#from some_module import Node  # Nodeクラスを適切な場所からインポート
#from pysi.plan.demand_processing import *
#from plan.demand_processing import shiftS2P_LV
from pysi.plan.operations import *
#from pysi.plan.operations import calcS2P, set_S2psi, get_set_childrenP2S2psi, shiftS2P_LV
#@250820 copied from pysi.pla.operations
# 同一node内のS2Pの処理
def shiftS2P_LV(psiS, shift_week, lv_week):  # LV:long vacations
    # ss = safety_stock_week
    sw = shift_week
    plan_len = len(psiS) - 1  # -1 for week list position
    for w in range(plan_len, sw, -1):  # backward planningで需要を降順でシフト
        # my_list = [1, 2, 3, 4, 5]
        # for i in range(2, len(my_list)):
        #    my_list[i] = my_list[i-1] + my_list[i-2]
        # 0:S
        # 1:CO
        # 2:I
        # 3:P
        eta_plan = w - sw  # sw:shift week (includung safty stock)
        eta_shift = check_lv_week_bw(lv_week, eta_plan)  # ETA:Estimate Time Arrival
        # リスト追加 extend
        # 安全在庫とカレンダ制約を考慮した着荷予定週Pに、w週Sからoffsetする
        psiS[eta_shift][3].extend(psiS[w][0])  # P made by shifting S with
    return psiS
# ************************************
# checking constraint to inactive week , that is "Long Vacation"
# ************************************
def check_lv_week_bw(const_lst, check_week):
    num = check_week
    if const_lst == []:
        pass
    else:
        while num in const_lst:
            num -= 1
    return num
def check_lv_week_fw(const_lst, check_week):
    num = check_week
    if const_lst == []:
        pass
    else:
        while num in const_lst:
            num += 1
    return num
# ****************************
# after demand leveling / planning outbound supply
# ****************************
def shiftS2P_LV_replace(psiS, shift_week, lv_week):  # LV:long vacations
    # ss = safety_stock_week
    sw = shift_week
    plan_len = len(psiS) - 1  # -1 for week list position
    for w in range(plan_len):  # foreward planningでsupplyのp [w][3]を初期化
        # psiS[w][0] = [] # S active
        psiS[w][1] = []  # CO
        psiS[w][2] = []  # I
        psiS[w][3] = []  # P
    for w in range(plan_len, sw, -1):  # backward planningでsupplyを降順でシフト
        # my_list = [1, 2, 3, 4, 5]
        # for i in range(2, len(my_list)):
        #    my_list[i] = my_list[i-1] + my_list[i-2]
        # 0:S
        # 1:CO
        # 2:I
        # 3:P
        eta_plan = w - sw  # sw:shift week ( including safty stock )
        eta_shift = check_lv_week_bw(lv_week, eta_plan)  # ETA:Eatimate Time Arrival
        # リスト追加 extend
        # 安全在庫とカレンダ制約を考慮した着荷予定週Pに、w週Sからoffsetする
        psiS[eta_shift][3].extend(psiS[w][0])  # P made by shifting S with
    return psiS
class Node:
    def __init__(self, name: str):
        self.name = name
        self.children: List['Node'] = []
        self.parent: Optional['Node'] = None
        # node position on network
        self.depth = 0
        self.width = 0
        # Geographic Position
        self.longitude = None
        self.latitude  = None
        # *******************
        # SKU linkage for GUI node visualisation
        # *******************
        self.sku_dict = {}  # product_name 2 SKU=PlanNode
        # *******************
        # SKU linkage for PSI planning #@250728 MEMO これを使わずにplan_node.を使う構造
        # *******************
        self.sku = None  # ← planning用SKU（このNodeが属するproductのみに使う）
        # *******************
        # move Node 2 SKU
        # *******************
        self.lot_size = 1  # default setting
        self.psi = []  # Placeholder for PSI data
        self.iso_week_demand = None  # Original demand converted to ISO week
        self.plan_range = 1
        self.plan_year_st = 2025
        # *******************
        # plan_range はあとで上書きされる前提
        # *******************
        length = 53 * self.plan_range
        # [S, CO, I, P] 用の 4 要素リストを用意
        self.psi4demand = [ [[], [], [], []] for _ in range(length) ]
        self.psi4supply = [ [[], [], [], []] for _ in range(length) ]
        self.psi4couple = [ [[], [], [], []] for _ in range(length) ]
        self.psi4accume = [ [[], [], [], []] for _ in range(length) ]
        #self.psi4demand = None
        #self.psi4supply = None
        #self.psi4couple = None
        #self.psi4accume = None
        self.safety_stock_week = 0
        self.long_vacation_weeks = []
        # For NetworkX
        self.leadtime = 1   # same as safety_stock_week
        self.nx_demand = 1  # weekly average demand by lot
        self.nx_weight = 1  # move_cost_all_to_nodeB (from nodeA to nodeB)
        self.nx_capacity = 1  # lot by lot
        # Evaluation
        self.decoupling_total_I = []  # total Inventory all over the plan
        # "lot_counts" is the bridge PSI2EVAL
        self.lot_counts = [0 for x in range(0, 53 * self.plan_range)]
        self.lot_counts_all = 0  # sum(self.lot_counts)
        # Settings for cost-profit evaluation parameter
        self.LT_boat = 1
        self.SS_days = 7
        self.HS_code = ""
        self.customs_tariff_rate = 0
        self.tariff_on_price = 0
        self.price_elasticity = 0
        # ******************************
        # evaluation data initialise rewardsを計算の初期化
        # ******************************
        # ******************************
        # Profit_Ratio #float
        # ******************************
        self.eval_profit_ratio = Profit_Ratio = 0.6
        # Revenue, Profit and Costs
        self.eval_revenue = 0
        self.eval_profit = 0
        self.eval_PO_cost = 0
        self.eval_P_cost = 0
        self.eval_WH_cost = 0
        self.eval_SGMC = 0
        self.eval_Dist_Cost = 0
        # ******************************
        # price
        # ******************************
        self.offering_price_ASIS = 0
        self.offering_price_TOBE = 0
        self.offering_price_CANBE = 0
        self.offering_price_WILLBE = 0
        self.offering_price_LETITBE = 0
        # ******************************
        # set_EVAL_cash_in_data #list for 53weeks * 5 years # 5年を想定
        # *******************************
        self.Profit = Profit = [0 for i in range(53 * self.plan_range)]
        self.Week_Intrest = Week_Intrest = [0 for i in range(53 * self.plan_range)]
        self.Cash_In = Cash_In = [0 for i in range(53 * self.plan_range)]
        self.Shipped_LOT = Shipped_LOT = [0 for i in range(53 * self.plan_range)]
        self.Shipped = Shipped = [0 for i in range(53 * self.plan_range)]
        # ******************************
        # set_EVAL_cash_out_data #list for 54 weeks
        # ******************************
        self.SGMC = SGMC = [0 for i in range(53 * self.plan_range)]
        self.PO_manage = PO_manage = [0 for i in range(53 * self.plan_range)]
        self.PO_cost = PO_cost = [0 for i in range(53 * self.plan_range)]
        self.P_unit = P_unit = [0 for i in range(53 * self.plan_range)]
        self.P_cost = P_cost = [0 for i in range(53 * self.plan_range)]
        self.I = I = [0 for i in range(53 * self.plan_range)]
        self.I_unit = I_unit = [0 for i in range(53 * self.plan_range)]
        self.WH_cost = WH_cost = [0 for i in range(53 * self.plan_range)]
        self.Dist_Cost = Dist_Cost = [0 for i in range(53 * self.plan_range)]
        # Cost structure demand
        self.price_sales_shipped = 0
        self.cost_total = 0
        self.profit = 0
        self.marketing_promotion = 0
        self.sales_admin_cost = 0
        self.SGA_total = 0
        self.custom_tax = 0
        self.tax_portion = 0
        self.logistics_costs = 0
        self.warehouse_cost = 0
        self.direct_materials_costs = 0
        self.purchase_total_cost = 0
        self.prod_indirect_labor = 0
        self.prod_indirect_others = 0
        self.direct_labor_costs = 0
        self.depreciation_others = 0
        self.manufacturing_overhead = 0
        # Profit accumulated root to node
        self.cs_profit_accume = 0
        # Cost Structure
        self.cs_price_sales_shipped = 0
        self.cs_cost_total = 0
        self.cs_profit = 0
        self.cs_marketing_promotion = 0
        self.cs_sales_admin_cost = 0
        self.cs_SGA_total = 0
        #self.cs_custom_tax = 0
        #self.cs_tariff_rate = 0
        #self.cs_tariff_cost = 0
        self.tariff_rate = 0
        self.tariff_cost = 0
        self.cs_tax_portion = 0
        self.cs_logistics_costs = 0
        self.cs_warehouse_cost = 0
        self.cs_direct_materials_costs = 0
        self.cs_purchase_total_cost = 0
        self.cs_prod_indirect_labor = 0
        self.cs_prod_indirect_others = 0
        self.cs_direct_labor_costs = 0
        self.cs_depreciation_others = 0
        self.cs_manufacturing_overhead = 0
        # Evaluated cost = Cost Structure X lot_counts
        self.eval_cs_price_sales_shipped = 0  # revenue
        self.eval_cs_cost_total = 0  # cost
        self.eval_cs_profit = 0  # profit
        self.eval_cs_marketing_promotion = 0
        self.eval_cs_sales_admin_cost = 0
        self.eval_cs_SGA_total = 0
        #@250803 ADD for "cost propagation"
        self.cs_fixed_cost = 0
        #self.eval_cs_custom_tax = 0 # stop tariff rate
        self.eval_cs_tax_portion = 0
        self.eval_cs_logistics_costs = 0
        self.eval_cs_warehouse_cost = 0
        self.eval_cs_direct_materials_costs = 0
        self.eval_cs_purchase_total_cost = 0
        self.eval_cs_prod_indirect_labor = 0
        self.eval_cs_prod_indirect_others = 0
        self.eval_cs_direct_labor_costs = 0
        self.eval_cs_depreciation_others = 0
        self.eval_cs_manufacturing_overhead = 0
        # Shipped lots count W / M / Q / Y / LifeCycle
        self.shipped_lots_W = []  # 53*plan_range
        self.shipped_lots_M = []  # 12*plan_range
        self.shipped_lots_Q = []  # 4*plan_range
        self.shipped_lots_Y = []  # 1*plan_range
        self.shipped_lots_L = []  # 1  # lifecycle a year
        # Planned Amount
        self.amt_price_sales_shipped = []    # Revenue cash_IN???
        self.amt_cost_total = []
        self.amt_profit = []                 # Profit
        self.amt_marketing_promotion = []
        self.amt_sales_admin_cost = []
        self.amt_SGA_total = []
        self.amt_custom_tax = []
        self.amt_tax_portion = []
        self.amt_logistiamt_costs = []
        self.amt_warehouse_cost = []
        self.amt_direct_materials_costs = [] # FOB@port
        self.amt_purchase_total_cost = []    #
        self.amt_prod_indirect_labor = []
        self.amt_prod_indirect_others = []
        self.amt_direct_labor_costs = []
        self.amt_depreciation_others = []
        self.amt_manufacturing_overhead = []
        # Shipped amt W / M / Q / Y / LifeCycle
        self.shipped_amt_W = []  # 53*plan_range
        self.shipped_amt_M = []  # 12*plan_range
        self.shipped_amt_Q = []  # 4*plan_range
        self.shipped_amt_Y = []  # 1*plan_range
        self.shipped_amt_L = []  # 1  # lifecycle a year
        # Control FLAGs
        self.cost_standard_flag = 0
        self.PSI_graph_flag = "OFF"
        self.buffering_stock_flag = "OFF"
        self.revenue = 0
        self.profit  = 0
        self.AR_lead_time = 0 # Accounts Receivable 売掛
        self.AP_lead_time = 0 # Accounts Payable 買掛
    # ***********************
    # SKU linkage
    # ***********************
    def add_sku(self, product_name: str): #@250728 未使用
        sku = SKU(product_name, self.name)
        self.sku_dict[product_name] = sku
        return sku
    def get_sku(self, product_name):
        return self.sku_dict[product_name]
    def add_child(self, child: 'Node'):
        """Add a child node to the current node."""
        self.children.append(child)
        child.parent = self
    def iter_nodes(self):
        yield self
        for child in self.children:
            yield from child.iter_nodes()
    def find_node(self, condition: Callable[['Node'], bool]) -> Optional['Node']:
        for node in self.iter_nodes():
            if condition(node):
                return node
        return None
    def find_all(self, condition: Callable[['Node'], bool]) -> List['Node']:
        return [node for node in self.iter_nodes() if condition(node)]
    def count_nodes(self, condition: Callable[['Node'], bool] = lambda x: True) -> int:
        return sum(1 for node in self.iter_nodes() if condition(node))
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "lead_time": self.lead_time,
            "capacity": self.capacity,
            "tags": self.tags,
            "meta": self.meta,
            "children": [child.to_dict() for child in self.children]
        }
    def from_dict(self, data: Dict[str, Any]):
        self.name = data.get("name", self.name)
        self.lead_time = data.get("lead_time", 0)
        self.capacity = data.get("capacity", None)
        self.tags = data.get("tags", [])
        self.meta = data.get("meta", {})
        for child_data in data.get("children", []):
            child = Node(name=child_data.get("name", ""))
            child.from_dict(child_data)
            self.add_child(child)
    def set_depth(self, depth: int):
        """Recursively set the depth of the node and its children."""
        self.depth = depth
        for child in self.children:
            child.set_depth(depth + 1)
    def print_tree(self, level: int = 0):
        """Print the tree structure starting from the current node."""
        print("  " * level + f"Node: {self.name}")
        for child in self.children:
            child.print_tree(level + 1)
    # ********************************
    # ココで属性をセット@240417
    # ********************************
    def set_attributes(self, row):
        #print("set_attributes(self, row):", row)
        # self.lot_size = int(row[3])
        # self.leadtime = int(row[4])  # 前提:SS=0
        # self.long_vacation_weeks = eval(row[5])
        self.lot_size = int(row["lot_size"])
        # ********************************
        # with using NetworkX
        # ********************************
        # weightとcapacityは、edge=(node_A,node_B)の属性でnodeで一意ではない
        self.leadtime = int(row["leadtime"])  # 前提:SS=0 # "weight"4NetworkX
        self.capacity = int(row["process_capa"])  # "capacity"4NetworkX
        self.long_vacation_weeks = eval(row["long_vacation_weeks"])
        # **************************
        # BU_SC_node_profile     business_unit_supplychain_node
        # **************************
        # @240421 機械学習のフラグはstop
        ## **************************
        ## plan_basic_parameter ***sequencing is TEMPORARY
        ## **************************
        #        self.PlanningYear           = row['plan_year']
        #        self.plan_engine            = row['plan_engine']
        #        self.reward_sw              = row['reward_sw']
        # 多段階PSIのフラグはstop
        ## ***************************
        ## business unit identify
        ## ***************************
        #        self.product_name           = row['product_name']
        #        self.SC_tree_id             = row['SC_tree_id']
        #        self.node_from              = row['node_from']
        #        self.node_to                = row['node_to']
        # ***************************
        # ココからcost-profit evaluation 用の属性セット
        # ***************************
        self.LT_boat = float(row["LT_boat"])
        self.SS_days = float(row["SS_days"])
        print("row[ customs_tariff_rate ]", row["customs_tariff_rate"])
        self.HS_code              = str(row["HS_code"])
        self.customs_tariff_rate  = float(row["customs_tariff_rate"])
        self.price_elasticity     = float(row["price_elasticity"])
        self.cost_standard_flag   = float(row["cost_standard_flag"])
        self.AR_lead_time   = float(row["AR_lead_time"])
        self.AP_lead_time   = float(row["AP_lead_time"])
        self.PSI_graph_flag       = str(row["PSI_graph_flag"])
        self.buffering_stock_flag = str(row["buffering_stock_flag"])
        self.base_leaf = None
    def set_parent(self):
        # def set_parent(self, node):
        # treeを辿りながら親ノードを探索
        if self.children == []:
            pass
        else:
            for child in self.children:
                child.parent = self
                # child.parent = node
    def set_cost_attr(
        self,
        price_sales_shipped,
        cost_total,
        profit,
        marketing_promotion=None,
        sales_admin_cost=None,
        SGA_total=None,
        #custom_tax=None,
        #tax_portion=None,
        logistics_costs=None,
        warehouse_cost=None,
        direct_materials_costs=None,
        purchase_total_cost=None,
        prod_indirect_labor=None,
        prod_indirect_others=None,
        direct_labor_costs=None,
        depreciation_others=None,
        manufacturing_overhead=None,
    ):
        # self.node_name = node_name # node_name is STOP
        self.price_sales_shipped = price_sales_shipped
        self.cost_total = cost_total
        self.profit = profit
        self.marketing_promotion = marketing_promotion
        self.sales_admin_cost = sales_admin_cost
        self.SGA_total = SGA_total
        #self.custom_tax = custom_tax
        #self.tax_portion = tax_portion
        self.logistics_costs = logistics_costs
        self.warehouse_cost = warehouse_cost
        self.direct_materials_costs = direct_materials_costs
        self.purchase_total_cost = purchase_total_cost
        self.prod_indirect_labor = prod_indirect_labor
        self.prod_indirect_others = prod_indirect_others
        self.direct_labor_costs = direct_labor_costs
        self.depreciation_others = depreciation_others
        self.manufacturing_overhead = manufacturing_overhead
    def normalize_cost(self):
        cost_total = self.add_tax_sum_cost()
        # self.node_name = node_name # node_name is STOP
        self.direct_materials_costs = self.direct_materials_costs / cost_total
        #self.custom_tax = custom_tax # STOP this is rate
        self.tax_portion            = self.tax_portion            / cost_total
        self.profit                 = self.profit                 / cost_total
        self.marketing_promotion    = self.marketing_promotion    / cost_total
        self.sales_admin_cost       = self.sales_admin_cost       / cost_total
        self.logistics_costs        = self.logistics_costs        / cost_total
        self.warehouse_cost         = self.warehouse_cost         / cost_total
        self.prod_indirect_labor    = self.prod_indirect_labor    / cost_total
        self.prod_indirect_others   = self.prod_indirect_others   / cost_total
        self.direct_labor_costs     = self.direct_labor_costs     / cost_total
        self.depreciation_others    = self.depreciation_others    / cost_total
        self.SGA_total              = ( self.marketing_promotion
                                    + self.sales_admin_cost )
        self.purchase_total_cost    = ( self.logistics_costs
                                    + self.warehouse_cost
                                    + self.direct_materials_costs
                                    + self.tax_portion )
        self.manufacturing_overhead = ( self.prod_indirect_labor
                                    +  self.prod_indirect_others
                                    +  self.direct_labor_costs
                                    +  self.depreciation_others )
        self.cost_total             = ( self.purchase_total_cost
                                    + self.SGA_total
                                    + self.manufacturing_overhead )
        self.price_sales_shipped    = self.cost_total + self.profit
    def add_tax_sum_cost(self):
        # calc_custom_tax
        self.tax_portion = self.direct_materials_costs * self.customs_tariff_rate
        cost_total = 0
        cost_total = (
            self.direct_materials_costs
            # this is CUSTOM_TAX
            #+ self.direct_materials_costs * self.customs_tariff_rate
            + self.tax_portion
            + self.marketing_promotion
            + self.sales_admin_cost
            + self.logistics_costs
            + self.warehouse_cost
            + self.prod_indirect_labor
            + self.prod_indirect_others
            + self.direct_labor_costs
            + self.depreciation_others
            + self.profit
        )
        print("cost_total", self.name, cost_total)
        return cost_total
    def print_cost_attr(self):
        # self.node_name = node_name # node_name is STOP
        print("self.price_sales_shipped", self.price_sales_shipped)
        print("self.cost_total", self.cost_total)
        print("self.profit", self.profit)
        print("self.marketing_promotion", self.marketing_promotion)
        print("self.sales_admin_cost", self.sales_admin_cost)
        print("self.SGA_total", self.SGA_total)
        #print("self.custom_tax", self.custom_tax)
        #print("self.tax_portion", self.tax_portion)
        print("self.logistics_costs", self.logistics_costs)
        print("self.warehouse_cost", self.warehouse_cost)
        print("self.direct_materials_costs", self.direct_materials_costs)
        print("self.purchase_total_cost", self.purchase_total_cost)
        print("self.prod_indirect_labor", self.prod_indirect_labor)
        print("self.prod_indirect_others", self.prod_indirect_others)
        print("self.direct_labor_costs", self.direct_labor_costs)
        print("self.depreciation_others", self.depreciation_others)
        print("self.manufacturing_overhead", self.manufacturing_overhead)
    def set_plan_range_lot_counts(self, plan_range, plan_year_st):
        # print("node.plan_range", self.name, self.plan_range)
        self.plan_range = plan_range
        self.plan_year_st = plan_year_st
        self.lot_counts = [0 for x in range(0, 53 * self.plan_range)]
        for child in self.children:
            child.set_plan_range_lot_counts(plan_range, plan_year_st)
    #@250818 ADD
    # node_base.py
    import math  # ← 忘れずに
    # 実週長に合わせて PSI バッファを初期化（子にも伝搬）
    def set_plan_range_by_weeks(self, weeks_count: int, plan_year_st: int, preserve: bool = False):
        if weeks_count <= 0:
            raise ValueError("weeks_count must be > 0")
        # 既存の配列を保全したい場合に備えて待避
        old_d = getattr(self, "psi4demand", None)
        old_s = getattr(self, "psi4supply", None)
        old_len = len(old_d) if isinstance(old_d, list) else 0
        self.plan_year_st = int(plan_year_st)
        # plan_range は表示や既存互換のため保持（ロジックは配列長で回す）
        self.plan_range   = max(1, math.ceil(weeks_count / 53))
        # 新しい器を作る
        if preserve and old_len:
            new_d = [[[], [], [], []] for _ in range(weeks_count)]
            new_s = [[[], [], [], []] for _ in range(weeks_count)]
            upto = min(old_len, weeks_count)
            # 既存データを可能な範囲でコピー（浅いコピーでOK：lot_id は文字列）
            for w in range(upto):
                new_d[w][0].extend(old_d[w][0]); new_d[w][1].extend(old_d[w][1])
                new_d[w][2].extend(old_d[w][2]); new_d[w][3].extend(old_d[w][3])
                new_s[w][0].extend(old_s[w][0]); new_s[w][1].extend(old_s[w][1])
                new_s[w][2].extend(old_s[w][2]); new_s[w][3].extend(old_s[w][3])
            self.psi4demand = new_d
            self.psi4supply = new_s
        else:
            # 毎回まっさらで良ければこちら
            self.psi4demand = [[[], [], [], []] for _ in range(weeks_count)]
            self.psi4supply = [[[], [], [], []] for _ in range(weeks_count)]
        self.lot_counts = [0] * weeks_count
        # 子にも同じ weeks_count / plan_year_st を伝搬
        for child in self.children:
            child.set_plan_range_by_weeks(weeks_count, plan_year_st, preserve=preserve)
    # ユーティリティ（ループ長は常に実週長を返す）
    def plan_len(self) -> int:
        return len(self.psi4demand)
    #@250818 ADD
    def set_plan_range_all_buffers(self, plan_range, plan_year_st):
        self.set_plan_range_lot_counts(plan_range, plan_year_st)
        self.psi4demand = [
            [[], [], [], []] for _ in range(53 * plan_range)
        ]
        for child in self.children:
            child.set_plan_range_all_buffers(plan_range, plan_year_st)
    #@250818 ADD
    def set_S2psi(self, pSi):
        # ここが唯一の正本
        assert isinstance(pSi, list), f"pSi must be list, got {type(pSi)}"
        assert len(pSi) == len(self.psi4demand), \
            f"len(pSi)={len(pSi)} != len(psi4demand)={len(self.psi4demand)} (node={self.name})"
        # Sバケツに投入（extend／置換は要件に応じて）
        for w in range(len(self.psi4demand)):
            # 置き換えにしたい場合は次の1行に：
            # self.psi4demand[w][0] = list(pSi[w])
            self.psi4demand[w][0].extend(pSi[w])
    def calcS2P(self): # backward planning
        # **************************
        # Safety Stock as LT shift
        # **************************
        # leadtimeとsafety_stock_weekは、ここでは同じ
        # 同一node内なので、ssのみで良い
        shift_week = int(round(self.SS_days / 7))
        ## stop 同一node内でのLT shiftは無し
        ## SS is rounded_int_num
        # shift_week = self.leadtime +  int(round(self.SS_days / 7))
        # **************************
        # long vacation weeks
        # **************************
        lv_week = self.long_vacation_weeks
        # 同じnode内でのS to P の計算処理 # backward planning
        self.psi4demand = shiftS2P_LV(self.psi4demand, shift_week, lv_week)
        pass
    # --- PlanNode に 1-hop 集約を追加 ---------------------------------
    #親ノード側で parent.calcP2S() を呼ぶだけで、全ての子の P を LT でオフセットして親の S に貯めるようになります。
    #オフセット方向は通常 parent_before_child=True（親S=子P−LT） です。
    def _calcP2S(self, *, layer: str = "demand",
                parent_before_child: bool = True,
                dedup: bool = True):
        """
        子ノードの P を、この親ノードの S に 1-hop 集約する。
        layer: "demand" or "supply" （通常は demand 面で運ぶ）
        parent_before_child=True のとき、親S週 = 子P週 - LT  （親は“先に”出荷）
                            False のとき、親S週 = 子P週 + LT
        dedup=True で親Sの lot_id 重複を回避（同週Sに同じIDが複数回入るのを防止）
        """
        psi_parent = self.psi4demand if layer == "demand" else self.psi4supply
        weeks = len(psi_parent)
        if weeks == 0:
            return
        # 親Sの重複回避用キャッシュ（任意）
        seen = [set() for _ in range(weeks)] if dedup else None
        for ch in getattr(self, "children", []) or []:
            psi_child = ch.psi4demand if layer == "demand" else ch.psi4supply
            if len(psi_child) != weeks:
                # 長さ不一致はスキップ（または合わせ込む）
                continue
            LT = int(getattr(ch, "leadtime", 0) or 0)
            # 方向：子P週 -> 親S週
            sign = -1 if parent_before_child else +1
            for w in range(weeks):
                P_child = psi_child[w][3]  # 子の P バケツ
                if not P_child:
                    continue
                wp = w + sign * LT         # 親の S 週
                if 0 <= wp < weeks:
                    if not dedup:
                        psi_parent[wp][0].extend(P_child)
                    else:
                        # 重複を避けて append
                        dst = psi_parent[wp][0]
                        pool = seen[wp]
                        for lot in P_child:
                            if lot not in pool:
                                dst.append(lot)
                                pool.add(lot)
    # monkey-patch（node_base.PlanNode にメソッドが無い場合のみ）
    try:
        from pysi.network.node_base import PlanNode
        if not hasattr(PlanNode, "calcP2S"):
            PlanNode.calcP2S = _calcP2S
    except Exception:
        pass
    # psi4demand にセットした lot を、psi4supply にも初期転写
    #@250818 ADD
    # 例: copy_demand_to_supply（latest を差し替え）
    def copy_demand_to_supply(self):
        plan_len = len(self.psi4demand)   # ★ここを固定長から実週長へ
        for w in range(plan_len):
            lots_list = self.psi4demand[w][0]
            self.psi4supply[w][0].extend(lots_list)
    #@250818 UPDATE
    def get_set_childrenP2S2psi(self):
        """子の P を leadtime だけ前倒しして自分の S に集約（実配列長で）"""
        plan_len = len(self.psi4demand)
        for child in self.children:
            L = min(plan_len, len(child.psi4demand))
            lt = int(getattr(self, "leadtime", 0))
            for w in range(lt, L):
                ws = w - lt
                # P(=index 3) を親の S(=index 0) に積む
                self.psi4demand[ws][0].extend(child.psi4demand[w][3])
    # ******************
    # for debug
    # ******************
    def show_sum_cs(self):
        cs_sum = 0
        cs_sum = (
            self.cs_direct_materials_costs
            + self.cs_marketing_promotion
            + self.cs_sales_admin_cost
            + self.cs_tax_portion
            + self.cs_logistics_costs
            + self.cs_warehouse_cost
            + self.cs_prod_indirect_labor
            + self.cs_prod_indirect_others
            + self.cs_direct_labor_costs
            + self.cs_depreciation_others
            + self.cs_profit
        )
        print("cs_sum", self.name, cs_sum)
    # ******************************
    # evaluation
    # ******************************
    #@250818 ADD
    def set_lot_counts(self):
        # supply の実長を基準にする
        plan_len = len(self.psi4supply)
        # lot_counts の長さを合わせる（足りなければ伸ばす／長ければ切る）
        if len(getattr(self, "lot_counts", [])) != plan_len:
            self.lot_counts = [0 for _ in range(plan_len)]
        for w in range(plan_len):
            self.lot_counts[w] = len(self.psi4supply[w][3])  # P
        self.lot_counts_all = sum(self.lot_counts)
    def EvalPlanSIP_cost(self):
        L = self.lot_counts_all    # nodeの全ロット数 # psi[w][3]=PO
        # evaluated cost = Cost Structure X lot_counts
        self.eval_cs_price_sales_shipped    = L * self.cs_price_sales_shipped
        self.eval_cs_cost_total             = L * self.cs_cost_total
        self.eval_cs_profit                 = L * self.cs_profit
        self.eval_cs_marketing_promotion    = L * self.cs_marketing_promotion
        self.eval_cs_sales_admin_cost       = L * self.cs_sales_admin_cost
        self.eval_cs_SGA_total              = L * self.cs_SGA_total
        self.eval_cs_logistics_costs        = L * self.cs_logistics_costs
        self.eval_cs_warehouse_cost         = L * self.cs_warehouse_cost
        self.eval_cs_direct_materials_costs = L * self.cs_direct_materials_costs
        #self.eval_cs_custom_tax             = L * self.cs_custom_tax # STOP
        #@ RUN
        self.eval_cs_tax_portion            = L * self.cs_tax_portion
        print(" L = self.lot_counts_all", L )
        print("self.cs_price_sales_shipped   ", self.cs_price_sales_shipped    )
        print("self.cs_cost_total            ", self.cs_cost_total             )
        print("self.cs_profit                ", self.cs_profit                 )
        print("self.cs_marketing_promotion   ", self.cs_marketing_promotion    )
        print("self.cs_sales_admin_cost      ", self.cs_sales_admin_cost       )
        print("self.cs_SGA_total             ", self.cs_SGA_total              )
        print("self.cs_logistics_costs       ", self.cs_logistics_costs        )
        print("self.cs_warehouse_cost        ", self.cs_warehouse_cost         )
        print("self.cs_direct_materials_costs", self.cs_direct_materials_costs )
        #@STOP normalize_costで定義済み
        # ****************************
        # custom_tax = materials_cost imported X custom_tariff
        # ****************************
        #self.eval_cs_tax_portion            = self.eval_cs_direct_materials_costs * self.customs_tariff_rate
        self.eval_cs_purchase_total_cost    = L * self.cs_purchase_total_cost
        self.eval_cs_prod_indirect_labor    = L * self.cs_prod_indirect_labor
        self.eval_cs_prod_indirect_others   = L * self.cs_prod_indirect_others
        self.eval_cs_direct_labor_costs     = L * self.cs_direct_labor_costs
        self.eval_cs_depreciation_others    = L * self.cs_depreciation_others
        self.eval_cs_manufacturing_overhead = L * self.cs_manufacturing_overhead
        # 在庫係数の計算
        I_total_qty_planned, I_total_qty_init = self.I_lot_counts_all()
        if I_total_qty_init == 0:
            I_cost_coeff = 0
        else:
            I_cost_coeff =  I_total_qty_planned / I_total_qty_init
        print("self.name",self.name)
        print("I_total_qty_planned", I_total_qty_planned)
        print("I_total_qty_init", I_total_qty_init)
        print("I_cost_coeff", I_cost_coeff)
        # 在庫の増減係数を掛けてセット
        print("self.eval_cs_warehouse_cost", self.eval_cs_warehouse_cost)
        self.eval_cs_warehouse_cost *= ( 1 + I_cost_coeff )
        print("self.eval_cs_warehouse_cost", self.eval_cs_warehouse_cost)
        self.eval_cs_cost_total = (
            self.eval_cs_marketing_promotion +
            self.eval_cs_sales_admin_cost +
            #self.eval_cs_SGA_total +
            #self.eval_cs_custom_tax +
            self.eval_cs_tax_portion +
            self.eval_cs_logistics_costs +
            self.eval_cs_warehouse_cost +
            self.eval_cs_direct_materials_costs +
            #self.eval_cs_purchase_total_cost +
            self.eval_cs_prod_indirect_labor +
            self.eval_cs_prod_indirect_others +
            self.eval_cs_direct_labor_costs +
            self.eval_cs_depreciation_others #@END +
            #self.eval_cs_manufacturing_overhead
        )
        # profit = revenue - cost
        self.eval_cs_profit = self.eval_cs_price_sales_shipped - self.eval_cs_cost_total
        return self.eval_cs_price_sales_shipped, self.eval_cs_profit
    # *****************************
    # ここでCPU_LOTsを抽出する
    # *****************************
    #@250818 UPDATE
    def extract_CPU(self, csv_writer):
        plan_len = len(self.psi4supply)  # 計画長＝実配列長
        for w in range(1, plan_len):
            s  = self.psi4supply[w][0]
            co = self.psi4supply[w][1]
            i0 = self.psi4supply[w - 1][2]
            i1 = self.psi4supply[w][2]
            p  = self.psi4supply[w][3]
            # --- S
            for step_no, lot_id in enumerate(s):
                lot_id_yyyyww = lot_id + str(self.plan_year_st) + str(w).zfill(4)
                csv_writer.writerow([w, lot_id_yyyyww, "s", self.name, self.longitude, self.latitude, step_no, self.lot_size])
            # --- I1
            for step_no, lot_id in enumerate(i1):
                lot_id_yyyyww = lot_id + str(self.plan_year_st) + str(w).zfill(4)
                csv_writer.writerow([w, lot_id_yyyyww, "i1", self.name, self.longitude, self.latitude, step_no, self.lot_size])
            # --- P
            for step_no, lot_id in enumerate(p):
                lot_id_yyyyww = lot_id + str(self.plan_year_st) + str(w).zfill(4)
                csv_writer.writerow([w, lot_id_yyyyww, "p", self.name, self.longitude, self.latitude, step_no, self.lot_size])
    # ******************************
    # planning operation on tree
    # ******************************
    # ******************************
    # in or out    : root_node_outbound
    # plan layer   : demand layer
    # node order   : preorder # Leaf2Root
    # time         : Foreward
    # calculation  : PS2I
    # ******************************
    #@250818 UPDATE
    def calcPS2I4demand(self):
        plan_len = len(self.psi4demand)
        for w in range(1, plan_len):
            s  = self.psi4demand[w][0]
            co = self.psi4demand[w][1]
            i0 = self.psi4demand[w - 1][2]
            i1 = self.psi4demand[w][2]
            p  = self.psi4demand[w][3]
            # I(n-1)+P(n)-S(n) を順序は気にせず差分で表現
            work = i0 + p
            diff_list = [x for x in work if x not in s]
            self.psi4demand[w][2] = diff_list
    # *********************************
    # #@250626 TEST DATA DUMP4ALLOCATION
    # *********************************
    #@250626 TEST DATA DUMP4ALLOCATION
    #@250818 UPDATE
    def dump_PSI_psi4demand(self):
        print("dumpping node = ", self.name)
        plan_len = len(self.psi4demand)
        for w in range(1, plan_len):
            s  = self.psi4demand[w][0]
            co = self.psi4demand[w][1]
            i0 = self.psi4demand[w - 1][2]
            i1 = self.psi4demand[w][2]
            p  = self.psi4demand[w][3]
            print("s = self.psi4demand[w][0]", w, s, "&[w][3]", p, "&[w][2]", i1)
    #@250818 UPDATE
    def calcPS2I4supply(self):
        plan_len = len(self.psi4supply)
        for w in range(1, plan_len):
            s  = self.psi4supply[w][0]
            co = self.psi4supply[w][1]
            i0 = self.psi4supply[w - 1][2]
            i1 = self.psi4supply[w][2]
            p  = self.psi4supply[w][3]
            def fifo_lot_diff(i0: list, p: list, s: list) -> list:
                work = i0 + p  # 順序保持
                result, used = [], set()
                for lot in work:
                    if lot not in s and lot not in used:
                        result.append(lot); used.add(lot)
                return result
            diff_list = fifo_lot_diff(i0, p, s)
            self.psi4supply[w][2] = diff_list
            if self.name == "DADCAL":
                if w < 58:
                    print("s, co, i0, i1, p ", w)
                    print("s" , w, s )
                    print("co", w, co)
                    print("i0", w, i0)
                    print("i1", w, diff_list)
                    print("p" , w, p )
    #@250818 UPDATE
    def calcPS2I_decouple4supply(self):
        # まず長さを揃える：supply を demand に合わせる
        demand_len = len(self.psi4demand)
        if len(self.psi4supply) != demand_len:
            self.psi4supply = [[[], [], [], []] for _ in range(demand_len)]
        plan_len = demand_len  # 以降は同長
        # demand の S をそのまま supply の S にコピー
        for w in range(plan_len):
            self.psi4supply[w][0] = self.psi4demand[w][0].copy()
        # その上で supply 側の PS→I を計算
        for w in range(1, plan_len):
            s  = self.psi4supply[w][0]
            co = self.psi4supply[w][1]
            i0 = self.psi4supply[w - 1][2]
            i1 = self.psi4supply[w][2]
            p  = self.psi4supply[w][3]
            work = i0 + p
            diff_list = [x for x in work if x not in s]
            self.psi4supply[w][2] = diff_list
    def calcS2P(self): # backward planning
        # **************************
        # Safety Stock as LT shift
        # **************************
        # leadtimeとsafety_stock_weekは、ここでは同じ
        # 同一node内なので、ssのみで良い
        shift_week = int(round(self.SS_days / 7))
        ## stop 同一node内でのLT shiftは無し
        ## SS is rounded_int_num
        # shift_week = self.leadtime +  int(round(self.SS_days / 7))
        # **************************
        # long vacation weeks
        # **************************
        lv_week = self.long_vacation_weeks
        # 同じnode内でのS to P の計算処理 # backward planning
        self.psi4demand = shiftS2P_LV(self.psi4demand, shift_week, lv_week)
        pass
    def calcS2P_4supply(self):    # "self.psi4supply"
        # **************************
        # Safety Stock as LT shift
        # **************************
        # leadtimeとsafety_stock_weekは、ここでは同じ
        # 同一node内なので、ssのみで良い
        shift_week = int(round(self.SS_days / 7))
        ## stop 同一node内でのLT shiftは無し
        ## SS is rounded_int_num
        # shift_week = self.leadtime +  int(round(self.SS_days / 7))
        # **************************
        # long vacation weeks
        # **************************
        lv_week = self.long_vacation_weeks
        # S to P の計算処理
        self.psi4supply = shiftS2P_LV_replace(self.psi4supply, shift_week, lv_week)
        pass
    def set_plan_range_lot_counts(self, plan_range, plan_year_st):
        # print("node.plan_range", self.name, self.plan_range)
        self.plan_range = plan_range
        self.plan_year_st = plan_year_st
        self.lot_counts = [0 for x in range(0, 53 * self.plan_range)]
        for child in self.children:
            child.set_plan_range_lot_counts(plan_range, plan_year_st)
    #@250818 UPDATE
    def I_lot_counts_all(self):
        lot_all_supply = 0
        lot_all_demand = 0
        # どちらも参照するので min（両者を同長に保っているなら len(self.psi4demand) でもOK）
        plan_len = min(len(self.psi4demand), len(self.psi4supply))
        lot_counts_I_supply = [0] * plan_len
        lot_counts_I_demand = [0] * plan_len
        for w in range(plan_len):
            lot_counts_I_supply[w] = len(self.psi4supply[w][2])  # I
            lot_counts_I_demand[w] = len(self.psi4demand[w][2])  # I
        if self.name == "HAM":
            print("lot_counts_I_supply", lot_counts_I_supply)
        lot_all_supply = sum(lot_counts_I_supply)
        lot_all_demand = sum(lot_counts_I_demand)
        return lot_all_supply, lot_all_demand
    def eval_buffer_stock(self):
        """
        PSI情報をもとに、在庫水準（I）、未出荷（CO）、生産（P）ロット数の異常を評価。
        評価結果はログ出力される。
        """
        if self.psi4supply is None or len(self.psi4supply) == 0:
            print(f"[Warning] {self.name}: No supply PSI data available.")
            return
        threshold_weeks = self.safety_stock_week if self.safety_stock_week > 0 else self.leadtime
        safe_threshold = threshold_weeks * self.nx_demand
        co_threshold = self.nx_demand * 2  # 未出荷ロットの目安
        p_max_threshold = self.nx_capacity  # 許容量超えた生産負荷
        for w, week_data in enumerate(self.psi4supply):
            if len(week_data) < 4:
                continue
            # 在庫評価
            inventory = week_data[2]
            inventory_qty = sum(inventory) if isinstance(inventory, list) else inventory
            if inventory_qty < safe_threshold:
                print(f"[Stock Alert] {self.name} - W{w}: Inventory {inventory_qty} < Safe {safe_threshold}")
            # CO評価
            co = week_data[1]
            co_qty = sum(co) if isinstance(co, list) else co
            if co_qty > co_threshold:
                print(f"[CO Alert] {self.name} - W{w}: CarryOver {co_qty} > Limit {co_threshold}")
            # P評価
            p = week_data[3]
            p_qty = len(p) if isinstance(p, list) else p
            if p_qty > p_max_threshold:
                print(f"[Production Alert] {self.name} - W{w}: Production {p_qty} > Capacity {p_max_threshold}")
    def optimize_network(self):
        """
        ネットワーク最適化処理：
        赤字の場合や特定コスト項目が過大な場合に、改善案を提示する。
        """
        print(f"[Optimize] {self.name} evaluating cost structure...")
        # 基準閾値（例：%として定義）
        max_sga_ratio = 0.2
        max_logistics_ratio = 0.15
        max_warehouse_ratio = 0.10
        max_tax_ratio = 0.05
        # コスト合計と各項目を抽出
        total_cost = self.eval_cs_cost_total
        if total_cost == 0:
            print(f" - {self.name}: Skipped (no cost data)")
            return
        alerts = []
        # 各コスト比率を評価
        sga = self.eval_cs_SGA_total / total_cost
        if sga > max_sga_ratio:
            alerts.append(f"SG&A比率高: {sga:.2%} > {max_sga_ratio:.0%}")
            self.eval_cs_SGA_total *= 0.9  # 10%削減シミュレーション
        logistics = self.eval_cs_logistics_costs / total_cost
        if logistics > max_logistics_ratio:
            alerts.append(f"物流費高: {logistics:.2%} > {max_logistics_ratio:.0%}")
            self.eval_cs_logistics_costs *= 0.9
        wh = self.eval_cs_warehouse_cost / total_cost
        if wh > max_warehouse_ratio:
            alerts.append(f"倉庫費高: {wh:.2%} > {max_warehouse_ratio:.0%}")
            self.eval_cs_warehouse_cost *= 0.9
        tax = self.eval_cs_tax_portion / total_cost
        if tax > max_tax_ratio:
            alerts.append(f"税金高: {tax:.2%} > {max_tax_ratio:.0%}")
            self.eval_cs_tax_portion *= 0.95
        if alerts:
            print(f" - {self.name} コスト最適化対象:\n   " + "\n   ".join(alerts))
            # 再計算（簡易）
            self.eval_cs_cost_total = (
                self.eval_cs_SGA_total + self.eval_cs_logistics_costs +
                self.eval_cs_warehouse_cost + self.eval_cs_tax_portion +
                self.eval_cs_direct_materials_costs +
                self.eval_cs_prod_indirect_labor + self.eval_cs_prod_indirect_others +
                self.eval_cs_direct_labor_costs + self.eval_cs_depreciation_others
            )
            self.eval_cs_profit = self.eval_cs_price_sales_shipped - self.eval_cs_cost_total
            print(f"   => 改善後利益: {self.eval_cs_profit:.2f}")
        else:
            print(f" - {self.name}: コスト構成は良好です。")
# *************************
# 移行期なので継承のみ
# *************************
class GUINode(Node):
    # まだ何も追加しないので、Node とまったく同じ
    pass
class PlanNode(Node):
    # こちらもまったく同じ
    pass
#class GUINode(Node):
#    def __init__(self, name: str):
#        super().__init__(name)
#        self.position = (0, 0)       # GUI上の座標（x, y）
#        self.color = "#ffffff"       # ノードの表示色
#        self.folded = False          # 折りたたみ表示フラグ
#        self.selected = False        # 選択状態
#class PlanNode(Node):
#    def __init__(self, node_id: str, name: str, initial_inventory: int = 0):
#        super().__init__(name)
#        self.node_id = node_id
#        self.initial_inventory = initial_inventory
#        self.inventory = initial_inventory
#
#        # 週次PSI記録（簡易ロジック用）
#        self.weekly_plan = {}
#
#    def reset(self):
#        """PSI週次状態の初期化"""
#        self.inventory = self.initial_inventory
#        self.weekly_plan = {}
#
#    def plan_week(self, week: int, demand: int = 0, supply: int = 0):
#        """1週分のPSI処理"""
#        self.inventory += supply - demand
#        self.weekly_plan[week] = {
#            "week": week,
#            "node_id": self.node_id,
#            "name": self.name,
#            "demand": demand,
#            "supply": supply,
#            "inventory": self.inventory
#        }
#
#    def get_plan_summary(self):
#        """記録された週次データを返す"""
#        return list(self.weekly_plan.values())
# *************************
# class SKU
# *************************
class SKU:
    def __init__(self, product_name, node_name):
        self.product_name = product_name
        self.node_name = node_name
        # node_dict[sku.node_name] でNodeへアクセスできる
        self.psi_node_ref = None
        self.psi_table = defaultdict(lambda: {"I": 0, "P": 0, "S": 0, "CO": 0})  # week単位
        # *******************
        # move Node 2 SKU
        # *******************
        self.lot_size = 1  # default setting
        self.psi = []  # Placeholder for PSI data
        self.iso_week_demand = None  # Original demand converted to ISO week
        self.psi4demand = None
        self.psi4supply = None
        self.psi4couple = None
        self.psi4accume = None
        self.plan_range = 1
        self.plan_year_st = 2025
        self.safety_stock_week = 0
        self.long_vacation_weeks = []
        # For NetworkX
        self.leadtime = 1   # same as safety_stock_week
        self.nx_demand = 1  # weekly average demand by lot
        self.nx_weight = 1  # move_cost_all_to_nodeB (from nodeA to nodeB)
        self.nx_capacity = 1  # lot by lot
        # Evaluation
        self.decoupling_total_I = []  # total Inventory all over the plan
        # "lot_counts" is the bridge PSI2EVAL
        self.lot_counts = [0 for x in range(0, 53 * self.plan_range)]
        self.lot_counts_all = 0  # sum(self.lot_counts)
        # Settings for cost-profit evaluation parameter
        self.LT_boat = 1
        self.SS_days = 7
        self.HS_code = ""
        self.customs_tariff_rate = 0
        self.tariff_on_price = 0
        self.price_elasticity = 0
        # ******************************
        # evaluation data initialise rewardsを計算の初期化
        # ******************************
        # ******************************
        # Profit_Ratio #float
        # ******************************
        self.eval_profit_ratio = Profit_Ratio = 0.6
        # Revenue, Profit and Costs
        self.eval_revenue = 0
        self.eval_profit = 0
        self.eval_PO_cost = 0
        self.eval_P_cost = 0
        self.eval_WH_cost = 0
        self.eval_SGMC = 0
        self.eval_Dist_Cost = 0
        # ******************************
        # set_EVAL_cash_in_data #list for 53weeks * 5 years # 5年を想定
        # *******************************
        self.Profit = Profit = [0 for i in range(53 * self.plan_range)]
        self.Week_Intrest = Week_Intrest = [0 for i in range(53 * self.plan_range)]
        self.Cash_In = Cash_In = [0 for i in range(53 * self.plan_range)]
        self.Shipped_LOT = Shipped_LOT = [0 for i in range(53 * self.plan_range)]
        self.Shipped = Shipped = [0 for i in range(53 * self.plan_range)]
        # ******************************
        # set_EVAL_cash_out_data #list for 54 weeks
        # ******************************
        self.SGMC = SGMC = [0 for i in range(53 * self.plan_range)]
        self.PO_manage = PO_manage = [0 for i in range(53 * self.plan_range)]
        self.PO_cost = PO_cost = [0 for i in range(53 * self.plan_range)]
        self.P_unit = P_unit = [0 for i in range(53 * self.plan_range)]
        self.P_cost = P_cost = [0 for i in range(53 * self.plan_range)]
        self.I = I = [0 for i in range(53 * self.plan_range)]
        self.I_unit = I_unit = [0 for i in range(53 * self.plan_range)]
        self.WH_cost = WH_cost = [0 for i in range(53 * self.plan_range)]
        self.Dist_Cost = Dist_Cost = [0 for i in range(53 * self.plan_range)]
        # Cost structure demand
        self.price_sales_shipped = 0
        self.cost_total = 0
        self.profit = 0
        self.marketing_promotion = 0
        self.sales_admin_cost = 0
        self.SGA_total = 0
        self.custom_tax = 0
        self.tax_portion = 0
        self.logistics_costs = 0
        self.warehouse_cost = 0
        self.direct_materials_costs = 0
        self.purchase_total_cost = 0
        self.prod_indirect_labor = 0
        self.prod_indirect_others = 0
        self.direct_labor_costs = 0
        self.depreciation_others = 0
        self.manufacturing_overhead = 0
        # Profit accumulated root to node
        self.cs_profit_accume = 0
        # Cost Structure
        self.cs_price_sales_shipped = 0
        self.cs_cost_total = 0
        self.cs_profit = 0
        self.cs_marketing_promotion = 0
        self.cs_sales_admin_cost = 0
        self.cs_SGA_total = 0
        #self.cs_custom_tax = 0 # stop tariff_rate
        self.cs_tax_portion = 0
        self.cs_logistics_costs = 0
        self.cs_warehouse_cost = 0
        self.cs_direct_materials_costs = 0
        self.cs_purchase_total_cost = 0
        self.cs_prod_indirect_labor = 0
        self.cs_prod_indirect_others = 0
        self.cs_direct_labor_costs = 0
        self.cs_depreciation_others = 0
        self.cs_manufacturing_overhead = 0
        # Evaluated cost = Cost Structure X lot_counts
        self.eval_cs_price_sales_shipped = 0  # revenue
        self.eval_cs_cost_total = 0  # cost
        self.eval_cs_profit = 0  # profit
        self.eval_cs_marketing_promotion = 0
        self.eval_cs_sales_admin_cost = 0
        self.eval_cs_SGA_total = 0
        #self.eval_cs_custom_tax = 0 # stop tariff rate
        self.eval_cs_tax_portion = 0
        self.eval_cs_logistics_costs = 0
        self.eval_cs_warehouse_cost = 0
        self.eval_cs_direct_materials_costs = 0
        self.eval_cs_purchase_total_cost = 0
        self.eval_cs_prod_indirect_labor = 0
        self.eval_cs_prod_indirect_others = 0
        self.eval_cs_direct_labor_costs = 0
        self.eval_cs_depreciation_others = 0
        self.eval_cs_manufacturing_overhead = 0
        # Shipped lots count W / M / Q / Y / LifeCycle
        self.shipped_lots_W = []  # 53*plan_range
        self.shipped_lots_M = []  # 12*plan_range
        self.shipped_lots_Q = []  # 4*plan_range
        self.shipped_lots_Y = []  # 1*plan_range
        self.shipped_lots_L = []  # 1  # lifecycle a year
        # Planned Amount
        self.amt_price_sales_shipped = []    # Revenue cash_IN???
        self.amt_cost_total = []
        self.amt_profit = []                 # Profit
        self.amt_marketing_promotion = []
        self.amt_sales_admin_cost = []
        self.amt_SGA_total = []
        self.amt_custom_tax = []
        self.amt_tax_portion = []
        self.amt_logistiamt_costs = []
        self.amt_warehouse_cost = []
        self.amt_direct_materials_costs = [] # FOB@port
        self.amt_purchase_total_cost = []    #
        self.amt_prod_indirect_labor = []
        self.amt_prod_indirect_others = []
        self.amt_direct_labor_costs = []
        self.amt_depreciation_others = []
        self.amt_manufacturing_overhead = []
        # Shipped amt W / M / Q / Y / LifeCycle
        self.shipped_amt_W = []  # 53*plan_range
        self.shipped_amt_M = []  # 12*plan_range
        self.shipped_amt_Q = []  # 4*plan_range
        self.shipped_amt_Y = []  # 1*plan_range
        self.shipped_amt_L = []  # 1  # lifecycle a year
        # Control FLAGs
        self.cost_standard_flag = 0
        self.PSI_graph_flag = "OFF"
        self.buffering_stock_flag = "OFF"
        self.revenue = 0
        self.profit  = 0
        self.AR_lead_time = 0 # Accounts Receivable 売掛
        self.AP_lead_time = 0 # Accounts Payable 買掛
    def set_attributes(self, row):
        """
        SKU単位の属性セット関数。
        PSI関連のロジックおよびコスト関連をSKUオブジェクトに保持する。
        """
        self.lot_size = int(row["lot_size"])
        self.leadtime = int(row["leadtime"])
        self.long_vacation_weeks = eval(row["long_vacation_weeks"])
        self.LT_boat = float(row["LT_boat"])
        self.SS_days = float(row["SS_days"])
        self.HS_code = str(row["HS_code"])
        self.customs_tariff_rate = float(row["customs_tariff_rate"])
        self.price_elasticity = float(row["price_elasticity"])
        self.cost_standard_flag = float(row["cost_standard_flag"])
        self.AR_lead_time = float(row["AR_lead_time"])
        self.AP_lead_time = float(row["AP_lead_time"])
        self.PSI_graph_flag = str(row["PSI_graph_flag"])
        self.buffering_stock_flag = str(row["buffering_stock_flag"])
## ✅ ① `SKU.set_cost_attr()` の追加定義案（Node版に準拠）
### 🔧 `SKU`クラス内に以下を追加：
    def set_cost_attr(
        self,
        price_sales_shipped,
        cost_total,
        profit,
        marketing_promotion=None,
        sales_admin_cost=None,
        SGA_total=None,
        logistics_costs=None,
        warehouse_cost=None,
        direct_materials_costs=None,
        purchase_total_cost=None,
        prod_indirect_labor=None,
        prod_indirect_others=None,
        direct_labor_costs=None,
        depreciation_others=None,
        manufacturing_overhead=None,
        ):
        self.price_sales_shipped = price_sales_shipped
        self.cost_total = cost_total
        self.profit = profit
        self.marketing_promotion = marketing_promotion or 0
        self.sales_admin_cost = sales_admin_cost or 0
        self.SGA_total = SGA_total or (self.marketing_promotion + self.sales_admin_cost)
        self.logistics_costs = logistics_costs or 0
        self.warehouse_cost = warehouse_cost or 0
        self.direct_materials_costs = direct_materials_costs or 0
        self.purchase_total_cost = purchase_total_cost or (
        self.logistics_costs + self.warehouse_cost + self.direct_materials_costs )
        self.prod_indirect_labor = prod_indirect_labor or 0
        self.prod_indirect_others = prod_indirect_others or 0
        self.direct_labor_costs = direct_labor_costs or 0
        self.depreciation_others = depreciation_others or 0
        self.manufacturing_overhead = manufacturing_overhead or (
        self.prod_indirect_labor + self.prod_indirect_others + self.direct_labor_costs + self.depreciation_others
        )
    def normalize_cost(self):
        cost_total = self.add_tax_sum_cost()
        # self.node_name = node_name # node_name is STOP
        self.direct_materials_costs = self.direct_materials_costs / cost_total
        #self.custom_tax = custom_tax # STOP this is rate
        self.tax_portion            = self.tax_portion            / cost_total
        self.profit                 = self.profit                 / cost_total
        self.marketing_promotion    = self.marketing_promotion    / cost_total
        self.sales_admin_cost       = self.sales_admin_cost       / cost_total
        self.logistics_costs        = self.logistics_costs        / cost_total
        self.warehouse_cost         = self.warehouse_cost         / cost_total
        self.prod_indirect_labor    = self.prod_indirect_labor    / cost_total
        self.prod_indirect_others   = self.prod_indirect_others   / cost_total
        self.direct_labor_costs     = self.direct_labor_costs     / cost_total
        self.depreciation_others    = self.depreciation_others    / cost_total
        self.SGA_total              = ( self.marketing_promotion
                                    + self.sales_admin_cost )
        self.purchase_total_cost    = ( self.logistics_costs
                                    + self.warehouse_cost
                                    + self.direct_materials_costs
                                    + self.tax_portion )
        self.manufacturing_overhead = ( self.prod_indirect_labor
                                    +  self.prod_indirect_others
                                    +  self.direct_labor_costs
                                    +  self.depreciation_others )
        self.cost_total             = ( self.purchase_total_cost
                                    + self.SGA_total
                                    + self.manufacturing_overhead )
        self.price_sales_shipped    = self.cost_total + self.profit
    def add_tax_sum_cost(self):
        # calc_custom_tax
        self.tax_portion = self.direct_materials_costs * self.customs_tariff_rate
        cost_total = 0
        cost_total = (
            self.direct_materials_costs
            # this is CUSTOM_TAX
            #+ self.direct_materials_costs * self.customs_tariff_rate
            + self.tax_portion
            + self.marketing_promotion
            + self.sales_admin_cost
            + self.logistics_costs
            + self.warehouse_cost
            + self.prod_indirect_labor
            + self.prod_indirect_others
            + self.direct_labor_costs
            + self.depreciation_others
            + self.profit
        )
        print("SKU cost_total", self.product_name, self.node_name, cost_total)
        return cost_total
