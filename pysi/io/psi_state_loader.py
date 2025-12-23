# pysi/io/psi_state_loader.py
from __future__ import annotations

import os
import json
from dataclasses import dataclass
from typing import Dict, Optional, List, Tuple, Iterable

import pandas as pd

from pysi.network.node_base import Node

# PlanNode が別クラスなら使う。無ければ Node を流用
try:
    from pysi.network.plan_node import PlanNode
except ImportError:  # CSV版など
    PlanNode = Node   # type: ignore


BUCKET_IDX = {"S": 0, "CO": 1, "I": 2, "P": 3}


# ---------------------------------------------------------
# 共通ユーティリティ
# ---------------------------------------------------------

def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _safe_exists(path: str) -> bool:
    return os.path.isfile(path)


def _walk_nodes(root: Optional[Node]) -> Iterable[Node]:
    if not root:
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


# ---------------------------------------------------------
# 物理ツリー（physical_tree_*.json）ローダー
# ---------------------------------------------------------

def _build_physical_tree(payload: dict) -> Optional[Node]:
    """
    physical_tree_outbound.json / inbound.json から Node ツリーを復元。
    payload 形式:
    {
      "schema_version": "psi_physical_tree_v1",
      "bound": "OUT" or "IN",
      "nodes": [
        {
          "node_name": ...,
          "parent_name": ... or null,
          "lat": ...,
          "lon": ...,
          "leadtime_days": int,
          "ss_days": int,
          "long_vacation_weeks": [...],
          "tags": [...],
          "office_role": "corporate_HQ" | "sales_office" | ...
        },
        ...
      ]
    }
    """
    nodes_def = payload.get("nodes") or []
    if not nodes_def:
        return None

    # 1) Node インスタンス生成
    nodes: Dict[str, Node] = {}
    for rec in nodes_def:
        nm = rec["node_name"]
        n = nodes.get(nm)
        if n is None:
            n = Node(nm)
            nodes[nm] = n

        # 属性設定
        n.lat = rec.get("lat", None)
        n.lon = rec.get("lon", None)
        n.leadtime = int(rec.get("leadtime_days", 0) or 0)
        n.SS_days = int(rec.get("ss_days", 0) or 0)
        n.long_vacation_weeks = list(rec.get("long_vacation_weeks") or [])
        tags = list(rec.get("tags") or [])
        if tags:
            n.tags = tags
        office_role = rec.get("office_role")
        if office_role:
            n.office_role = office_role

    # 2) 親子リンク
    root_candidates = set(nodes.keys())
    for rec in nodes_def:
        nm = rec["node_name"]
        parent_nm = rec.get("parent_name")
        if parent_nm:
            parent = nodes.get(parent_nm)
            child = nodes.get(nm)
            if parent and child:
                parent.add_child(child)
                if child.name in root_candidates:
                    root_candidates.remove(child.name)

    # 3) ルート決定
    root: Optional[Node] = None
    if "supply_point" in nodes:
        root = nodes["supply_point"]
    elif root_candidates:
        root = nodes[sorted(root_candidates)[0]]
    else:
        root = next(iter(nodes.values()))
    return root


def load_physical_trees(base_dir: str) -> Tuple[Optional[Node], Optional[Node]]:
    """
    base_dir/psi_state/ から physical_tree_outbound/inbound を読み込む。
    """
    psi_dir = os.path.join(base_dir, "psi_state")
    out_path = os.path.join(psi_dir, "physical_tree_outbound.json")
    in_path = os.path.join(psi_dir, "physical_tree_inbound.json")

    root_out = _build_physical_tree(_load_json(out_path)) if _safe_exists(out_path) else None
    root_in  = _build_physical_tree(_load_json(in_path))  if _safe_exists(in_path) else None

    return root_out, root_in


# ---------------------------------------------------------
# 計画ツリー（product_tree_*.json）ローダー
# ---------------------------------------------------------

def _build_product_roots(payload: dict) -> Dict[str, PlanNode]:
    """
    product_tree_outbound.json / inbound.json から
    product_name -> PlanNode(root) 辞書を復元。
    payload 形式:
    {
      "schema_version": "psi_plan_tree_v1",
      "bound": "OUT" or "IN",
      "products": [
        {
          "product_name": "...",
          "root_node_name": "supply_point",
          "nodes": [
            {
              "node_name": "...",
              "leadtime_days": ...,
              "ss_days": ...,
              "long_vacation_weeks": [...],
              "role": "MOM" | "DAD" | "LEAF" | ...,
              "parent_name": "...",
              "pricing": {...},
              "costs": {...}
            },
            ...
          ],
          "edges": [
            { "from_node": "...", "to_node": "...", "edge_type": "...", "leadtime_days": ... },
            ...
          ]
        },
        ...
      ]
    }
    """
    products_payload = payload.get("products") or []
    result: Dict[str, PlanNode] = {}

    for p in products_payload:
        product_name = p["product_name"]
        nodes_def = p.get("nodes") or []
        edges_def = p.get("edges") or []

        # 1) PlanNode インスタンス生成
        nodes: Dict[str, PlanNode] = {}
        for rec in nodes_def:
            nm = rec["node_name"]
            n = nodes.get(nm)
            if n is None:
                n = PlanNode(nm)
                nodes[nm] = n

            n.leadtime = int(rec.get("leadtime_days", 0) or 0)
            n.SS_days  = int(rec.get("ss_days", 0) or 0)
            n.long_vacation_weeks = list(rec.get("long_vacation_weeks") or [])

            role = rec.get("role")
            if role:
                n.role = role

            # pricing
            pricing = rec.get("pricing") or {}
            n.offering_price_ASIS = pricing.get("offering_price_ASIS")
            n.offering_price_TOBE = pricing.get("offering_price_TOBE")

            # costs（あれば）
            costs = rec.get("costs") or {}
            n.unit_cost_dm    = costs.get("unit_cost_dm")
            n.unit_cost_tariff = costs.get("unit_cost_tariff")

            # office_role があれば拾う（計画ツリー側にも持たせられる）
            if "office_role" in rec:
                n.office_role = rec["office_role"]

        # 2) edges で親子リンク（parent_name ではなく edges を信頼）
        for e in edges_def:
            frm = e["from_node"]
            to  = e["to_node"]
            parent = nodes.get(frm)
            child  = nodes.get(to)
            if not parent or not child:
                continue
            parent.add_child(child)

        # 3) root 決定
        root_name = p.get("root_node_name")
        root = None
        if root_name and root_name in nodes:
            root = nodes[root_name]
        else:
            # 入次数0ノードを root 候補に
            indeg = {nm: 0 for nm in nodes.keys()}
            for parent in nodes.values():
                for child in getattr(parent, "children", []) or []:
                    indeg[child.name] = indeg.get(child.name, 0) + 1
            zero = [nm for nm, d in indeg.items() if d == 0]
            root = nodes[zero[0]] if zero else next(iter(nodes.values()))

        result[product_name] = root

    return result


def load_product_trees(base_dir: str) -> Tuple[Dict[str, PlanNode], Dict[str, PlanNode]]:
    """
    base_dir/psi_state/ から product_tree_outbound/inbound を読み込む。
    戻り値:
      (prod_tree_dict_OT, prod_tree_dict_IN)
    """
    psi_dir = os.path.join(base_dir, "psi_state")
    out_path = os.path.join(psi_dir, "product_tree_outbound.json")
    in_path  = os.path.join(psi_dir, "product_tree_inbound.json")

    prod_ot: Dict[str, PlanNode] = {}
    prod_in: Dict[str, PlanNode] = {}

    if _safe_exists(out_path):
        prod_ot = _build_product_roots(_load_json(out_path))
    if _safe_exists(in_path):
        prod_in = _build_product_roots(_load_json(in_path))

    return prod_ot, prod_in


# ---------------------------------------------------------
# psi_events.parquet → Node.psi4demand の再構築
# ---------------------------------------------------------

def _build_name_map_per_product(prod_tree_dict: Dict[str, PlanNode]) -> Dict[str, Dict[str, PlanNode]]:
    """
    product_name -> { node_name -> PlanNode } の辞書を一気に作る。
    """
    result: Dict[str, Dict[str, PlanNode]] = {}
    for prod, root in prod_tree_dict.items():
        name2node: Dict[str, PlanNode] = {}
        for n in _walk_nodes(root):
            name2node[n.name] = n
        result[prod] = name2node
    return result


def attach_psi_events_from_parquet(
    base_dir: str,
    prod_tree_dict_OT: Dict[str, PlanNode],
    weeks_hint: Optional[int] = None,
    logger=None,
) -> Optional[pd.DataFrame]:
    """
    psi_state/psi_events.parquet を読み込み、
    OUT側 product ツリーに psi4demand[w][bucket_idx] を復元する。

    ※ inbound 側にも付与したければ、必要に応じて拡張可能。
    """
    psi_dir = os.path.join(base_dir, "psi_state")
    path = os.path.join(psi_dir, "psi_events.parquet")
    if not _safe_exists(path):
        if logger:
            logger.warning("[psi_state_loader] psi_events.parquet not found; PSI attach skipped")
        return None

    df = pd.read_parquet(path)

    if df.empty:
        if logger:
            logger.info("[psi_state_loader] psi_events.parquet is empty; PSI attach skipped")
        return df

    # 最小必須列チェック
    required_cols = {"product_name", "node_name", "iso_index", "bucket", "lot_id"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"psi_events.parquet is missing columns: {missing}")

    # 週数決定
    max_week = int(df["iso_index"].max()) + 1
    weeks = weeks_hint if weeks_hint and weeks_hint > max_week else max_week

    # product -> node_name -> PlanNode
    name_map = _build_name_map_per_product(prod_tree_dict_OT)

    # まず全ノードの psi4demand を初期化
    for prod, root in prod_tree_dict_OT.items():
        if not root:
            continue
        for n in _walk_nodes(root):
            n.psi4demand = [[[] for _ in range(4)] for __ in range(weeks)]

    # イベントを流し込む
    # CO/FIFO順位を表す seq 列などがあれば、あとで使えるようにそのまま残す。
    for rec in df.itertuples(index=False):
        prod = getattr(rec, "product_name")
        node_nm = getattr(rec, "node_name")
        w = int(getattr(rec, "iso_index"))
        bucket_code = str(getattr(rec, "bucket") or "S").upper()
        lot_id = getattr(rec, "lot_id")
        qty = getattr(rec, "qty", 1.0)

        nm2node = name_map.get(prod)
        if not nm2node:
            continue
        node = nm2node.get(node_nm)
        if not node:
            continue
        if not (0 <= w < weeks):
            continue

        idx = BUCKET_IDX.get(bucket_code)
        if idx is None:
            continue

        # 今は lot_id をそのまま push（qty は別途集計用に使う想定）
        node.psi4demand[w][idx].append(lot_id)

        # 将来: seq や FIFO/LIFO制御したければ、ここで順序を意識

    if logger:
        logger.info(f"[psi_state_loader] PSI events attached for {len(prod_tree_dict_OT)} products, weeks={weeks}")

    return df


# ---------------------------------------------------------
# parameters.json / metadata.json / state_hash.txt
# ---------------------------------------------------------

def load_parameters(base_dir: str) -> dict:
    psi_dir = os.path.join(base_dir, "psi_state")
    path = os.path.join(psi_dir, "parameters.json")
    return _load_json(path) if _safe_exists(path) else {}


def load_metadata(base_dir: str) -> dict:
    psi_dir = os.path.join(base_dir, "psi_state")
    path = os.path.join(psi_dir, "metadata.json")
    return _load_json(path) if _safe_exists(path) else {}


def load_state_hash(base_dir: str) -> Optional[str]:
    psi_dir = os.path.join(base_dir, "psi_state")
    path = os.path.join(psi_dir, "state_hash.txt")
    if not _safe_exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        line = f.readline().strip()
    return line or None


def verify_state_hash(base_dir: str, logger=None) -> Tuple[Optional[str], Optional[str]]:
    """
    state_hash.txt と 実計算値を比較する。
    戻り値: (stored_hash, computed_hash)
    """
    stored = load_state_hash(base_dir)

    try:
        # 保存側の compute_state_hash を再利用
        from pysi.io.psi_state_io import compute_state_hash
    except Exception:
        if logger:
            logger.warning("[psi_state_loader] compute_state_hash not available; skip verification")
        return stored, None

    psi_dir = os.path.join(base_dir, "psi_state")
    computed = compute_state_hash(psi_dir)

    if logger:
        if stored and computed and stored != computed:
            logger.warning(f"[psi_state_loader] state_hash mismatch: stored={stored}, computed={computed}")
        elif stored and computed:
            logger.info(f"[psi_state_loader] state_hash verified: {stored}")

    return stored, computed


# ---------------------------------------------------------
# PSI State 全体をまとめるデータクラス
# ---------------------------------------------------------

@dataclass
class PsiState:
    base_dir: str
    physical_root_out: Optional[Node]
    physical_root_in: Optional[Node]
    prod_tree_dict_OT: Dict[str, PlanNode]
    prod_tree_dict_IN: Dict[str, PlanNode]
    parameters: dict
    metadata: dict
    state_hash: Optional[str] = None
    psi_events_df: Optional[pd.DataFrame] = None

    @property
    def product_name_list(self) -> List[str]:
        return sorted(self.prod_tree_dict_OT.keys())


def load_psi_state(base_dir: str, attach_psi: bool = True, logger=None) -> PsiState:
    """
    psi_state ディレクトリ一式から PsiState を組み立てるメイン関数。
    """
    # 1) 物理ツリー
    physical_out, physical_in = load_physical_trees(base_dir)

    # 2) 計画ツリー（multi-product）
    prod_ot, prod_in = load_product_trees(base_dir)

    # 3) parameters / metadata / hash
    params = load_parameters(base_dir)
    meta = load_metadata(base_dir)
    st_hash = load_state_hash(base_dir)

    # 4) PSI events（必要なら付与）
    df = None
    if attach_psi and prod_ot:
        df = attach_psi_events_from_parquet(base_dir, prod_ot, weeks_hint=params.get("calendar", {}).get("weeks"), logger=logger)

    state = PsiState(
        base_dir=base_dir,
        physical_root_out=physical_out,
        physical_root_in=physical_in,
        prod_tree_dict_OT=prod_ot,
        prod_tree_dict_IN=prod_in,
        parameters=params,
        metadata=meta,
        state_hash=st_hash,
        psi_events_df=df,
    )

    # 5) 任意: state_hash 検証（ここでは必須にしない）
    verify_state_hash(base_dir, logger=logger)

    if logger:
        logger.info(
            f"[psi_state_loader] loaded psi_state: "
            f"{len(state.product_name_list)} products, "
            f"physical_out={'yes' if physical_out else 'no'}, "
            f"physical_in={'yes' if physical_in else 'no'}"
        )

    return state


# ---------------------------------------------------------
# PlanEnv 互換オブジェクト（pipeline 用）
# ---------------------------------------------------------

@dataclass
class PsiStatePlanEnv:
    """
    SqlPlanEnv の最小互換:
      - product_name_list
      - prod_tree_dict_OT
      - prod_tree_dict_IN
      - get_roots(product_name)
    """
    psi_state: PsiState

    def __post_init__(self):
        self.product_name_list: List[str] = self.psi_state.product_name_list
        self.prod_tree_dict_OT: Dict[str, PlanNode] = self.psi_state.prod_tree_dict_OT
        self.prod_tree_dict_IN: Dict[str, PlanNode] = self.psi_state.prod_tree_dict_IN

    def get_roots(self, product_name: str) -> Tuple[Optional[PlanNode], Optional[PlanNode]]:
        r_ot = self.prod_tree_dict_OT.get(product_name)
        r_in = self.prod_tree_dict_IN.get(product_name, None)
        # IN が無ければ OUT をフォールバックで返す
        if r_in is None:
            r_in = r_ot
        return r_ot, r_in

    def reload(self):
        """
        SqlPlanEnv とのインターフェース合わせ用ダミー。
        psi_state からの PlanEnv では reload は意味を持たないので no-op。
        """
        return
