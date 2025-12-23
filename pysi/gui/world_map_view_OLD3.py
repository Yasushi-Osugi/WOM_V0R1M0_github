from __future__ import annotations

import os
import csv
from dataclasses import dataclass, field
from typing import Callable, Optional, Any, Dict, Tuple, List, Iterable


# ============================================================
# Geo lookup (CSV) unified resolver
# ============================================================
def _resolve_data_dir(env: Any) -> Optional[str]:
    """
    Resolve data directory from:
      1) env.data_dir
      2) env.cfg.DATA_DIRECTORY
      3) env.cfg.data_dir (fallback)
    """
    if env is None:
        return None

    d = getattr(env, "data_dir", None)
    if isinstance(d, str) and d.strip():
        return d

    cfg = getattr(env, "cfg", None)
    if cfg is not None:
        d2 = getattr(cfg, "DATA_DIRECTORY", None)
        if isinstance(d2, str) and d2.strip():
            return d2
        d3 = getattr(cfg, "data_dir", None)
        if isinstance(d3, str) and d3.strip():
            return d3

    return None


def _geo_lookup_from_csv(env: Any) -> Dict[str, Tuple[float, float]]:
    """
    node_geo.csv から {node_name: (lat, lon)} を返す
    """
    data_dir = _resolve_data_dir(env)
    if not data_dir:
        return {}

    path = os.path.join(data_dir, "node_geo.csv")
    if not os.path.exists(path):
        return {}

    geo: Dict[str, Tuple[float, float]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("node_name") or row.get("name") or "").strip()
            if not name:
                continue
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
            except Exception:
                continue
            geo[name] = (lat, lon)
    return geo


# ============================================================
# State container
# ============================================================
@dataclass
class MapState:
    fig: Any = None
    ax: Any = None
    canvas: Any = None

    used_cartopy: bool = False
    data_crs: Any = None

    pos: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    nodes: Dict[str, Any] = field(default_factory=dict)

    all_edges: List[Tuple[str, str]] = field(default_factory=list)
    high_edges: List[Tuple[str, str]] = field(default_factory=list)

    anno_artist: Any = None
    highlight_artists: List[Any] = field(default_factory=list)

    cids: List[int] = field(default_factory=list)


# ============================================================
# Public entry
# ============================================================
def show_world_map(
    env: Any,
    product_name: Optional[str] = None,
    on_select: Optional[Callable[..., None]] = None,
    parent: Any = None,
) -> "WorldMapView":
    view = WorldMapView(env=env, product_name=product_name, on_select=on_select, parent=parent)
    view.show()
    return view


# ============================================================
# WorldMapView
# ============================================================
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

        self.state = MapState()

        # backward compatible aliases (app.py)
        self.fig_network = None
        self.ax_network = None
        self.canvas_network = None

    # --------------------------------------------------------
    # Main
    # --------------------------------------------------------
    def show(self) -> "WorldMapView":
        self._ensure_network_axes(parent=self.parent)
        ax = self.ax_network
        if ax is None:
            print("[WORLD-MAP] no axes")
            return self
        fig = ax.figure

        # collect nodes
        nodes_all: Dict[str, Any] = {}
        env = self.env
        if env:
            for tree_dict in (
                getattr(env, "prod_tree_dict_OT", None),
                getattr(env, "prod_tree_dict_IN", None),
            ):
                if tree_dict:
                    for _prod, root in tree_dict.items():
                        for n in self._walk_nodes(root):
                            if getattr(n, "name", None):
                                nodes_all[n.name] = n

        # geo lookup (env.geo_lookup -> CSV fallback)
        GEO: Dict[str, Tuple[float, float]] = {}
        if hasattr(env, "geo_lookup"):
            try:
                GEO = env.geo_lookup() or {}
            except Exception:
                GEO = {}
        if not GEO:
            GEO = _geo_lookup_from_csv(env)

        # background
        ax.clear()
        ax.set_title("Global Supply Chain Map", fontsize=12)

        used_cartopy = False
        data_crs = None
        try:
            import cartopy.crs as ccrs
            import cartopy.feature as cfeature

            fig = ax.figure
            ax.remove()
            ax = fig.add_subplot(111, projection=ccrs.PlateCarree(central_longitude=180))
            ax.add_feature(cfeature.OCEAN.with_scale("110m"), facecolor="#e6f2ff")
            ax.add_feature(cfeature.LAND.with_scale("110m"), facecolor="#f6f6f6")
            ax.add_feature(cfeature.COASTLINE.with_scale("110m"), linewidth=0.4)
            ax.add_feature(cfeature.BORDERS.with_scale("110m"), linewidth=0.4)
            ax.set_global()
            used_cartopy = True
            data_crs = ccrs.PlateCarree()
        except Exception:
            ax.set_xlim(-180, 180)
            ax.set_ylim(-90, 90)

        self.ax_network = ax

        # draw nodes
        pos: Dict[str, Tuple[float, float]] = {}
        missing_geo = []
        for name, node in nodes_all.items():
            geo = GEO.get(name)
            if not geo:
                missing_geo.append(name)
                continue
            lat, lon = geo
            pos[name] = (lon, lat)
            ax.plot(lon, lat, "o", ms=6, zorder=3)
            ax.text(lon, lat, f" {name}", fontsize=8, zorder=4)

        if missing_geo:
            print("[WORLD-MAP] missing geo for nodes (first 20):", missing_geo[:20])

        # state
        self.state.used_cartopy = used_cartopy
        self.state.data_crs = data_crs
        self.state.pos = pos
        self.state.nodes = nodes_all

        # events
        canvas = fig.canvas
        self.state.canvas = canvas
        for cid in self.state.cids:
            canvas.mpl_disconnect(cid)
        self.state.cids = [
            canvas.mpl_connect("button_press_event", self._on_map_click),
            canvas.mpl_connect("key_press_event", self._on_map_key),
        ]

        self.fig_network = fig
        self.canvas_network = canvas

        canvas.draw_idle()
        return self

    # --------------------------------------------------------
    # Handlers
    # --------------------------------------------------------
    def _on_map_click(self, event):
        ax = self.ax_network
        if event.inaxes is not ax:
            return

        x, y = event.xdata, event.ydata
        if x is None or y is None:
            return

        hit, best = None, 1e9
        for name, (lon, lat) in self.state.pos.items():
            d = abs(lon - x) + abs(lat - y)
            if d < best:
                hit, best = name, d

        if not hit:
            return

        self._clear_map_highlights()

        anno = ax.annotate(hit, xy=self.state.pos[hit], xytext=(6, 6),
                           textcoords="offset points",
                           bbox=dict(boxstyle="round", fc="w"))
        ring, = ax.plot([self.state.pos[hit][0]], [self.state.pos[hit][1]],
                        "o", ms=18, mfc="none", mec="red")

        self.state.highlight_artists = [ring, anno]
        self.state.anno_artist = anno
        self.state.canvas.draw_idle()

        cb = self._map_on_select
        if callable(cb):
            cb(hit, source="world_map")

    def _on_map_key(self, event):
        if event.key == "escape":
            self._clear_map_highlights()

    # --------------------------------------------------------
    # Helpers
    # --------------------------------------------------------
    def _ensure_network_axes(self, parent=None):
        import matplotlib.pyplot as plt
        if self.ax_network is None:
            fig = plt.figure()
            self.ax_network = fig.add_subplot(111)

    def _walk_nodes(self, root) -> Iterable[Any]:
        if root is None:
            return
        stack = [root]
        seen = set()
        while stack:
            n = stack.pop()
            if id(n) in seen:
                continue
            seen.add(id(n))
            yield n
            for c in getattr(n, "children", []) or []:
                stack.append(c)

    def _clear_map_highlights(self):
        for a in self.state.highlight_artists:
            try:
                a.remove()
            except Exception:
                pass
        self.state.highlight_artists = []
        if self.state.anno_artist:
            try:
                self.state.anno_artist.remove()
            except Exception:
                pass
            self.state.anno_artist = None
        if self.state.canvas:
            self.state.canvas.draw_idle()
