# real_engine_bridge.py
# real_engine_bridge.py（差分）
from typing import Any, Dict, Optional
import os, csv, io, re
from engine_api import PlanNode as EPNode
DATA_DIR = os.environ.get(
    "PSI_DATA_DIR",
    r"C:\Users\ohsug\PySI_V0R8\_data_parameters\data_PySI_V0R8_bridge"
)
def build_plan_graph(scenario_name: str,
                     product: Optional[str] = None,
                     filters: Optional[Dict[str, Any]] = None) -> EPNode:
    ot = _read_rows(os.path.join(DATA_DIR, "product_tree_outbound.csv"))
    it = _read_rows(os.path.join(DATA_DIR, "product_tree_inbound.csv"))
    # SKU集合（両方から）
    sku_all = sorted({(r.get("Product_name") or r.get("Product_n")) for r in (ot+it)})
    sku_sel = [product] if (product and product in sku_all) else sku_all
    super_root = EPNode("ROOT", f"{scenario_name}-ROOT", "root")
    for sku in sku_sel:
        sku_root = EPNode(f"SKU::{sku}", sku, "SKU", sku=sku)
        root_out = _build_tree_for_product(ot, sku, direction="OUT", facet_include=True)
        if root_out: sku_root.add_child(root_out)
        # build_plan_graph 内
        root_in  = _build_tree_for_product(it, sku, direction="IN",  facet_include=True)  # ← True に
        #root_in  = _build_tree_for_product(it, sku, direction="IN",  facet_include=False)  # ← facet除外
        if root_in:  sku_root.add_child(root_in)
        super_root.add_child(sku_root)
    return super_root
# ---- 公開API ---------------------------------------------------------------
def run_core(root: EPNode, horizon_weeks: int, seed: int | None,
             overrides: Dict[str, Any] | None) -> None:
    #"""接続確認用（あとで実エンジンに差し替え）。各ノードにダミーKPIソースを置く。"""
    #def walk(n: EPNode):
    #    n.attrs.setdefault("shipped_qty", 100.0)
    #    n.attrs.setdefault("price", 250.0)
    #    n.attrs.setdefault("cogs", 200.0)
    #    for c in n.children: walk(c)
    #walk(root)
    # 呼ばれたことが分かるように上書き
    def mark(n):
        n.attrs["price"] = 260.0
        n.attrs["shipped_qty"] = 123.0
        for c in n.children: mark(c)
    mark(root)
# ---- ヘルパ ---------------------------------------------------------------
# CSVのエンコーディングを自動判別（utf-8-sig優先→cp932）
def _read_rows(path: str):
    for enc in ("utf-8-sig","cp932","utf-8"):
        try:
            with io.open(path, "r", encoding=enc, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeError:
            continue
    # 最後に失敗したら例外
    with open(path, newline="") as f:
        return list(csv.DictReader(f))
# 列名のマッピング（ヘッダ揺れに強く）
COL = {
    "product": ("Product_name","Product_n"),
    "parent":  ("Parent_node","Parent_no"),
    "child":   ("Child_node","Child_nod"),
    "label":   ("child_node_name","child_node"),
    "lot":     ("lot_size",),
    "lt":      ("leadtime",),
    "flag":    ("PSI_graph_flag",),
    "tariff":  ("customs_tariff_rate",),
    "elas":    ("price_elasticity",),
}
def _g(row, key, default=None):
    for k in COL[key]:
        if k in row and row[k] != "":
            return row[k]
    return default
REGION_PAT = re.compile(r".*[_-]([A-Z]{2,3})$")  # 末尾の _JPN / -JPN 等を抽出
def _guess_region(node_id: str):
    m = REGION_PAT.match(node_id)
    return m.group(1) if m else None
def _guess_type(node_id: str) -> str:
    if node_id.startswith("DAD"): return "DAD"
    if node_id.startswith("WS1"): return "WS1"
    if node_id.startswith("WS2"): return "WS2"
    if node_id.startswith("RT"):  return "RT"
    if node_id.startswith("CS"):  return "CS"
    if node_id == "supply_point": return "root"
    return "node"
def _build_tree_for_product(rows, product_name: str, *,
                            direction: str, facet_include: bool) -> Optional[EPNode]:
    """direction: 'OUT' or 'IN'。INはIDに 'IN::' プレフィックスを付与。"""
    pr = [r for r in rows
          if (_g(r,"product")==product_name)
          and ((_g(r,"flag") or "ON") in ("ON","On","on"))]
    if not pr:
        return None
    nodes: dict[str, EPNode] = {}
    def ensure(nid: str, label: Optional[str]=None) -> EPNode:
        nid_pref = nid if direction=="OUT" else f"IN::{nid}"
        if nid_pref not in nodes:
            attrs = {
                "direction": direction,
                "facet_exclude": (not facet_include),   # ← これでUIの候補から除外
                "legacy_id": nid,                       # 表示用に元IDも保持
            }
            nodes[nid_pref] = EPNode(
                id=nid_pref,
                name=label or nid,
                node_type=_guess_type(nid),
                sku=product_name,
                region=_guess_region(nid),
                channel=("Retail" if nid.startswith("RT") else ("Consumer" if nid.startswith("CS") else None)),
                attrs=attrs
            )
        return nodes[nid_pref]
    for r in pr:
        p = _g(r,"parent"); c = _g(r,"child"); lbl = _g(r,"label") or c
        if not p or not c:
            continue
        parent = ensure(p, p); child = ensure(c, lbl)
        # child側にエッジ属性（簡易）
        try:
            if _g(r,"lot"): child.attrs["lot_size"] = int(float(_g(r,"lot")))
            if _g(r,"lt"):  child.attrs["lead_time_days"] = int(float(_g(r,"lt")))
        except Exception:
            pass
        if _g(r,"tariff"): child.attrs["tariff_rate"] = float(_g(r,"tariff"))
        if _g(r,"elas"):   child.attrs["price_elasticity"] = float(_g(r,"elas"))
        parent.add_child(child)
    # ルート推定
    children = {_g(r,"child") for r in pr}
    parents  = {_g(r,"parent") for r in pr}
    roots = [nid for nid in parents if nid and nid not in children]
    root_raw = roots[0] if roots else ("supply_point" if "supply_point" in {**{_g(r,'parent'):1 for r in pr}, **{_g(r,'child'):1 for r in pr}} else next(iter(nodes)))
    root_id = root_raw if direction=="OUT" else f"IN::{root_raw}"
    nodes[root_id].node_type = "root"
    return nodes[root_id]
#@250811 ADD
# 1) 既存ノード→EPNode写像時に“元ノード”を保持
def _map_to_plan_node(n) -> EPNode:
    pn = EPNode(
        id=getattr(n,"id",getattr(n,"name","unknown")),
        name=getattr(n,"name",getattr(n,"id","node")),
        node_type=getattr(n,"node_type","node"),
        sku=getattr(n,"sku",None),
        region=getattr(n,"region",None),
        channel=getattr(n,"channel",None),
        attrs={}
    )
    pn.attrs["_legacy"] = n  # ← これだけ追加
    for c in getattr(n, "children", []):
        pn.add_child(_map_to_plan_node(c))
    return pn
## 2) 実行（まずは実エンジン呼び出し→なければ簡易サマリ）
#def run_core(root: EPNode, horizon_weeks: int, seed: int | None,
#             overrides: Dict[str, Any] | None) -> None:
#    try:
#        # 例：あなたの実関数に合わせて import/引数名を調整
#        from psi_core.engine import run_weekly
#        legacy_root = root.attrs.get("_legacy") or _find_legacy(root)
#        if legacy_root is not None:
#            run_weekly(legacy_root, horizon=horizon_weeks, seed=seed, overrides=overrides or {})
#            _pull_back_kpis(legacy_root, root)  # psi4*→attrs へ転記
#            return
#    except Exception as e:
#        print("[bridge] real engine call failed, fallback:", e)
#    _smoke(root)  # ← 既存のダミーにフォールバック
def _find_legacy(n: EPNode):
    if "_legacy" in n.attrs: return n.attrs["_legacy"]
    for c in n.children:
        r = _find_legacy(c)
        if r is not None: return r
    return None
def _pull_back_kpis(legacy_node, ep_node: EPNode):
    """最小版：psi4demand/psi4supply の lot 数で shipped_qty を作る（精緻化は後段）"""
    lots_out = getattr(legacy_node, "psi4demand", None)
    lots_in  = getattr(legacy_node, "psi4supply", None)
    def _count(L):
        try:    return sum(len(L[w][0]) for w in range(1, len(L)))  # 週×レーン0 仮
        except: return 0
    ep_node.attrs["shipped_qty"] = float((_count(lots_out) + _count(lots_in)) / 2.0)
    # 価格/原価は当面デフォルト（後で resolve(price/cogs) に置換）
    ep_node.attrs.setdefault("price", 250.0)
    ep_node.attrs.setdefault("cogs", 200.0)
    # 子へ
    for lc, ec in zip(getattr(legacy_node, "children", []), ep_node.children):
        _pull_back_kpis(lc, ec)
