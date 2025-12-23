# pysi/io/psi_state_io.py
from __future__ import annotations

import os
import json
import hashlib
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import pandas as pd

from pysi.network.node_base import Node


# ---------------------------------------------------------------------
# 汎用ユーティリティ
# ---------------------------------------------------------------------

def walk_nodes(root: Optional[Node]) -> Iterable[Node]:
    """root から子孫ノードを DFS でたどる。"""
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


def _parent_map(root: Optional[Node]) -> Dict[str, Optional[str]]:
    """node_name -> parent_name の辞書を作る。"""
    parent = {}
    if not root:
        return parent
    for n in walk_nodes(root):
        for c in getattr(n, "children", []) or []:
            parent[c.name] = n.name
        parent.setdefault(n.name, None)
    return parent


# ---------------------------------------------------------------------
# 1) physical_tree_* の export
# ---------------------------------------------------------------------

def export_physical_tree(
    root_out: Optional[Node],
    root_in: Optional[Node],
    out_path: str,
    in_path: str,
    office_meta: Optional[dict] = None,
) -> None:
    """
    物理系 OUT/IN ツリーを JSON に出力する。
    office_meta は以下のような任意情報:
      {
        "corporate_HQ": "corporate_HQ",
        "sales_office": "sales_office",
        "production_office": "supply_point",
        "procurement_office": "procurement_office",
      }
    """

    def to_payload(root: Optional[Node], bound: str) -> dict:
        parent = _parent_map(root)
        nodes = []
        if root:
            for n in walk_nodes(root):
                tags = list(getattr(n, "tags", []))
                # 予約語ノードのタグ付け（不足していれば追加）
                if n.name == getattr(office_meta or {}, "corporate_HQ", None):
                    if "corporate_HQ" not in tags:
                        tags.append("corporate_HQ")
                if n.name == getattr(office_meta or {}, "sales_office", None):
                    if "sales_office" not in tags:
                        tags.append("sales_office")
                if n.name == getattr(office_meta or {}, "production_office", None):
                    if "production_office" not in tags:
                        tags.append("production_office")
                if n.name == getattr(office_meta or {}, "procurement_office", None):
                    if "procurement_office" not in tags:
                        tags.append("procurement_office")

                nodes.append(
                    {
                        "node_name": n.name,
                        "parent_name": parent.get(n.name),
                        "lat": getattr(n, "lat", None),
                        "lon": getattr(n, "lon", None),
                        "leadtime_days": int(getattr(n, "leadtime", 0)),
                        "ss_days": int(getattr(n, "SS_days", 0)),
                        "long_vacation_weeks": list(
                            getattr(n, "long_vacation_weeks", [])
                        ),
                        "tags": tags,
                    }
                )
        return {
            "schema_version": "psi_physical_tree_v1",
            "bound": bound,
            "nodes": nodes,
        }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(to_payload(root_out, "OUT"), f, ensure_ascii=False, indent=2)
    with open(in_path, "w", encoding="utf-8") as f:
        json.dump(to_payload(root_in, "IN"), f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------
# 2) product_tree_* の export
#    prod_roots_out / prod_roots_in = {product_name: root(Node)}
# ---------------------------------------------------------------------

def export_product_trees(
    prod_roots_out: Dict[str, Optional[Node]],
    prod_roots_in: Dict[str, Optional[Node]],
    out_path: str,
    in_path: str,
) -> None:
    def build_products(roots: Dict[str, Optional[Node]]) -> List[dict]:
        products = []
        for product, root in roots.items():
            if not root:
                continue

            parent = _parent_map(root)

            nodes = []
            for n in walk_nodes(root):
                nodes.append(
                    {
                        "node_name": n.name,
                        "parent_name": parent.get(n.name),
                        "leadtime_days": int(getattr(n, "leadtime", 0)),
                        "ss_days": int(getattr(n, "SS_days", 0)),
                        "long_vacation_weeks": list(
                            getattr(n, "long_vacation_weeks", [])
                        ),
                        "role": getattr(n, "role", None),
                        "pricing": {
                            "offering_price_ASIS": getattr(
                                n, "offering_price_ASIS", None
                            ),
                            "offering_price_TOBE": getattr(
                                n, "offering_price_TOBE", None
                            ),
                        },
                        "costs": {
                            "unit_cost_dm": getattr(n, "unit_cost_dm", None),
                            "unit_cost_tariff": getattr(n, "unit_cost_tariff", None),
                        },
                    }
                )

            edges = []
            for p in walk_nodes(root):
                for c in getattr(p, "children", []) or []:
                    edges.append(
                        {
                            "from_node": p.name,
                            "to_node": c.name,
                            "edge_type": getattr(c, "edge_type", None),
                            "leadtime_days": int(getattr(c, "leadtime", 0)),
                        }
                    )

            products.append(
                {
                    "product_name": product,
                    "root_node_name": root.name,
                    "nodes": nodes,
                    "edges": edges,
                }
            )
        return products

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "schema_version": "psi_plan_tree_v1",
                "bound": "OUT",
                "products": build_products(prod_roots_out),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    with open(in_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "schema_version": "psi_plan_tree_v1",
                "bound": "IN",
                "products": build_products(prod_roots_in),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


# ---------------------------------------------------------------------
# 3) psi_events.parquet の export
#    bucket: "P","CO","S","I"
#    seq   : 週内順序（list index）
# ---------------------------------------------------------------------

BUCKET_CODES = ["P", "CO", "S", "I"]  # ここは実装に合わせて並び替えてOK


def collect_psi_events(
    prod_roots_out: Dict[str, Optional[Node]],
    weeks: int,
    fifo_mode: str = "FIFO",
) -> pd.DataFrame:
    """
    各 product OUTツリーから psi4*** を走査し、
    ロング形式の DataFrame を返す。
    fifo_mode は将来拡張用（今は値をそのまま保持するだけ）。
    """
    records: List[dict] = []

    for product, root in prod_roots_out.items():
        if not root:
            continue

        for node in walk_nodes(root):
            psi = getattr(node, "psi4demand", None)
            if psi is None:
                continue

            for w in range(min(len(psi), weeks)):
                # psi[w][bucket_idx] が list[lot_id]
                for bucket_idx, bucket_code in enumerate(BUCKET_CODES):
                    if bucket_idx >= len(psi[w]):
                        continue
                    lots = psi[w][bucket_idx] or []
                    for seq, lot_id in enumerate(lots):
                        records.append(
                            {
                                "product_name": product,
                                "bound": "OUT",
                                "node_name": node.name,
                                "iso_index": int(w),
                                "bucket": bucket_code,
                                "seq": int(seq),
                                "lot_id": lot_id,
                                "qty": 1.0,  # lot=1単位。必要なら変換テーブルで上書き
                                "fifo_mode": fifo_mode,
                            }
                        )

    return pd.DataFrame.from_records(records)


def export_psi_events_parquet(
    prod_roots_out: Dict[str, Optional[Node]],
    weeks: int,
    path: str,
    fifo_mode: str = "FIFO",
) -> None:
    df = collect_psi_events(prod_roots_out, weeks, fifo_mode=fifo_mode)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)


# ---------------------------------------------------------------------
# 4) parameters.json / metadata.json / state_hash
# ---------------------------------------------------------------------

def write_json(path: str, payload: dict, default_schema: str) -> None:
    p = dict(payload)
    p.setdefault("schema_version", default_schema)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)


def compute_state_hash(base_dir: str) -> str:
    """base_dir 以下の全ファイルから SHA-256 を計算する。"""
    h = hashlib.sha256()
    for root, _, files in os.walk(base_dir):
        for name in sorted(files):
            if name == "state_hash.txt":
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, base_dir).replace("\\", "/")
            h.update(rel.encode("utf-8"))
            with open(full, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    h.update(chunk)
    return "sha256:" + h.hexdigest()


def write_state_hash(base_dir: str, path: str) -> str:
    sh = compute_state_hash(base_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(sh + "\n")
    return sh


# ---------------------------------------------------------------------
# 5) ワンショット: GUI から呼ぶエクスポート関数
# ---------------------------------------------------------------------

def export_psi_state(
    save_dir: str,
    physical_root_out: Optional[Node],
    physical_root_in: Optional[Node],
    prod_roots_out: Dict[str, Optional[Node]],
    prod_roots_in: Dict[str, Optional[Node]],
    weeks: int,
    params: dict,
    meta: dict,
    office_meta: Optional[dict] = None,
    fifo_mode: str = "FIFO",
) -> str:
    """
    save_dir/psi_state/ 以下に PSI_State v1 を書き出し、
    最終的な state_hash を返す。
    """
    base = os.path.join(save_dir, "psi_state")
    os.makedirs(base, exist_ok=True)

    # physical
    export_physical_tree(
        physical_root_out,
        physical_root_in,
        os.path.join(base, "physical_tree_outbound.json"),
        os.path.join(base, "physical_tree_inbound.json"),
        office_meta=office_meta,
    )

    # plan
    export_product_trees(
        prod_roots_out,
        prod_roots_in,
        os.path.join(base, "product_tree_outbound.json"),
        os.path.join(base, "product_tree_inbound.json"),
    )

    # PSI events
    export_psi_events_parquet(
        prod_roots_out,
        weeks,
        os.path.join(base, "psi_events.parquet"),
        fifo_mode=fifo_mode,
    )

    # parameters / metadata
    write_json(os.path.join(base, "parameters.json"), params, "psi_parameters_v1")
    write_json(os.path.join(base, "metadata.json"), meta, "psi_metadata_v1")

    # state_hash
    state_hash = write_state_hash(base, os.path.join(base, "state_hash.txt"))
    return state_hash
