#NetworkGraphApp.py
import tkinter as tk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import networkx as nx
import numpy as np
import gc
class NetworkGraphApp:
    def __init__(self, root):
        self.root = root
        self.canvas_network = None
        self.ax_network = None
        self.info_window = None
        self.info_frame = None
        self.info_label = None
        self.info_canvas = None
        self.annotation_artist = None
        self.last_highlight_node = None
        self.last_clicked_node = None
        self.nodes_outbound = {}  # 仮の初期化
        self.nodes_inbound = {}   # 仮の初期化
        self.decouple_node_selected = set()  # 仮の初期化
        self.G = nx.Graph()       # 仮の初期化
        self.pos_E2E = {}         # 仮の初期化
        self.total_revenue = 0    # 仮の初期化
        self.total_profit = 0     # 仮の初期化
        # キャンバスと軸の初期化
        self.fig_network, self.ax_network = plt.subplots()
        self.canvas_network = FigureCanvasTkAgg(self.fig_network, master=self.root)
        self.canvas_network.get_tk_widget().pack()
        # クリックイベントを一度だけ登録
        self.canvas_network.mpl_connect('button_press_event', self.on_plot_click)
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
        plt.close(self.fig_network)  # メモリ解放のため閉じる
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
            # ノード情報文字列の作成
            revenue = round(select_node.eval_cs_price_sales_shipped)
            profit = round(select_node.eval_cs_profit)
            profit_ratio = round((profit / revenue) * 100, 1) if revenue != 0 else 0
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
                f" profit_ratio: {profit_ratio     }%\n"
                f" revenue     : {revenue:,}\n"
                f" profit      : {profit:,}\n\n"
                f" Cost_Structure\n"
                f" SGA_total   : {round(select_node.eval_cs_SGA_total):,}\n"
                f" Custom_tax  : {round(select_node.eval_cs_tax_portion):,}\n"
                f" Logi_costs  : {round(select_node.eval_cs_logistics_costs):,}\n"
                f" WH_cost     : {round(select_node.eval_cs_warehouse_cost):,}\n"
                f" Direct_MTRL : {round(select_node.eval_cs_direct_materials_costs):,}\n"
            )
            # 情報ウィンドウを表示
            self.show_info_graph(node_info, select_node)
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
