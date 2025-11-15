# pysi/io_adapters/csv.py
from __future__ import annotations
from typing import Dict, Any, Optional
import pandas as pd
from pathlib import Path

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
        self.tables = self.schema_cfg.get("tables", {})
        self.columns = self.schema_cfg.get("columns", {})
        self.logger = logger

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
    def build_tree(self, raw: Dict[str, pd.DataFrame]):
        return {"graph": "placeholder", "raw": raw}

    def derive_params(self, raw: Dict[str, pd.DataFrame]):
        return {"capacity": {}, "lt": {}, "ss": {}, "meta": {"source": "csv"}}

    def build_initial_demand(self, raw, params):
        return {}

    def collect_result(self, root, params):
        return {"psi": [], "psi_df": pd.DataFrame(), "kpis": {"fill_rate": 1.0, "note": "csv"}}

    def to_series_df(self, result: Dict[str, Any]) -> pd.DataFrame:
        return pd.DataFrame({"week_idx": [0, 1, 2], "inventory": [10, 9, 8]})

    def export_csv(self, result: Dict[str, Any], out_dir: str = "out") -> None:
        p = Path(out_dir); p.mkdir(parents=True, exist_ok=True)
        (p / "kpi.txt").write_text(str(result.get("kpis", {})))
