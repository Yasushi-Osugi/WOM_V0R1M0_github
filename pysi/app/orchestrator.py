# pysi/app/orchestrator.py
"""
Global Weekly PSI Planner - Orchestrator
- Step1 calendar → Step2 schema → Step3 ETL → Step4 I/O → Step5 checks → Step6 report（任意）
- 既存DB/CSV/ネットワークビルダから (node, product) を自動検出して処理
"""
# Starter
#
#leaf モード：
#
#python -m pysi.app.orchestrator --db var\psi.sqlite --scenario Baseline --mode leaf --write-all-nodes --report
#
#
#tree モード：
#
#python -m pysi.app.orchestrator --db var\psi.sqlite --scenario Baseline `
#  --mode tree --network pysi.network.factory:factory `
#  --data-dir data --write-all-nodes --report --product JPN_RICE_1
from __future__ import annotations
import argparse
import importlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Optional, Tuple, Set
# --- DB/ETL/IO ----------------------------------------------------
from pysi.db.apply_schema import apply_schema
from pysi.db.calendar_sync import sync_calendar_iso
from pysi.etl.etl_monthly_to_lots import run_etl
from pysi.io.psi_io_adapters import (
    _open,
    get_scenario_id,
    get_scenario_bounds,
)
# --- tree専用の薄い書戻し -----------------------------------------
from pysi.io.tree_writeback import (
    write_both_layers_for_pair,     # ← これ1本で S生成→計算→DB書戻し まで完結
    pairs_from_weekly_demand,
    node_names_from_plan_root,
    intersect_pairs_with_network,
)
# --- Report（無ければスキップ可能） -------------------------------
try:
    from pysi.report.psi_report import (
        fetch_weekly_counts,
        get_scenario_id as _rep_get_scenario_id,
        get_node_id as _rep_get_node_id,
        get_product_id as _rep_get_product_id,
        plot_weekly,
    )
except Exception:
    fetch_weekly_counts = None
# ========== ヘルパ ==========
def _load_factory(spec: str):
    """
    'pysi.network.factory:factory' のような文字列から関数オブジェクトを取得
    """
    if ":" not in spec:
        raise ValueError("--network は 'pkg.module:factory_func' 形式で指定してください")
    mod_name, func_name = spec.split(":", 1)
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, func_name)
    if not callable(fn):
        raise TypeError(f"{spec} は呼び出し可能ではありません")
    return fn
def _scenario_bounds_from_csv(csv_path: str) -> Tuple[int, int]:
    """
    CSV（S_month_data.csv/sku_S_month_data.csv 的な）から plan_year_st / plan_range を推定。
    """
    import pandas as pd
    df = pd.read_csv(csv_path)
    years = sorted(set(int(y) for y in df["year"].unique()))
    return years[0], max(1, len(years))
def _ensure_calendar(conn: sqlite3.Connection, args) -> Tuple[int, int, int]:
    """
    calendar_iso を冪等に整備。
    優先度: CLI指定 > CSV推定 > 既存シナリオ値
    """
    plan_year_st = args.plan_year_st
    plan_range   = args.plan_range
    sid: Optional[int] = None
    if plan_year_st is None or plan_range is None:
        if args.csv and not args.skip_etl:
            try:
                plan_year_st, plan_range = _scenario_bounds_from_csv(args.csv)
            except Exception:
                plan_year_st = plan_year_st or 2025
                plan_range   = plan_range or 1
        else:
            # 既存シナリオから読む（存在しない場合は sid=None のまま）
            try:
                sid = get_scenario_id(conn, args.scenario)
                pys, pr = get_scenario_bounds(conn, sid)
                plan_year_st = plan_year_st or pys
                plan_range   = plan_range or pr
            except Exception:
                sid = None
    # スキップ指定がなければ calendar を整える
    n_weeks = 0
    if not args.skip_calendar:
        if sid is not None:
            # シナリオ基準で同期
            n_weeks = sync_calendar_iso(conn, scenario_id=sid)
        else:
            # CLI/CSV で境界が決まっている場合はこちら
            n_weeks = sync_calendar_iso(conn, plan_year_st=int(plan_year_st), plan_range=int(plan_range))
    else:
        cur = conn.execute("SELECT COUNT(*) FROM calendar_iso")
        n_weeks = int(cur.fetchone()[0] or 0)
    return int(plan_year_st), int(plan_range), int(n_weeks)
def _pairs_from_db(conn: sqlite3.Connection, scenario_id: int) -> Set[Tuple[str, str]]:
    """
    DBの weekly_demand から (node_name, product_name) のユニークペアを掘り出す。
    """
    rows = conn.execute(
        """
        SELECT n.name, p.name
        FROM weekly_demand wd
        JOIN node n    ON wd.node_id = n.id
        JOIN product p ON wd.product_id = p.id
        WHERE wd.scenario_id = ?
        GROUP BY n.name, p.name
        """,
        (scenario_id,),
    ).fetchall()
    return {(r[0], r[1]) for r in rows}
def _report_one(conn, scenario: str, node_name: str, product_name: str,
                layer: str, outdir: str, fmt: str = "png") -> Optional[str]:
    """
    週間グラフの 1 枚出力。psi_report.plot_weekly の引数ゆらぎに耐える。
    """
    if fetch_weekly_counts is None:
        return None
    from pathlib import Path
    import inspect
    Path(outdir).mkdir(parents=True, exist_ok=True)
    sid = _rep_get_scenario_id(conn, scenario)
    nid = _rep_get_node_id(conn, node_name)
    pid = _rep_get_product_id(conn, product_name)
    df = fetch_weekly_counts(conn, sid, nid, pid, layer)
    out = Path(outdir) / f"{scenario}_{layer}_{node_name}_{product_name}_weekly_chart.{fmt}"
    title = f"{scenario} / {layer} / {node_name} / {product_name}"
    # psi_report.plot_weekly のシグネチャに合わせて呼び分ける
    try:
        sig = inspect.signature(plot_weekly)
        params = list(sig.parameters.keys())
        if "outpath" in params:
            plot_weekly(df, title=title, outpath=str(out))
        elif "out" in params:
            plot_weekly(df, title=title, out=str(out))
        elif len(params) >= 3:
            plot_weekly(df, title, str(out))
        elif len(params) == 2:
            plot_weekly(df, str(out))
        else:
            res = plot_weekly(df, title=title)
            try:
                res.savefig(str(out))  # fig なら保存
            except Exception:
                import matplotlib.pyplot as plt
                plt.tight_layout(); plt.savefig(str(out)); plt.close()
    except TypeError:
        try:
            plot_weekly(df, title, str(out))
        except Exception:
            import matplotlib.pyplot as plt
            plt.tight_layout(); plt.savefig(str(out)); plt.close()
    return str(out)
# ========== CLI ==========
def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="PySI Orchestrator")
    ap.add_argument("--db", required=True, help="SQLite DB path (e.g. var/psi.sqlite)")
    ap.add_argument("--scenario", required=True, help="Scenario name (e.g. Baseline)")
    ap.add_argument("--schema", help="Apply DDL (schema.sql) before run")
    ap.add_argument("--csv", help="Monthly demand CSV for ETL (S_month_data.csv / sku_S_month_data.csv)")
    ap.add_argument("--default-lot-size", type=int, default=50)
    # カレンダ制御
    ap.add_argument("--plan-year-st", type=int)
    ap.add_argument("--plan-range", type=int)
    ap.add_argument("--skip-calendar", action="store_true")
    ap.add_argument("--skip-etl", action="store_true")
    # モード
    ap.add_argument("--mode", choices=["leaf", "tree"], default="leaf")
    ap.add_argument("--network", help="tree モードで使う factory（pkg.module:factory）")
    # factory が参照する CSV ディレクトリ & 製品指定
    ap.add_argument("--data-dir", default="data",
                    help="factory が参照するCSV群のディレクトリ（product_tree_*.csv 等）")
    ap.add_argument("--product", help="factoryに渡す製品名（省略時はCSV先頭 or 環境変数 PYSI_PRODUCT）")
    # 出力
    ap.add_argument("--write-all-nodes", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--report-outdir", default="report")
    ap.add_argument("--report-fmt", default="png")
    return ap
def main():
    args = build_argparser().parse_args()
    # DDL
    if args.schema:
        apply_schema(args.db, args.schema)
        print(f"DDL applied: {args.db}")
    with _open(args.db) as conn:
        # ETL（必要なら）
        if args.csv and not args.skip_etl:
            run_etl(args.db, args.csv, args.scenario, args.default_lot_size)
        # カレンダ冪等整備
        pys, pr, n_weeks = _ensure_calendar(conn, args)
        # ---- leaf モード ------------------------------------------------
        if args.mode == "leaf":
            sid = get_scenario_id(conn, args.scenario)
            pairs = _pairs_from_db(conn, sid)
            written = []
            for node_name, product_name in sorted(pairs):
                # これ1回で「S生成→計算→demand/supply 両レイヤ書戻し」まで完結
                res = write_both_layers_for_pair(conn, sid, node_name, product_name)
                item = {"node": node_name, "product": product_name}
                if isinstance(res, dict):
                    item.update(res)  # 例: {"d_rows": ..., "s_rows": ..., "w_d": ..., "w_s": ...}
                written.append(item)
            # レポート（必要なら）
            reports = []
            if args.report and fetch_weekly_counts is not None:
                for p in written:
                    out = _report_one(conn, args.scenario, p["node"], p["product"],
                                      "demand", args.report_outdir, args.report_fmt)
                    if out:
                        reports.append(out)
            print(json.dumps({
                "scenario": args.scenario,
                "plan_year_st": pys,
                "plan_range": pr,
                "weeks": n_weeks,
                "mode": "leaf",
                "pairs_total": len(written),
                "written": written,
                "reports": reports,
            }, ensure_ascii=False, indent=2))
            return
        # ---- tree モード ------------------------------------------------
        if args.mode == "tree":
            if not args.network:
                raise ValueError("--network に 'pysi.network.factory:factory' のような指定が必要です")
            factory = _load_factory(args.network)
            # data_dir / product を渡せる実装なら渡し、TypeErrorならフォールバック
            try:
                root = factory(data_dir=args.data_dir, product_name=getattr(args, "product", None))
            except TypeError:
                try:
                    root = factory()
                except TypeError:
                    root = factory(args.data_dir)
            # 状態出力
            print(json.dumps({
                "scenario": args.scenario,
                "plan_year_st": pys,
                "plan_range": pr,
                "weeks": n_weeks,
                "mode": "tree",
                "root_node": getattr(root, "name", "<unknown>"),
                "data_dir": str(Path(args.data_dir).resolve()),
            }, ensure_ascii=False, indent=2))
            # 交差ペアの抽出（ネットワークに含まれ、かつDBに週次需要があるもの）
            sid = get_scenario_id(conn, args.scenario)
            net_nodes = node_names_from_plan_root(root)
            db_pairs = pairs_from_weekly_demand(conn, sid)
            pairs = sorted(intersect_pairs_with_network(db_pairs, net_nodes))
            # フォールバック：何もなければ (root.name, 既定product)
            if not pairs:
                fallback_product = args.product or os.getenv("PYSI_PRODUCT") or "prod-A"
                pairs = [(root.name, fallback_product)]
            # 計算＆書戻し：write_both_layers_for_pair だけで一括実行
            written = []
            for node_name, product_name in pairs:
                try:
                    res = write_both_layers_for_pair(conn, sid, node_name, product_name)
                except Exception as e:
                    import sys
                    print(f"[WARN] write_both_layers_for_pair failed: node={node_name}, product={product_name} -> {e}",
                          file=sys.stderr)
                    res = {}
                item = {"node": node_name, "product": product_name}
                if isinstance(res, dict):
                    item.update(res)
                written.append(item)
            # 進捗
            print(json.dumps({"written": written}, ensure_ascii=False, indent=2))
            # レポート
            reports = []
            if args.report and fetch_weekly_counts is not None:
                for p in written:
                    out = _report_one(conn, args.scenario, p["node"], p["product"],
                                      "demand", args.report_outdir, args.report_fmt)
                    if out:
                        reports.append(out)
            print(json.dumps({
                "scenario": args.scenario,
                "plan_year_st": pys,
                "plan_range": pr,
                "weeks": n_weeks,
                "mode": "tree",
                "pairs_total": len(written),
                "written": written,
                "reports": reports,
            }, ensure_ascii=False, indent=2))
            return
if __name__ == "__main__":
    main()
