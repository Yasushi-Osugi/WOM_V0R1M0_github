# pysi/gui/cockpit_tk.py

# 目的：
# Product選択
# MOM選択（node_geo.csv の MOM* から）
# KPI（Profit / Service / CCC(暫定) / Util / Inventory / NetCash）
# タブ切替：MOM PSI×Cap / Service / Cashflow（全体/選択MOM）

from __future__ import annotations

import os
import math
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass

import numpy as np

# cockpit_tk.py の上部に追加
try:
    from pysi.gui.world_map_view import show_world_map
except ImportError:
    # パスが通っていない場合のデバッグ用
    def show_world_map(*args, **kwargs):
        print("[Error] world_map_view.py could not be imported.")

# ----------------------------
# UI Selection State
# ----------------------------
@dataclass
class SelectionState:
    """Single source of truth for GUI selection.

    Key design: use node_name (Node.name) as the common key across
    - world map (geo dict)
    - supply chain network
    - PSI mini view
    """
    selected_node: str | None = None
    selected_product: str | None = None
    selected_week: int | None = None

import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


from pysi.gui.network_viewer_patched import show_network_E2E_matplotlib






# ----------------------------
# Helpers: tree traversal
# ----------------------------
def iter_nodes(root):
    stack = [root]
    while stack:
        n = stack.pop()
        if n is None:
            continue
        yield n
        for c in getattr(n, "children", []) or []:
            stack.append(c)

def find_node_by_name(root, name: str):
    for n in iter_nodes(root):
        if getattr(n, "name", None) == name:
            return n
    return None

def leaf_nodes(root):
    leaves = []
    for n in iter_nodes(root):
        ch = getattr(n, "children", []) or []
        if not ch:
            leaves.append(n)
    return leaves

def count_lots(x):
    # x is list of lot_id
    return len(x) if x else 0


# ----------------------------
# Service KPI (JIT deviation)
# ----------------------------
def _percentile(sorted_vals, p: float) -> float:
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    k = int(round((n - 1) * p))
    k = max(0, min(n - 1, k))
    return float(sorted_vals[k])

def compute_service_jit_for_product(root_outbound, weeks_count: int | None = None):
    W = weeks_count or len(root_outbound.psi4demand)
    leaves = leaf_nodes(root_outbound)

    demand_week = {}
    ship_week = {}

    for lf in leaves:
        for w in range(min(W, len(lf.psi4demand))):
            for lot_id in (lf.psi4demand[w][0] or []):
                if lot_id not in demand_week:
                    demand_week[lot_id] = w

        for w in range(min(W, len(lf.psi4supply))):
            for lot_id in (lf.psi4supply[w][0] or []):
                if lot_id not in ship_week:
                    ship_week[lot_id] = w

    diffs_abs = []
    late = []
    early = []
    unfilled = 0
    filled = 0

    for lot_id, dw in demand_week.items():
        sw = ship_week.get(lot_id)
        if sw is None:
            unfilled += 1
            continue
        filled += 1
        d = sw - dw
        diffs_abs.append(abs(d))
        if d > 0:
            late.append(float(d))
        elif d < 0:
            early.append(float(abs(d)))

    diffs_abs.sort()

    jit_mad = (sum(diffs_abs) / len(diffs_abs)) if diffs_abs else 0.0
    jit_p95 = _percentile(diffs_abs, 0.95)
    avg_late = (sum(late) / len(late)) if late else 0.0
    avg_early = (sum(early) / len(early)) if early else 0.0

    return {
        "jit_mad_weeks": jit_mad,
        "jit_p95_weeks": jit_p95,
        "unfilled_lots": unfilled,
        "filled_lots": filled,
        "total_demand_lots": len(demand_week),
        "avg_late_weeks": avg_late,
        "avg_early_weeks": avg_early,
    }


# ----------------------------
# Inventory / Utilization
# ----------------------------
def compute_total_inventory_lots(root_outbound, weeks_count: int | None = None):
    # simplest: sum of I lots count across nodes for a representative week (last week) and/or average
    W = weeks_count or len(root_outbound.psi4supply)
    if W <= 0:
        return 0, 0.0

    inv_per_week = []
    for w in range(W):
        s = 0
        for n in iter_nodes(root_outbound):
            try:
                s += count_lots(n.psi4supply[w][2])
            except Exception:
                pass
        inv_per_week.append(s)

    return int(inv_per_week[-1]), float(sum(inv_per_week) / len(inv_per_week))

def compute_utilization_series(env, product: str, mom_name: str, root_outbound):
    # used_lots: MOM node P lots if available else root_outbound P lots
    # cap_lots: env.weekly_capability[product][mom_name][w]
    cap = (((getattr(env, "weekly_capability", {}) or {}).get(product, {}) or {}).get(mom_name, None))
    if cap is None:
        return None, None

    W = len(cap)
    mom = find_node_by_name(root_outbound, mom_name)  # outbound tree may contain MOM. If not, use root_outbound.
    node_for_used = mom if mom is not None else root_outbound

    used = []
    for w in range(W):
        # P slot: try attr=3 (Purchase/Production) in your convention,
        # but fallback if missing
        p_lots = None
        try:
            p_lots = node_for_used.psi4supply[w][3]
        except Exception:
            p_lots = None
        if p_lots is None:
            try:
                p_lots = node_for_used.psi4supply[w][0]  # fallback to S if P not available
            except Exception:
                p_lots = []
        used.append(count_lots(p_lots))

    util = []
    for u, c in zip(used, cap):
        if c and c > 0:
            util.append(u / c)
        else:
            util.append(0.0)
    return np.array(used, dtype=float), np.array(util, dtype=float)


# ----------------------------
# Cashflow: compute df (NO CSV required)
# ----------------------------
def shift_right(values, k: int):
    """Non-circular shift (delay)."""
    values = np.array(values, dtype=float)
    if k <= 0:
        return values
    out = np.zeros_like(values)
    if k < len(values):
        out[k:] = values[:-k]
    return out

def build_cashflow_df_outbound(root_outbound, output_period: int):
    """
    returns DataFrame like your CSV but in-memory.
    """
    data = []
    week_cols = [f"w{i+1}" for i in range(output_period)]

    def collect(node, level, position):
        ar_days = getattr(node, "AR_lead_time", 0) or 0
        ap_days = getattr(node, "AP_lead_time", 0) or 0
        ar_shift = int(ar_days // 7)
        ap_shift = int(ap_days // 7)

        weekly_in = None
        weekly_out = None

        for attr in range(4):  # 0:S, 1:CarryOver, 2:I, 3:P (your convention)
            if attr == 0:
                price = getattr(node, "cs_price_sales_shipped", 0) or 0
            elif attr in [1, 2]:
                price = getattr(node, "cs_purchase_total_cost", 0) or 0
            elif attr == 3:
                price = getattr(node, "cs_direct_materials_costs", 0) or 0
            else:
                price = 0

            base = [getattr(node, "name", ""), level, position, price, attr]
            vals = []
            for w in range(output_period):
                try:
                    vals.append(count_lots(node.psi4supply[w][attr]) * price)
                except Exception:
                    vals.append(0)
            data.append(base + vals)

            if attr == 0:
                weekly_in = shift_right(vals, ar_shift)
                data.append([getattr(node, "name", ""), level, position, price, "IN"] + list(vals))
            elif attr == 3:
                weekly_out = shift_right(vals, ap_shift)
                data.append([getattr(node, "name", ""), level, position, price, "OUT"] + list(vals))

        if weekly_in is None:
            weekly_in = np.zeros(output_period)
        if weekly_out is None:
            weekly_out = np.zeros(output_period)
        net = np.array(weekly_in) - np.array(weekly_out)
        data.append([getattr(node, "name", ""), level, position, 0, "NET"] + list(net))

        for i, child in enumerate(getattr(node, "children", []) or []):
            collect(child, level + 1, i + 1)

    collect(root_outbound, 0, 1)

    cols = ["node_name", "Level", "Position", "Price", "PSI_attribute"] + week_cols
    return pd.DataFrame(data, columns=cols)

def cashflow_kpis_from_df(df, node_name: str | None = None):
    week_cols = [c for c in df.columns if c.startswith("w")]
    d = df
    if node_name is not None:
        d = d[d["node_name"] == node_name]

    dnet = d[d["PSI_attribute"] == "NET"]
    if dnet.empty:
        return {"net_cash_min": 0.0, "net_cash_sum": 0.0, "cum_net_cash_min": 0.0}

    net = dnet[week_cols].sum(axis=0).astype(float).values
    net_cash_min = float(net.min()) if len(net) else 0.0
    net_cash_sum = float(net.sum()) if len(net) else 0.0
    cum = net.cumsum() if len(net) else np.array([])
    cum_min = float(cum.min()) if len(cum) else 0.0
    return {"net_cash_min": net_cash_min, "net_cash_sum": net_cash_sum, "cum_net_cash_min": cum_min}


# ----------------------------
# Plotters (matplotlib embedding)
# ----------------------------
def clear_frame(frame):
    for w in frame.winfo_children():
        w.destroy()

def plot_mom_psi_cap(frame, env, product: str, mom_name: str, root_outbound):
    clear_frame(frame)

    # NOTE:
    # ここは「MOM固定」ではなく、cockpit の選択ノード（leaf/WS/PAD/MOM 何でも）を描けるようにする。
    node_name = mom_name  # 引数名は互換維持。実体は「描画したいノード名」

    # node の解決：env.node_dict があれば最優先（outbound/inbound両方を含められる）
    node = None
    node_dict = getattr(env, "node_dict", None)
    if isinstance(node_dict, dict) and node_name:
        node = node_dict.get(node_name)
    if node is None and node_name:
        node = find_node_by_name(root_outbound, node_name)
    if node is None:
        node = root_outbound

    # capability は「そのノードに定義されていれば重ねる」。無ければ PSI だけ描く。
    cap = (((getattr(env, "weekly_capability", {}) or {}).get(product, {}) or {}).get(node_name, None))

    # 描画期間W：capがあればcap優先、無ければpsi長
    psi_supply = getattr(node, "psi4supply", None) or []
    psi_demand = getattr(node, "psi4demand", None) or []
    W = 0
    if cap is not None:
        W = len(cap)
    W = max(W, len(psi_supply), len(psi_demand))
    if W <= 0:
        tk.Label(frame, text=f"No PSI data for {product}:{node_name}").pack()
        return

    # series: S lots, I lots, P lots (fallback)
    s_series = []
    i_series = []
    p_series = []
    for w in range(W):
        try:
            if w < len(psi_supply):
                s_series.append(count_lots(psi_supply[w][0]))
            else:
                s_series.append(count_lots(psi_demand[w][0]) if w < len(psi_demand) else 0)
        except Exception:
            s_series.append(0)
        try:
            i_series.append(count_lots(psi_supply[w][2]) if w < len(psi_supply) else 0)
        except Exception:
            i_series.append(0)
        try:
            p_series.append(count_lots(psi_supply[w][3]) if w < len(psi_supply) else 0)
        except Exception:
            p_series.append(0)

    fig, ax = plt.subplots(figsize=(8.6, 3.2), dpi=110)
    x = np.arange(1, W + 1)

    ax.plot(x, s_series, marker="o", linewidth=1, markersize=2, label="S (Ship/Sales lots)")
    ax.plot(x, p_series, marker="o", linewidth=1, markersize=2, label="P (Production lots)")
    ax.plot(x, i_series, marker="o", linewidth=1, markersize=2, label="I (Inventory lots)")

    #@STOP
    #if cap is not None:
    #    ax.plot(x, cap, marker=None, linewidth=2, label="Capability (lots/week)")

    if cap is not None:
        # cap length must match W; pad with NaN (line breaks) or trim.
        cap_list = list(cap)
        if len(cap_list) < W:
            cap_list = cap_list + [float("nan")] * (W - len(cap_list))
        elif len(cap_list) > W:
            cap_list = cap_list[:W]
        ax.plot(x, cap_list, marker=None, linewidth=2, label="Capability (lots/week)")



    title = f"{product} / {node_name} : PSI"
    if cap is not None:
        title += " vs Capability"
    ax.set_title(title)
    ax.set_xlabel("Week")
    ax.set_ylabel("Lots")
    ax.legend(loc="upper left", fontsize=9)

    canvas = FigureCanvasTkAgg(fig, master=frame)
    canvas.draw()
    canvas.get_tk_widget().pack(fill="both", expand=True)
    plt.close(fig)

def plot_service(frame, env, product: str, root_outbound):
    clear_frame(frame)
    k = compute_service_jit_for_product(root_outbound)

    txt = (
        f"Service (Leaf JIT)\n\n"
        f"JIT MAD (weeks)     : {k['jit_mad_weeks']:.2f}\n"
        f"JIT P95 (weeks)     : {k['jit_p95_weeks']:.2f}\n"
        f"Unfilled lots       : {k['unfilled_lots']}\n"
        f"Filled lots         : {k['filled_lots']}\n"
        f"Total demand lots   : {k['total_demand_lots']}\n"
        f"Avg Late (weeks)    : {k['avg_late_weeks']:.2f}\n"
        f"Avg Early (weeks)   : {k['avg_early_weeks']:.2f}\n"
    )
    lab = tk.Label(frame, text=txt, justify="left", font=("Segoe UI", 11))
    lab.pack(anchor="w", padx=10, pady=10)

def plot_cashflow(frame, df_cash, title: str, node_name: str | None = None):
    clear_frame(frame)

    week_cols = [c for c in df_cash.columns if c.startswith("w")]
    d = df_cash
    if node_name is not None:
        d = d[d["node_name"] == node_name]

    # sum across rows for each attribute
    def series(attr):
        dd = d[d["PSI_attribute"] == attr]
        if dd.empty:
            return np.zeros(len(week_cols))
        return dd[week_cols].sum(axis=0).astype(float).values

    cash_in = series("IN")
    cash_out = series("OUT")
    net = series("NET")

    W = len(week_cols)
    x = np.arange(1, W + 1)

    fig, ax1 = plt.subplots(figsize=(8.6, 3.2), dpi=110)
    bar_w = 0.35
    ax1.bar(x - bar_w / 2, cash_in, width=bar_w, alpha=0.7, label="Cash In")
    ax1.bar(x + bar_w / 2, cash_out, width=bar_w, alpha=0.7, label="Cash Out")
    ax2 = ax1.twinx()
    ax2.plot(x, net, marker="o", linewidth=1, markersize=2, label="Net Cash")

    ax1.set_title(title)
    ax1.set_xlabel("Week")
    ax1.set_ylabel("Cash In/Out")
    ax2.set_ylabel("Net Cash")

    ax1.legend(loc="upper left", fontsize=9)
    ax2.legend(loc="upper right", fontsize=9)

    canvas = FigureCanvasTkAgg(fig, master=frame)
    canvas.draw()
    canvas.get_tk_widget().pack(fill="both", expand=True)
    plt.close(fig)


# ----------------------------
# Cockpit UI
# ----------------------------
class WOMCockpit(tk.Tk):
    def __init__(self, env, rerun_fn=None):
        super().__init__()
        self.env = env
        self.rerun_fn = rerun_fn  # ★ injected from main4cockpit.py
        self.title("WOM Cockpit (Minimal)")
        self.geometry("1100x700")

        # resolve product list
        self.products = sorted(list((getattr(env, "prod_tree_dict_OT", {}) or {}).keys()))
        if not self.products and getattr(env, "product_selected", None):
            self.products = [env.product_selected]

        # MOM list from node_geo.csv
        self.moms_geo = self._load_moms_from_geo()
        # if weekly_capability exists, intersect with capability keys
        self.moms = self._resolve_moms()

        # state vars
        self.var_product = tk.StringVar(value=getattr(env, "product_selected", self.products[0] if self.products else ""))
        self.var_mom = tk.StringVar(value=self.moms[0] if self.moms else "")

        # selection state (node_name common key)
        self.state = SelectionState(
            selected_node=self.var_mom.get() if self.var_mom.get() else None,
            selected_product=self.var_product.get() if self.var_product.get() else None,
        )

        # top controls
        self._build_header()

        # L1: PSI mini (selected node)
        self.l1_frame = ttk.Labelframe(self, text="L1: Selected Node PSI (mini)")
        self.l1_frame.pack(fill="x", padx=10, pady=(0, 6))
        self.l1_text = tk.Text(self.l1_frame, height=6, wrap="word")
        self.l1_text.pack(fill="x", padx=6, pady=6)

        # KPI panel
        self.kpi_frame = ttk.Frame(self)
        self.kpi_frame.pack(fill="x", padx=10, pady=8)
        self.kpi_labels = {}
        self._build_kpi_cards()

        # tabs
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_psi = ttk.Frame(self.nb)
        self.tab_service = ttk.Frame(self.nb)
        self.tab_cash = ttk.Frame(self.nb)

        self.nb.add(self.tab_psi, text="MOM PSI × Capability")
        self.nb.add(self.tab_service, text="Service (Leaf JIT)")
        self.nb.add(self.tab_cash, text="Cashflow (Total / MOM)")

        # tab inner frames
        self.frame_psi_plot = ttk.Frame(self.tab_psi)
        self.frame_psi_plot.pack(fill="both", expand=True)

        self.frame_service = ttk.Frame(self.tab_service)
        self.frame_service.pack(fill="both", expand=True)

        self.frame_cash_controls = ttk.Frame(self.tab_cash)
        self.frame_cash_controls.pack(fill="x", padx=5, pady=5)

        self.frame_cash_total = ttk.Frame(self.tab_cash)
        self.frame_cash_total.pack(fill="both", expand=True)

        # cash controls (Total vs MOM)
        self.var_cash_mode = tk.StringVar(value="TOTAL")
        ttk.Radiobutton(self.frame_cash_controls, text="Total (Outbound sum)", variable=self.var_cash_mode, value="TOTAL", command=self.refresh).pack(side="left")
        ttk.Radiobutton(self.frame_cash_controls, text="Selected MOM", variable=self.var_cash_mode, value="MOM", command=self.refresh).pack(side="left", padx=10)

        # cached cash df
        self.df_cash = None

        # initial draw
        self.refresh()

    def _build_header(self):
        frm = ttk.Frame(self)
        frm.pack(fill="x", padx=10, pady=10)

        ttk.Label(frm, text="Product:", width=10).pack(side="left")
        self.cb_product = ttk.Combobox(frm, textvariable=self.var_product, values=self.products, width=35, state="readonly")
        self.cb_product.pack(side="left", padx=5)
        self.cb_product.bind("<<ComboboxSelected>>", lambda e: self.on_change_product())

        ttk.Label(frm, text="MOM:", width=6).pack(side="left", padx=(20, 0))
        self.cb_mom = ttk.Combobox(frm, textvariable=self.var_mom, values=self.moms, width=20, state="readonly")
        self.cb_mom.pack(side="left", padx=5)
        self.cb_mom.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        ttk.Button(frm, text="Run (recompute)", command=self.run_and_refresh).pack(side="right")
        ttk.Button(frm, text="World Map", command=self.open_world_map).pack(side="right", padx=8)
        ttk.Button(frm, text="Network",   command=self.open_network).pack(side="right", padx=8)
        ttk.Button(frm, text="Select Node", command=self.open_node_selector).pack(side="right", padx=8)


    #@STOP
    #def open_node_selector(self):
    #    prod = self.var_product.get() if self.var_product.get() else None
    #    if not prod:
    #        return
    #    from pysi.gui.node_selector import open_node_selector
    #    open_node_selector(self.root, self.env, prod, on_select=self.set_selected_node)

    def open_node_selector(self):
        """Open V0R7-like tree selector to pick any node."""
        prod = self.var_product.get() if self.var_product.get() else None
        if not prod:
            return

        from pysi.gui.node_selector import open_node_selector as _open_node_selector
        _open_node_selector(self, self.env, prod, on_select=self.set_selected_node)





    # ----------------------------
    # Selection plumbing (single entry point)
    # ----------------------------
    def set_selected_node(self, node_name: str | None, *, source: str = ""):
        """Update selection state and refresh dependent views.
        node_name is the common key across map/network/PSI.
        """
        self.state.selected_node = node_name
        self.state.selected_product = self.var_product.get() if self.var_product.get() else None
        self.render_l1_psi_mini()

    def _ensure_env_node_dict(self):
        """Build env.node_dict once (node_name -> Node) from available trees.
        Keeps L1 rendering fast without repeated traversals.
        """
        env = self.env
        if isinstance(getattr(env, "node_dict", None), dict) and env.node_dict:
            return

        node_dict = {}
        roots = []
        prod = self.var_product.get()
        if prod:
            roots.append((getattr(env, "prod_tree_dict_OT", {}) or {}).get(prod))
            roots.append((getattr(env, "prod_tree_dict_IN", {}) or {}).get(prod))
        if not prod:
            for r in (getattr(env, "prod_tree_dict_OT", {}) or {}).values():
                roots.append(r)
            for r in (getattr(env, "prod_tree_dict_IN", {}) or {}).values():
                roots.append(r)

        for root in roots:
            if not root:
                continue
            for n in iter_nodes(root):
                name = getattr(n, "name", None)
                if name and name not in node_dict:
                    node_dict[name] = n

        env.node_dict = node_dict

    def l1_clear(self):
        self.l1_text.delete("1.0", "end")

    def l1_show_text(self, s: str):
        self.l1_clear()
        self.l1_text.insert("end", s)

    def render_l1_psi_mini(self):
        node_name = getattr(self.state, "selected_node", None)
        if not node_name:
            self.l1_show_text("[L1] no node selected")
            return

        self._ensure_env_node_dict()
        node_dict = getattr(self.env, "node_dict", None)
        if not isinstance(node_dict, dict):
            self.l1_show_text("[L1] env.node_dict not available")
            return

        node = node_dict.get(node_name)
        if node is None:
            self.l1_show_text(f"[L1] node not found: {node_name}")
            return

        self.l1_draw_mini_from_node(node)

    def l1_draw_mini_from_node(self, node):
        """Default mini view: last 10 weeks of S/I/P lot counts (supply layer)."""
        def cnt(x):
            return len(x) if x else 0

        psi4 = getattr(node, "psi4supply", None) or []
        W = min(10, len(psi4))
        lines = [f"node: {getattr(node, 'name', '')}", ""]
        for w in range(W):
            try:
                S = cnt(psi4[w][0])
                I = cnt(psi4[w][2])
                P = cnt(psi4[w][3])
            except Exception:
                S = I = P = 0
            lines.append(f"w{w+1:02d}  S:{S:4d}  I:{I:4d}  P:{P:4d}")
        if W == 0:
            lines.append("(psi4supply is empty)")
        self.l1_show_text("\n".join(lines))

    # ----------------------------
    # World Map integration
    # ----------------------------
    def open_world_map(self):
        """Open World Map view and wire click -> set_selected_node()."""
        prod = self.var_product.get() if self.var_product.get() else None
        parent = getattr(self, "root", None) or getattr(self, "master", None)

        # Preferred: env has show_world_map that accepts on_select callback.
        if hasattr(self.env, "show_world_map"):
            fn = getattr(self.env, "show_world_map")
            try:
                # new signature: show_world_map(product_name=..., on_select=...)

                #@STOP
                #return fn(product_name=prod, on_select=self.set_selected_node)

                self._map_view = fn(product_name=prod, on_select=self.set_selected_node, parent_tk=parent)
                return self._map_view

            except TypeError:
                # old signature fallback: show_world_map(product_name=...)

                #@STOP
                #return fn(product_name=prod)
                
                self._map_view = show_world_map(self.env, product_name=prod, on_select=self.set_selected_node, parent_tk=parent)
                return self._map_view

        # Fallback: optional helper module
        try:
            from pysi.gui.world_map_view import show_world_map  # type: ignore
            return show_world_map(self.env, product_name=prod, on_select=self.set_selected_node)
        except Exception as e:
            self.l1_show_text(f"[World Map] not available: {e}")
            return None



    def open_world_map(self):
        """Open World Map view and wire click -> set_selected_node()."""
        prod = self.var_product.get() if self.var_product.get() else None
        if not prod:
            return None

        parent = getattr(self, "root", None) or getattr(self, "master", None)

        # Preferred: env has show_world_map that accepts on_select callback.
        if hasattr(self.env, "show_world_map"):
            fn = getattr(self.env, "show_world_map")
            try:
                # new signature: show_world_map(product_name=..., on_select=..., parent_tk=...)
                self._world_map_view = fn(
                    product_name=prod,
                    on_select=self.set_selected_node,
                    parent_tk=parent,
                )
                return self._world_map_view

            except TypeError:
                # old signature fallback: show_world_map(product_name=...) OR show_world_map(product_name=..., on_select=...)
                try:
                    # Try without parent_tk first
                    self._world_map_view = fn(product_name=prod, on_select=self.set_selected_node)
                    return self._world_map_view
                except TypeError:
                    # Last resort: only product_name
                    self._world_map_view = fn(product_name=prod)
                    return self._world_map_view

        # Fallback: helper module (pysi.gui.world_map_view)
        try:
            from pysi.gui.world_map_view import show_world_map  # type: ignore

            self._world_map_view = show_world_map(
                self.env,
                product_name=prod,
                on_select=self.set_selected_node,
                parent_tk=parent,
            )
            return self._world_map_view

        except Exception as e:
            self.l1_show_text(f"[World Map] not available: {e}")
            return None




    def open_world_map(self):
            """Open World Map view and wire click -> set_selected_node()."""
            prod = self.var_product.get() if self.var_product.get() else None
            
            # main4cockpit_B.py で root を渡している場合はそれを利用、
            # 無ければ self (WOMCockpit) 自身を親とする
            parent = getattr(self, "root", self) 

            # 直接外部モジュールを呼び出す形に整理します
            try:
                from pysi.gui.world_map_view import show_world_map
                
                # world_map_view.py の show_world_map(env, product_name, on_select, parent_tk) に合わせる
                return show_world_map(
                    env=self.env, 
                    product_name=prod, 
                    on_select=self.set_selected_node, # コールバックを登録
                    parent_tk=parent
                )
            except Exception as e:
                self.l1_show_text(f"[World Map] Error: {e}")
                import traceback
                traceback.print_exc()
                return None


    def open_world_map(self):
        """Open World Map view and wire click -> set_selected_node()."""
        prod = self.var_product.get() if self.var_product.get() else None
        if not prod:
            return None

        parent = self  # tk.Tk なので self が親

        # Preferred: env has show_world_map that accepts on_select callback.
        if hasattr(self.env, "show_world_map"):
            fn = getattr(self.env, "show_world_map")
            try:
                self._world_map_view = fn(
                    product_name=prod,
                    on_select=self.set_selected_node,
                    parent_tk=parent,
                )
                return self._world_map_view
            except TypeError:
                # old signature fallback
                try:
                    self._world_map_view = fn(product_name=prod, on_select=self.set_selected_node)
                    return self._world_map_view
                except TypeError:
                    self._world_map_view = fn(product_name=prod)
                    return self._world_map_view

        # Fallback: helper module
        try:
            from pysi.gui.world_map_view import show_world_map  # type: ignore
            self._world_map_view = show_world_map(
                self.env,
                product_name=prod,
                on_select=self.set_selected_node,
                parent_tk=parent,
            )
            return self._world_map_view
        except Exception as e:
            self.l1_show_text(f"[World Map] not available: {e}")
            return None


























    def _build_kpi_cards(self):
        # simple label grid (not fancy cards, but clean)
        for i, key in enumerate(["Profit", "Service(JIT MAD)", "CCC(placeholder)", "Utilization", "Inventory(last/avg)", "NetCash(min/cum_min)"]):
            lab = ttk.Label(self.kpi_frame, text=f"{key}: -", anchor="w")
            lab.grid(row=0, column=i, sticky="w", padx=8)
            self.kpi_labels[key] = lab

    def _load_moms_from_geo(self):
        # env.load_directory should exist in your code; fallback to current dir
        base = getattr(self.env, "load_directory", ".")
        path = os.path.join(base, "node_geo.csv")
        if not os.path.exists(path):
            return []
        df = pd.read_csv(path, encoding="utf-8-sig")
        moms = sorted(df["node_name"].astype(str)[df["node_name"].astype(str).str.startswith("MOM")].unique().tolist())
        return moms

    def _resolve_moms(self):
        # prefer MOMs that exist in weekly_capability for current product (if any)
        wc = getattr(self.env, "weekly_capability", {}) or {}
        prod = getattr(self.env, "product_selected", None)
        cap_keys = set((wc.get(prod, {}) or {}).keys()) if prod else set()

        if cap_keys:
            moms = [m for m in (self.moms_geo or sorted(list(cap_keys))) if m in cap_keys]
            return moms or sorted(list(cap_keys))
        return self.moms_geo

    def on_change_product(self):
        # update env.product_selected then refresh mom list intersection
        self.env.product_selected = self.var_product.get()
        self.products = sorted(list((getattr(self.env, "prod_tree_dict_OT", {}) or {}).keys())) or self.products
        self.moms = self._resolve_moms()
        self.cb_mom["values"] = self.moms
        if self.moms and self.var_mom.get() not in self.moms:
            self.var_mom.set(self.moms[0])
        self.refresh()

    def run_and_refresh(self):
        """
        ★ rerun_fn があれば：pipeline を再実行して env を差し替え
        ★ なければ：従来フォールバック（軽量再計算）
        """
        prod = self.var_product.get()

        if callable(self.rerun_fn):
            try:
                new_env = self.rerun_fn(product=prod)
            except TypeError:
                # 互換用（万が一 positional のみだった場合）
                new_env = self.rerun_fn(prod)

            if new_env is not None:
                # env swap
                self.env = new_env

                # lists refresh (product / mom)
                self.products = sorted(list((getattr(self.env, "prod_tree_dict_OT", {}) or {}).keys())) or self.products
                self.moms_geo = self._load_moms_from_geo()
                self.moms = self._resolve_moms()

                # combobox update
                self.cb_product["values"] = self.products
                self.cb_mom["values"] = self.moms

                # keep selection stable
                if self.products and prod not in self.products:
                    prod = self.products[0]
                self.var_product.set(prod)
                self.env.product_selected = prod

                if self.moms:
                    if self.var_mom.get() not in self.moms:
                        self.var_mom.set(self.moms[0])
        else:
            # fallback: only call evaluation if exists
            if hasattr(self.env, "demand_leveling4multi_prod"):
                self.env.demand_leveling4multi_prod()

        self.refresh()

    def refresh(self):
        prod = self.var_product.get()
        mom = self.var_mom.get()

        # roots by product
        root_ot = (getattr(self.env, "prod_tree_dict_OT", {}) or {}).get(prod, None)
        if root_ot is None and hasattr(self.env, "root_node_outbound_byprod"):
            root_ot = self.env.root_node_outbound_byprod

        if root_ot is None:
            return

        # ★ ここがAの心臓：PSIグラフの対象ノードは「選択ノード」を優先
        # （leaf/WS/PAD/MOM など全拠点を飛べる）
        selected_node = getattr(self.state, "selected_node", None)
        node_for_plot = selected_node or mom

        # update eval profit
        if hasattr(self.env, "update_evaluation_results4multi_product"):
            try:
                self.env.update_evaluation_results4multi_product()
            except Exception:
                pass

        total_profit = float(getattr(self.env, "total_profit", 0) or 0)
        total_revenue = float(getattr(self.env, "total_revenue", 0) or 0)
        profit_ratio = (total_profit / total_revenue) if total_revenue else 0.0

        # Service
        svc = compute_service_jit_for_product(root_ot)
        jit_mad = svc["jit_mad_weeks"]
        unfilled = svc["unfilled_lots"]

        # Inventory
        inv_last, inv_avg = compute_total_inventory_lots(root_ot)

        # Utilization (series mean)
        used, util = compute_utilization_series(self.env, prod, mom, root_ot)
        util_mean = float(util.mean()) if util is not None and len(util) else 0.0

        # Cashflow DF (cache per refresh)
        output_period = 53 * int(getattr(root_ot, "plan_range", 1))
        self.df_cash = build_cashflow_df_outbound(root_ot, output_period=output_period)

        # Cash KPIs: total + mom
        cash_total = cashflow_kpis_from_df(self.df_cash, node_name=None)
        cash_mom = cashflow_kpis_from_df(self.df_cash, node_name=mom) if mom else {"net_cash_min": 0, "cum_net_cash_min": 0}

        # KPI labels
        self.kpi_labels["Profit"].configure(text=f"Profit: {total_profit:,.0f}   (Rev {total_revenue:,.0f}, Margin {profit_ratio*100:.1f}%)")
        self.kpi_labels["Service(JIT MAD)"].configure(text=f"Service(JIT): MAD {jit_mad:.2f}w / Unfilled {unfilled}")
        self.kpi_labels["CCC(placeholder)"].configure(text="CCC: (hook later)  ※暫定")
        self.kpi_labels["Utilization"].configure(text=f"Utilization({mom}): {util_mean*100:.1f}%")
        self.kpi_labels["Inventory(last/avg)"].configure(text=f"Inventory: last {inv_last:,} lots / avg {inv_avg:,.1f} lots")
        self.kpi_labels["NetCash(min/cum_min)"].configure(
            text=f"NetCash Total: min {cash_total['net_cash_min']:,.0f}, cum_min {cash_total['cum_net_cash_min']:,.0f}  |  "
                 f"{mom}: min {cash_mom['net_cash_min']:,.0f}, cum_min {cash_mom['cum_net_cash_min']:,.0f}"
        )

        # plots
        plot_mom_psi_cap(self.frame_psi_plot, self.env, prod, node_for_plot, root_ot)
        plot_service(self.frame_service, self.env, prod, root_ot)

        mode = self.var_cash_mode.get()
        if mode == "TOTAL":
            plot_cashflow(self.frame_cash_total, self.df_cash, title=f"Cashflow TOTAL (Outbound sum) : {prod}", node_name=None)
        else:
            plot_cashflow(self.frame_cash_total, self.df_cash, title=f"Cashflow MOM : {prod} / {mom}", node_name=mom)


    #@STOP
    #def open_network(self):
    #    prod = self.var_product.get() if self.var_product.get() else None
    #    if not prod:
    #        return
    #    show_network_E2E_matplotlib(
    #        self.env,
    #        product_name=prod,
    #        on_select=self.set_selected_node,   # ←ここがCの心臓
    #    )


    def open_network(self):
        prod = self.var_product.get() if self.var_product.get() else None
        if not prod:
            return
        
        #@STOP
        #from pysi.gui.network_viewer_patched import show_network_E2E_matplotlib

        self._network_viewer = show_network_E2E_matplotlib(
            self.env,
            product_name=prod,
            on_select=self.set_selected_node,
        )

    def set_selected_node(self, node_name: str, source: str = ""):
        """Update selection state and refresh dependent views.
        node_name is the common key across map/network/PSI.
        """
        self.state.selected_node = node_name
        self.state.selected_product = self.var_product.get() if self.var_product.get() else None
    
        # ...既存処理...
        if hasattr(self, "_network_viewer") and self._network_viewer:
            try:
                self._network_viewer.set_selected_node(node_name)
            except Exception:
                pass


        # ---- A: Network Viewer にも同期（ここを追加） ----
        viewer = getattr(self, "_network_viewer", None)
        if viewer is not None:
            try:
                viewer.set_selected_node(node_name)
            except Exception:
                pass

        # （Cで使う）WorldMapにも同期したいので、ハンドルがあれば反映
        wmv = getattr(self, "_world_map_view", None)
        if wmv is not None:
            try:
                wmv.set_selected_node(node_name)  # ← Cで world_map_view に追加する
            except Exception:
                pass
        # -----------------------------------------------

        self.render_l1_psi_mini()
        self.refresh()

def launch_cockpit(env, rerun_fn=None):
    app = WOMCockpit(env, rerun_fn=rerun_fn)
    app.mainloop()
