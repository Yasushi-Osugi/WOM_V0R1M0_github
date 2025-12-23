# main4cockpit_B.py

# STARTER
#python main.py --backend mvp --skip-orchestrate --csv data --scenario Baseline --ui cockpit
#python main.py --backend mvp --skip-orchestrate --csv data --ui planner




from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
import tkinter as tk
from typing import Optional
import logging

from pysi.utils.config import Config

# pipeline/hook/plugin関連をインポート
from pysi.core.hooks.core import HookBus, set_global, autoload_plugins
from pysi.core.wom_pipeline import WOMPipelineRunner, call_register_if_present


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _default_paths() -> dict[str, Path]:
    root = _repo_root()
    return {
        "db": root / "var" / "psi.sqlite",
        "schema": root / "pysi" / "db" / "schema_core_only.sql",
        "csv": root / "data",
    }


def _ensure_parent_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def _apply_schema_if_needed(db_path: Path, schema_sql: Optional[Path]) -> None:
    import sqlite3
    row_exists = lambda conn, t: conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?;", (t,)
    ).fetchone() is not None

    _ensure_parent_dir(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        if row_exists(conn, "calendar_iso") and row_exists(conn, "scenario"):
            return
        if not schema_sql or not schema_sql.exists():
            raise FileNotFoundError(f"schema file not found: {schema_sql}")
        sql = schema_sql.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.commit()
        print(f"[schema] applied: {schema_sql.name}")
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    d = _default_paths()
    ap = argparse.ArgumentParser(description="WOM Cockpit launcher (pipeline + plugin)")
    ap.add_argument("--scenario", default=os.getenv("PYSI_SCENARIO", "Baseline"))
    ap.add_argument("--db", default=str(d["db"]))
    ap.add_argument("--schema", default=str(d["schema"]))
    ap.add_argument("--csv", default=str(d["csv"]))
    ap.add_argument("--ui", choices=["planner", "cockpit"], default="cockpit")

    ap.add_argument("--default-lot-size", type=int, default=1000)
    ap.add_argument("--plan-year-st", type=int, default=2024)
    ap.add_argument("--plan-range", type=int, default=3)
    ap.add_argument("--backend", choices=["sql", "mvp"], default=os.getenv("PYSI_BACKEND", "sql"))
    ap.add_argument("--skip-orchestrate", action="store_true")
    ap.add_argument("--product", default=None)
    return ap.parse_args()


def launch_gui(config: Config, psi_env: object) -> None:
    if hasattr(psi_env, "reload"):
        psi_env.reload()
    if not hasattr(psi_env, "global_nodes"):
        setattr(psi_env, "global_nodes", {})
    if not hasattr(psi_env, "product_name_list"):
        setattr(psi_env, "product_name_list", [])

    from pysi.gui.app import PSIPlannerApp

    gui_root = tk.Tk()
    _ = PSIPlannerApp(gui_root, config, psi_env=psi_env)
    gui_root.mainloop()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db).resolve()
    schema_sql = Path(args.schema).resolve() if args.schema else None

    # 1) schema auto apply
    if args.backend == "sql" and not args.skip_orchestrate:
        _apply_schema_if_needed(db_path, schema_sql)

    # 2) hook bus / plugins
    logging.basicConfig(level=logging.INFO)
    bus = HookBus()
    set_global(bus)
    autoload_plugins("pysi.plugins")
    call_register_if_present("pysi.plugins", bus)

    runner = WOMPipelineRunner(bus=bus)

    # CSV path
    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = (_repo_root() / csv_path).resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV folder/file not found: {csv_path}")

    # 3) first pipeline run
    result = runner.run(
        data_dir=str(csv_path),
        product=args.product,
        scenario_id=args.scenario
    )
    env = result.get("env")
    
    if env is None:
        raise RuntimeError("WOMPipelineRunnerのrun結果からenvが取得できません")

    #@ADD
    if env:
        # world_map_view.py が期待する属性名に合わせて注入
        env.data_dir = str(csv_path) 
        # もし WOMEnv 内部で directory を使っているならそれも合わせる
        env.directory = str(csv_path)


    # --- world_map_view.py が参照する data_dir を注入（CSV運用の統一） ---
    # env に data_dir が無い / 空 の場合だけ入れる
    try:
        if not getattr(env, "data_dir", None):
            env.data_dir = str(csv_path)
    except Exception:
        pass


    if args.ui == "cockpit":
        from pysi.gui.cockpit_tk import launch_cockpit

        # ★ rerun_fn: cockpitで選ばれた product を pipeline に渡して env を作り直す
        def rerun_from_cockpit(product: str):
            r = runner.run(
                data_dir=str(csv_path),
                product=product,
                scenario_id=args.scenario
            )
            return r.get("env")

        launch_cockpit(env, rerun_fn=rerun_from_cockpit)
    else:
        launch_gui(Config(), env)


if __name__ == "__main__":
    repo = _repo_root()
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    main()
