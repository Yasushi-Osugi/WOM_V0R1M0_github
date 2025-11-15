#PySI_V0R8_SQL_040_test

#動作確認コマンド

## フルスキーマを指定して起動（適用 → ETL/計算 → GUI）
#python .\main.py --backend sql --scenario Baseline --plan-year-st 2024 --plan-range 3 --schema .\pysi\db\schema.sql


# ***************************************

## 1) スキーマ→ETL→計算→書戻し をGUI前に自動実行（計画年も明示）
#python .\main.py --backend sql --scenario Baseline --plan-year-st 2024 --plan-range 3

## 2) 以降は既存DBでGUIをすぐ確認したいとき
#python .\main.py --backend sql --skip-orchestrate

# ***************************************

#a) 正攻法（オーケストレート→GUI）
#python .\main.py --backend sql --scenario Baseline --plan-year-st 2024 --plan-range 3

#先頭のエラー（int(None)) は解消され、lot_bucket まで更新→GUIに製品リストが出るはずです。
#
#b) 既存DBのみでGUI（確認用）
#python .\main.py --backend sql --skip-orchestrate


#a) を一度成功させた後なら、product_name_list が空でなくなります。
#
#c) 軽快なMVPモード（互換シムで落ちない）
#python .\main.py --backend mvp


#依然として map/network はMVP実装に依存しますが、global_nodes 未定義で落ちる問題は回避されます。
#（必要なら app.py 側にも getattr(..., default) を追加して堅牢化します）
#
#追加メモ（原因の見立て）
#
#orchestrator.py の argparse は plan_year_st / plan_range を args に格納しており、未指定だと None。
#_ensure_calendar() で int(args.plan_year_st) して落ちています。
#→ フラグをCLIフォールバックに明示でOK。

#2/3 の「products: []」は、DBにまだ週次/lotが無いため。1/3の修正が入れば解消。

#3/3 の AttributeError は GUI実装がSQL前提になった影響。短期は互換シムで回避、長期は app.py を getattr ベースにするとより堅牢。


# main.py  (040_unified_v3: apply schema before orchestrator)
from __future__ import annotations

import argparse
import os
import sys
import subprocess
import sqlite3
from pathlib import Path
import tkinter as tk
from typing import Optional, List

from pysi.utils.config import Config

from pysi.core.hooks.core import autoload_plugins
#from pysi.hooks.core import autoload_plugins


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _default_paths() -> dict[str, Path]:
    root = _repo_root()
    return {
        "db": root / "var" / "psi.sqlite",
        # Seedに合わせて core_only を既定化
        "schema": root / "pysi" / "db" / "schema_core_only.sql",
        "csv": root / "data" / "sku_S_month_data.csv",
    }


def _ensure_parent_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


# ------------------------------- schema helpers --------------------------------

def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?;", (name,)
    ).fetchone()
    return row is not None


def _apply_schema_if_needed(db_path: Path, schema_sql: Optional[Path]) -> None:
    """calendar_iso などコアが無ければ schema を適用。冪等。"""
    _ensure_parent_dir(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        if _table_exists(conn, "calendar_iso") and _table_exists(conn, "scenario"):
            return  # 既に適用済み
        if not schema_sql or not schema_sql.exists():
            raise FileNotFoundError(f"schema file not found: {schema_sql}")
        sql = schema_sql.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.commit()
        print(f"[schema] applied: {schema_sql.name}")
    finally:
        conn.close()

# ------------------------------- orchestrate -----------------------------------

def _orchestrate_via_api(db_path: Path, *, scenario: str,
                         schema_sql: Optional[Path],
                         monthly_csv: Optional[Path],
                         default_lot_size: Optional[int],
                         plan_year_st: int, plan_range: int) -> Optional[int]:
    try:
        from pysi.app.orchestrator import orchestrate  # type: ignore
    except Exception:
        return None

    schema_for_run = str(schema_sql) if (schema_sql and schema_sql.exists()) else None
    csv_for_run = str(monthly_csv) if (monthly_csv and monthly_csv.exists()) else None

    rows = orchestrate(
        str(db_path),
        scenario=scenario,
        schema_sql=schema_for_run,
        monthly_csv=csv_for_run,
        default_lot_size=default_lot_size,
        product_filter=None,
        plan_year_st=plan_year_st,
        plan_range=plan_range,
    )
    try:
        return int(rows) if rows is not None else None
    except Exception:
        return None


def _orchestrate_via_cli(db_path: Path, *, scenario: str,
                         schema_sql: Optional[Path],
                         monthly_csv: Optional[Path],
                         default_lot_size: Optional[int],
                         plan_year_st: int, plan_range: int) -> int:
    args: List[str] = [
        sys.executable, "-m", "pysi.app.orchestrator",
        "--db", str(db_path),
        "--scenario", scenario,
        "--mode", "leaf",
        "--write-all-nodes",
        "--plan-year-st", str(plan_year_st),
        "--plan-range", str(plan_range),
    ]
    if schema_sql and schema_sql.exists():
        # orchestratorが無視しても、直前に適用済みなので実害なし
        args += ["--schema", str(schema_sql)]
    if monthly_csv and monthly_csv.exists():
        args += ["--csv", str(monthly_csv)]
    if default_lot_size is not None:
        args += ["--default-lot-size", str(default_lot_size)]

    proc = subprocess.run(args, capture_output=True, text=True, cwd=str(_repo_root()))
    if proc.returncode != 0:
        print("[WARN] Orchestrator CLI failed:", proc.stderr[-1000:])
        raise SystemExit(proc.returncode)
    return 0


def orchestrate_once(db_path: Path, *, scenario: str,
                     schema_sql: Optional[Path],
                     monthly_csv: Optional[Path],
                     default_lot_size: Optional[int],
                     plan_year_st: int, plan_range: int) -> None:
    # 1) まずはスキーマ適用（無ければ）
    _apply_schema_if_needed(db_path, schema_sql)

    # 2) orchestrator（API -> CLI フォールバック）
    rows = _orchestrate_via_api(
        db_path, scenario=scenario,
        schema_sql=schema_sql, monthly_csv=monthly_csv,
        default_lot_size=default_lot_size,
        plan_year_st=plan_year_st, plan_range=plan_range,
    )
    if rows is None:
        rows = _orchestrate_via_cli(
            db_path, scenario=scenario,
            schema_sql=schema_sql, monthly_csv=monthly_csv,
            default_lot_size=default_lot_size,
            plan_year_st=plan_year_st, plan_range=plan_range,
        )
    print(f"[orchestrate] completed (rows={rows}).")

# ------------------------------- env & GUI -------------------------------------

def build_env(db_path: Path, *, use_sql_backend: bool) -> object:
    if use_sql_backend:
        from pysi.io.sql_planenv import SqlPlanEnv
        return SqlPlanEnv(str(db_path))
    else:
        from pysi.psi_planner_mvp.plan_env_main import PlanEnv
        env = PlanEnv(Config())
        env.load_data_files()
        return env


def _ensure_env_compat(env: object) -> object:
    if not hasattr(env, "global_nodes"):
        setattr(env, "global_nodes", {})
    if not hasattr(env, "product_name_list"):
        setattr(env, "product_name_list", [])
    return env


def launch_gui(config: Config, psi_env: object) -> None:
    if hasattr(psi_env, "reload"):
        psi_env.reload()
    psi_env = _ensure_env_compat(psi_env)

    from pysi.gui.app import PSIPlannerApp
    root = tk.Tk()
    app = PSIPlannerApp(root, config, psi_env=psi_env)
    root.mainloop()


def parse_args() -> argparse.Namespace:
    d = _default_paths()
    ap = argparse.ArgumentParser(description="PySI GUI launcher")
    ap.add_argument("--scenario", default=os.getenv("PYSI_SCENARIO", "Baseline"))
    ap.add_argument("--db", default=str(d["db"]))
    ap.add_argument("--schema", default=str(d["schema"]))
    ap.add_argument("--csv", default=str(d["csv"]))
    ap.add_argument("--default-lot-size", type=int, default=1000)
    ap.add_argument("--plan-year-st", type=int, default=2024)
    ap.add_argument("--plan-range", type=int, default=3)
    ap.add_argument("--backend", choices=["sql", "mvp"],
                    default=os.getenv("PYSI_BACKEND", "sql"))
    ap.add_argument("--skip-orchestrate", action="store_true")
    return ap.parse_args()


def main() -> None:
    args = parse_args()

    #@251010 ADD for Hook and Plugin
    # ---- ここで一度だけプラグインをロード ----
    autoload_plugins("pysi.plugins")



    config = Config()

    db_path = Path(args.db).resolve()
    schema_sql = Path(args.schema).resolve() if args.schema else None
    csv_path = Path(args.csv).resolve() if args.csv else None
    use_sql_backend = args.backend == "sql"

    if use_sql_backend and not args.skip_orchestrate:
        try:
            orchestrate_once(
                db_path,
                scenario=args.scenario,
                schema_sql=schema_sql,
                monthly_csv=csv_path,
                default_lot_size=args.default_lot_size,
                plan_year_st=args.plan_year_st,
                plan_range=args.plan_range,
            )
        except Exception as e:
            print(f"[WARN] Orchestration failed: {e}\n       Launching GUI with existing DB...")

    psi_env = build_env(db_path, use_sql_backend=use_sql_backend)
    launch_gui(config, psi_env)


if __name__ == "__main__":
    repo = _repo_root()
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    main()
