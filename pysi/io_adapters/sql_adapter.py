# pysi/io_adapters/sql.py
from __future__ import annotations
from typing import Dict, Any, Optional
import pandas as pd

try:
    import sqlalchemy as sa
except Exception:  # optional dependency
    sa = None

STANDARD = {
    "products": ("product_id", "name"),
    "nodes": ("node_id", "name", "role"),
    "edges": ("src", "dst", "product_id", "capacity", "cost"),
    "demand": ("week_idx", "product_id", "node_id", "qty"),
}

class SQLAdapter:
    """
    設定駆動のSQLアダプタ。
    - dsn: "sqlite:///path/to.db" 等
    - schema: スキーマ名（任意）
    - schema_cfg:
        tables: {logical_name -> table_or_view_name}
        columns:{logical_name -> {standard_name: actual_name}}
    """
    def __init__(self, dsn: str, schema: Optional[str] = None,
                 schema_cfg: Optional[Dict[str, Any]] = None, logger=None):
        if sa is None:
            raise RuntimeError("sqlalchemy is required for SQLAdapter (pip install sqlalchemy)")
        self.dsn, self.schema, self.logger = dsn, schema, logger
        self.schema_cfg = schema_cfg or {}
        self.tables = self.schema_cfg.get("tables", {})
        self.columns = self.schema_cfg.get("columns", {})
        self.engine = sa.create_engine(self.dsn, future=True)

    def _select_with_mapping(self, logical: str) -> pd.DataFrame:
        std_cols = STANDARD[logical]
        colmap: Dict[str, str] = self.columns.get(logical, {k: k for k in std_cols})  # {standard: actual}
        sel = ", ".join([f"{colmap.get(k, k)} AS {k}" for k in std_cols])
        table = self.tables.get(logical, logical)
        tbl = f"{self.schema}.{table}" if self.schema else table
        q = f"SELECT {sel} FROM {tbl}"
        with self.engine.connect() as cx:
            return pd.read_sql(q, cx)

    def load_all(self, spec: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        try:
            return dict(
                products=self._select_with_mapping("products"),
                nodes=self._select_with_mapping("nodes"),
                edges=self._select_with_mapping("edges"),
                demand=self._select_with_mapping("demand"),
            )
        except Exception as e:
            self.logger and self.logger.exception(f"SQL load_all failed: {e}")
            # 空で返す（最小動作）
            return dict(products=pd.DataFrame(), nodes=pd.DataFrame(),
                        edges=pd.DataFrame(), demand=pd.DataFrame())

    # ↓ 以下は“器”。あなたの実装に差し替え予定
    def build_tree(self, raw: Dict[str, pd.DataFrame]):
        return {"graph": "placeholder", "raw": raw}

    def derive_params(self, raw: Dict[str, pd.DataFrame]):
        return {"capacity": {}, "lt": {}, "ss": {}, "meta": {"source": "sql"}}

    def build_initial_demand(self, raw, params):
        return {}

    def collect_result(self, root, params):
        return {"psi": [], "psi_df": pd.DataFrame(), "kpis": {"fill_rate": 1.0, "note": "sql"}}

    def to_series_df(self, result: Dict[str, Any]) -> pd.DataFrame:
        # 可視化用のダミー
        return pd.DataFrame({"week_idx": [0, 1, 2], "inventory": [10, 9, 8]})

    def export_csv(self, result: Dict[str, Any], out_dir: str = "out") -> None:
        # DB書き戻しは exporter フックに任せる前提。ここは空でOK。
        return
