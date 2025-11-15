#load_data_files.py
def load_data_files(self):
    """
    Robust loader:
      1) ディレクトリ決定・存在チェック
      2) GUIノード（outbound/inbound）構築
      3) CSV行から product_name_list を抽出（sku_dictに依存しない）
      4) 製品別の PlanNode ツリーを構築（SKU を安全生成）
      5) PlanNode を GUI ノードの sku_dict にリンク
      6) 価格テーブル読込 → 伝播 → PlanNodeへ反映
      7) （任意）月次需要→週次スロットはファイルがあれば処理
      8) offering price を CSV 出力
    """
    import os, csv
    # -------------------------
    # 0) 初期ガード・準備
    # -------------------------
    # ディレクトリ設定（None禁止）
    if not getattr(self, "directory", None):
        if getattr(self, "config", None) and getattr(self.config, "DATA_DIRECTORY", None):
            self.directory = self.config.DATA_DIRECTORY
        else:
            raise RuntimeError("DATA directory is not set. Provide Config.DATA_DIRECTORY or set self.directory.")
    directory = self.directory
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"Data directory not found: {directory}")
    data_file_list = set(os.listdir(directory))
    # 便利ヘルパ
    def _path(fname: str) -> str:
        return os.path.join(directory, fname)
    def _read_csv(path: str) -> list[dict]:
        if not os.path.exists(path):
            return []
        with open(path, newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
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
    # 保険：辞書で初期化（Noneは使わない）
    self.nodes_outbound = {}
    self.nodes_inbound  = {}
    # -------------------------
    # 1) GUIノードツリーの構築（あれば）
    # -------------------------
    nodes_outbound, root_node_outbound = {}, None
    nodes_inbound,  root_node_inbound  = {}, None
    if "product_tree_outbound.csv" in data_file_list:
        file_path_OT = _path("product_tree_outbound.csv")
        nodes_outbound, root_name_ot = create_tree_set_attribute(file_path_OT)
        root_node_outbound = nodes_outbound[root_name_ot]
        set_positions(root_node_outbound)
        set_parent_all(root_node_outbound)
        print_parent_all(root_node_outbound)
        self.nodes_outbound = nodes_outbound
        self.root_node_outbound = root_node_outbound
    else:
        print("error: product_tree_outbound.csv is missed")
    if "product_tree_inbound.csv" in data_file_list:
        file_path_IN = _path("product_tree_inbound.csv")
        nodes_inbound, root_name_in = create_tree_set_attribute(file_path_IN)
        root_node_inbound = nodes_inbound[root_name_in]
        set_positions(root_node_inbound)
        set_parent_all(root_node_inbound)
        print_parent_all(root_node_inbound)
        self.nodes_inbound = nodes_inbound
        self.root_node_inbound = root_node_inbound
    else:
        print("error: product_tree_inbound.csv is missed")
    # GUIツリーが 0 件の場合は続けても export が空になるので警告だけ出す（処理は継続）
    if not self.nodes_outbound:
        print("[WARN] nodes_outbound is empty. Export may be empty if no plan trees are built/linked.")
    # -------------------------
    # 2) CSV行から製品名の抽出
    # -------------------------
    rows_ot = _read_csv(_path("product_tree_outbound.csv")) if "product_tree_outbound.csv" in data_file_list else []
    rows_in = _read_csv(_path("product_tree_inbound.csv"))  if "product_tree_inbound.csv"  in data_file_list else []
    prods_ot = {r["Product_name"].strip() for r in rows_ot if r.get("Product_name")}
    prods_in = {r["Product_name"].strip() for r in rows_in if r.get("Product_name")}
    product_name_list = sorted(prods_ot | prods_in)
    self.product_name_list = product_name_list
    self.product_selected  = product_name_list[0] if product_name_list else None
    print("[DEBUG] products detected:", self.product_name_list)
    if not self.product_name_list:
        print("[ERROR] No Product_name found in product_tree_*.csv. Check column names and data.")
        # offering price はこの時点では出せないが、処理継続すると空CSVになるため、ここで終了
        return
    # GUIのコンボボックスがある場合のみ更新（CLI実行時は未定義）
    if hasattr(self, "cb_product"):
        self.cb_product["values"] = self.product_name_list
        if self.product_name_list:
            self.cb_product.current(0)
    # -------------------------
    # 3) 製品別 PlanNode ツリー構築（SKU安全）
    # -------------------------
    # SKU import の安全化（無ければ簡易SKUを定義）
    try:
        from pysi.network.node_base import SKU as _SKU
    except Exception:
        class _SKU:
            def __init__(self, product_name, node_name):
                self.product_name = product_name
                self.node_name = node_name
                # offering price 等、後段で自由に属性追加される前提
                self.offering_price_ASIS = None
                self.offering_price_TOBE = None
    def build_prod_tree_from_rows(rows: list[dict], product_name: str) -> dict[str, PlanNode]:
        """Product_name でフィルタした行群から PlanNode ツリー辞書を構築"""
        node_dict: dict[str, PlanNode] = {}
        rows_p = [r for r in rows if r.get("Product_name") == product_name]
        for r in rows_p:
            p_name = r["Parent_node"].strip()
            c_name = r["Child_node"].strip()
            if p_name not in node_dict:
                node_dict[p_name] = PlanNode(name=p_name)
            if c_name not in node_dict:
                node_dict[c_name] = PlanNode(name=c_name)
            parent = node_dict[p_name]
            child  = node_dict[c_name]
            # 任意属性
            try:
                child.lot_size = int(r.get("lot_size") or 0) or None
            except Exception:
                child.lot_size = None
            try:
                child.leadtime = int(r.get("leadtime") or 0) or None
            except Exception:
                child.leadtime = None
            # SKU を必ず付与（後段の価格伝播・評価で使う）
            if not getattr(child, "sku", None):
                child.sku = _SKU(product_name, child.name)
            parent.add_child(child)
        return node_dict
    prod_tree_dict_OT: dict[str, PlanNode] = {}
    prod_tree_dict_IN: dict[str, PlanNode] = {}
    for prod_nm in product_name_list:
        # outbound
        node4psi_dict_OT = build_prod_tree_from_rows(rows_ot, prod_nm) if rows_ot else {}
        if node4psi_dict_OT:
            if "supply_point" not in node4psi_dict_OT:
                # ルート推定（親を持たないノードの先頭）
                has_parent = {r["Child_node"].strip() for r in rows_ot if r.get("Product_name") == prod_nm}
                candidates = [n for n in node4psi_dict_OT.keys() if n not in has_parent]
                root_name = "supply_point" if "supply_point" in node4psi_dict_OT else (candidates[0] if candidates else None)
            else:
                root_name = "supply_point"
            if root_name:
                prod_tree_root_OT = node4psi_dict_OT[root_name]
                set_parent_all(prod_tree_root_OT)
                prod_tree_dict_OT[prod_nm] = prod_tree_root_OT
        # inbound
        node4psi_dict_IN = build_prod_tree_from_rows(rows_in, prod_nm) if rows_in else {}
        if node4psi_dict_IN:
            if "supply_point" not in node4psi_dict_IN:
                has_parent = {r["Child_node"].strip() for r in rows_in if r.get("Product_name") == prod_nm}
                candidates = [n for n in node4psi_dict_IN.keys() if n not in has_parent]
                root_name = "supply_point" if "supply_point" in node4psi_dict_IN else (candidates[0] if candidates else None)
            else:
                root_name = "supply_point"
            if root_name:
                prod_tree_root_IN = node4psi_dict_IN[root_name]
                set_parent_all(prod_tree_root_IN)
                prod_tree_dict_IN[prod_nm] = prod_tree_root_IN
    # 保存（以降のメソッドで参照）
    self.prod_tree_dict_OT = prod_tree_dict_OT
    self.prod_tree_dict_IN = prod_tree_dict_IN
    # -------------------------
    # 4) PlanNode → GUIノードへリンク
    # -------------------------
    def link_planning_nodes_to_gui_sku(product_tree_root: PlanNode, gui_node_dict: dict[str, GUINode], product_name: str):
        def traverse(n: PlanNode):
            if n is None:
                return
            gui_node = gui_node_dict.get(n.name) if gui_node_dict else None
            if gui_node is not None:
                if not hasattr(gui_node, "sku_dict"):
                    gui_node.sku_dict = {}
                # 「plan_node を sku_dict[product_name] に直接入れる」設計
                gui_node.sku_dict[product_name] = n
            for c in getattr(n, "children", []):
                traverse(c)
        traverse(product_tree_root)
    if self.nodes_outbound:
        for prod_nm, root in self.prod_tree_dict_OT.items():
            link_planning_nodes_to_gui_sku(root, self.nodes_outbound, prod_nm)
    if self.nodes_inbound:
        for prod_nm, root in self.prod_tree_dict_IN.items():
            link_planning_nodes_to_gui_sku(root, self.nodes_inbound, prod_nm)
    # -------------------------
    # 5) コストテーブル読込 → PlanNodeへ反映（任意）
    # -------------------------
    def load_cost_param_csv(filepath: str) -> dict:
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
    def cost_param_setter(product_tree_root: PlanNode, param_dict: dict, product_name: str):
        def traverse(node: PlanNode):
            node_name = node.name
            setting = param_dict.get(product_name, {}).get(node_name)
            if setting:
                sku = getattr(node, "sku", None)
                if not sku:
                    # 念のためSKUがない場合でも作る
                    sku = _SKU(product_name, node.name)
                    node.sku = sku
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
                # PlanNode側のミラー（既存設計に合わせて）
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
            for c in getattr(node, "children", []):
                traverse(c)
        traverse(product_tree_root)
    # 読み込み（任意）
    cost_param_OT_dict = load_cost_param_csv(_path("sku_cost_table_outbound.csv")) if "sku_cost_table_outbound.csv" in data_file_list else {}
    cost_param_IN_dict = load_cost_param_csv(_path("sku_cost_table_inbound.csv"))  if "sku_cost_table_inbound.csv"  in data_file_list else {}
    for product_name, root in self.prod_tree_dict_OT.items():
        if cost_param_OT_dict:
            cost_param_setter(root, cost_param_OT_dict, product_name)
    for product_name, root in self.prod_tree_dict_IN.items():
        if cost_param_IN_dict:
            cost_param_setter(root, cost_param_IN_dict, product_name)
    # -------------------------
    # 6) 価格テーブル → 伝播 → PlanNodeへ反映
    # -------------------------
    # TOBE/ASIS の割当（ファイルがある場合のみ）
    if "selling_price_table.csv" in data_file_list:
        tobe_price_dict = load_tobe_prices(_path("selling_price_table.csv"))
        assign_tobe_prices_to_leaf_nodes(self.prod_tree_dict_OT, tobe_price_dict)
    if "shipping_price_table.csv" in data_file_list:
        asis_price_dict = load_asis_prices(_path("shipping_price_table.csv"))
        assign_asis_prices_to_root_nodes(self.prod_tree_dict_OT, asis_price_dict)
    # 初期伝播（関数が存在する前提；無ければスキップ）
    try:
        gui_run_initial_propagation(self.prod_tree_dict_OT, directory)
    except Exception as e:
        print(f"[WARN] gui_run_initial_propagation skipped: {e}")
    # PlanNode へ評価値コピー
    try:
        propagate_cost_to_plan_nodes(self.prod_tree_dict_OT)
        propagate_cost_to_plan_nodes(self.prod_tree_dict_IN)
    except Exception as e:
        print(f"[WARN] propagate_cost_to_plan_nodes skipped: {e}")
    # -------------------------
    # 7) 需要データ（任意・あれば）
    # -------------------------
    # ※ convert_monthly_to_weekly を使う実装は別途（ここでは存在チェックのみ）
    if "S_month_data.csv" in data_file_list:
        print("[INFO] S_month_data.csv detected. Demand processing can be executed in a dedicated step.")
        # 需要→週次スロット設定はプロジェクト固有の実装に依存するため、ここでは触らない
        # set_df_Slots2psi4demand(...) 等は別タイミングで実行してください
    # -------------------------
    # 8) offering price エクスポート
    # -------------------------
    try:
        out_csv = _path("offering_price_ASIS_TOBE.csv")
        self.export_offering_prices(out_csv)
    except Exception as e:
        print(f"[WARN] export_offering_prices skipped: {e}")
    # 最後に状況表示
    print("product_name_list", self.product_name_list)
    print("End of load_data_files")
