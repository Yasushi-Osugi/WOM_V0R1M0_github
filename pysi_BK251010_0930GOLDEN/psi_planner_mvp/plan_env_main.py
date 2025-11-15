#plan_env_main.py
#EPNode = "Engine Proxy Node"
# ******************************
#@250811 chatGPT defined
# ******************************
#
# plan_env.py などに配置
from __future__ import annotations
from typing import Dict, List, Tuple, Optional, Type
import csv, os
# ********************************
# library import
# ********************************
import copy
import pickle
# ********************************
# library import
# ********************************
from collections import defaultdict
import numpy as np
from dateutil.relativedelta import relativedelta
import calendar
# ********************************
# Allocation logic
# ********************************
from datetime import date, timedelta
from math import floor
# ********************************
# Cost Evaluation
# ********************************
import json
# ********************************
# PySI library import
# ********************************
from pysi.network.node_base import Node, PlanNode, GUINode, SKU
from pysi.utils.config import Config
from pysi.utils.file_io import *
from pysi.utils.calendar445 import Calendar445
#from pysi.plan.demand_generate import convert_monthly_to_weekly
from pysi.plan.demand_generate import (
    _normalize_monthly_demand_df_sku,
    convert_monthly_to_weekly_sku,
    check_plan_range,
)
from pysi.plan.operations import *
# "plan.demand_processing" is merged in "plan.operations"
#from plan.demand_processing import *
from pysi.plan.operations import set_df_Slots2psi4demand
from pysi.network.node_base import Node, PlanNode, GUINode
from pysi.evaluate.evaluate_cost_models_v2 import gui_run_initial_propagation, propagate_cost_to_plan_nodes, load_tobe_prices, assign_tobe_prices_to_leaf_nodes, load_asis_prices, assign_asis_prices_to_root_nodes
# 既存の PlanNode を注入できるようにしておく（未指定なら内蔵の極小版を使う）
class _MiniPlanNode:
    def __init__(self, name: str, node_type: str = "node"):
        self.id = name              # 既存系が id と name を持つ想定に合わせる
        self.name = name
        self.node_type = node_type
        self.children: List["_MiniPlanNode"] = []
        self.parent: Optional["_MiniPlanNode"] = None
        # 任意属性（必要に応じてエンジン橋渡し時に使う）
        self.lot_size: Optional[int] = None
        self.leadtime: Optional[int] = None
        self.sku_name: Optional[str] = None     # 「SKUクラス不使用」前提で文字列だけ持つ
    def add_child(self, c: "_MiniPlanNode"):
        c.parent = self
        self.children.append(c)
# ******************************
#@250811 chatGPT defined
# ******************************
class PlanEnv:
    """GUIを剥がした最小の計画モデルホルダ
       - prod_tree_dict_OT/IN に {product_name: PlanNode(root)} を持つ
    """
    def __init__(self, config: Optional):
    #def __init__(self):
        self.base_dir: str = ""
        self.product_name_list: List[str] = []
        self.product_selected: Optional[str] = None
        self.prod_tree_dict_OT: Dict[str, object] = {}
        self.prod_tree_dict_IN: Dict[str, object] = {}
        self.config = config
        self.tree_structure = None
        # setup_uiの前にproduct selectを初期化
        self.product_name_list = []
        self.product_selected = None
        # 必要な初期化処理を後から呼び出す
        self.initialize_parameters()
        # ********************************
        # PSI planner
        # ********************************
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
        self.nodes_out_opt      = {}
        self.leaf_nodes_opt     = []
        self.optimized_root     = None
        self.optimized_nodes    = {}
        self.node_psi_dict_In4Dm = {}  # 需要側 PSI 辞書
        self.node_psi_dict_In4Sp = {}  # 供給側 PSI 辞書
        # market
        self.market_potential = 0
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
        #self.directory = None
        self.directory = config.DATA_DIRECTORY
        self.load_directory = None
        self.base_leaf_name = {} # { product_name: leaf_node_name, ,,,}
        # supply_plan / decoupling / buffer stock
        self.decouple_node_dic = {}
        self.decouple_node_selected = []
    # ---- public helpers -------------------------------------------------
    def get_roots(self, product: Optional[str] = None) -> Tuple[object, object]:
        """選択製品の (OUT_root, IN_root) を返す（無い側は None）"""
        p = product or self.product_selected
        return self.prod_tree_dict_OT.get(p), self.prod_tree_dict_IN.get(p)
    def iter_products(self):
        for p in self.product_name_list:
            yield p
    # ---- factory --------------------------------------------------------
    @classmethod
    def from_dir(cls, dir_path: str, PlanNodeClass: Type = _MiniPlanNode) -> "PlanEnv":
        """CSVディレクトリから PlanEnv を構築する最小版。
           期待列: Product_name, Parent_node, Child_node, lot_size, leadtime
        """
        def _read_csv(path: str) -> List[dict]:
            with open(path, newline="", encoding="utf-8-sig") as f:
                return list(csv.DictReader(f))
        def _build_prod_tree(rows: List[dict], product: str) -> Optional[object]:
            rows_p = [r for r in rows if r.get("Product_name") == product]
            if not rows_p:
                return None
            nodes: Dict[str, object] = {}
            has_parent = set()
            for r in rows_p:
                pn = r["Parent_node"].strip()
                cn = r["Child_node"].strip()
                # ノード生成
                if pn not in nodes: nodes[pn] = PlanNodeClass(pn)
                if cn not in nodes: nodes[cn] = PlanNodeClass(cn)
                parent = nodes[pn]; child = nodes[cn]
                # 属性（あれば）
                try: child.lot_size = int(r.get("lot_size", "") or 0) or None
                except: pass
                try: child.leadtime = int(r.get("leadtime", "") or 0) or None
                except: pass
                child.sku_name = product
                # 接続
                parent.add_child(child)
                has_parent.add(cn)
            # ルート推定：親を持たないノード、なければ 'supply_point' 優先
            candidates = [n for n in nodes if n not in has_parent]
            root_name = "supply_point" if "supply_point" in nodes else (candidates[0] if candidates else None)
            return nodes[root_name] if root_name else None
        # --- 準備
        env = cls()
        env.base_dir = dir_path
        # ファイル存在確認
        ot_path = os.path.join(dir_path, "product_tree_outbound.csv")
        in_path = os.path.join(dir_path, "product_tree_inbound.csv")
        rows_ot = _read_csv(ot_path) if os.path.exists(ot_path) else []
        rows_in = _read_csv(in_path) if os.path.exists(in_path) else []
        # 製品一覧（OUT/IN の和集合）
        prods = {r["Product_name"] for r in rows_ot} | {r["Product_name"] for r in rows_in}
        env.product_name_list = sorted(prods)
        env.product_selected = env.product_name_list[0] if env.product_name_list else None
        # 製品別ツリーを構築
        for p in env.product_name_list:
            root_ot = _build_prod_tree(rows_ot, p)
            root_in = _build_prod_tree(rows_in, p)
            if root_ot: env.prod_tree_dict_OT[p] = root_ot
            if root_in: env.prod_tree_dict_IN[p] = root_in
        return env
# ******************************
# PlanEnv method def(self, xxx) start
# ******************************
# *****************************
    def initialize_parameters(self):
        self.directory      = self.config.DATA_DIRECTORY
        self.load_directory = self.config.DATA_DIRECTORY
        print("Initializing parameters")
        self.lot_size     = self.config.DEFAULT_LOT_SIZE
        self.plan_year_st = self.config.DEFAULT_START_YEAR
        self.plan_range   = self.config.DEFAULT_PLAN_RANGE
        self.pre_proc_LT  = self.config.DEFAULT_PRE_PROC_LT
        # self.market_potential = 0 # initial setting from "demand_generate"
        self.target_share = self.config.DEFAULT_TARGET_SHARE
        self.total_supply = 0
        #if not hasattr(self, 'gmp_entry') or not hasattr(self, 'ts_entry') or not hasattr(self, 'tsp_entry'):
        #    raise AttributeError("Required UI components (gmp_entry, ts_entry, tsp_entry) have not been initialized.")
        print("Setting market potential and share")
        # Calculation and setting of Global Market Potential
        #market_potential = getattr(self, 'market_potential', self.config.DEFAULT_MARKET_POTENTIAL)  # Including initial settings
        self.market_potential = self.config.DEFAULT_MARKET_POTENTIAL  # Including initial settings
        self.target_share             = 0.5 # target_share
        target_share      =  self.target_share      # 0.5 #
        market_potential  =  self.market_potential
        total_supply_plan = round(market_potential * target_share)
        # Calculation and setting of Total Supply Plan
        self.market_potential         = market_potential
        self.target_share             = target_share
        self.total_supply_plan        = total_supply_plan
        print(f"At initialization - market_potential: {self.market_potential}, target_share: {self.target_share}")  # Add log
    #@250819 Refactoring
    def load_data_files(self):
        """
        データファイルの読み込みと初期設定を実行
        """
        # --- ディレクトリとパラメータ初期化 ---
        self._init_data_directory()
        self._init_plan_parameters()
        # --- CSV 読み込み ---
        self._load_tree_csvs()
        # --- 製品リスト初期化 ---
        self._extract_product_names()
        # --- PlanNode ツリー構築 ---
        self._build_plan_node_trees()
        # --- GUIノードとPlanNodeのリンク ---
        self._link_plan_nodes_to_gui()
        # --- コストテーブル読み込み・反映 ---
        self._load_cost_tables()
        # --- 価格伝播の実行（TOBE/ASIS）---
        self._run_price_propagation()
        # --- 月次需要 → 週次PSIスロットに変換（if exists）---
        self.init_psi_spaces_and_demand()
        # --- オファリング価格を出力 ---
        self.export_offering_prices(os.path.join(self.directory, "offering_price_ASIS_TOBE.csv"))
        # --- 終了ログ ---
        print("product_name_list", self.product_name_list)
        print("End of load_data_files")
    # **************************************
    # smoke chack
    # **************************************
    #1) PSI バッファ長さの確認（全ノード同一長）
    ## どれか1製品を確認
    #prod = next(iter(psi.prod_tree_dict_OT))
    #root = psi.prod_tree_dict_OT[prod]
    #
    #def first_node(n):
    #    return n if not getattr(n, "children", []) else n.children[0]
    #
    #n0 = first_node(root)  # 適当な子
    #print("weeks(len psi4demand) =", len(n0.psi4demand), " plan_range=", psi.plan_r#ange)
    #assert len(n0.psi4demand) == 53 * psi.plan_range
    #
    #2) 週次Sロットの整合チェック（leafの合計=DFの合計）
    #
    #init_psi_spaces_and_demand() 内でも検証していますが、任意に1葉で再確認：
    #
    #def leaves(n):
    #    st=[n]; out=[]
    #    while st:
    #        x=st.pop()
    #        cs = getattr(x, "children", []) or []
    #        if not cs: out.append(x)
    #        else: st.extend(cs)
    #    return out
    #
    #leaf = leaves(root)[0]
    #psi_total = sum(len(leaf.psi4demand[w][0]) for w in range(len(leaf.psi4demand))#)
    #print(f"[{prod}] leaf={leaf.name} total S lots in PSI =", psi_total)
    ## ここで DataFrame 側の総計と一致していればOK（init_psi_spaces_and_demand() 内#のログとも一致するはず）
    #
    #3) オファリング価格CSVの出力確認
    #import os
    #out_csv = os.path.join(psi.directory, "offering_price_ASIS_TOBE.csv")
    #print("exists:", os.path.exists(out_csv), " path:", out_csv)
#関数名	主な役割
#_prepare_directories_and_config()	ディレクトリ・config の初期設定
#_load_gui_trees()	product_tree_outbound/inbound.csv をGUI用の辞書にロード
#_extract_product_names()	製品名一覧を抽出して self.product_name_list に保存
#_build_plan_trees_per_product()	PlanNode のツリーを製品ごとに構築し、属性をセット（lot_size, leadtime, holiday_weeks）
#_link_plan_nodes_to_gui()	PlanNode を GUIノード (GUINode) にリンク付け
#_load_and_assign_cost_tables()	sku_cost_table_xxx.csv を読み込んでコスト情報を PlanNode にセット
#_propagate_prices_and_costs()	TOBE/ASIS価格の伝播と計画ノードへの反映
#_check_demand_data()	月次需要データがあるか確認し、メッセージを出すだけ
#_export_offering_prices()	offering price CSV を出力（あれば）
    def _prepare_directories_and_config(self) -> bool:
        """Configとディレクトリの初期化。失敗したらFalseを返す"""
        import os
        if not getattr(self, "directory", None):
            if getattr(self, "config", None) and getattr(self.config, "DATA_DIRECTORY", None):
                self.directory = self.config.DATA_DIRECTORY
            else:
                print("[ERROR] DATA directory is not set.")
                return False
        directory = self.directory
        if not os.path.isdir(directory):
            print(f"[ERROR] Data directory not found: {directory}")
            return False
        self.load_directory = directory
        self.data_file_list = set(os.listdir(directory))
        print("Initializing parameters")
        self.lot_size     = getattr(self.config, "DEFAULT_LOT_SIZE", 1000)
        self.plan_year_st = getattr(self.config, "DEFAULT_START_YEAR", 2024)
        self.plan_range   = getattr(self.config, "DEFAULT_PLAN_RANGE", 3)
        self.pre_proc_LT  = getattr(self.config, "DEFAULT_PRE_PROC_LT", 2)
        self.target_share = getattr(self.config, "DEFAULT_TARGET_SHARE", 0.5)
        print("Setting market potential and share")
        self.market_potential  = getattr(self.config, "DEFAULT_MARKET_POTENTIAL", 10000)
        self.total_supply_plan = round(self.market_potential * self.target_share)
        print(f"At initialization - market_potential: {self.market_potential}, target_share: {self.target_share}")
        return True
    def _load_gui_trees(self):
        """
        product_tree_outbound.csv / product_tree_inbound.csv を読み込み、
        依存ユーティリティ無しで GUINode ツリー(dict)を構築する。
        - 期待列: Product_name, Parent_node, Child_node, [lot_size], [leadtime]
        - ルートは 'supply_point' 優先、無ければ「親を持たないノード」
        """
        import os, csv
        from pysi.network.node_base import GUINode
        def _path(fname: str) -> str:
            return os.path.join(self.directory, fname)
        def _read_csv(path: str) -> list[dict]:
            if not os.path.exists(path):
                return []
            with open(path, newline="", encoding="utf-8-sig") as f:
                return list(csv.DictReader(f))
        def _build_gui_tree(rows: list[dict]) -> tuple[dict[str, GUINode], str | None]:
            """
            CSV行全体から GUI ノード辞書を構築。製品横断のノード集合を作る。
            返り: (nodes_dict, root_name)  root_name は最初の製品のものを代表として採用する
            """
            nodes: dict[str, GUINode] = {}
            has_parent: set[str] = set()
            # ノード生成・接続
            for r in rows:
                pn = r.get("Parent_node", "").strip()
                cn = r.get("Child_node", "").strip()
                if not pn or not cn:
                    # 空行や不正行はスキップ
                    continue
                if pn not in nodes:
                    nodes[pn] = GUINode(name=pn)
                if cn not in nodes:
                    nodes[cn] = GUINode(name=cn)
                parent = nodes[pn]
                child  = nodes[cn]
                parent.add_child(child)
                child.parent = parent
                has_parent.add(cn)
                # 任意属性（あれば）
                # lot_size / leadtime は PlanNode 側で主に使う想定だが、一応保持
                try:
                    ls = int(r.get("lot_size") or 0) or None
                except Exception:
                    ls = None
                try:
                    lt = int(r.get("leadtime") or 0) or None
                except Exception:
                    lt = None
                if ls is not None:
                    setattr(child, "lot_size", ls)
                if lt is not None:
                    setattr(child, "leadtime", lt)
            if not nodes:
                return {}, None
            # ルート推定
            root_name = "supply_point" if "supply_point" in nodes else None
            if root_name is None:
                # 親を持たないものが候補
                candidates = [n for n in nodes.keys() if n not in has_parent]
                root_name = candidates[0] if candidates else None
            return nodes, root_name
        # --- OUTBOUND ---
        self.nodes_outbound, self.root_node_outbound = {}, None
        if "product_tree_outbound.csv" in getattr(self, "data_file_list", set()):
            rows_ot = _read_csv(_path("product_tree_outbound.csv"))
            nodes_ot, root_name_ot = _build_gui_tree(rows_ot)
            self.nodes_outbound = nodes_ot
            self.root_node_outbound = nodes_ot.get(root_name_ot) if root_name_ot else None
            if not nodes_ot:
                print("[ERROR] product_tree_outbound.csv had no valid rows.")
        else:
            print("[ERROR] product_tree_outbound.csv is missing.")
        # --- INBOUND ---
        self.nodes_inbound, self.root_node_inbound = {}, None
        if "product_tree_inbound.csv" in getattr(self, "data_file_list", set()):
            rows_in = _read_csv(_path("product_tree_inbound.csv"))
            nodes_in, root_name_in = _build_gui_tree(rows_in)
            self.nodes_inbound = nodes_in
            self.root_node_inbound = nodes_in.get(root_name_in) if root_name_in else None
            if not nodes_in:
                print("[ERROR] product_tree_inbound.csv had no valid rows.")
        else:
            print("[ERROR] product_tree_inbound.csv is missing.")
        # --- 簡易ログ（親子確認）---
        def _print_parent_all(root: GUINode | None):
            if root is None:
                return
            stack = [root]
            seen = set()
            while stack:
                n = stack.pop()
                if n in seen:
                    continue
                seen.add(n)
                p = getattr(n, "parent", None)
                print(f"[TREE] {getattr(n,'name',None)}  parent= {getattr(p,'name',None)}")
                for c in getattr(n, "children", []) or []:
                    stack.append(c)
        if self.root_node_outbound:
            _print_parent_all(self.root_node_outbound)
        if self.root_node_inbound:
            _print_parent_all(self.root_node_inbound)
        if not self.nodes_outbound:
            print("[WARN] nodes_outbound is empty. Export may be empty if no plan trees are built/linked.")
    def _extract_product_names(self):
        """product_tree_*.csv から製品名一覧を抽出"""
        import os, csv
        def _read_csv(path: str) -> list[dict]:
            if not os.path.exists(path):
                return []
            with open(path, newline="", encoding="utf-8-sig") as f:
                return list(csv.DictReader(f))
        def _path(fname: str) -> str:
            return os.path.join(self.directory, fname)
        rows_ot = _read_csv(_path("product_tree_outbound.csv")) if "product_tree_outbound.csv" in self.data_file_list else []
        rows_in = _read_csv(_path("product_tree_inbound.csv"))  if "product_tree_inbound.csv"  in self.data_file_list else []
        prods_ot = {r["Product_name"].strip() for r in rows_ot if r.get("Product_name")}
        prods_in = {r["Product_name"].strip() for r in rows_in if r.get("Product_name")}
        self.product_name_list = sorted(prods_ot | prods_in)
        self.product_selected  = self.product_name_list[0] if self.product_name_list else None
        print("[DEBUG] products detected:", self.product_name_list)
        if not self.product_name_list:
            print("[ERROR] No Product_name found in product_tree_*.csv. Check column names and data.")
    def _build_plan_node_trees(self):
        """製品別に PlanNode ツリーを構築して prod_tree_dict_XX に格納"""
        import os, csv
        from pysi.network.node_base import PlanNode
        from pysi.network.tree import set_parent_all
        #from pysi.utils.file_io import set_parent_all
        def _path(fname: str) -> str:
            return os.path.join(self.directory, fname)
        def _read_csv(path: str) -> list[dict]:
            if not os.path.exists(path):
                return []
            with open(path, newline="", encoding="utf-8-sig") as f:
                return list(csv.DictReader(f))
        def _build_tree(rows: list[dict], product: str) -> dict[str, PlanNode]:
            node_dict: dict[str, PlanNode] = {}
            rows_p = [r for r in rows if r.get("Product_name") == product]
            for r in rows_p:
                pn = r["Parent_node"].strip()
                cn = r["Child_node"].strip()
                if pn not in node_dict:
                    node_dict[pn] = PlanNode(name=pn)
                if cn not in node_dict:
                    node_dict[cn] = PlanNode(name=cn)
                parent = node_dict[pn]
                child  = node_dict[cn]
                try:
                    child.lot_size = int(r.get("lot_size") or 0) or None
                except:
                    child.lot_size = None
                try:
                    child.leadtime = int(r.get("leadtime") or 0) or None
                except:
                    child.leadtime = None
                # SKUは最低限の構造で安全に定義
                if not getattr(child, "sku", None):
                    child.sku = SKU(product, child.name)
                parent.add_child(child)
            return node_dict
        rows_ot = _read_csv(_path("product_tree_outbound.csv"))
        rows_in = _read_csv(_path("product_tree_inbound.csv"))
        self.prod_tree_dict_OT = {}
        self.prod_tree_dict_IN = {}
        for product in self.product_name_list:
            # OUTBOUND
            nodes_ot = _build_tree(rows_ot, product)
            if nodes_ot:
                root_name = "supply_point"
                if root_name not in nodes_ot:
                    has_parent = {r["Child_node"].strip() for r in rows_ot if r["Product_name"] == product}
                    candidates = [n for n in nodes_ot.keys() if n not in has_parent]
                    root_name = candidates[0] if candidates else None
                if root_name:
                    root = nodes_ot[root_name]
                    set_parent_all(root)
                    self.prod_tree_dict_OT[product] = root
            # INBOUND
            nodes_in = _build_tree(rows_in, product)
            if nodes_in:
                root_name = "supply_point"
                if root_name not in nodes_in:
                    has_parent = {r["Child_node"].strip() for r in rows_in if r["Product_name"] == product}
                    candidates = [n for n in nodes_in.keys() if n not in has_parent]
                    root_name = candidates[0] if candidates else None
                if root_name:
                    root = nodes_in[root_name]
                    set_parent_all(root)
                    self.prod_tree_dict_IN[product] = root
    # === PlanEnv class 内に追記（既存メソッドは消さない）====================
    def _init_data_directory(self):
        """
        旧: _prepare_directories_and_config() のラッパ
        True/False を返す旧関数と違い、ここでは失敗時に例外へ統一
        """
        ok = getattr(self, "_prepare_directories_and_config", None)
        if callable(ok):
            if not self._prepare_directories_and_config():
                raise RuntimeError("[ERROR] DATA directory initialization failed.")
        else:
            # 後方互換：最低限の初期化
            import os
            if not getattr(self, "directory", None):
                if getattr(self, "config", None) and getattr(self.config, "DATA_DIRECTORY", None):
                    self.directory = self.config.DATA_DIRECTORY
                else:
                    raise RuntimeError("[ERROR] DATA directory is not set.")
            if not os.path.isdir(self.directory):
                raise FileNotFoundError(f"[ERROR] Data directory not found: {self.directory}")
            self.load_directory = self.directory
            self.data_file_list = set(os.listdir(self.directory))
    def _init_plan_parameters(self):
        """
        既に __init__ や initialize_parameters() で設定済みでも安全に再確認する。
        """
        # もし initialize_parameters があるなら再利用
        if hasattr(self, "initialize_parameters") and callable(self.initialize_parameters):
            # directory を上書きしないため、必要プロパティのみ確認/補完
            if not getattr(self, "lot_size", None):
                self.initialize_parameters()
        else:
            # フォールバック：config から最低限を補完
            self.lot_size     = getattr(self.config, "DEFAULT_LOT_SIZE", 1000)
            self.plan_year_st = getattr(self.config, "DEFAULT_START_YEAR", 2024)
            self.plan_range   = getattr(self.config, "DEFAULT_PLAN_RANGE", 3)
            self.pre_proc_LT  = getattr(self.config, "DEFAULT_PRE_PROC_LT", 2)
            self.target_share = getattr(self.config, "DEFAULT_TARGET_SHARE", 0.5)
            self.market_potential  = getattr(self.config, "DEFAULT_MARKET_POTENTIAL", 10000)
            self.total_supply_plan = round(self.market_potential * self.target_share)
    def _load_tree_csvs(self):
        """
        旧: _load_gui_trees() のラッパ
        """
        if hasattr(self, "_load_gui_trees") and callable(self._load_gui_trees):
            self._load_gui_trees()
        else:
            raise AttributeError("Expected method _load_gui_trees() not found.")
    def _load_cost_tables(self):
        """
        sku_cost_table_outbound/inbound.csv を読み込み、PlanNode.sku / PlanNode.cs_* に反映。
        その後、必要なら PlanNode 側の評価値コピーを実施。
        """
        import os, csv
        # 既存の cost setter に合わせてローカル実装
        def _load_cost_param_csv(filepath: str) -> dict:
            param_dict = {}
            if not os.path.exists(filepath):
                return param_dict
            with open(filepath, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    product = row.get("product_name")
                    node    = row.get("node_name")
                    if not product or not node:
                        continue
                    param_dict.setdefault(product, {})[node] = {
                        "price": float(row.get("price_sales_shipped", 0) or 0),
                        "cost_total": float(row.get("cost_total", 0) or 0),
                        "profit_margin": float(row.get("profit", 0) or 0),
                        "marketing": float(row.get("marketing_promotion", 0) or 0),
                        "sales_admin_cost": float(row.get("sales_admin_cost", 0) or 0),
                        "SGA_total": float(row.get("SGA_total", 0) or 0),
                        "transport_cost": float(row.get("logistics_costs", 0) or 0),
                        "storage_cost": float(row.get("warehouse_cost", 0) or 0),
                        "purchase_price": float(row.get("direct_materials_costs", 0) or 0),
                        "tariff_cost": float(row.get("tariff_cost", 0) or 0),
                        "purchase_total_cost": float(row.get("purchase_total_cost", 0) or 0),
                        "direct_labor_costs": float(row.get("direct_labor_costs", 0) or 0),
                        "fixed_cost": float(row.get("manufacturing_overhead", 0) or 0),
                        "prod_indirect_labor": float(row.get("prod_indirect_labor", 0) or 0),
                        "prod_indirect_cost": float(row.get("prod_indirect_others", 0) or 0),
                        "depreciation_cost": float(row.get("depreciation_others", 0) or 0),
                    }
            return param_dict
        def _apply_costs(root, param_dict: dict, product_name: str):
            from pysi.network.node_base import SKU
            def walk(n):
                setting = param_dict.get(product_name, {}).get(n.name)
                if setting:
                    sku = getattr(n, "sku", None)
                    if not sku:
                        sku = SKU(product_name, n.name)
                        n.sku = sku
                    # SKU 側
                    sku.price               = setting["price"]
                    sku.cost_total          = setting["cost_total"]
                    sku.profit_margin       = setting["profit_margin"]
                    sku.marketing           = setting["marketing"]
                    sku.sales_admin_cost    = setting["sales_admin_cost"]
                    sku.SGA_total           = setting["SGA_total"]
                    sku.transport_cost      = setting["transport_cost"]
                    sku.storage_cost        = setting["storage_cost"]
                    sku.purchase_price      = setting["purchase_price"]
                    sku.tariff_cost         = setting["tariff_cost"]
                    sku.purchase_total_cost = setting["purchase_total_cost"]
                    sku.direct_labor_costs  = setting["direct_labor_costs"]
                    sku.fixed_cost          = setting["fixed_cost"]
                    sku.prod_indirect_labor = setting["prod_indirect_labor"]
                    sku.prod_indirect_cost  = setting["prod_indirect_cost"]
                    sku.depreciation_cost   = setting["depreciation_cost"]
                    # PlanNode 側ミラー
                    n.cs_price_sales_shipped    = sku.price
                    n.cs_cost_total             = sku.cost_total
                    n.cs_profit                 = sku.profit_margin
                    n.cs_marketing_promotion    = sku.marketing
                    n.cs_sales_admin_cost       = sku.sales_admin_cost
                    n.cs_SGA_total              = sku.SGA_total
                    n.cs_logistics_costs        = sku.transport_cost
                    n.cs_warehouse_cost         = sku.storage_cost
                    n.cs_direct_materials_costs = sku.purchase_price
                    n.cs_tax_portion            = sku.tariff_cost
                    n.cs_purchase_total_cost    = sku.purchase_total_cost
                    n.cs_direct_labor_costs     = sku.direct_labor_costs
                    n.cs_manufacturing_overhead = sku.fixed_cost
                    n.cs_prod_indirect_labor    = sku.prod_indirect_labor
                    n.cs_prod_indirect_others   = sku.prod_indirect_cost
                    n.cs_depreciation_others    = sku.depreciation_cost
                for c in getattr(n, "children", []):
                    walk(c)
            walk(root)
        ot_csv = os.path.join(self.directory, "sku_cost_table_outbound.csv")
        in_csv = os.path.join(self.directory, "sku_cost_table_inbound.csv")
        cost_ot = _load_cost_param_csv(ot_csv)
        cost_in = _load_cost_param_csv(in_csv)
        for prod, root in self.prod_tree_dict_OT.items():
            if cost_ot:
                _apply_costs(root, cost_ot, prod)
        for prod, root in self.prod_tree_dict_IN.items():
            if cost_in:
                _apply_costs(root, cost_in, prod)
    def _run_price_propagation(self):
        """
        selling_price_table / shipping_price_table があれば割当→初期伝播→PlanNodeへ反映
        """
        import os
        from pysi.evaluate.evaluate_cost_models_v2 import (
            load_tobe_prices, assign_tobe_prices_to_leaf_nodes,
            load_asis_prices, assign_asis_prices_to_root_nodes,
            gui_run_initial_propagation, propagate_cost_to_plan_nodes
        )
        # TOBE（末端価格）/ ASIS（起点価格）
        sp_csv = os.path.join(self.directory, "selling_price_table.csv")
        sh_csv = os.path.join(self.directory, "shipping_price_table.csv")
        if os.path.exists(sp_csv):
            tobe = load_tobe_prices(sp_csv)
            assign_tobe_prices_to_leaf_nodes(self.prod_tree_dict_OT, tobe)
        if os.path.exists(sh_csv):
            asis = load_asis_prices(sh_csv)
            assign_asis_prices_to_root_nodes(self.prod_tree_dict_OT, asis)
        # 初期コスト伝播
        try:
            gui_run_initial_propagation(self.prod_tree_dict_OT, self.directory)
        except Exception as e:
            print(f"[WARN] gui_run_initial_propagation skipped: {e}")
        try:
            propagate_cost_to_plan_nodes(self.prod_tree_dict_OT)
            propagate_cost_to_plan_nodes(self.prod_tree_dict_IN)
        except Exception as e:
            print(f"[WARN] propagate_cost_to_plan_nodes skipped: {e}")
    # ======================================================================
    # --- 1) ディレクトリ初期化（後方互換のため _init_data_directory を用意） ---
    def _init_data_directory(self):
        """Config から DATA_DIRECTORY を解決し、存在チェック。data_file_list を作成。"""
        import os
        # directory が未設定なら Config から
        if not getattr(self, "directory", None):
            if getattr(self, "config", None) and getattr(self.config, "DATA_DIRECTORY", None):
                self.directory = self.config.DATA_DIRECTORY
            else:
                raise RuntimeError("[ERROR] DATA directory is not set. Set Config.DATA_DIRECTORY or self.directory.")
        if not os.path.isdir(self.directory):
            raise FileNotFoundError(f"[ERROR] Data directory not found: {self.directory}")
        self.load_directory = self.directory
        self.data_file_list = set(os.listdir(self.directory))
    # --- 2) 計画パラメータ初期化（__init__の initialize_parameters と同値、静かめに） ---
    def _init_plan_parameters(self):
        """計画パラメータを idempotent に設定。"""
        # 既に initialize_parameters() 済みだが、再設定してもOKなように上書き
        cfg = getattr(self, "config", None)
        self.lot_size     = getattr(cfg, "DEFAULT_LOT_SIZE",     getattr(self, "lot_size",     1000))
        self.plan_year_st = getattr(cfg, "DEFAULT_START_YEAR",   getattr(self, "plan_year_st", 2024))
        self.plan_range   = getattr(cfg, "DEFAULT_PLAN_RANGE",   getattr(self, "plan_range",   3))
        self.pre_proc_LT  = getattr(cfg, "DEFAULT_PRE_PROC_LT",  getattr(self, "pre_proc_LT",  2))
        self.target_share = getattr(cfg, "DEFAULT_TARGET_SHARE", getattr(self, "target_share", 0.5))
        self.market_potential  = getattr(cfg, "DEFAULT_MARKET_POTENTIAL", getattr(self, "market_potential", 10000))
        self.total_supply_plan = round(self.market_potential * self.target_share)
    # --- 3) GUIツリーのロード（ラッパ。実体は既に _load_gui_trees を貼ってある想定） ---
    def _load_tree_csvs(self):
        """GUI向けノード辞書（outbound/inbound）を構築"""
        self._load_gui_trees()
    # --- 4) PlanNode を GUIノードに SKU紐付け ---
    def _link_plan_nodes_to_gui(self):
        """
        PlanNode の木（prod_tree_dict_OT/IN）を GUI ノード辞書（nodes_outbound/inbound）
        の sku_dict に製品キーでリンクする。
        """
        def _traverse(root):
            st = [root]
            while st:
                n = st.pop()
                yield n
                st.extend(getattr(n, "children", []) or [])
        # OUTBOUND 側
        if getattr(self, "nodes_outbound", None):
            for prod, root in (self.prod_tree_dict_OT or {}).items():
                for pn in _traverse(root):
                    gui_node = self.nodes_outbound.get(pn.name)
                    if gui_node is None:
                        continue
                    if not hasattr(gui_node, "sku_dict") or gui_node.sku_dict is None:
                        gui_node.sku_dict = {}
                    gui_node.sku_dict[prod] = pn
        # INBOUND 側（必要なら）
        if getattr(self, "nodes_inbound", None):
            for prod, root in (self.prod_tree_dict_IN or {}).items():
                for pn in _traverse(root):
                    gui_node = self.nodes_inbound.get(pn.name)
                    if gui_node is None:
                        continue
                    if not hasattr(gui_node, "sku_dict") or gui_node.sku_dict is None:
                        gui_node.sku_dict = {}
                    gui_node.sku_dict[prod] = pn
    # --- 5) コストテーブル読込と PlanNode への反映 ---
    def _load_cost_tables(self):
        """
        sku_cost_table_outbound.csv / inbound.csv を読み込んで PlanNode に属性反映。
        """
        import os, csv
        def _path(fn: str) -> str:
            return os.path.join(self.directory, fn)
        def _read_cost_csv(path: str) -> dict:
            if not os.path.exists(path):
                return {}
            out = {}
            with open(path, newline="", encoding="utf-8-sig") as f:
                rd = csv.DictReader(f)
                for row in rd:
                    prod = row.get("product_name")
                    node = row.get("node_name")
                    if not prod or not node:
                        continue
                    d = out.setdefault(prod, {})
                    d[node] = {
                        "price": float(row.get("price_sales_shipped", 0) or 0),
                        "cost_total": float(row.get("cost_total", 0) or 0),
                        "profit_margin": float(row.get("profit", 0) or 0),
                        "marketing": float(row.get("marketing_promotion", 0) or 0),
                        "sales_admin_cost": float(row.get("sales_admin_cost", 0) or 0),
                        "SGA_total": float(row.get("SGA_total", 0) or 0),
                        "transport_cost": float(row.get("logistics_costs", 0) or 0),
                        "storage_cost": float(row.get("warehouse_cost", 0) or 0),
                        "purchase_price": float(row.get("direct_materials_costs", 0) or 0),
                        "tariff_cost": float(row.get("tariff_cost", 0) or 0),
                        "purchase_total_cost": float(row.get("purchase_total_cost", 0) or 0),
                        "direct_labor_costs": float(row.get("direct_labor_costs", 0) or 0),
                        "fixed_cost": float(row.get("manufacturing_overhead", 0) or 0),
                        "prod_indirect_labor": float(row.get("prod_indirect_labor", 0) or 0),
                        "prod_indirect_cost": float(row.get("prod_indirect_others", 0) or 0),
                        "depreciation_cost": float(row.get("depreciation_others", 0) or 0),
                    }
            return out
        def _apply_costs_to_tree(root, prod_name: str, cost_map: dict):
            def walk(n):
                setting = cost_map.get(prod_name, {}).get(n.name)
                if setting:
                    sku = getattr(n, "sku", None)
                    if sku is None:
                        from pysi.network.node_base import SKU
                        sku = SKU(prod_name, n.name)
                        n.sku = sku
                    # SKU 側
                    sku.price               = setting["price"]
                    sku.cost_total          = setting["cost_total"]
                    sku.profit_margin       = setting["profit_margin"]
                    sku.marketing           = setting["marketing"]
                    sku.sales_admin_cost    = setting["sales_admin_cost"]
                    sku.SGA_total           = setting["SGA_total"]
                    sku.transport_cost      = setting["transport_cost"]
                    sku.storage_cost        = setting["storage_cost"]
                    sku.purchase_price      = setting["purchase_price"]
                    sku.tariff_cost         = setting["tariff_cost"]
                    sku.purchase_total_cost = setting["purchase_total_cost"]
                    sku.direct_labor_costs  = setting["direct_labor_costs"]
                    sku.fixed_cost          = setting["fixed_cost"]
                    sku.prod_indirect_labor = setting["prod_indirect_labor"]
                    sku.prod_indirect_cost  = setting["prod_indirect_cost"]
                    sku.depreciation_cost   = setting["depreciation_cost"]
                    # PlanNode ミラー
                    n.cs_price_sales_shipped    = sku.price
                    n.cs_cost_total             = sku.cost_total
                    n.cs_profit                 = sku.profit_margin
                    n.cs_marketing_promotion    = sku.marketing
                    n.cs_sales_admin_cost       = sku.sales_admin_cost
                    n.cs_SGA_total              = sku.SGA_total
                    n.cs_logistics_costs        = sku.transport_cost
                    n.cs_warehouse_cost         = sku.storage_cost
                    n.cs_direct_materials_costs = sku.purchase_price
                    n.cs_tax_portion            = sku.tariff_cost
                    n.cs_purchase_total_cost    = sku.purchase_total_cost
                    n.cs_direct_labor_costs     = sku.direct_labor_costs
                    n.cs_manufacturing_overhead = sku.fixed_cost
                    n.cs_prod_indirect_labor    = sku.prod_indirect_labor
                    n.cs_prod_indirect_others   = sku.prod_indirect_cost
                    n.cs_depreciation_others    = sku.depreciation_cost
                for c in getattr(n, "children", []) or []:
                    walk(c)
            walk(root)
        # 読み込み
        cost_ot = _read_cost_csv(_path("sku_cost_table_outbound.csv"))
        cost_in = _read_cost_csv(_path("sku_cost_table_inbound.csv"))
        # 反映
        for prod, root in (self.prod_tree_dict_OT or {}).items():
            if cost_ot:
                _apply_costs_to_tree(root, prod, cost_ot)
        for prod, root in (self.prod_tree_dict_IN or {}).items():
            if cost_in:
                _apply_costs_to_tree(root, prod, cost_in)
    # --- 6) 価格テーブル適用とコスト伝播 ---
    def _run_price_propagation(self):
        """
        selling_price_table.csv / shipping_price_table.csv があれば適用。
        その後 gui_run_initial_propagation / propagate_cost_to_plan_nodes を試みる。
        """
        import os
        try:
            # 価格割当
            sp = os.path.join(self.directory, "selling_price_table.csv")
            sh = os.path.join(self.directory, "shipping_price_table.csv")
            if os.path.exists(sp):
                tobe = load_tobe_prices(sp)
                assign_tobe_prices_to_leaf_nodes(self.prod_tree_dict_OT, tobe)
            if os.path.exists(sh):
                asis = load_asis_prices(sh)
                assign_asis_prices_to_root_nodes(self.prod_tree_dict_OT, asis)
            # 初期伝播（存在すれば実行）
            try:
                gui_run_initial_propagation(self.prod_tree_dict_OT, self.directory)
            except Exception as e:
                print(f"[WARN] gui_run_initial_propagation skipped: {e}")
            # 評価値コピー
            try:
                propagate_cost_to_plan_nodes(self.prod_tree_dict_OT)
                propagate_cost_to_plan_nodes(self.prod_tree_dict_IN)
            except Exception as e:
                print(f"[WARN] propagate_cost_to_plan_nodes skipped: {e}")
        except Exception as e:
            print(f"[WARN] _run_price_propagation failed: {e}")
    # === PlanEnv クラス内に追記 ===
    def init_psi_spaces_and_demand(self):
        import os
        import pandas as pd
        # --- 共通ヘルパ ---
        def _traverse(root):
            stack = [root]
            while stack:
                n = stack.pop()
                yield n
                stack.extend(getattr(n, "children", []) or [])
        def _alloc_psi_for_tree(root, plan_range, plan_year_st):
            """PSI器の確保。PlanNodeにネイティブAPIがあれば使用し、無ければ手動で確保。"""
            weeks = 53 * int(plan_range)
            ok = False
            if hasattr(root, "set_plan_range_lot_counts"):
                try:
                    root.set_plan_range_lot_counts(plan_range, plan_year_st)
                    if isinstance(getattr(root, "psi4demand", None), list) and len(root.psi4demand) >= weeks:
                        ok = True
                except Exception:
                    pass
            if not ok:
                # フォールバック：全ノードに [S,CO,I,P] 4スロットの週配列を用意
                for nd in _traverse(root):
                    nd.plan_range = plan_range
                    nd.plan_year_st = plan_year_st
                    if not isinstance(getattr(nd, "psi4demand", None), list) or len(nd.psi4demand) < weeks:
                        nd.psi4demand = [[[], [], [], []] for _ in range(weeks)]
                    if not isinstance(getattr(nd, "psi4supply", None), list) or len(nd.psi4supply) < weeks:
                        nd.psi4supply = [[[], [], [], []] for _ in range(weeks)]
        # 0) ガード
        if not self.prod_tree_dict_OT:
            print("[WARN] No outbound product trees. Run load_data_files() first.")
            return
        # 1) PSI器の初期確保（設定デフォルトで）
        plan_range   = int(getattr(self, "plan_range", 3) or 3)
        plan_year_st = int(getattr(self, "plan_year_st", 2024) or 2024)
        for _, root_ot in self.prod_tree_dict_OT.items():
            _alloc_psi_for_tree(root_ot, plan_range, plan_year_st)
        print("[INFO] PSI spaces allocated to all outbound nodes.")
        # 2) 月次CSV（sku_S_month_data.csv 優先）→ 正規化 → 週次化
        directory  = self.directory
        new_csv    = os.path.join(directory, "sku_S_month_data.csv")
        old_csv    = os.path.join(directory, "S_month_data.csv")
        month_csv  = new_csv if os.path.exists(new_csv) else old_csv
        if not os.path.exists(month_csv):
            print("[INFO] sku_S_month_data.csv (or S_month_data.csv) not found; PSI slots not set.")
            return
        try:
            df_month_raw = pd.read_csv(month_csv, encoding="utf-8-sig")
        except Exception as e:
            print(f"[WARN] Failed to read {os.path.basename(month_csv)}: {e}")
            return
        df_month = _normalize_monthly_demand_df_sku(df_month_raw)
        print("[DEBUG] monthly normalized head:\n", df_month.head(6))
        # lot_size 参照（find_node が無くても走査で拾えるように）
        def _lot_size_lookup(prod_name: str, node_name: str) -> int:
            root = self.prod_tree_dict_OT.get(prod_name)
            if root is None:
                return 1
            fn = getattr(root, "find_node", None)
            if callable(fn):
                nd = fn(lambda n: getattr(n, "name", None) == node_name)
                return int(getattr(nd, "lot_size", 1) or 1) if nd else 1
            for n in _traverse(root):
                if getattr(n, "name", None) == node_name:
                    return int(getattr(n, "lot_size", 1) or 1)
            return 1
        # **** start of replace ****
        df_weekly, plan_range, plan_year_st = convert_monthly_to_weekly_sku(df_month, _lot_size_lookup)
        # 3) 週次化後のレンジで再確保（完全リセット & 4レイヤー、リストで確保）
        weeks_count = 53 * plan_range
        for _, root_ot in self.prod_tree_dict_OT.items():
            if hasattr(root_ot, "set_plan_range_lot_counts"):
                try:
                    root_ot.set_plan_range_lot_counts(plan_range, plan_year_st)
                except Exception:
                    pass
            # 念のため自前でも完全リセット（0..weeks_count-1 でアクセス可能に）
            for n in _traverse(root_ot):
                n.psi4demand = [[[], [], [], []] for _ in range(weeks_count)]
                n.psi4supply = [[[], [], [], []] for _ in range(weeks_count)]
        # （任意）環境側のパラメータにも同期
        self.plan_range   = plan_range
        self.plan_year_st = plan_year_st
        # 4) by product で leaf→root に S ロット投入（既存ロジックを使用）
        for prod_name, root in self.prod_tree_dict_OT.items():
            df_w_prod = df_weekly[df_weekly["product_name"] == prod_name]
            if df_w_prod.empty:
                print(f"[INFO] no weekly demand rows for {prod_name}; skip.")
                continue
            set_df_Slots2psi4demand(root, df_w_prod)
        # **** end of replace ****
        # 5) デバッグ（0-basedに修正）
        try:
            sample_prod = next(iter(self.prod_tree_dict_OT.keys()))
            sample_root = self.prod_tree_dict_OT[sample_prod]
            any_node = next(_traverse(sample_root))
            weeks = min(5, len(any_node.psi4demand))
            print(f"[DEBUG] PSI slot lengths for node '{any_node.name}' (first {weeks} weeks):",
                [len(any_node.psi4demand[w][0]) for w in range(weeks)])
        except Exception:
            pass
        # 6) Validation（差し替え）
        def _validate_leaf_slots_against_df_local(root, df_weekly, product_name: str):
            """指定 product_name の df_weekly だけで、その製品の木(root)の leaf を検証する。"""
            def _iter_nodes(n):
                stack = [n]
                while stack:
                    x = stack.pop()
                    yield x
                    stack.extend(getattr(x, "children", []) or [])
            mismatches = []
            df_p = df_weekly[df_weekly["product_name"] == product_name].copy()
            # df に現れるノード（＝その製品で需要がある leaf 候補）
            df_nodes = set(df_p["node_name"].unique())
            # 製品の木の leaf を列挙
            leaves = [n for n in _iter_nodes(root) if not getattr(n, "children", [])]
            for leaf in leaves:
                df_leaf = df_p[df_p["node_name"] == leaf.name]
                df_total = int(df_leaf["S_lot"].sum()) if not df_leaf.empty else 0
                # 0-based list構造を想定
                psi_total = sum(len(leaf.psi4demand[w][0]) for w in range(len(leaf.psi4demand)))
                # ルール:
                # - df に leaf が登場していれば df_total と psi_total を厳密一致チェック
                # - df に登場しない leaf は「当該製品としては需要0が期待」→ psi_total が 0 でなければ警告
                if leaf.name in df_nodes:
                    if df_total != psi_total:
                        mismatches.append((product_name, leaf.name, df_total, psi_total))
                else:
                    if psi_total != 0:
                        mismatches.append((product_name, leaf.name, 0, psi_total))
            if mismatches:
                print("[WARN] Leaf Sロット総量の不一致（製品別チェック）:")
                for prod, leaf, df_total, psi_total in mismatches:
                    print(f"  - {prod} @ {leaf}: df={df_total} vs psi={psi_total}")
            else:
                print(f"[OK] {product_name}: df_weekly の総 S_lot と PSI の総ロットが全 leaf で一致。")
        def _preview_psi_counts_local(root, weeks=6):
            def _iter_nodes(n):
                stack = [n]
                while stack:
                    x = stack.pop()
                    yield x
                    stack.extend(getattr(x, "children", []) or [])
            for n in _iter_nodes(root):
                psi = getattr(n, "psi4demand", None)
                if not isinstance(psi, list):
                    continue
                W = min(weeks, len(psi))
                cnts = [[len(psi[w][i]) for i in range(4)] for w in range(W)]
                print(f"[{n.name}] first {W} weeks (S,CO,I,P counts): {cnts}")
        # 全製品についてバリデーションとプレビュー実行（← 呼び出し側も修正）
        for prod_name, root in self.prod_tree_dict_OT.items():
            _validate_leaf_slots_against_df_local(root, df_weekly, prod_name)
            _preview_psi_counts_local(root, weeks=6)
        # **************************************
        # validators
        # **************************************
        from pysi.plan.validators import (
            assert_unique_lot_ids,
            assert_no_intra_node_duplicates,
            check_lot_id_format,
            dump_weekly_lots_csv,
            DEFAULT_LOT_ID_PATTERN,   # 必要なら参照
        )
        # 1) 重複チェック
        total, dup_cnt, dup_head = assert_unique_lot_ids(self.prod_tree_dict_OT)
        print(f"[OK] lot_id uniqueness verified: total={total}, duplicates={dup_cnt}" if dup_cnt == 0
            else f"[WARN] duplicated lot_id(s): {dup_cnt} (showing first {len(dup_head)})")
        for node, lot in dup_head:
            print("  -", node, lot)
        # 2) 形式チェック（フォーマットを変えたい場合は pattern=... を渡す）
        total, bad_cnt, bad_head = check_lot_id_format(self.prod_tree_dict_OT)  # or pattern="^...$"
        print(f"[OK] lot_id format verified: total={total}" if bad_cnt == 0
            else f"[WARN] lot_id format mismatch: {bad_cnt} (showing first {len(bad_head)})")
        for node, lot in bad_head:
            print("  -", node, lot)
        # 3) 週次テーブルをダンプ（df_weekly があれば）
        if 'df_weekly' in locals():
            out_csv = os.path.join(self.directory, "_debug_weekly_lots.csv")
            if dump_weekly_lots_csv(df_weekly, out_csv):
                print("[INFO] weekly lots exported:", out_csv)
    # ******************************
    # define planning ENGINE
    # ******************************
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
        ##self.view_nx_matlib()
        #self.view_nx_matlib4opt()
        #self.root.after(1000, self.show_psi_by_product("outbound", "demand", self.product_selected))
        ##show_psi_by_product(self, bound, layer, product_name)
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
        #self.view_nx_matlib4opt()
        #self.root.after(1000, self.show_psi_by_product("outbound", "supply", self.product_selected))
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
            #tk.messagebox.showerror("Error", "PSI Plan data4multi-product is not loaded.")
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
        #self.view_nx_matlib4opt()
        # Update the PSI area
        #self.root.after(1000, self.show_psi_by_product("outbound", "supply", self.product_selected))
        #self.root.after(1000, self.show_psi("outbound", "supply"))
    def supply_planning(self):
        # Check if the necessary data is loaded
        if self.root_node_outbound is None or self.nodes_outbound is None:
            print("Error: PSI Plan data is not loaded. Please load the data first.")
            #tk.messagebox.showerror("Error", "PSI Plan data is NOT loaded. please File Open parameter directory first.")
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
        #self.view_nx_matlib4opt()
        # Update the PSI area
        #self.root.after(1000, self.show_psi("outbound", "supply"))
    #def eval_buffer_stock(self):
    #    pass
    def eval_buffer_stock(self):
        # Check if the necessary data is loaded
        if self.root_node_outbound is None or self.nodes_outbound is None:
            print("Error: PSI Plan data is not loaded. Please load the data first.")
            #tk.messagebox.showerror("Error", "PSI Plan data is NOT loaded. please File Open parameter directory first.")
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
    def update_evaluation_results4multi_product(self):
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
