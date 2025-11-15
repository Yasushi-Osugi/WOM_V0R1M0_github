#FastNetworkViewer.py
import numpy as np
from scipy.spatial import cKDTree
import networkx as nx
import matplotlib.pyplot as plt
import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
class FastNetworkViewer:
    def __init__(self, G, pos_E2E, nodes_outbound, nodes_inbound, flowDict_opt, decouple_node_selected):
        self.G = G
        self.pos = pos_E2E
        self.nodes_out = nodes_outbound
        self.nodes_in = nodes_inbound
        self.flowOpt = flowDict_opt
        self.decouple_sel = set(decouple_node_selected)
        # --- KD-Tree 構築 ---
        self.node_list = list(self.pos.keys())
        coords = np.array([self.pos[n] for n in self.node_list])
        self.kdtree = cKDTree(coords)
        # --- Matplotlib + Tkinter の初期化 ---
        self.root = tk.Tk()
        self.fig, self.ax = plt.subplots(figsize=(6,6))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        # --- 一度だけネットワークを描画 ---
        self._draw_static_network()
        # --- 注釈用オブジェクトを先に作っておく ---
        self.annotation = self.ax.annotate(
            "", xy=(0,0), xytext=(0.5, 0.0),
            textcoords='axes fraction', ha='center',
            color='red', fontsize=10,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.8)
        )
        # --- クリックイベント登録 ---
        self.fig.canvas.mpl_connect('button_press_event', self.on_click)
        # --- 情報ウィンドウ／PieCanvas の準備 ---
        self.info_win = None
        self.pie_canvas = None
        self.info_label = None
        tk.mainloop()
    def _draw_static_network(self):
        # ノード座標配列
        xs, ys = zip(*[self.pos[n] for n in self.node_list])
        # ノード色
        colors = ['brown' if n in self.decouple_sel else 'lightblue' for n in self.node_list]
        # scatter で描画して picker を有効化
        self.ax.scatter(xs, ys, s=100, c=colors, picker=True)
        # エッジと最適化パス（赤線）は最初だけ描画
        nx.draw_networkx_edges(self.G, self.pos, ax=self.ax, edge_color='lightgrey', width=0.5)
        for u, flows in self.flowOpt.items():
            for v, f in flows.items():
                if f > 0:
                    self.ax.plot(
                        [self.pos[u][0], self.pos[v][0]],
                        [self.pos[u][1], self.pos[v][1]],
                        color='red', linewidth=1
                    )
        nx.draw_networkx_labels(self.G, self.pos, font_size=8, ax=self.ax)
        self.canvas.draw()
    def on_click(self, event):
        # グラフ外クリックは無視
        if event.xdata is None or event.ydata is None:
            return
        # KD-Tree 最近傍クエリ
        dist, idx = self.kdtree.query([event.xdata, event.ydata])
        if dist > 0.5:   # しきい値：0.5
            return
        node = self.node_list[idx]
        select = self.nodes_out.get(node) or self.nodes_in.get(node)
        if select is None:
            return
        # 注釈テキストを更新
        txt = f"Node: {node}\nDegree: {self.G.degree[node]}"
        self.annotation.set_text(txt)
        # グラフ内の座標（絶対）ではなく、AxesFractionで固定表示したい場合はxytextだけ更新
        self.annotation.xy = (self.pos[node][0], self.pos[node][1])
        self.canvas.draw_idle()
        # 情報ウィンドウ更新
        self._update_info_window(node, select)
    def _update_info_window(self, node_name, select_node):
        # 一度も作ってなければ作成
        if self.info_win is None or not tk.Toplevel.winfo_exists(self.info_win):
            self.info_win = tk.Toplevel(self.root)
            self.info_win.title("Node Information")
            frame = tk.Frame(self.info_win)
            frame.pack()
            # 左にPie、右にテキスト
            self.pie_canvas = None
            self.info_label = tk.Label(frame, text="", justify='left', font=("Arial",10))
            self.info_label.grid(row=0, column=1, padx=10, sticky='nw')
            self.pie_frame = frame
        # Pieを再描画（古いキャンバスは破棄）
        if self.pie_canvas:
            self.pie_canvas.get_tk_widget().destroy()
        labels = ['Profit','SG&A','Tax','Logi','Ware','Mat']
        vals = [
            select_node.eval_cs_profit,
            select_node.eval_cs_SGA_total,
            select_node.eval_cs_tax_portion,
            select_node.eval_cs_logistics_costs,
            select_node.eval_cs_warehouse_cost,
            select_node.eval_cs_direct_materials_costs,
        ]
        # 非ゼロだけ抽出
        data = [(l,v) for l,v in zip(labels,vals) if v>0]
        if not data:
            data = [("No Data",1)]
        labels, vals = zip(*data)
        fig, ax = plt.subplots(figsize=(4,3))
        ax.pie(vals, labels=labels, autopct='%1.1f%%', startangle=90)
        ax.set_title(node_name, fontsize=9)
        self.pie_canvas = FigureCanvasTkAgg(fig, master=self.pie_frame)
        self.pie_canvas.get_tk_widget().grid(row=0, column=0)
        self.pie_canvas.draw()
        # テキスト情報
        info = (
            f"name: {select_node.name}\n"
            f"leadtime: {select_node.leadtime}\n"
            f"capacity: {select_node.nx_capacity}\n"
            f"profit_ratio: {round((select_node.eval_cs_profit / (select_node.eval_cs_price_sales_shipped or 1))*100,1)}%\n"
            f"revenue: {round(select_node.eval_cs_price_sales_shipped):,}\n"
            f"profit: {round(select_node.eval_cs_profit):,}\n"
        )
        self.info_label.config(text=info)
