# world_map_view_patched.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Any, Dict, Tuple, List, Iterable

# NOTE:
# - このファイルは「app.py の show_world_map 一式」を cockpit/app 両方から呼べる共通部品にするための器です。
# - 既存 app.py 側の実装を壊さずに移植する前提で、state と alias を用意しています。


@dataclass
class MapState:
    fig: Any = None
    ax: Any = None
    canvas: Any = None

    used_cartopy: bool = False
    data_crs: Any = None

    # pos: {node_name: (lon, lat)}
    pos: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    nodes: Dict[str, Any] = field(default_factory=dict)

    all_edges: List[Tuple[str, str]] = field(default_factory=list)
    high_edges: List[Tuple[str, str]] = field(default_factory=list)

    # highlight/annotation artists
    anno_artist: Any = None
    highlight_artists: List[Any] = field(default_factory=list)

    # mpl connection ids
    cids: List[int] = field(default_factory=list)


def show_world_map(
    env: Any,
    product_name: Optional[str] = None,
    on_select: Optional[Callable[..., None]] = None,
    parent: Any = None,
) -> "WorldMapView":
    """
    Common entry for World Map.
    env: PlanEnv / SqlPlanEnv / WOMEnv (geo_lookup を持つ想定でもOK・後で剥がせる)
    on_select: callback(node_name, source="world_map")
    parent: Tk container (必要なら)
    """
    view = WorldMapView(env=env, product_name=product_name, on_select=on_select, parent=parent)
    view.show()
    return view


class WorldMapView:
    def __init__(
        self,
        env: Any,
        product_name: Optional[str] = None,
        on_select: Optional[Callable[..., None]] = None,
        parent: Any = None,
    ):
        self.env = env
        self.product_name = product_name
        self._map_on_select = on_select
        self.parent = parent

        # state（旧 app.py の _map_* を集約する）
        self.state = MapState()

        # --- backward compat placeholders (app.py names) ---
        # show() の最後で本体を代入します
        self.fig_network = None
        self.ax_network = None
        self.canvas_network = None

        # NOTE: app.py 由来の周辺状態が必要ならここへ
        # self.world_map_fit_var / self.world_map_mode / etc...














    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def show(self) -> "WorldMapView":
        """
        Build & show world map.
        - app.py の show_world_map() の流れを崩さずに移植する
        - pos/nodes/edges を state に保持
        - mpl_connect / interactions を張る
        """
        # ここは既存 app.py の show_world_map を移植して埋める（NotImplementedでもOK）

        # --- Axes/Figure/Canvas ---
        self._ensure_network_axes(parent=self.parent)
        ax = getattr(self, "ax_network", None) or getattr(self.state, "ax", None)
        if ax is None:
            print("[WORLD-MAP] no axes")
            return self
        fig = ax.figure

        # --- collect nodes (OUT/IN) ---
        nodes_all: Dict[str, Any] = {}
        env = self.env
        if env:
            if getattr(env, "prod_tree_dict_OT", None):
                for _prod, _root in env.prod_tree_dict_OT.items():
                    for n in self._walk_nodes(_root):
                        nodes_all[getattr(n, "name", "")] = n
            if getattr(env, "prod_tree_dict_IN", None):
                for _prod, _root in env.prod_tree_dict_IN.items():
                    for n in self._walk_nodes(_root):
                        nodes_all[getattr(n, "name", "")] = n

        # --- geo lookup ---

        GEO: Dict[str, Tuple[float, float]] = {}
        
        if hasattr(env, "geo_lookup"):
            try:
                GEO = env.geo_lookup() or {}
            except Exception:
                GEO = {}
        else:
            # GUI側に GeoRepository を置く最終形にするなら、ここで差し替える
            GEO = {}

        print("[WORLD-MAP] geo_lookup keys sample:", list(GEO.keys())[:20])
        print("[WORLD-MAP] nodes_all sample:", list(nodes_all.keys())[:20])

        print("hasattr(env, str(data_dir) )", hasattr(env, str(data_dir) ))
        print("hasattr(env, str(cfg) )", hasattr(env, str(cfg) ))

        print("hasattr(env, str(data_dir) )", hasattr(env,"data_dir"))
        print("hasattr(env, str(datva_dir) )", hasattr(env,"cfg"))


        # --- background map ---
        ax.clear()
        ax.set_title("Global Supply Chain Map", fontsize=12)

        used_cartopy = False
        data_crs = None
        try:
            import cartopy.crs as ccrs
            import cartopy.feature as cfeature

            fig = ax.figure
            ax.remove()
            proj_map = ccrs.PlateCarree(central_longitude=180)
            ax = fig.add_subplot(111, projection=proj_map)

            # state / compat
            self.state.ax = ax
            self.ax_network = ax

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

        # --- draw nodes ---
        pos: Dict[str, Tuple[float, float]] = {}
        hub = {"sales_office", "procurement_office", "supply_point"}
        missing_geo = []

        for name, node in nodes_all.items():
            if not name:
                continue
            geo = GEO.get(name)
            if not geo:
                missing_geo.append(name)
                continue
            lat, lon = float(geo[0]), float(geo[1])
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

        if missing_geo:
            print(f"[WORLD-MAP] missing geo for nodes (first 20): {missing_geo[:20]}")

        # --- collect edges ---
        all_edges: set[Tuple[str, str]] = set()
        if env and getattr(env, "prod_tree_dict_OT", None):
            for _prod, _root in env.prod_tree_dict_OT.items():
                for p, c in self._iter_parent_child(_root):
                    all_edges.add((getattr(p, "name", ""), getattr(c, "name", "")))
        if env and getattr(env, "prod_tree_dict_IN", None):
            for _prod, _root in env.prod_tree_dict_IN.items():
                for p, c in self._iter_parent_child(_root):
                    all_edges.add((getattr(p, "name", ""), getattr(c, "name", "")))

        # --- highlight selected product edges ---
        highlight_edges_ot, highlight_edges_in = set(), set()
        selected_names: set[str] = set()

        if self.product_name and env:
            root_ot = getattr(env, "prod_tree_dict_OT", {}).get(self.product_name) if getattr(env, "prod_tree_dict_OT", None) else None
            if root_ot:
                for p, c in self._iter_parent_child(root_ot):
                    highlight_edges_ot.add((getattr(p, "name", ""), getattr(c, "name", "")))
                for n in self._walk_nodes(root_ot):
                    if getattr(n, "name", None):
                        selected_names.add(n.name)

            root_in = getattr(env, "prod_tree_dict_IN", {}).get(self.product_name) if getattr(env, "prod_tree_dict_IN", None) else None
            if root_in:
                for p, c in self._iter_parent_child(root_in):
                    highlight_edges_in.add((getattr(p, "name", ""), getattr(c, "name", "")))
                for n in self._walk_nodes(root_in):
                    if getattr(n, "name", None):
                        selected_names.add(n.name)

        try:
            import cartopy.crs as ccrs
        except Exception:
            ccrs = None

        def _seg(u: str, v: str, color: str, lw: float, arrow: bool = False, z: int = 3):
            if u not in pos or v not in pos:
                return
            x1, y1 = pos[u]
            x2, y2 = pos[v]
            if used_cartopy and ccrs is not None and data_crs is not None:
                ax.plot([x1, x2], [y1, y2], color=color, lw=lw, alpha=0.8, transform=ccrs.Geodetic(), zorder=z)
                if arrow:
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
            _seg(v, u, "seagreen", 2.2, arrow=True, z=5)

        # --- state save ---
        self.state.used_cartopy = used_cartopy
        self.state.data_crs = data_crs
        self.state.pos = pos
        self.state.nodes = nodes_all
        self.state.all_edges = list(all_edges)
        self.state.high_edges = list(highlight_edges_ot | highlight_edges_in)

        # --- connect events ---
        canvas = fig.canvas
        self.state.canvas = canvas

        # disconnect previous
        for cid in list(self.state.cids):
            try:
                canvas.mpl_disconnect(cid)
            except Exception:
                pass
        self.state.cids = []

        self.state.cids.extend([
            canvas.mpl_connect("scroll_event", self._on_map_scroll),
            canvas.mpl_connect("button_press_event", self._on_map_click),
            canvas.mpl_connect("key_press_event", self._on_map_key),
        ])

        # view helpers
        pts = self._collect_geo_points()
        mode = "fit" if getattr(self, "world_map_mode", "global") == "fit" else "global"
        self._apply_world_limits(ax, pts, mode)

        self._install_map_interactions()

        # draw
        try:
            canvas.draw_idle()
        except Exception:
            pass

        # --- Backward-compatible aliases (app.py used these names) ---
        # Keep these in sync with the historical PSIPlannerApp fields.
        self.fig_network = fig
        self.ax_network = ax
        self.canvas_network = canvas

        return self

    # ------------------------------------------------------------------
    # Key / Mouse handlers
    # ------------------------------------------------------------------
    def _on_map_click(self, event):
        """Left click: annotate + highlight nearest node; then notify cockpit via callback."""
        ax = getattr(self.state, "ax", None) if hasattr(self, "state") else getattr(self, "_map_ax", None)
        if ax is None or getattr(event, "inaxes", None) is not ax:
            return

        pair = self._event_lonlat(event)
        if not pair:
            self._clear_map_highlights()
            return
        x, y = pair

        pos = (self.state.pos if hasattr(self, "state") else getattr(self, "_map_pos", None)) or {}
        if not pos:
            return

        used_cartopy = bool(getattr(self.state, "used_cartopy", False)) if hasattr(self, "state") else bool(getattr(self, "_map_used_cartopy", False))
        data_crs = getattr(self.state, "data_crs", None) if hasattr(self, "state") else getattr(self, "_map_data_crs", None)

        if used_cartopy and data_crs is not None:
            xmin, xmax, ymin, ymax = ax.get_extent(crs=data_crs)
        else:
            xmin, xmax = ax.get_xlim()
            ymin, ymax = ax.get_ylim()

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

        node = (self.state.nodes.get(hit) if hasattr(self, "state") else getattr(self, "_map_nodes", {}).get(hit))
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
                info, xy=pos[hit], xytext=(6, 6), textcoords="offset points", fontsize=9,
                bbox=dict(boxstyle="round", fc="w", ec="#333", alpha=0.9),
                transform=data_crs, zorder=10
            )
            ring, = ax.plot([pos[hit][0]], [pos[hit][1]], "o", ms=18, mfc="none", mec="red", mew=2, alpha=0.7, transform=data_crs, zorder=9)
        else:
            anno = ax.annotate(
                info, xy=pos[hit], xytext=(6, 6), textcoords="offset points", fontsize=9,
                bbox=dict(boxstyle="round", fc="w", ec="#333", alpha=0.9),
                zorder=10
            )
            ring, = ax.plot([pos[hit][0]], [pos[hit][1]], "o", ms=18, mfc="none", mec="red", mew=2, alpha=0.7, zorder=9)

        self.state.anno_artist = anno
        self.state.highlight_artists = [ring, anno]

        canvas = getattr(self.state, "canvas", None)
        if canvas is not None:
            try:
                canvas.draw_idle()
            except Exception:
                pass

        # ★ Notify cockpit/app
        cb = getattr(self, "_map_on_select", None)
        if callable(cb):
            cb(hit, source="world_map")

    def _on_map_key(self, event):
        """Key bindings for world map.

        - esc : clear highlight/annotation
        - a   : fit all nodes
        - f   : fit highlighted product edges (OUT/IN)
        - w   : global extent
        """
        if event is None:
            return
        key = getattr(event, "key", None)

        if key == "escape":
            self._clear_map_highlights()
            return

        ax = getattr(self.state, "ax", None) if hasattr(self, "state") else getattr(self, "_map_ax", None)
        if ax is None:
            return

        used_cartopy = bool(getattr(self.state, "used_cartopy", False)) if hasattr(self, "state") else bool(getattr(self, "_map_used_cartopy", False))
        pos = (getattr(self.state, "pos", None) if hasattr(self, "state") else getattr(self, "_map_pos", None)) or {}
        highlight_edges = (getattr(self.state, "high_edges", None) if hasattr(self, "state") else getattr(self, "_map_high_edges", None)) or []

        if key == "a":
            if pos:
                lons = [p[0] for p in pos.values()]
                lats = [p[1] for p in pos.values()]
                self._fit_lonlat(lons, lats, edges=None)

        elif key == "w":
            if used_cartopy:
                try:
                    ax.set_global()
                except Exception:
                    pass
            else:
                ax.set_xlim(-180, 180)
                ax.set_ylim(-90, 90)

        elif key == "f":
            # Fit to nodes that appear in highlighted edges; keep "from-node" bias via edges argument.
            if pos and highlight_edges:
                nodes = set(u for u, v in highlight_edges) | set(v for u, v in highlight_edges)
                lons = [pos[n][0] for n in nodes if n in pos]
                lats = [pos[n][1] for n in nodes if n in pos]
                if lons and lats:
                    self._fit_lonlat(lons, lats, edges=highlight_edges)

        canvas = getattr(self.state, "canvas", None) if hasattr(self, "state") else getattr(self, "_map_canvas", None)
        if canvas is not None:
            try:
                canvas.draw_idle()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Helpers (stubs/ported from app.py as needed)
    # ------------------------------------------------------------------
    def _ensure_network_axes(self, parent=None):
        """Create Matplotlib figure/axes/canvas. (port from app.py or implement minimal)"""
        # NotImplemented OK: あなたの環境に合わせて差し込み
        # ここでは「fig_network/ax_network/canvas_network」を作る前提
        import matplotlib.pyplot as plt

        # 既に存在するなら再利用
        if getattr(self, "ax_network", None) is not None:
            self.state.ax = self.ax_network
            self.state.fig = self.ax_network.figure
            self.state.canvas = self.ax_network.figure.canvas
            return

        fig = plt.figure()
        ax = fig.add_subplot(111)
        canvas = fig.canvas

        self.state.fig = fig
        self.state.ax = ax
        self.state.canvas = canvas

        # compat fields (old app.py naming)
        self.fig_network = fig
        self.ax_network = ax
        self.canvas_network = canvas

    def _walk_nodes(self, root) -> Iterable[Any]:
        """Yield nodes in tree."""
        # TODO: app.py から移植
        if root is None:
            return
        stack = [root]
        seen = set()
        while stack:
            n = stack.pop()
            if n is None or id(n) in seen:
                continue
            seen.add(id(n))
            yield n
            # children
            ch = getattr(n, "children", None) or getattr(n, "child", None)
            if ch:
                if isinstance(ch, (list, tuple)):
                    stack.extend(list(ch))
                else:
                    stack.append(ch)

    def _iter_parent_child(self, root) -> Iterable[Tuple[Any, Any]]:
        """Yield (parent, child) edges in tree."""
        # TODO: app.py から移植
        if root is None:
            return
        stack = [root]
        seen = set()
        while stack:
            p = stack.pop()
            if p is None or id(p) in seen:
                continue
            seen.add(id(p))
            children = getattr(p, "children", None)
            if children:
                for c in children:
                    yield p, c
                    stack.append(c)

    def _collect_geo_points(self) -> List[Tuple[float, float]]:
        """Collect (lon, lat) points for fitting."""
        pos = self.state.pos or {}
        return list(pos.values())

    def _apply_world_limits(self, ax, pts, mode: str):
        """Apply extent (global/fit)."""
        # TODO: app.py のロジックをそのまま移植してOK
        if mode == "global":
            try:
                ax.set_global()
            except Exception:
                ax.set_xlim(-180, 180)
                ax.set_ylim(-90, 90)
            return

        if not pts:
            return
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        padx = max(5.0, (xmax - xmin) * 0.08)
        pady = max(3.0, (ymax - ymin) * 0.10)

        try:
            import cartopy.crs as ccrs
            data_crs = self.state.data_crs or ccrs.PlateCarree()
            ax.set_extent([xmin - padx, xmax + padx, ymin - pady, ymax + pady], crs=data_crs)
        except Exception:
            ax.set_xlim(xmin - padx, xmax + padx)
            ax.set_ylim(ymin - pady, ymax + pady)

    def _install_map_interactions(self):
        """Optional: pan/drag interactions (port if needed)."""
        # TODO: app.py から移植（右ドラッグ pan 等）
        return

    def _event_lonlat(self, event) -> Optional[Tuple[float, float]]:
        """Return (lon, lat) from mouse event, handling cartopy if present."""
        if event is None:
            return None
        # cartopy 使用時でも event.xdata/ydata が lon/lat になるケースが多いので、まずそれを使う
        x = getattr(event, "xdata", None)
        y = getattr(event, "ydata", None)
        if x is None or y is None:
            return None
        return float(x), float(y)

    def _on_map_scroll(self, event):
        # TODO: app.py から移植（ズーム）
        return

    def _clear_map_highlights(self):
        """Remove highlight/annotation artists."""
        for a in list(self.state.highlight_artists or []):
            try:
                a.remove()
            except Exception:
                pass
        self.state.highlight_artists = []
        if self.state.anno_artist is not None:
            try:
                self.state.anno_artist.remove()
            except Exception:
                pass
        self.state.anno_artist = None

        canvas = getattr(self.state, "canvas", None)
        if canvas is not None:
            try:
                canvas.draw_idle()
            except Exception:
                pass

    def _fit_lonlat(self, lons, lats, edges=None):
        """Fit lon/lat extent with optional 'from-node' bias via edges. (port your preferred version here)"""
        # NOTE: あなたの app.py 由来の “水平フォーカス(5%)版” をここに置く想定
        # ここは NotImplemented のままでも雛形としてOKです。
        try:
            import numpy as np
            import cartopy.crs as ccrs
        except Exception:
            return

        ax = getattr(self.state, "ax", None)
        if ax is None or not lons or not lats:
            return

        used_cartopy = bool(getattr(self.state, "used_cartopy", False))
        if not used_cartopy:
            # 非 cartopy の場合は単純 fit
            xmin, xmax = min(lons), max(lons)
            ymin, ymax = min(lats), max(lats)
            padx = max(5.0, (xmax - xmin) * 0.08)
            pady = max(3.0, (ymax - ymin) * 0.10)
            ax.set_xlim(xmin - padx, xmax + padx)
            ax.set_ylim(ymin - pady, ymax + pady)
            return

        # cartopy 版：ここにあなたの “focal_lon を左 5%” の実装を貼る
        # （既に world_map_view.py に実装済みなら、それをそのまま移植）
        return
