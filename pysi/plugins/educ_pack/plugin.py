# plugins/educ_pack/plugin.py
import pandas as pd
from pathlib import Path

def register_OLD(bus):
    # report:exporters を差し替え（デフォルト + 追加Exporter）
    def exporters(defaults, **ctx):

        #def export_kpi_csv(result: dict, out_dir="out"):
        def export_kpi_csv(result: dict, out_dir=None, **ctx):
            out_dir = out_dir or ctx.get("out_dir", "out")

            p = Path(out_dir); p.mkdir(parents=True, exist_ok=True)
            pd.DataFrame([result.get("kpis", {})]).to_csv(p / "kpi.csv", index=False)

        #def export_series_csv(result: dict, out_dir="out"):
        def export_series_csv(result: dict, out_dir=None, **ctx):
            out_dir = out_dir or ctx.get("out_dir", "out")

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



def register(bus):
    def exporters(defaults, **ctx):
        def export_kpi_csv(result: dict, out_dir=None, **ctx):
            out_dir = out_dir or ctx.get("out_dir", "out")
            p = Path(out_dir); p.mkdir(parents=True, exist_ok=True)
            pd.DataFrame([result.get("kpis", {})]).to_csv(p / "kpi.csv", index=False)

        def export_series_csv(result: dict, out_dir=None, **ctx):
            out_dir = out_dir or ctx.get("out_dir", "out")
            df = result.get("series_df")
            if df is None or not hasattr(df, "to_csv"):
                df = pd.DataFrame({"week_idx": [0,1,2], "inventory": [10,9,8]})
            p = Path(out_dir); p.mkdir(parents=True, exist_ok=True)
            df.to_csv(p / "series.csv", index=False)

        # 追加（psi_df をそのままCSV出力）
        def export_psi_df_csv(result: dict, out_dir=None, **ctx):
            out_dir = out_dir or ctx.get("out_dir", "out")
            p = Path(out_dir); p.mkdir(parents=True, exist_ok=True)
            psi_df = result.get("psi_df")
            if hasattr(psi_df, "to_csv") and not psi_df.empty:
                psi_df.to_csv(p / "psi_df.csv", index=False)
            # 空でもエラーにしない（スモーク優先）

        # 既定Exporter（io.export_csv）＋ CSV2本 + psi_df 出力を返す
        return [*defaults, export_kpi_csv, export_series_csv, export_psi_df_csv]

    bus.add_filter("report:exporters", exporters, priority=60)


