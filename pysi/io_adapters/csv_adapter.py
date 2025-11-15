# pysi/io_adapters/csv_adapter.py

from __future__ import annotations
from typing import Dict, Any, Optional
import pandas as pd
from pathlib import Path

import numpy as np
import networkx as nx

STANDARD = {
    "products": ("product_id", "name"),
    "nodes": ("node_id", "name", "role"),
    "edges": ("src", "dst", "product_id", "capacity", "cost"),
    "demand": ("week_idx", "product_id", "node_id", "qty"),
}

def _rename_to_standard(df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
    # mapping: {standard: actual} を逆転して rename
    inv = {v: k for k, v in mapping.items()}
    return df.rename(columns=inv)

class CSVAdapter:
    """
    設定駆動のCSVアダプタ。
    - root: CSVルートパス
    - schema_cfg:
        tables: {logical -> filename.csv}
        columns:{logical -> {standard_name: actual_name}}
    """
    def __init__(self, root: str, schema_cfg: Optional[Dict[str, Any]] = None, logger=None):
        self.root = Path(root)
        self.schema_cfg = schema_cfg or {}

        self.tables = self.schema_cfg.get("tables", {})   # 例: {"products": "products.csv", ...}
        self.columns = self.schema_cfg.get("columns", {}) # 例: {"products": {"product_id":"prod_id", ...}}

        self.logger = logger

        self._demand_map = {}  # ← 保持

    #@251015 ADD # run_one_step() は後で PSI 更新に差し替えます（今は雛形のままでOK）
    def build_tree_OLD2(self, raw):
        g = nx.DiGraph()
        for _, r in raw["nodes"].iterrows():
            g.add_node(r["node_id"], name=r.get("name"), role=r.get("role"))
        for _, r in raw["edges"].iterrows():
            g.add_edge(r["src"], r["dst"],
                       product_id=r["product_id"],
                       capacity=float(r.get("capacity", np.inf)),
                       cost=float(r.get("cost", 0.0)))
        return {"graph": g}

    def build_initial_demand_OLD2(self, raw, params):
        dem = raw["demand"].copy()
        H = int(dem["week_idx"].max()) + 1 if not dem.empty else 0
        demand_map = {}
        for (node, prod), grp in dem.groupby(["node_id", "product_id"]):
            arr = np.zeros(H, dtype=float)
            for _, r in grp.iterrows():
                arr[int(r["week_idx"])] += float(r["qty"])
            demand_map[(node, prod)] = arr
        return dict(horizon=H, series=demand_map)

    def to_series_df_OLD(self, result, horizon: int = 0):
        H = int(horizon or 0)
        if H <= 0:
            H = 3
        return pd.DataFrame({
            "week_idx": list(range(H)),
            "inventory": [max(0, 10 - i) for i in range(H)],  # ダミー在庫
        })

    def _read_csv_logical(self, logical: str, default_file: str) -> pd.DataFrame:
        file = self.tables.get(logical, default_file)
        path = self.root / file
        df = pd.read_csv(path) if path.exists() else pd.DataFrame()
        if logical in self.columns and not df.empty:
            df = _rename_to_standard(df, self.columns[logical])
        return df

    def load_all(self, spec: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        products = self._read_csv_logical("products", "products.csv")
        nodes    = self._read_csv_logical("nodes",    "nodes.csv")
        edges    = self._read_csv_logical("edges",    "edges.csv")
        demand   = self._read_csv_logical("demand",   "demand.csv")
        return dict(products=products, nodes=nodes, edges=edges, demand=demand)

    # ↓ 以下は“器”。あなたの実装に差し替え予定
    def build_tree_OLD(self, raw: Dict[str, pd.DataFrame]):
        return {"graph": "placeholder", "raw": raw}

    def derive_params(self, raw: Dict[str, pd.DataFrame]):
        return {"capacity": {}, "lt": {}, "ss": {}, "meta": {"source": "csv"}}

    def build_initial_demand_OLD(self, raw, params):
        return {}

    def collect_result_OLD(self, root, params):
        return {"psi": [], "psi_df": pd.DataFrame(), "kpis": {"fill_rate": 1.0, "note": "csv"}}

    def export_csv_OLD(self, result, out_dir="out", **kwargs):
        p = Path(out_dir); p.mkdir(parents=True, exist_ok=True)
        (p / "kpi.txt").write_text(str(result.get("kpis", {})))

    def build_initial_demand(self, raw, params):
        """
        demand.csv → {(node_id, product_id): {week_idx: qty}} に変換
        """
        dem = {}
        df = raw.get("demand")
        if df is None or df.empty:
            self._demand_map = {}
            return {}
        for _, r in df.iterrows():
            node = str(r["node_id"]); prod = str(r["product_id"])
            week = int(r["week_idx"]); qty = float(r["qty"])
            dem.setdefault((node, prod), {})
            dem[(node, prod)][week] = dem[(node, prod)].get(week, 0.0) + qty
        self._demand_map = dem
        return dem



    def collect_result_OLD2(self, root, params):
        inv = {}
        if isinstance(root, dict):
            inv = root.get("state", {}).get("inventory", {})
        end_inventory = float(sum(inv.values())) if inv else 0.0
        # 既存KPIに end_inventory を追加
        return {
            "psi": [],
            "kpis": {"fill_rate": 1.0, "note": "csv", "end_inventory": end_inventory},
        }

    def collect_result_OLD3(self, root, params):
        """
        - root をそのまま結果に入れて、下流（exporter / to_series_df）が履歴や在庫へアクセスできるようにする
        - demand_total_series を _demand_map から合成して返す（週次の需要合計）
        - 既存の KPI は維持しつつ、end_inventory を追加
        """
        # 在庫合計（終値）
        inv = {}
        if isinstance(root, dict):
            inv = root.get("state", {}).get("inventory", {})
        end_inventory = float(sum(inv.values())) if inv else 0.0

        # 週次需要の合計（demand_total_series）
        H = 0
        if getattr(self, "_demand_map", None):
            try:
                H = max((max(by_week.keys()) for by_week in self._demand_map.values()), default=-1) + 1
            except ValueError:
                H = 0
        demand_total_series = [0.0] * H
        for _, by_week in (self._demand_map or {}).items():
            for w, q in by_week.items():
                if 0 <= w < H:
                    demand_total_series[w] += float(q)

        return {
            "psi": [],
            "kpis": {"fill_rate": 1.0, "note": "csv", "end_inventory": end_inventory},
            "root": root,
            "demand_total_series": demand_total_series,  # ← ここがポイント
            # 既に他所で psi_df を作る場合は、pipeline 側で上書き/追加されます
        }

    def collect_result_OLD4(self, root, params):
        """
        - root をそのまま結果に入れて、下流（exporter / to_series_df）が履歴や在庫へアクセスできるようにする
        - demand_total_series を _demand_map から合成して返す（週次の需要合計）
        - 既存の KPI は維持しつつ、end_inventory を追加
        """
        # 在庫合計（終値）
        inv = {}
        if isinstance(root, dict):
            inv = root.get("state", {}).get("inventory", {})
        end_inventory = float(sum(inv.values())) if inv else 0.0

        # 週次需要の合計（demand_total_series）
        H = 0
        if getattr(self, "_demand_map", None):
            try:
                H = max((max(by_week.keys()) for by_week in self._demand_map.values()), default=-1) + 1
            except ValueError:
                H = 0
        demand_total_series = [0.0] * H
        for _, by_week in (self._demand_map or {}).items():
            for w, q in by_week.items():
                if 0 <= w < H:
                    demand_total_series[w] += float(q)

        return {
            "psi": [],
            "kpis": {"fill_rate": 1.0, "note": "csv", "end_inventory": end_inventory},
            "root": root,
            "demand_total_series": demand_total_series,  # ← ここがポイント
        }

    def collect_result(self, root, params):
        """
        - root をそのまま返して、下流（exporter / to_series_df）が履歴や在庫へアクセスできるようにする
        - demand_total_series を _demand_map から合成して返す（週次の需要合計）
        - 既存の KPI は維持しつつ、end_inventory を追加
        """
        # 在庫合計（終値）
        inv = {}
        if isinstance(root, dict):
            inv = root.get("state", {}).get("inventory", {})
        end_inventory = float(sum(inv.values())) if inv else 0.0

        # 週次需要の合計（demand_total_series）
        H = 0
        if getattr(self, "_demand_map", None):
            try:
                H = max((max(by_week.keys()) for by_week in self._demand_map.values()), default=-1) + 1
            except ValueError:
                H = 0
        demand_total_series = [0.0] * H
        for _, by_week in (self._demand_map or {}).items():
            for w, q in by_week.items():
                if 0 <= w < H:
                    demand_total_series[w] += float(q)

        result = {
            "psi": [],
            "kpis": {"fill_rate": 1.0, "note": "csv", "end_inventory": end_inventory},
            "root": root,
            "demand_total_series": demand_total_series,
        }

        # 旧API互換: もしどこかで psi_df を参照していれば、そのまま残す（あれば）
        existing_psi_df = root.get("state", {}).get("psi_df") if isinstance(root, dict) else None
        if existing_psi_df is not None:
            result["psi_df"] = existing_psi_df

        return result


    def to_series_df(self, result, horizon: int = 0):
        """
        優先順位：
        1) result["root"]["state"]["hist"] に weekごとの在庫履歴があれば、それを最優先で使う
        2) 無ければ _demand_map（需要合計）からダミー在庫を再計算（従来のフォールバック）

        どちらの場合も、horizon が与えられていれば、その長さにパディングorトリムする。
        """
        import pandas as pd

        # ---------- 1) 履歴優先 ----------
        hist = None
        try:
            hist = (result or {}).get("root", {}).get("state", {}).get("hist")
        except Exception:
            hist = None

        if hist:
            df = pd.DataFrame(hist)  # 期待キー: "week" or "week_idx", "inventory", あれば "avg_urgency"
            # week カラム名の揺れを吸収
            if "week_idx" in df.columns:
                pass
            elif "week" in df.columns:
                df = df.rename(columns={"week": "week_idx"})
            else:
                # フォールバック（長さから連番を振る）
                df["week_idx"] = range(len(df))

            # demand_total は result から与えられたものを優先
            dem = (result or {}).get("demand_total_series", None)

            # horizon で長さを調整
            if horizon and horizon > 0:
                idx = pd.Index(range(int(horizon)), name="week_idx")
                df = df.set_index("week_idx").reindex(idx).reset_index()

                # inventory 欠損は前方埋め→ゼロ埋め
                if "inventory" in df.columns:

                    #df["inventory"] = df["inventory"].fillna(method="ffill").fillna(0.0)
                    df["inventory"] = df["inventory"].ffill().fillna(0.0)

                else:
                    df["inventory"] = 0.0
                # demand_total_series も同様に調整
                if isinstance(dem, list):
                    dem = (dem + [0.0] * horizon)[:horizon]

            # demand_total 欄を確定
            if isinstance(dem, list) and len(dem) == len(df):
                df["demand_total"] = dem
            else:
                df["demand_total"] = 0.0

            # ★ 追加：avg_urgency 列（無ければ None のままでもOK。必要なら fillna(0.0) に変更可）
            if "avg_urgency" not in df.columns:
                df["avg_urgency"] = None

            return df[["week_idx", "demand_total", "inventory", "avg_urgency"]]

        # ---------- 2) フォールバック（従来ロジック） ----------
        H = int(horizon or 0)
        if H <= 0:
            if getattr(self, "_demand_map", None):
                try:
                    H = max((max(by_week.keys()) for by_week in self._demand_map.values()), default=-1) + 1
                except ValueError:
                    H = 0
            if H <= 0:
                H = 3

        demand_total = [0.0] * H
        for _, by_week in (self._demand_map or {}).items():
            for w, q in by_week.items():
                if 0 <= w < H:
                    demand_total[w] += float(q)

        init_inv = 100.0
        inv = []
        cum = 0.0
        for w in range(H):
            cum += demand_total[w]
            inv.append(max(0.0, init_inv - cum))

        # フォールバック時は avg_urgency は出せないので None
        return pd.DataFrame({
            "week_idx": list(range(H)),
            "demand_total": demand_total,
            "inventory": inv,
            "avg_urgency": [None] * H,
        })

    def export_csv(self, result, out_dir="out", **kwargs):
        p = Path(out_dir); p.mkdir(parents=True, exist_ok=True)
        (p / "kpi.txt").write_text(str(result.get("kpis", {})))

    def build_tree_OLD(self, raw):
        G = nx.DiGraph()
        for _, r in raw["nodes"].iterrows():
            G.add_node(str(r["node_id"]), role=str(r.get("role", "")))
        for _, r in raw["edges"].iterrows():
            G.add_edge(str(r["src"]), str(r["dst"]),
                    product=str(r["product_id"]),
                    capacity=float(r.get("capacity", 0) or 0.0),
                    cost=float(r.get("cost", 0) or 0.0))
        # 初期在庫（全ノード同値でOK、後で拡張）
        state = {"inventory": {n: 100.0 for n in G.nodes}}
        return {"graph": G, "state": state, "raw": raw}

    # ← ここを置き換え
    def build_tree(self, raw):
        """
        edges.csv をもとに有向グラフを構築し、葉ノード集合と初期在庫をセット。
        戻り値: {"graph": nx.DiGraph, "state": {"inventory": dict, "leafs": set}, "raw": raw}
        """
        edges = raw.get("edges", pd.DataFrame())
        nodes_df = raw.get("nodes", pd.DataFrame())

        G = nx.DiGraph()

        # 1) ノードを追加（nodes.csv があれば優先、なければ edges から推定）
        if not nodes_df.empty and "node_id" in nodes_df.columns:
            # 任意の属性（name, role 等）があれば付与
            for _, r in nodes_df.iterrows():
                attrs = {c: r[c] for c in nodes_df.columns if c != "node_id"}
                G.add_node(str(r["node_id"]), **attrs)
        else:
            # edges から src/dst のユニーク集合をノードに
            if not edges.empty:
                node_ids = pd.unique(pd.concat([edges["src"], edges["dst"]], ignore_index=True))
                for nid in node_ids:
                    G.add_node(str(nid))

        # 2) エッジを追加（属性：product, capacity, cost）
        if not edges.empty:
            for _, r in edges.iterrows():
                src = str(r.get("src"))
                dst = str(r.get("dst"))
                if not (src and dst):
                    continue
                G.add_edge(
                    src, dst,
                    product=r.get("product_id"),
                    capacity=float(r.get("capacity")) if pd.notna(r.get("capacity")) else None,
                    cost=float(r.get("cost")) if pd.notna(r.get("cost")) else None,
                )

        # 3) 葉ノード集合（出次数=0）
        leaf_nodes = {n for n in G.nodes if G.out_degree(n) == 0}

        # 4) 初期在庫（まずは定数でOK。将来は CSV/DB から）
        inventory = {n: 100.0 for n in G.nodes}

        state = {"inventory": inventory, "leafs": leaf_nodes}
        return {"graph": G, "state": state, "raw": raw}
