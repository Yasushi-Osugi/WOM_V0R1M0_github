# pysi/scenario/store.py

from __future__ import annotations

import sqlite3, json, datetime as dt
from typing import Optional, List, Tuple
import pandas as pd

# あなたの既存ローダに合わせて import
from pysi.evaluate.offering_price import build_offering_price_frame      # 価格テーブル
from pysi.evaluate.cost_df_loader import build_cost_df_from_sql          # 原価・数量など（存在すれば）


def get_db_path_from(self_obj) -> str:
    # SQLバックエンドから安全にDBパスを取るヘルパ
    for attr in ("db_path", "dbfile", "db"):
        if hasattr(self_obj, attr):
            v = getattr(self_obj, attr)
            if isinstance(v, str) and v:
                return v
    return r"var/psi.sqlite"

def list_scenarios(db_path: str) -> List[Tuple[str, str]]:
    """
    return [(id, name), ...]  新しい順
    """
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("""
            SELECT id, COALESCE(name,id) AS name
              FROM scenario
             ORDER BY datetime(created_at) DESC, id ASC
        """).fetchall()
    except Exception:
        rows = []
    finally:
        con.close()
    return [(r[0], r[1]) for r in rows]




def _now():
    return dt.datetime.now().isoformat(timespec="seconds")

def _mk_run_id(prefix: str = "RUN") -> str:
    # 例: RUN_2025-10-06_12-34-56
    return f"{prefix}_{dt.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"

def create_run_OLD(con: sqlite3.Connection, scenario_id: Optional[str], label: Optional[str]=None, note: Optional[str]=None) -> str:
    run_id = _mk_run_id()
    con.execute("""INSERT INTO scenario_run(run_id, scenario_id, started_at, finished_at, label, note)
                   VALUES(?,?,?,?,?,?)""",
                (run_id, scenario_id, _now(), _now(), label, note))
    return run_id





def _safe_sum(series: pd.Series) -> float:
    try:
        return float(pd.to_numeric(series, errors="coerce").fillna(0).sum())
    except Exception:
        return 0.0

def save_run_results(db_path: str, scenario_id: Optional[str], label: Optional[str]=None, note: Optional[str]=None) -> str:
    """シナリオID（None可）での結果を scenario_run/summary/node に保存して run_id を返す"""
    con = sqlite3.connect(db_path)
    try:
        run_id = create_run(con, scenario_id, label=label, note=note)

        # --- 価格フレーム（ASIS/TOBE）
        price_df = build_offering_price_frame(db_path, scenario_id=scenario_id)

        # --- コスト/数量系（存在する前提。なければ空DF）
        try:
            cost_df = build_cost_df_from_sql(db_path, scenario_id=scenario_id)
        except Exception:
            cost_df = pd.DataFrame()

        # ===== 集計（summary） =====
        # revenue / cost / profit 列が無い場合は0で埋める（将来の実装に追随しやすく）
        rev = _safe_sum(cost_df.get("revenue"))
        cst = _safe_sum(cost_df.get("total_cost"))
        prf = _safe_sum(cost_df.get("profit"))
        prr = (prf / rev) if rev > 0 else 0.0

        con.execute("""INSERT INTO scenario_result_summary(run_id,total_revenue,total_cost,total_profit,profit_ratio)
                       VALUES(?,?,?,?,?)""", (run_id, rev, cst, prf, prr))

        # ===== ノード別明細 =====
        # price_df は ["product_name","node_name","offering_price_ASIS","offering_price_TOBE", ...]
        # cost_df に node別KPIがあれば join、無ければ価格だけ保存
        cols = ["product_name","node_name","offering_price_ASIS","offering_price_TOBE"]
        df = price_df[cols].copy()

        # あれば追加（なければスキップ）
        for col in ("revenue","total_cost","profit","shipped_qty"):
            if col in cost_df.columns:
                df = df.merge(cost_df[["product_name","node_name",col]], on=["product_name","node_name"], how="left")

        df = df.fillna(0.0)

        for r in df.to_dict("records"):
            con.execute(
                """INSERT INTO scenario_result_node
                   (run_id, product_name, node_name, offering_price_ASIS, offering_price_TOBE,
                    revenue, cost, profit)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (run_id, r["product_name"], r["node_name"],
                 float(r.get("offering_price_ASIS",0.0)), float(r.get("offering_price_TOBE",0.0)),
                 float(r.get("revenue",0.0)), float(r.get("total_cost",0.0)), float(r.get("profit",0.0)))
            )

        con.commit()
        return run_id
    finally:
        con.close()

def list_runs(db_path: str, scenario_id: Optional[str]=None, limit: int=20):
    con = sqlite3.connect(db_path)
    try:
        if scenario_id is None:
            q = "SELECT run_id,scenario_id,started_at,label FROM scenario_run ORDER BY rowid DESC LIMIT ?"
            return con.execute(q, (limit,)).fetchall()
        else:
            q = "SELECT run_id,scenario_id,started_at,label FROM scenario_run WHERE scenario_id IS ? ORDER BY rowid DESC LIMIT ?"
            return con.execute(q, (scenario_id, limit)).fetchall()
    finally:
        con.close()




def _now():
    return dt.datetime.now().isoformat(timespec="seconds")

def _mk_run_id(prefix: str = "RUN") -> str:
    return f"{prefix}_{dt.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"

def _run_id_decl(con: sqlite3.Connection) -> str:
    """scenario_run.run_id の宣言型を返す（例: 'INTEGER', 'TEXT'）。失敗時は''。"""
    try:
        for cid, name, ctype, *_ in con.execute("PRAGMA table_info(scenario_run)"):
            if name == "run_id":
                return (ctype or "").upper()
    except Exception:
        pass
    return ""

def create_run(con: sqlite3.Connection,
               scenario_id: Optional[str],
               label: Optional[str]=None,
               note: Optional[str]=None) -> str:
    """
    run_id が INTEGER のDBでも TEXT のDBでも動くように自動判別してINSERTする。
    戻り値は文字列（INTEGERのときは str(lastrowid)）。
    """
    decl = _run_id_decl(con)
    started = _now()
    finished = _now()

    if "INT" in decl:  # run_id が INTEGER (PRIMARY KEY) の系
        cur = con.execute(
            "INSERT INTO scenario_run(scenario_id, started_at, finished_at, label, note) "
            "VALUES (?,?,?,?,?)",
            (scenario_id, started, finished, label, note)
        )
        return str(cur.lastrowid)
    else:  # TEXT 系（推奨）
        run_id = _mk_run_id()
        con.execute(
            "INSERT INTO scenario_run(run_id, scenario_id, started_at, finished_at, label, note) "
            "VALUES (?,?,?,?,?,?)",
            (run_id, scenario_id, started, finished, label, note)
        )
        return run_id

def list_scenarios(db_path: str) -> List[Tuple[str, str]]:
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("""
            SELECT id, COALESCE(name,id) AS name
              FROM scenario
             ORDER BY datetime(created_at) DESC, id ASC
        """).fetchall()
    except Exception:
        rows = []
    finally:
        con.close()
    return [(r[0], r[1]) for r in rows]

def get_db_path_from(self_obj) -> str:
    for attr in ("db_path", "dbfile", "db"):
        if hasattr(self_obj, attr):
            v = getattr(self_obj, attr)
            if isinstance(v, str) and v:
                return v
    return r"var/psi.sqlite"

def _safe_sum(series: pd.Series) -> float:
    try:
        return float(pd.to_numeric(series, errors="coerce").fillna(0).sum())
    except Exception:
        return 0.0

def save_run_results(db_path: str,
                     scenario_id: Optional[str],
                     label: Optional[str]=None,
                     note: Optional[str]=None) -> str:
    con = sqlite3.connect(db_path)
    try:
        run_id = create_run(con, scenario_id, label=label, note=note)

        # 価格フレーム
        price_df = build_offering_price_frame(db_path, scenario_id=scenario_id)

        # コスト/数量（無ければ空）
        try:
            cost_df = build_cost_df_from_sql(db_path, scenario_id=scenario_id)
        except Exception:
            cost_df = pd.DataFrame()

        # Summary
        rev = _safe_sum(cost_df.get("revenue"))
        cst = _safe_sum(cost_df.get("total_cost"))
        prf = _safe_sum(cost_df.get("profit"))
        prr = (prf / rev) if rev > 0 else 0.0

        con.execute(
            "INSERT INTO scenario_result_summary(run_id,total_revenue,total_cost,total_profit,profit_ratio) "
            "VALUES(?,?,?,?,?)",
            (run_id, rev, cst, prf, prr)
        )

        # Node明細
        cols = ["product_name","node_name","offering_price_ASIS","offering_price_TOBE"]
        df = price_df[cols].copy()
        for col in ("revenue","total_cost","profit","shipped_qty"):
            if col in getattr(cost_df, "columns", []):
                df = df.merge(cost_df[["product_name","node_name",col]],
                              on=["product_name","node_name"], how="left")
        df = df.fillna(0.0)

        for r in df.to_dict("records"):
            con.execute(
                "INSERT INTO scenario_result_node "
                "(run_id, product_name, node_name, offering_price_ASIS, offering_price_TOBE, "
                " revenue, cost, profit) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (run_id, r["product_name"], r["node_name"],
                 float(r.get("offering_price_ASIS",0.0)),
                 float(r.get("offering_price_TOBE",0.0)),
                 float(r.get("revenue",0.0)),
                 float(r.get("total_cost",0.0)),
                 float(r.get("profit",0.0)))
            )

        con.commit()
        return run_id
    finally:
        con.close()
