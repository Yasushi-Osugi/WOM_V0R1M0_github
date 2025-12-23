# pysi/gui/network_viewer_patched.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple, List

try:
    import tkinter as tk
except Exception:
    tk = None

import math

import networkx as nx
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


#@STOP
## ------------------------------------------------------------
## Core layout helper (shared by V0R7 and WOM)
## ------------------------------------------------------------
#try:
#    # core/tree.py が同じ前提
#    from pysi.core.tree import make_E2E_positions
#except Exception:
#    try:
#        from pysi.core.tree import make_E2E_positions  # fallback identical
#    except Exception as e:
#        make_E2E_positions = None  # type: ignore

from pysi.network.tree import make_E2E_positions



def _iter_tree_nodes(root: Any) -> List[Any]:
    """Traverse a tree whose nodes have .children (list) or dict-like children."""
    if root is None:
        return []
    out = []
    stack = [root]
    seen = set()
    while stack:
        n = stack.pop()
        if id(n) in seen:
            continue
        seen.add(id(n))
        out.append(n)

        kids = getattr(n, "children", None)
        if kids is None:
            # some trees may use .child or .child_nodes
            kids = getattr(n, "child", None)
        if kids is None:
            kids = getattr(n, "child_nodes", None)

        if kids is None:
            continue

        if isinstance(kids, dict):
            stack.extend(list(kids.values()))
        elif isinstance(kids, (list, tuple, set)):
            stack.extend(list(kids))
        else:
            # single child
            stack.append(kids)
    return out


def _node_name(node: Any) -> str:
    """Extract display key from a tree node. Prefer .name then .node_name then str(node)."""
    for k in ("name", "node_name", "id"):
        v = getattr(node, k, None)
        if isinstance(v, str) and v:
            return v
    return str(node)


def _build_graphs_from_roots(root_out: Any, root_in: Any) -> Tuple[nx.DiGraph, nx.DiGraph, nx.DiGraph]:
    """
    Build:
      G   : all nodes/edges
      Gdm : demand-ish edges (outbound)  (blue)
      Gsp : supply-ish edges (inbound)   (green)
    Note: colors are set in drawing, graphs just carry topology.
    """
    G = nx.DiGraph()
    Gdm = nx.DiGraph()
    Gsp = nx.DiGraph()

    def add_tree_edges(root: Any, target: nx.DiGraph):
        if root is None:
            return
        for n in _iter_tree_nodes(root):
            pn = _node_name(n)
            target.add_node(pn)
            G.add_node(pn)
            kids = getattr(n, "children", None)
            if kids is None:
                kids = getattr(n, "child_nodes", None)
            if kids is None:
                continue

            if isinstance(kids, dict):
                it = kids.values()
            elif isinstance(kids, (list, tuple, set)):
                it = kids
            else:
                it = [kids]

            for c in it:
                cn = _node_name(c)
                # parent -> child edges
                target.add_edge(pn, cn)
                G.add_edge(pn, cn)

    # outbound を demand graph として扱う（青）
    add_tree_edges(root_out, Gdm)
    # inbound を supply graph として扱う（緑）
    add_tree_edges(root_in, Gsp)

    return G, Gdm, Gsp


# ------------------------------------------------------------
# Drawing
# ------------------------------------------------------------
def draw_network_e2e(
    ax,
    G: nx.DiGraph,
    Gdm: nx.DiGraph,
    Gsp: nx.DiGraph,
    pos: Dict[str, Tuple[float, float]],
    *,
    highlight_flow: Optional[Dict[str, Dict[str, float]]] = None,
    selected_node: Optional[str] = None,
) -> None:
    """
    Draw base network + selected node highlight.
    highlight_flow: (optional) optimiser result dict; if empty, nothing drawn.
    """
    ax.clear()
    ax.set_axis_off()

    # --- base edges (all) faint ---
    nx.draw_networkx_edges(G, pos, ax=ax, edge_color="lightgray", arrows=False, width=0.8)

    # --- outbound / inbound edges ---
    if Gdm.number_of_edges() > 0:
        nx.draw_networkx_edges(Gdm, pos, ax=ax, edge_color="royalblue", arrows=False, width=1.6)
    if Gsp.number_of_edges() > 0:
        nx.draw_networkx_edges(Gsp, pos, ax=ax, edge_color="seagreen", arrows=False, width=1.6)

    # --- nodes base ---
    nodes_all = list(G.nodes())
    if nodes_all:
        nx.draw_networkx_nodes(G, pos, nodelist=nodes_all, ax=ax, node_size=90, node_color="#1f77b4", linewidths=0.0)

    # --- labels base (small) ---
    if nodes_all:
        nx.draw_networkx_labels(G, pos, ax=ax, font_size=8)

    # --- optimiser flow highlight (red) : safe-guarded ---
    if isinstance(highlight_flow, dict) and highlight_flow:
        for u, flows in highlight_flow.items():
            if not isinstance(flows, dict):
                continue
            for v, f in flows.items():
                try:
                    if float(f) > 0 and (u in pos) and (v in pos):
                        nx.draw_networkx_edges(
                            G,
                            pos,
                            ax=ax,
                            edgelist=[(u, v)],
                            edge_color="red",
                            arrows=False,
                            width=2.2,
                        )
                except Exception:
                    pass

    # --- selected node highlight ---
    if selected_node and (selected_node in pos):
        # ring + bigger node
        nx.draw_networkx_nodes(
            G,
            pos,
            nodelist=[selected_node],
            ax=ax,
            node_size=260,
            node_color="orange",
            linewidths=2.0,
            edgecolors="black",
        )
        # emphasize label (draw again)
        nx.draw_networkx_labels(
            G,
            pos,
            ax=ax,
            labels={selected_node: selected_node},
            font_size=10,
            font_weight="bold",
        )


# ------------------------------------------------------------
# Viewer
# ------------------------------------------------------------
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
        if make_E2E_positions is None:
            raise RuntimeError("make_E2E_positions is not available (pysi.core.tree import failed).")

        self.env = env
        self.product_name = product_name
        self.root_out = root_out
        self.root_in = root_in
        self.highlight_flow = highlight_flow or {}
        self.on_select = on_select
        self.dx = dx
        self.dy = dy
        self.office_margin = office_margin

        # selection state in this viewer
        self.selected_node: Optional[str] = None

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

    # ---- external API: allow cockpit/world_map/tree to push selection ----
    def set_selected_node(self, node_name: Optional[str]) -> None:
        self.selected_node = node_name if node_name else None
        self._draw()

    def _build_state(self) -> Dict[str, Any]:
        G, Gdm, Gsp = _build_graphs_from_roots(self.root_out, self.root_in)

        # layout (pos_E2E)
        # make_E2E_positions が V0R7/WOM共通の core にある前提
        pos = make_E2E_positions(
            self.root_out,
            self.root_in,
            dx=self.dx,
            dy=self.dy,
            office_margin=self.office_margin,
        )

        # normalize pos into (float,float)
        pos2: Dict[str, Tuple[float, float]] = {}
        for k, v in (pos or {}).items():
            try:
                pos2[str(k)] = (float(v[0]), float(v[1]))
            except Exception:
                pass

        return {"G": G, "Gdm": Gdm, "Gsp": Gsp, "pos": pos2}

    def _draw(self) -> None:
        st = self.state
        G: nx.DiGraph = st["G"]
        Gdm: nx.DiGraph = st["Gdm"]
        Gsp: nx.DiGraph = st["Gsp"]
        pos: Dict[str, Tuple[float, float]] = st["pos"]

        draw_network_e2e(
            self.ax,
            G,
            Gdm,
            Gsp,
            pos,
            highlight_flow=self.highlight_flow,
            selected_node=self.selected_node,
        )

        self.ax.set_title(f"{self.product_name} - E2E Network", fontsize=12)
        self.canvas.draw_idle()

    def _on_plot_click(self, event) -> None:
        # click on axes only
        if event.inaxes is not self.ax:
            return
        x, y = getattr(event, "xdata", None), getattr(event, "ydata", None)
        if x is None or y is None:
            return

        pos: Dict[str, Tuple[float, float]] = self.state["pos"]
        if not pos:
            return

        # nearest node
        hit = None
        best = 1e18
        for name, (px, py) in pos.items():
            d = (px - x) ** 2 + (py - y) ** 2
            if d < best:
                hit = name
                best = d

        if hit is None:
            return

        # threshold to avoid accidental clicks (grid-scale based)
        # pos_E2E is typically integer-ish; 1.0 is reasonable
        if best > 1.0:
            return

        # update local highlight
        self.selected_node = hit
        self._draw()

        # callback to cockpit
        cb = self.on_select
        if callable(cb):
            try:
                cb(hit, source="network")
            except TypeError:
                cb(hit)


# ------------------------------------------------------------
# public API
# ------------------------------------------------------------
def show_network_E2E_matplotlib(
    env: Any,
    *,
    product_name: Optional[str] = None,
    root_out: Any = None,
    root_in: Any = None,
    highlight_flow: Optional[Dict[str, Dict[str, float]]] = None,
    on_select: Optional[Callable[..., Any]] = None,
    parent: Optional[Any] = None,
    dx: float = 1.0,
    dy: float = 1.0,
    office_margin: float = 1.0,
) -> NetworkViewer:
    """
    Open E2E network viewer window.
    If root_out/root_in not provided, try to fetch from env.prod_tree_dict_OT/IN using product_name.
    Returns the viewer so the caller can push selection updates (viewer.set_selected_node()).
    """
    prod = product_name
    if not prod:
        # try env current product or first in list
        prod = getattr(env, "product_name", None) or None

    if (root_out is None) and prod is not None:
        root_out = getattr(env, "prod_tree_dict_OT", {}).get(prod)
    if (root_in is None) and prod is not None:
        root_in = getattr(env, "prod_tree_dict_IN", {}).get(prod)

    viewer = NetworkViewer(
        env,
        prod or "(unknown)",
        root_out,
        root_in,
        highlight_flow=highlight_flow,
        on_select=on_select,
        parent=parent,
        dx=dx,
        dy=dy,
        office_margin=office_margin,
    )
    return viewer
