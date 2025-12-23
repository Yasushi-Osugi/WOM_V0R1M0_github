# pysi/gui/world_map_view.py
# ------------------------------------------------------------
# World Map view extracted from huge gui/app.py
#
# Goal:
#   - Keep cockpit_tk.py light: only "import and call"
#   - Keep app.py compatibility: PSIPlannerApp.show_world_map delegates here
#   - Preserve original flow:
#       show() -> build pos/nodes/edges -> save _map_* -> mpl_connect -> _on_map_click
#
# Callback:
#   on_select(node_name, source="world_map")  # keyword arg allowed
# ------------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Any

import matplotlib.pyplot as plt

OnSelect = Callable[[str], None]  # we may call with keyword arg source="world_map"


def show_world_map(
    env: Any,
    product_name: str | None = None,
    on_select: Optional[Callable[[str], None]] = None,
    *,
    parent_tk: Any | None = None,
    title: str = "Global Supply Chain Map",
) -> "WorldMapView":
    """
    Common entry point for App and Cockpit.

    env must provide (preferably):
      - prod_tree_dict_OT / prod_tree_dict_IN (optional)
      - geo_lookup() -> {node_name: (lat, lon)}  ※あなたの前提と一致
    """
    view = WorldMapView(env, product_name=product_name, on_select=on_select, parent_tk=parent_tk, title=title)
    view.show()
    return view


@dataclass
class _MapState:
    ax: Any | None = None
    fig: Any | None = None
    canvas: Any | None = None

    used_cartopy: bool = False
    data_crs: Any | None = None

    pos: Dict[str, Tuple[float, float]] = None   # node_name -> (lon, lat)
    nodes: Dict[str, Any] = None                 # node_name -> node obj
    all_edges: List[Tuple[str, str]] = None
    high_edges: List[Tuple[str, str]] = None

    anno_artist: Any | None = None
    highlight_artists: List[Any] = None

    cids: List[int] = None


class WorldMapView:
    def __init__(
        self,
        env: Any,
        *,
        product_name: str | None = None,
        on_select: Optional[Callable[[str], None]] = None,
        parent_tk: Any | None = None,
        title: str = "Global Supply Chain Map",
    ):
        self.env = env
        self.product_name = product_name
        self._map_on_select = on_select  # ★ cockpit/app callback
        self.parent_tk = parent_tk
        self.title = title

        self.state = _MapState(
            pos={},
            nodes={},
            all_edges=[],
            high_edges=[],
            highlight_artists=[],
            cids=[],
        )

        # keep names similar to app.py (migration friendly)
        self.world_map_mode = getattr(env, "world_map_mode", "global")  # or "fit"
        self.world_map_fit = getattr(env, "world_map_fit", True)

    # ------------------------------------------------------------
    # Main entry (equivalent to app.py show_world_map)
    # ------------------------------------------------------------
    def show(self) -> None:
        ax, fig, canvas = self._ensure_axes_and_canvas()

        nodes_all = self._collect_all_nodes(self.env)
        geo = self._geo_lookup(self.env)

        used_cartopy, data_crs, ax = self._setup_background(ax, fig)

        pos, missing_geo = self._draw_nodes(ax, nodes_all, geo, used_cartopy=used_cartopy, data_crs=data_crs)
        if missing_geo:
            print(f"[WORLD-MAP] missing geo for nodes (first 20): {missing_geo[:20]}")

        all_edges = self._collect_all_edges(self.env)
        highlight_edges_ot, highlight_edges_in, selected_names = self._collect_highlight_edges(self.env, self.product_name)

        self._draw_edges(
            ax,
            pos,
            all_edges=all_edges,
            highlight_edges_ot=highlight_edges_ot,
            highlight_edges_in=highlight_edges_in,
            used_cartopy=used_cartopy,
            data_crs=data_crs,
        )

        self._auto_fit(ax, pos, selected_names, used_cartopy=used_cartopy)
        self._draw_legend(ax)

        # ---- state save (same contract as app.py) ----
        self._disconnect_events()
        self.state.ax = ax
        self.state.fig = fig
        self.state.canvas = canvas
        self.state.used_cartopy = used_cartopy
        self.state.data_crs = data_crs
        self.state.pos = pos
        self.state.nodes = nodes_all
        self.state.all_edges = list(all_edges)
        self.state.high_edges = list(highlight_edges_ot | highlight_edges_in)

        # base events
        self._connect_base_events()

        # optional interactions (drag-pan etc.)
        self._install_map_interactions()

        # initial draw
        if canvas is not None:
            try:
                canvas.draw_idle()
            except Exception:
                pass
        else:
            plt.show(block=False)

    # ------------------------------------------------------------
    # Canvas / Axes (keep it independent from app.py)
    # ------------------------------------------------------------
    def _ensure_axes_and_canvas(self):
        fig, ax = plt.subplots(figsize=(11, 6), dpi=110)
        try:
            fig.canvas.manager.set_window_title(self.title)  # optional
        except Exception:
            pass
        canvas = fig.canvas

        # Optional Tk embedding (if parent_tk is provided)
        if self.parent_tk is not None:
            try:
                import tkinter as tk
                from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
                top = tk.Toplevel(self.parent_tk)
                top.title(self.title)
                top.geometry("1200x700")
                tk_canvas = FigureCanvasTkAgg(fig, master=top)
                tk_canvas.draw()
                tk_canvas.get_tk_widget().pack(fill="both", expand=True)
                canvas = tk_canvas
            except Exception as e:
                print(f"[WORLD-MAP] Tk embedding failed, fallback to plt.show(): {e}")

        return ax, fig, canvas

    # ------------------------------------------------------------
    # Data collection
    # ------------------------------------------------------------
    def _geo_lookup(self, env) -> Dict[str, Tuple[float, float]]:
        if hasattr(env, "geo_lookup") and callable(getattr(env, "geo_lookup")):
            return env.geo_lookup()
        print("[WORLD-MAP] env.geo_lookup() not found. Returning empty geo dict.")
        return {}

    def _collect_all_nodes(self, env) -> Dict[str, Any]:
        nodes_all: Dict[str, Any] = {}

        if getattr(env, "prod_tree_dict_OT", None):
            for _prod, _root in env.prod_tree_dict_OT.items():
                for n in self._walk_nodes(_root):
                    name = getattr(n, "name", None)
                    if name:
                        nodes_all[name] = n

        if getattr(env, "prod_tree_dict_IN", None):
            for _prod, _root in env.prod_tree_dict_IN.items():
                for n in self._walk_nodes(_root):
                    name = getattr(n, "name", None)
                    if name:
                        nodes_all[name] = n

        if not nodes_all:
            nodes_out = getattr(env, "nodes_outbound", {}) or {}
            nodes_in = getattr(env, "nodes_inbound", {}) or {}
            nodes_all = {**nodes_out, **nodes_in}

        return nodes_all

    def _collect_all_edges(self, env) -> set[Tuple[str, str]]:
        # same strategy as app.py: graph G first, else derive from trees
        all_edges: set[Tuple[str, str]] = set()

        G = getattr(env, "G", None)
        if G is not None and hasattr(G, "edges"):
            try:
                return set(G.edges())
            except Exception:
                pass

        if getattr(env, "prod_tree_dict_OT", None):
            for _prod, _root in env.prod_tree_dict_OT.items():
                for p, c in self._iter_parent_child(_root):
                    all_edges.add((getattr(p, "name", "") or "", getattr(c, "name", "") or ""))

        if getattr(env, "prod_tree_dict_IN", None):
            for _prod, _root in env.prod_tree_dict_IN.items():
                for p, c in self._iter_parent_child(_root):
                    all_edges.add((getattr(p, "name", "") or "", getattr(c, "name", "") or ""))

        return all_edges

    def _collect_highlight_edges(self, env, product_name: str | None):
        highlight_edges_ot: set[Tuple[str, str]] = set()
        highlight_edges_in: set[Tuple[str, str]] = set()
        selected_names: set[str] = set()

        if not product_name:
            return highlight_edges_ot, highlight_edges_in, selected_names

        root_ot = (getattr(env, "prod_tree_dict_OT", {}) or {}).get(product_name) if getattr(env, "prod_tree_dict_OT", None) else None
        if root_ot:
            for p, c in self._iter_parent_child(root_ot):
                highlight_edges_ot.add((getattr(p, "name", "") or "", getattr(c, "name", "") or ""))
            for n in self._walk_nodes(root_ot):
                nm = getattr(n, "name", None)
                if nm:
                    selected_names.add(nm)

        root_in = (getattr(env, "prod_tree_dict_IN", {}) or {}).get(product_name) if getattr(env, "prod_tree_dict_IN", None) else None
        if root_in:
            for p, c in self._iter_parent_child(root_in):
                highlight_edges_in.add((getattr(p, "name", "") or "", getattr(c, "name", "") or ""))
            for n in self._walk_nodes(root_in):
                nm = getattr(n, "name", None)
                if nm:
                    selected_names.add(nm)

        return highlight_edges_ot, highlight_edges_in, selected_names

    # ------------------------------------------------------------
    # Background / draw
    # ------------------------------------------------------------
    def _setup_background(self, ax, fig):
        used_cartopy = False
        data_crs = None

        ax.clear()
        ax.set_title(self.title, fontsize=12)

        try:
            import cartopy.crs as ccrs
            import cartopy.feature as cfeature

            fig = ax.figure
            ax.remove()
            proj_map = ccrs.PlateCarree(central_longitude=180)
            ax = fig.add_subplot(111, projection=proj_map)

            ax.add_feature(cfeature.OCEAN.with_scale("110m"), facecolor="#e6f2ff")
            ax.add_feature(cfeature.LAND.with_scale("110m"), facecolor="#f6f6f6")
            ax.add_feature(cfeature.COASTLINE.with_scale("110m"), linewidth=0.4, edgecolor="#555")
            ax.add_feature(cfeature.BORDERS.with_scale("110m"), linewidth=0.4, edgecolor="#777")
            ax.set_global()

            gl = ax.gridlines(draw_labels=True, linewidth=0.2, color="gray", alpha=0.5, linestyle="--")
            gl.top_labels = gl.right_labels = False

            used_cartopy = True
            data_crs = ccrs.PlateCarree()
        except Exception:
            ax.set_xlim(-180, 180)
            ax.set_ylim(-90, 90)
            ax.set_facecolor("#e6f2ff")

        return used_cartopy, data_crs, ax

    def _draw_nodes(self, ax, nodes_all: Dict[str, Any], geo: Dict[str, Tuple[float, float]], *, used_cartopy: bool, data_crs):
        pos: Dict[str, Tuple[float, float]] = {}
        hub = {"sales_office", "procurement_office", "supply_point"}
        missing_geo: List[str] = []

        for name, node in nodes_all.items():
            g = geo.get(name)
            if not g:
                missing_geo.append(name)
                continue
            lat, lon = float(g[0]), float(g[1])
            x, y = lon, lat
            pos[name] = (x, y)

            color = "#1f77b4" if name not in hub else "#444444"
            ms = 15 if name not in hub else 30

            if used_cartopy and data_crs is not None:
                ax.plot(x, y, "o", ms=max(ms, 12), mfc=color, alpha=0.15, mec="none", transform=data_crs, zorder=3)
                ax.plot(x, y, "o", ms=7, mfc=color, mec="white", mew=0.8, transform=data_crs, zorder=4)
                ax.text(x, y, f" {name}", fontsize=8, va="bottom", transform=data_crs, zorder=4)
            else:
                ax.plot(x, y, "o", ms=max(ms, 12), mfc=color, alpha=0.15, mec="none", zorder=3)
                ax.plot(x, y, "o", ms=7, mfc=color, mec="white", mew=0.8, zorder=4)
                ax.text(x, y, f" {name}", fontsize=8, va="bottom", zorder=4)

        return pos, missing_geo

    def _draw_edges(
        self,
        ax,
        pos: Dict[str, Tuple[float, float]],
        *,
        all_edges: set[Tuple[str, str]],
        highlight_edges_ot: set[Tuple[str, str]],
        highlight_edges_in: set[Tuple[str, str]],
        used_cartopy: bool,
        data_crs,
    ):
        try:
            import cartopy.crs as ccrs
        except Exception:
            ccrs = None

        def _seg(u: str, v: str, color: str, lw: float, *, arrow: bool = False, z: int = 3):
            if u not in pos or v not in pos:
                return
            x1, y1 = pos[u]
            x2, y2 = pos[v]
            if used_cartopy and ccrs is not None:
                ax.plot([x1, x2], [y1, y2], color=color, lw=lw, alpha=0.8, transform=ccrs.Geodetic(), zorder=z)
                if arrow and data_crs is not None:
                    ax.plot(x2, y2, marker=">", color=color, ms=6, transform=data_crs, zorder=z + 1)
            else:
                ax.plot([x1, x2], [y1, y2], color=color, lw=lw, alpha=0.8, zorder=z)
                if arrow:
                    ax.plot(x2, y2, marker=">", color=color, ms=6, zorder=z + 1)

        for (u, v) in all_edges:
            _seg(u, v, "#cccccc", 1.0, arrow=False, z=3)

        for (u, v) in highlight_edges_ot:
            _seg(u, v, "royalblue", 2.2, arrow=True, z=5)

        for (u, v) in highlight_edges_in:
            _seg(v, u, "seagreen", 2.2, arrow=True, z=5)  # reverse for inbound

    def _auto_fit(self, ax, pos: Dict[str, Tuple[float, float]], selected_names: set[str], *, used_cartopy: bool):
        def _wrap_lon(lon: float, center: float = 180.0) -> float:
            return ((lon - center + 180.0) % 360.0) - 180.0

        fit = bool(getattr(self, "world_map_fit", True))
        if not pos:
            return

        fit_keys = [k for k in selected_names if k in pos] or list(pos.keys())
        xs = [pos[k][0] for k in fit_keys]
        ys = [pos[k][1] for k in fit_keys]

        ymin, ymax = min(ys), max(ys)
        xs_wrapped = [_wrap_lon(x, center=180.0) for x in xs]
        xmin_c, xmax_c = min(xs_wrapped), max(xs_wrapped)

        lon_pad = max(5.0, (xmax_c - xmin_c) * 0.08)
        lat_pad = max(3.0, (ymax - ymin) * 0.10)

        if fit:
            if used_cartopy:
                try:
                    ax.set_extent([xmin_c - lon_pad, xmax_c + lon_pad, ymin - lat_pad, ymax + lat_pad], crs=ax.projection)
                except Exception:
                    pass
            else:
                ax.set_xlim(xmin_c - lon_pad, xmax_c + lon_pad)
                ax.set_ylim(ymin - lat_pad, ymax + lat_pad)
        else:
            if used_cartopy:
                try:
                    ax.set_global()
                except Exception:
                    pass
            else:
                ax.set_xlim(-180, 180)
                ax.set_ylim(-90, 90)

    def _draw_legend(self, ax):
        ax.plot([], [], color="#cccccc", lw=1.2, label="All edges")
        ax.plot([], [], color="royalblue", lw=2.2, label="Outbound (product)")
        ax.plot([], [], color="seagreen", lw=2.2, label="Inbound (product)")
        ax.legend(loc="lower left", fontsize=8)

    # ------------------------------------------------------------
    # Event wiring (base)
    # ------------------------------------------------------------
    def _disconnect_events(self):
        if not self.state.canvas or not self.state.cids:
            return
        try:
            canvas = self.state.canvas
            if hasattr(canvas, "mpl_disconnect"):
                for cid in list(self.state.cids):
                    canvas.mpl_disconnect(cid)
        except Exception:
            pass
        self.state.cids = []

    def _connect_base_events(self):
        if not self.state.canvas:
            return
        canvas = self.state.canvas
        if hasattr(canvas, "mpl_connect"):
            self.state.cids = [
                canvas.mpl_connect("scroll_event", self._on_map_scroll),
                canvas.mpl_connect("button_press_event", self._on_map_click),
                canvas.mpl_connect("key_press_event", self._on_map_key),
            ]

    # ------------------------------------------------------------
    # Click handler (SelectionState bridge)
    # ------------------------------------------------------------
    def _on_map_click(self, event):
        ax = self.state.ax
        if ax is None or getattr(event, "inaxes", None) is not ax:
            return

        pair = self._event_lonlat(event)
        if not pair:
            self._clear_map_highlights()
            return
        x, y = pair

        pos = self.state.pos or {}
        if not pos:
            return

        used_cartopy = bool(self.state.used_cartopy)
        data_crs = self.state.data_crs

        try:
            if used_cartopy and data_crs is not None and hasattr(ax, "get_extent"):
                xmin, xmax, ymin, ymax = ax.get_extent(crs=data_crs)
            else:
                xmin, xmax = ax.get_xlim()
                ymin, ymax = ax.get_ylim()
        except Exception:
            xmin, xmax, ymin, ymax = -180, 180, -90, 90

        thr = 0.01 * ((xmax - xmin) + (ymax - ymin))
        hit, best = None, 1e9
        for name, (lon, lat) in pos.items():
            d = abs(lon - x) + abs(lat - y)
            if d < best:
                hit, best = name, d

        if hit is None or best > thr:
            self._clear_map_highlights()
            return

        self._clear_map_highlights()

        node = (self.state.nodes or {}).get(hit)
        info = hit
        if node is not None:
            rows = []
            for k in ("lat", "lon", "node_type", "capacity", "cost_coeff", "revenue_coeff"):
                if hasattr(node, k):
                    rows.append(f"{k}: {getattr(node, k)}")
            if rows:
                info = hit + "\n" + "\n".join(rows)

        if used_cartopy and data_crs is not None:
            anno = ax.annotate(
                info, xy=pos[hit], xytext=(6, 6), textcoords="offset points",
                fontsize=9, bbox=dict(boxstyle="round", fc="w", ec="#333", alpha=0.9),
                transform=data_crs, zorder=10
            )
            ring, = ax.plot([pos[hit][0]], [pos[hit][1]], "o", ms=18, mfc="none", mec="red", mew=2,
                            alpha=0.7, transform=data_crs, zorder=9)
        else:
            anno = ax.annotate(
                info, xy=pos[hit], xytext=(6, 6), textcoords="offset points",
                fontsize=9, bbox=dict(boxstyle="round", fc="w", ec="#333", alpha=0.9),
                zorder=10
            )
            ring, = ax.plot([pos[hit][0]], [pos[hit][1]], "o", ms=18, mfc="none", mec="red", mew=2,
                            alpha=0.7, zorder=9)

        self.state.anno_artist = anno
        self.state.highlight_artists = [ring, anno]

        if self.state.canvas is not None:
            try:
                self.state.canvas.draw_idle()
            except Exception:
                pass

        # ★ cockpit/app sync
        cb = getattr(self, "_map_on_select", None)
        if callable(cb):
            try:
                cb(hit, source="world_map")
            except TypeError:
                cb(hit)

    # ------------------------------------------------------------
    # Stubs: paste from app.py (OK to keep NotImplemented for now)
    # ------------------------------------------------------------
    def _event_lonlat(self, event) -> Optional[Tuple[float, float]]:
        # TODO: if your app.py has robust cartopy conversion, paste it here
        x = getattr(event, "xdata", None)
        y = getattr(event, "ydata", None)
        if x is None or y is None:
            return None
        return float(x), float(y)

    #def _install_map_interactions(self):
    #    # TODO: paste right-drag pan wiring (press/release/motion)
    #    return
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




    #def _on_map_press(self, event):
    #    raise NotImplementedError
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


    #def _on_map_release(self, event):
    #    raise NotImplementedError
    # --- ボタン離し：パン終了 ---
    def _on_map_release(self, event):
        if getattr(self, "_map_panning", False):
            self._map_panning = False
            self._set_map_cursor(None)

    #def _on_map_motion(self, event):
    #    raise NotImplementedError
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


    #def _on_map_scroll(self, event):
    #    # TODO: paste zoom logic
    #    return
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


    #def _on_map_key(self, event):
    #    # TODO: paste key logic (a/f/w etc.)
    #    return
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






    def _fit_lonlat(self, lons: Sequence[float], lats: Sequence[float], edges=None):
    #    raise NotImplementedError
    #def _fit_lonlat(self, lons, lats, edges=None):
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







    def _clear_map_highlights(self):
        if self.state.highlight_artists:
            for a in list(self.state.highlight_artists):
                try:
                    a.remove()
                except Exception:
                    pass
        self.state.highlight_artists = []
        self.state.anno_artist = None
        if self.state.canvas is not None:
            try:
                self.state.canvas.draw_idle()
            except Exception:
                pass

    # ---- Tree traversal helpers (paste from app.py if needed) ----
    def _walk_nodes(self, root) -> Iterable[Any]:
        if root is None:
            return []
        stack = [root]
        out = []
        while stack:
            n = stack.pop()
            if n is None:
                continue
            out.append(n)
            children = getattr(n, "children", None) or []
            for c in children:
                stack.append(c)
        return out

    def _iter_parent_child(self, root) -> Iterable[Tuple[Any, Any]]:
        if root is None:
            return []
        out = []
        stack = [root]
        while stack:
            p = stack.pop()
            if p is None:
                continue
            children = getattr(p, "children", None) or []
            for c in children:
                out.append((p, c))
                stack.append(c)
        return out

    # ---- View limit helpers (paste from app.py) ----
    def _collect_geo_points(self):
        raise NotImplementedError

    def _apply_world_limits(self, ax, pts, mode: str):
        raise NotImplementedError
