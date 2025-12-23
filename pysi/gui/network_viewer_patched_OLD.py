# -*- coding: utf-8 -*-
"""
network_viewer (V0R7-style) for WOM / PySI

This module provides an E2E network (outbound+inbound) viewer using matplotlib+tkinter.

Key features:
- Uses pysi.network.tree.make_E2E_positions(...) to compute V0R7-style left/right layout.
- Draws outbound edges (blue) and inbound edges (green) on a single NetworkX graph.
- Optional highlight_flow (optimised flows) in red; safe when missing/empty.
- Supports click-to-select: on_select(node_name, source="network") callback.

Designed to be dropped into WOM cockpit and called like:

    show_network_E2E_matplotlib(env, product_name=prod, on_select=cockpit.set_selected_node)

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple, Set, Iterable

import math

import networkx as nx

# Matplotlib / Tkinter embedding
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None
    ttk = None


# ---------------------------------------------------------------------
# Imports from core/tree.py (shared by V0R7 and WOM)
# ---------------------------------------------------------------------
def _import_tree_helpers():
    """
    Import helpers from the shared tree.py.

    We keep this dynamic to match both repository layouts.
    """
    candidates = [
        ("pysi.network.tree", ["make_E2E_positions", "make_edge_weight_capacity", "float2int"]),
        ("pysi.network.tree", ["make_E2E_positions", "make_edge_weight_capacity", "float2int"]),
        ("pysi.core.tree", ["make_E2E_positions", "make_edge_weight_capacity", "float2int"]),
        ("tree", ["make_E2E_positions", "make_edge_weight_capacity", "float2int"]),
    ]
    last_err: Optional[Exception] = None
    for mod, names in candidates:
        try:
            m = __import__(mod, fromlist=names)
            return (getattr(m, names[0]), getattr(m, names[1]), getattr(m, names[2]))
        except Exception as e:
            last_err = e
    raise ImportError(f"Cannot import make_E2E_positions helpers. last_err={last_err!r}")


make_E2E_positions, make_edge_weight_capacity, float2int = _import_tree_helpers()


# ---------------------------------------------------------------------
# Tree -> NetworkX conversion (minimal, compatible with Node(name, children))
# ---------------------------------------------------------------------
def G_add_edge_from_tree(node: Any, G: nx.DiGraph) -> None:
    """Add edges recursively from outbound tree."""
    if node is None:
        return
    if getattr(node, "children", None) is None:
        return
    if node.children == []:
        return
    for child in node.children:
        w, cap = make_edge_weight_capacity(node, child)
        w_i = float2int(w)
        cap_i = round(float(cap)) + 1  # keep old behaviour
        G.add_edge(node.name, child.name, weight=w_i, capacity=cap_i)
        G_add_edge_from_tree(child, G)


def G_add_edge_from_inbound_tree(node: Any, supplyers_capacity: float, G: nx.DiGraph) -> None:
    """Add edges recursively from inbound tree (towards procurement_office)."""
    if node is None:
        return
    if getattr(node, "children", None) is None:
        return
    if node.children == []:
        return
    for child in node.children:
        w, cap = make_edge_weight_capacity(node, child)
        w_i = float2int(w)
        cap_i = round(float(cap)) + 1
        # inbound tree direction: procurement -> suppliers, but for drawing we keep parent->child
        G.add_edge(node.name, child.name, weight=w_i, capacity=cap_i)
        G_add_edge_from_inbound_tree(child, supplyers_capacity, G)


def G_add_nodes_from_tree(node: Any, G: nx.DiGraph) -> None:
    """Add nodes recursively from tree."""
    if node is None:
        return
    G.add_node(node.name)
    if getattr(node, "children", None) is None or node.children == []:
        return
    for child in node.children:
        G_add_nodes_from_tree(child, G)


# ---------------------------------------------------------------------
# Viewer
# ---------------------------------------------------------------------
@dataclass
class NetworkViewerState:
    product_name: str
    root_out: Any
    root_in: Any
    pos: Dict[str, Tuple[float, float]]
    graph: nx.DiGraph


class NetworkViewer:
    """
    Tkinter window that renders E2E network with click selection.
    """

    def __init__(
        self,
        env: Any,
        product_name: str,
        root_out: Any,
        root_in: Any,
        *,
        highlight_flow: Optional[Dict[str, Dict[str, float]]] = None,
        on_select: Optional[Callable[..., Any]] = None,
        parent: Optional[Any] = None,
        dx: float = 1.0,
        dy: float = 1.0,
        office_margin: float = 1.0,
    ) -> None:
        if tk is None:
            raise RuntimeError("Tkinter is not available in this environment.")

        self.env = env
        self.product_name = product_name
        self.root_out = root_out
        self.root_in = root_in
        self.highlight_flow = highlight_flow or {}
        self.on_select = on_select
        self.dx = dx
        self.dy = dy
        self.office_margin = office_margin

        self._toplevel = tk.Toplevel(parent) if parent is not None else tk.Toplevel()
        self._toplevel.title("Supply Chain Network (E2E)")

        # Figure / Axes / Canvas
        self.fig = Figure(figsize=(8, 6), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self._toplevel)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # Build state and draw
        self.state = self._build_state()
        self._draw()

        # interactions
        self.canvas.mpl_connect("button_press_event", self._on_plot_click)

    # -------------------
    # Build and draw
    # -------------------
    def _build_state(self) -> NetworkViewerState:
        # Compute positions using shared helper
        pos = make_E2E_positions(
            root_node_outbound=self.root_out,
            root_node_inbound=self.root_in,
            dx=self.dx,
            dy=self.dy,
            office_margin=self.office_margin,
        )

        # Build a unified graph for drawing (nodes+edges from both)
        G = nx.DiGraph()

        if self.root_out is not None:
            G_add_nodes_from_tree(self.root_out, G)
            G_add_edge_from_tree(self.root_out, G)

        if self.root_in is not None:
            G_add_nodes_from_tree(self.root_in, G)
            # capacity hint
            supplyers_capacity = getattr(self.root_in, "nx_demand", 0) * 2
            G_add_edge_from_inbound_tree(self.root_in, supplyers_capacity, G)

        return NetworkViewerState(
            product_name=self.product_name,
            root_out=self.root_out,
            root_in=self.root_in,
            pos=pos,
            graph=G,
        )

    def _draw(self) -> None:
        ax = self.ax
        ax.clear()
        ax.set_title(f"{self.product_name} - E2E Network")

        G = self.state.graph
        pos = self.state.pos

        # Split edges by "which tree" they belong to, for coloring.
        outbound_edges: Set[Tuple[str, str]] = set()
        inbound_edges: Set[Tuple[str, str]] = set()

        if self.root_out is not None:
            for u, v in self._collect_edges_from_tree(self.root_out):
                outbound_edges.add((u, v))
        if self.root_in is not None:
            for u, v in self._collect_edges_from_tree(self.root_in):
                inbound_edges.add((u, v))

        all_edges = list(G.edges())
        nx.draw_networkx_edges(G, pos, edgelist=all_edges, ax=ax, width=0.6, alpha=0.25)

        if outbound_edges:
            nx.draw_networkx_edges(G, pos, edgelist=list(outbound_edges), ax=ax, width=1.8, alpha=0.9)
        if inbound_edges:
            nx.draw_networkx_edges(G, pos, edgelist=list(inbound_edges), ax=ax, width=1.8, alpha=0.9)

        # Nodes
        nx.draw_networkx_nodes(G, pos, ax=ax, node_size=60, alpha=0.9)

        # Labels
        labels = {n: str(n) for n in G.nodes()}
        nx.draw_networkx_labels(G, pos, labels=labels, font_size=8, ax=ax)

        # Optimised flow highlights (red), safe when absent
        self._draw_highlight_flow(ax, G, pos, self.highlight_flow)

        # Axes cosmetics
        ax.set_axis_off()
        self.canvas.draw()

    def _draw_highlight_flow(
        self,
        ax: Any,
        G: nx.DiGraph,
        pos: Dict[str, Tuple[float, float]],
        highlight_flow: Dict[str, Dict[str, float]],
    ) -> None:
        if not isinstance(highlight_flow, dict) or not highlight_flow:
            return
        for u, flows in highlight_flow.items():
            if not isinstance(flows, dict):
                continue
            for v, f in flows.items():
                try:
                    if float(f) <= 0:
                        continue
                except Exception:
                    continue
                if (u not in pos) or (v not in pos):
                    continue
                nx.draw_networkx_edges(
                    G,
                    pos,
                    edgelist=[(u, v)],
                    ax=ax,
                    edge_color="red",
                    width=2.2,
                    alpha=0.95,
                    arrows=False,
                )

    def _collect_edges_from_tree(self, node: Any) -> Iterable[Tuple[str, str]]:
        if node is None:
            return []
        out = []
        children = getattr(node, "children", None) or []
        for ch in children:
            out.append((node.name, ch.name))
            out.extend(self._collect_edges_from_tree(ch))
        return out

    # -------------------
    # Interaction
    # -------------------
    def _on_plot_click(self, event: Any) -> None:
        if event.inaxes is not self.ax:
            return
        x = getattr(event, "xdata", None)
        y = getattr(event, "ydata", None)
        if x is None or y is None:
            return

        pos = self.state.pos or {}
        if not pos:
            return

        hit, best = None, 1e18
        for name, (px, py) in pos.items():
            d = (px - x) ** 2 + (py - y) ** 2
            if d < best:
                hit, best = name, d

        if hit is None:
            return

        # Threshold in layout units (dx/dy grid). Tune if needed.
        thr2 = 0.9 ** 2
        if best > thr2:
            return

        cb = self.on_select
        if callable(cb):
            try:
                cb(hit, source="network")
            except TypeError:
                cb(hit)

        # optional: light visual feedback (title update)
        try:
            self._toplevel.title(f"Supply Chain Network (E2E) - {hit}")
        except Exception:
            pass

    # -------------------
    # Public
    # -------------------
    def close(self) -> None:
        try:
            self._toplevel.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------
# Public API (what cockpit imports)
# ---------------------------------------------------------------------
def show_network_E2E_matplotlib(
    env: Any,
    product_name: Optional[str] = None,
    root_out: Any = None,
    root_in: Any = None,
    *,
    highlight_flow: Optional[Dict[str, Dict[str, float]]] = None,
    on_select: Optional[Callable[..., Any]] = None,
    parent: Optional[Any] = None,
    dx: float = 1.0,
    dy: float = 1.0,
    office_margin: float = 1.0,
) -> NetworkViewer:
    """
    Open a Tk window that shows E2E network diagram.

    - If root_out/root_in are None, tries env.prod_tree_dict_OT/IN[product_name].
    - highlight_flow may be {} when optimiser isn't run.
    - on_select will be called on node click.
    """
    if product_name is None:
        # Try to infer
        product_name = getattr(env, "selected_product", None) or "product"

    if root_out is None:
        root_out = getattr(env, "prod_tree_dict_OT", {}).get(product_name)
    if root_in is None:
        root_in = getattr(env, "prod_tree_dict_IN", {}).get(product_name)

    return NetworkViewer(
        env,
        product_name=product_name,
        root_out=root_out,
        root_in=root_in,
        highlight_flow=highlight_flow,
        on_select=on_select,
        parent=parent,
        dx=dx,
        dy=dy,
        office_margin=office_margin,
    )
