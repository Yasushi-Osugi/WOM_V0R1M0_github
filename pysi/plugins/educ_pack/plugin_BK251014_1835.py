# pysi/plugins/educ_pack/plugin.py
import pandas as pd
from pathlib import Path

def register(bus):
    def exporters(defaults, **ctx):
        def export_kpi(result: dict, out_dir="out"):
            p = Path(out_dir); p.mkdir(parents=True, exist_ok=True)
            pd.DataFrame([result.get("kpis", {})]).to_csv(p / "kpi.csv", index=False)
        def export_series(result: dict, out_dir="out"):
            df = result.get("psi_df") or pd.DataFrame({"week_idx":[0,1,2],"inventory":[10,9,8]})
            p = Path(out_dir); p.mkdir(parents=True, exist_ok=True)
            df.to_csv(p / "series.csv", index=False)
        return [*defaults, export_kpi, export_series]
    bus.add_filter("report:exporters", exporters, priority=60)

# plugins/educ_pack/plugin.py
import pandas as pd
from pathlib import Path

def register(bus):
    # report:exporters を差し替え（デフォルト + 追加Exporter）
    def exporters(defaults, **ctx):
        def export_kpi_csv(result: dict, out_dir="out"):
            p = Path(out_dir); p.mkdir(parents=True, exist_ok=True)
            pd.DataFrame([result.get("kpis", {})]).to_csv(p / "kpi.csv", index=False)

        def export_series_csv(result: dict, out_dir="out"):
            # pipeline 側で result["series_df"] を詰める（次のステップで対応）
            df = result.get("series_df")
            if df is None or not hasattr(df, "to_csv"):
                # 最低限のフォールバック
                df = pd.DataFrame({"week_idx": [0,1,2], "inventory": [10,9,8]})
            p = Path(out_dir); p.mkdir(parents=True, exist_ok=True)
            df.to_csv(p / "series.csv", index=False)

        # 既定の出力（kpi.txt など）も残しつつ、CSV出力を追加
        return [*defaults, export_kpi_csv, export_series_csv]

    bus.add_filter("report:exporters", exporters, priority=60)

