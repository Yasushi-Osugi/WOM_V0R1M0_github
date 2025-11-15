# pysi/scenario/store.py

from __future__ import annotations

import sqlite3, json, datetime as dt
from typing import Optional, List, Tuple
import pandas as pd

# あなたの既存ローダに合わせて import
from pysi.evaluate.offering_price import build_offering_price_frame      # 価格テーブル
from pysi.evaluate.cost_df_loader import build_cost_df_from_sql          # 原価・数量など（存在すれば）



def list_runs_OLD(db_path: str, scenario_id: Optional[str]=None, limit: int=20):
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


def list_runs_OLD(db_path: str, scenario_id: Optional[str]=None, limit: int=20):
    con = sqlite3.connect(db_path)
    try:
        if scenario_id is None:
            q = "SELECT run_id,scenario_id,started_at,label FROM scenario_run ORDER BY rowid DESC LIMIT ?"
            return con.execute(q, (limit,)).fetchall()
        else:
            q = "SELECT run_id,scenario_id,started_at,label FROM scenario_run WHERE scenario_id = ? ORDER BY rowid DESC LIMIT ?"
            return con.execute(q, (scenario_id, limit)).fetchall()
    finally:
        con.close()


# pysi/scenario/store.py
def list_runs(db_path: str, scenario_id: Optional[str]=None, limit: int=20):
    con = sqlite3.connect(db_path)
    try:
        if scenario_id is None:
            q = "SELECT run_id,scenario_id,started_at,label FROM scenario_run ORDER BY rowid DESC LIMIT ?"
            return con.execute(q, (limit,)).fetchall()
        else:
            q = "SELECT run_id,scenario_id,started_at,label FROM scenario_run WHERE scenario_id = ? ORDER BY rowid DESC LIMIT ?"
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


def create_run_OLD(con: sqlite3.Connection,
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



def _scenario_id_notnull(con: sqlite3.Connection) -> bool:
    try:
        for _, name, ctype, notnull, *_ in con.execute("PRAGMA table_info(scenario_run)"):
            if name == "scenario_id":
                return bool(notnull)
    except Exception:
        pass
    return False

def create_run(con: sqlite3.Connection,
               scenario_id: Optional[str],
               label: Optional[str]=None,
               note: Optional[str]=None) -> str:
    """
    run_id が INTEGER/TEXT どちらでも動作。
    scenario_id が NULL 禁止のDBでは 'BASE' を保存（GUIの BASE(None) 用の代替）。
    """
    decl = _run_id_decl(con)
    started = _now()
    finished = _now()

    # NULL禁止なら 'BASE' で代替、許可なら None のまま
    sid_value = scenario_id
    if sid_value is None and _scenario_id_notnull(con):
        sid_value = "BASE"

    if "INT" in (decl or ""):  # run_id が INTEGER の系
        cur = con.execute(
            "INSERT INTO scenario_run(scenario_id, started_at, finished_at, label, note) "
            "VALUES (?,?,?,?,?)",
            (sid_value, started, finished, label, note)
        )
        return str(cur.lastrowid)
    else:                        # TEXT の系
        run_id = _mk_run_id()
        con.execute(
            "INSERT INTO scenario_run(run_id, scenario_id, started_at, finished_at, label, note) "
            "VALUES (?,?,?,?,?,?)",
            (run_id, sid_value, started, finished, label, note)
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

def save_run_results_OLD(db_path: str,
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


def save_run_results_OLD2(db_path: str,
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

        # ===== Summary =====
        rev = _safe_sum(cost_df.get("revenue"))
        cst = _safe_sum(cost_df.get("total_cost"))
        prf = _safe_sum(cost_df.get("profit"))
        prr = (prf / rev) if rev > 0 else 0.0

        con.execute(
            "INSERT INTO scenario_result_summary(run_id,total_revenue,total_cost,total_profit,profit_ratio) "
            "VALUES(?,?,?,?,?)",
            (run_id, rev, cst, prf, prr)
        )

        # ===== Node 明細 =====
        cols = ["product_name","node_name","offering_price_ASIS","offering_price_TOBE"]
        df = price_df[cols].copy()

        # cost_dfが持っていれば join（なければスキップ）
        for col in ("revenue","total_cost","profit","shipped_qty"):
            if col in getattr(cost_df, "columns", []):
                df = df.merge(
                    cost_df[["product_name","node_name",col]],
                    on=["product_name","node_name"], how="left"
                )

        # price 列（NOT NULL のため必ず埋める）
        import pandas as _pd
        tobe = _pd.to_numeric(df["offering_price_TOBE"], errors="coerce")
        asis = _pd.to_numeric(df["offering_price_ASIS"], errors="coerce")
        df["price"] = tobe.where(tobe > 0).combine_first(asis.where(asis > 0)).fillna(0.0)

        df = df.fillna(0.0)

        # 必要列だけ INSERT。DB側が NOT NULL の price を含める！
        for r in df.to_dict("records"):
            con.execute(
                "INSERT INTO scenario_result_node "
                "(run_id, product_name, node_name, price, "
                " offering_price_ASIS, offering_price_TOBE, revenue, cost, profit) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (run_id,
                 r["product_name"], r["node_name"],
                 float(r.get("price", 0.0)),
                 float(r.get("offering_price_ASIS", 0.0)),
                 float(r.get("offering_price_TOBE", 0.0)),
                 float(r.get("revenue", 0.0)),
                 float(r.get("total_cost", 0.0)),
                 float(r.get("profit", 0.0)))
            )

        con.commit()
        return run_id
    finally:
        con.close()


def save_run_results_OLD3(db_path: str,
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

        # ===== Summary =====
        rev = _safe_sum(cost_df.get("revenue"))
        # node側は 'cost'、summaryは 'total_cost' の命名なので両取り
        cst = _safe_sum(cost_df.get("total_cost"))
        prf = _safe_sum(cost_df.get("profit"))
        prr = (prf / rev) if rev > 0 else 0.0

        con.execute(
            "INSERT INTO scenario_result_summary(run_id,total_revenue,total_cost,total_profit,profit_ratio) "
            "VALUES(?,?,?,?,?)",
            (run_id, rev, cst, prf, prr)
        )

        # ===== Node 明細 =====
        import pandas as _pd

        # 価格列
        cols = ["product_name","node_name","offering_price_ASIS","offering_price_TOBE"]
        df = price_df[cols].copy()

        # cost_df から拾えるものを拾う（候補名を順に探す）
        def _pick(name_candidates):
            for nm in name_candidates:
                if nm in getattr(cost_df, "columns", []):
                    return cost_df[["product_name","node_name", nm]].rename(columns={nm: name_candidates[0]})
            # 無いときは0.0列
            return pd.DataFrame(columns=["product_name","node_name", name_candidates[0]])

        # 代表名 : 候補一覧
        WANT = {
            "revenue":               ["revenue"],
            "profit":                ["profit"],
            "cost":                  ["cost", "total_cost"],
            "logistics_costs":       ["logistics_costs", "cs_logistics_costs"],
            "warehouse_cost":        ["warehouse_cost", "cs_warehouse_cost"],
            "manufacturing_overhead":["manufacturing_overhead", "mfg_overhead", "cs_mfg_overhead"],
            "direct_materials_costs":["direct_materials_costs", "cs_direct_materials_costs"],
            "tax_portion":           ["tax_portion", "cs_tax_portion"],
        }

        # 必要なコスト系を順次マージ
        for rep, cands in WANT.items():
            part = _pick(cands)
            if len(part) == 0:
                # 0行DFになってしまう場合は0.0で埋めた同形DFを作る
                part = df[["product_name","node_name"]].copy()
                part[rep] = 0.0
            else:
                # 欠損→0
                part[rep] = _pd.to_numeric(part[rep], errors="coerce").fillna(0.0)
            df = df.merge(part, on=["product_name","node_name"], how="left")

        # 保存用の price 列（NOT NULLのため必須）
        tobe = _pd.to_numeric(df["offering_price_TOBE"], errors="coerce")
        asis = _pd.to_numeric(df["offering_price_ASIS"], errors="coerce")
        df["price"] = tobe.where(tobe > 0).combine_first(asis.where(asis > 0)).fillna(0.0)

        # 最後に欠損は0で埋める
        df = df.fillna(0.0)

        # INSERT（NOT NULL な列をすべて含める）
        sql = (
            "INSERT INTO scenario_result_node "
            "(run_id, product_name, node_name, "
            " price, offering_price_ASIS, offering_price_TOBE, "
            " revenue, profit, cost, "
            " logistics_costs, warehouse_cost, manufacturing_overhead, "
            " direct_materials_costs, tax_portion) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        )
        for r in df.to_dict("records"):
            con.execute(sql, (
                run_id,
                r["product_name"], r["node_name"],
                float(r.get("price", 0.0)),
                float(r.get("offering_price_ASIS", 0.0)),
                float(r.get("offering_price_TOBE", 0.0)),
                float(r.get("revenue", 0.0)),
                float(r.get("profit", 0.0)),
                float(r.get("cost", 0.0)),
                float(r.get("logistics_costs", 0.0)),
                float(r.get("warehouse_cost", 0.0)),
                float(r.get("manufacturing_overhead", 0.0)),
                float(r.get("direct_materials_costs", 0.0)),
                float(r.get("tax_portion", 0.0)),
            ))

        con.commit()
        return run_id
    finally:
        con.close()



def save_run_results_OLD4(db_path: str,
                     scenario_id: Optional[str],
                     label: Optional[str]=None,
                     note: Optional[str]=None) -> str:
    con = sqlite3.connect(db_path)
    try:
        # 1) run レコード作成（run_id を取得）
        run_id = create_run(con, scenario_id, label=label, note=note)

        # 2) 価格フレーム
        price_df = build_offering_price_frame(db_path, scenario_id=scenario_id)

        # 3) コスト/数量（無ければ空）
        try:
            cost_df = build_cost_df_from_sql(db_path, scenario_id=scenario_id)
        except Exception:
            cost_df = pd.DataFrame()

        # 4) ===== Summary をロバストに計算 =====
        def _pick_first_col(df: pd.DataFrame, candidates):
            for c in candidates:
                if c in getattr(df, "columns", []):
                    return c
            return None

        rev_col = _pick_first_col(cost_df, ["revenue", "total_revenue", "sales_revenue", "price_sales_shipped"])
        cst_col = _pick_first_col(cost_df, ["total_cost", "cost", "full_cost"])
        prf_col = _pick_first_col(cost_df, ["profit", "gross_profit"])

        rev = _safe_sum(cost_df[rev_col]) if rev_col else 0.0
        cst = _safe_sum(cost_df[cst_col]) if cst_col else 0.0

        # 利益は列があればそれを、無ければ rev - cst
        if prf_col:
            prf = _safe_sum(cost_df[prf_col])
        else:
            prf = rev - cst if (rev or cst) else 0.0

        # 最後の保険：rev==0 かつ price_sales_shipped がある場合は
        # 末端ノード（CS_で始まる）を代理売上に使う
        if rev == 0.0 and "price_sales_shipped" in getattr(cost_df, "columns", []):
            try:
                if "node_name" in cost_df.columns:
                    mask_cs = cost_df["node_name"].astype(str).str.startswith("CS_")
                    proxy_rev = _safe_sum(cost_df.loc[mask_cs, "price_sales_shipped"])
                else:
                    proxy_rev = _safe_sum(cost_df["price_sales_shipped"])
                if proxy_rev > 0:
                    rev = proxy_rev
                    if not prf_col and cst_col:
                        prf = rev - cst
            except Exception:
                pass

        prr = (prf / rev) if rev > 0 else 0.0

        con.execute(
            "INSERT INTO scenario_result_summary(run_id,total_revenue,total_cost,total_profit,profit_ratio) "
            "VALUES(?,?,?,?,?)",
            (run_id, rev, cst, prf, prr)
        )

        # 5) ===== Node 明細 =====
        # 価格列
        cols = ["product_name", "node_name", "offering_price_ASIS", "offering_price_TOBE"]
        df = price_df[cols].copy()

        # cost_df から拾えるものを候補名順に探してマージ
        def _pick(name_candidates):
            for nm in name_candidates:
                if nm in getattr(cost_df, "columns", []):
                    part = cost_df[["product_name", "node_name", nm]].copy()
                    part = part.rename(columns={nm: name_candidates[0]})
                    part[name_candidates[0]] = pd.to_numeric(part[name_candidates[0]], errors="coerce").fillna(0.0)
                    return part
            # 無いときはゼロ列
            part = df[["product_name", "node_name"]].copy()
            part[name_candidates[0]] = 0.0
            return part

        WANT = {
            "revenue":                 ["revenue"],
            "profit":                  ["profit"],
            "cost":                    ["cost", "total_cost"],
            "logistics_costs":         ["logistics_costs", "cs_logistics_costs"],
            "warehouse_cost":          ["warehouse_cost", "cs_warehouse_cost"],
            "manufacturing_overhead":  ["manufacturing_overhead", "mfg_overhead", "cs_mfg_overhead"],
            "direct_materials_costs":  ["direct_materials_costs", "cs_direct_materials_costs"],
            "tax_portion":             ["tax_portion", "cs_tax_portion"],
        }

        for rep, cands in WANT.items():
            part = _pick(cands)
            df = df.merge(part, on=["product_name", "node_name"], how="left")

        # price（NOT NULL 対応）：TOBE 優先→ASIS→0
        tobe = pd.to_numeric(df["offering_price_TOBE"], errors="coerce")
        asis = pd.to_numeric(df["offering_price_ASIS"], errors="coerce")
        df["price"] = tobe.where(tobe > 0).combine_first(asis.where(asis > 0)).fillna(0.0)

        # 最後に欠損は 0
        df = df.fillna(0.0)

        # INSERT（NOT NULL な列をすべて含める）
        sql = (
            "INSERT INTO scenario_result_node "
            "(run_id, product_name, node_name, "
            " price, offering_price_ASIS, offering_price_TOBE, "
            " revenue, profit, cost, "
            " logistics_costs, warehouse_cost, manufacturing_overhead, "
            " direct_materials_costs, tax_portion) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        )
        for r in df.to_dict("records"):
            con.execute(sql, (
                run_id,
                r["product_name"], r["node_name"],
                float(r.get("price", 0.0)),
                float(r.get("offering_price_ASIS", 0.0)),
                float(r.get("offering_price_TOBE", 0.0)),
                float(r.get("revenue", 0.0)),
                float(r.get("profit", 0.0)),
                float(r.get("cost", 0.0)),
                float(r.get("logistics_costs", 0.0)),
                float(r.get("warehouse_cost", 0.0)),
                float(r.get("manufacturing_overhead", 0.0)),
                float(r.get("direct_materials_costs", 0.0)),
                float(r.get("tax_portion", 0.0)),
            ))

        con.commit()
        return run_id
    finally:
        con.close()


def save_run_results_OLD5(db_path: str,
                     scenario_id: Optional[str],
                     label: Optional[str]=None,
                     note: Optional[str]=None) -> str:
    con = sqlite3.connect(db_path)
    try:
        # 1) run レコード作成
        run_id = create_run(con, scenario_id, label=label, note=note)

        # 2) 価格フレーム
        price_df = build_offering_price_frame(db_path, scenario_id=scenario_id)

        # 3) コスト/数量（無ければ空）
        try:
            cost_df = build_cost_df_from_sql(db_path, scenario_id=scenario_id)
        except Exception:
            cost_df = pd.DataFrame()

        # ---------- サマリー計算（ロバスト） ----------
        def _pick_first_col(df: pd.DataFrame, candidates):
            for c in candidates:
                if c in getattr(df, "columns", []):
                    return c
            return None

        rev_col = _pick_first_col(cost_df, ["revenue", "total_revenue", "sales_revenue", "price_sales_shipped"])
        cst_col = _pick_first_col(cost_df, ["total_cost", "cost", "full_cost"])
        prf_col = _pick_first_col(cost_df, ["profit", "gross_profit"])

        # まず候補列から合計
        rev = _safe_sum(cost_df[rev_col]) if rev_col else 0.0
        cst = _safe_sum(cost_df[cst_col]) if cst_col else 0.0
        prf = _safe_sum(cost_df[prf_col]) if prf_col else (rev - cst if (rev or cst) else 0.0)

        # 追加フォールバック：コスト構成（円グラフで使う列）から再計算
        # これらは「金額（合計）」として保持されている想定
        COMPONENTS = [
            "direct_materials_costs", "tax_portion", "logistics_costs", "warehouse_cost",
            "marketing_promotion", "sales_admin_cost",
            "prod_indirect_labor", "prod_indirect_others",
            "direct_labor_costs", "depreciation_others", "manufacturing_overhead"
        ]
        existing_comp = [c for c in COMPONENTS if c in getattr(cost_df, "columns", [])]
        if existing_comp:
            comp_df = cost_df[existing_comp].apply(pd.to_numeric, errors="coerce").fillna(0.0)
            cost_from_comp = float(comp_df.sum().sum())  # 全ノードのコスト合計
        else:
            cost_from_comp = 0.0


        # --- helper ---
        def _num_series(df: pd.DataFrame, col: str) -> pd.Series:
            """df[col] を数値Seriesとして返す。列が無ければ空Series。"""
            if col in getattr(df, "columns", []):
                return pd.to_numeric(df[col], errors="coerce").fillna(0.0)
            return pd.Series([], dtype="float64")
        # --- end of helper ---

        profit_from_df = float(_num_series(cost_df, "profit").sum())
        #profit_from_df = float(pd.to_numeric(cost_df.get("profit", 0), errors="coerce").fillna(0.0).sum())



        rev_from_comp = cost_from_comp + profit_from_df  # 「コスト合計＋Profit＝売上」とみなす

        # 既存計算が0に近い場合はフォールバック値を採用
        if rev <= 0 and rev_from_comp > 0:
            rev = rev_from_comp
            cst = cost_from_comp
            prf = profit_from_df
        elif prf_col is None and (rev > 0 or cst > 0):
            # 利益列が無い場合は rev - cst にしておく
            prf = rev - cst

        prr = (prf / rev) if rev > 0 else 0.0

        con.execute(
            "INSERT INTO scenario_result_summary(run_id,total_revenue,total_cost,total_profit,profit_ratio) "
            "VALUES(?,?,?,?,?)",
            (run_id, rev, cst, prf, prr)
        )

        # ---------- ノード明細 ----------
        # 価格列
        cols = ["product_name","node_name","offering_price_ASIS","offering_price_TOBE"]
        df = price_df[cols].copy()

        # cost_df から拾える列を順にマージ（無ければ0列）
        def _part(name_candidates):
            for nm in name_candidates:
                if nm in getattr(cost_df, "columns", []):
                    part = cost_df[["product_name","node_name", nm]].copy()
                    part = part.rename(columns={nm: name_candidates[0]})
                    part[name_candidates[0]] = pd.to_numeric(part[name_candidates[0]], errors="coerce").fillna(0.0)
                    return part
            z = df[["product_name","node_name"]].copy()
            z[name_candidates[0]] = 0.0
            return z

        WANT = {
            "revenue":               ["revenue", "total_revenue", "sales_revenue", "price_sales_shipped"],
            "profit":                ["profit", "gross_profit"],
            "cost":                  ["cost", "total_cost", "full_cost"],
            "logistics_costs":       ["logistics_costs", "cs_logistics_costs"],
            "warehouse_cost":        ["warehouse_cost", "cs_warehouse_cost"],
            "manufacturing_overhead":["manufacturing_overhead", "mfg_overhead", "cs_mfg_overhead"],
            "direct_materials_costs":["direct_materials_costs", "cs_direct_materials_costs"],
            "tax_portion":           ["tax_portion", "cs_tax_portion"],
        }

        for rep, cands in WANT.items():
            df = df.merge(_part(cands), on=["product_name","node_name"], how="left")

        # さらに、ノード単位でも「コスト構成＋Profit」から revenue/cost/profit を補完
        if existing_comp:
            comp_cols_in_df = [c for c in existing_comp if c in df.columns]
            node_cost_comp = df[comp_cols_in_df].apply(pd.to_numeric, errors="coerce").fillna(0.0).sum(axis=1)
        else:
            node_cost_comp = pd.Series([0.0]*len(df))

        node_profit = pd.to_numeric(df.get("profit", 0.0), errors="coerce").fillna(0.0)
        node_rev_comp = node_cost_comp + node_profit

        # 既存が0のところだけ置き換え
        df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0.0)
        df["cost"]    = pd.to_numeric(df["cost"],    errors="coerce").fillna(0.0)
        df["profit"]  = pd.to_numeric(df["profit"],  errors="coerce").fillna(0.0)

        df.loc[df["revenue"]<=0, "revenue"] = node_rev_comp
        df.loc[df["cost"]   <=0, "cost"]    = node_cost_comp
        # 利益列がゼロで、revenue/cost がある場合は差分で補完
        need_pr = (df["profit"]<=0) & ((df["revenue"]>0) | (df["cost"]>0))
        df.loc[need_pr, "profit"] = df.loc[need_pr, "revenue"] - df.loc[need_pr, "cost"]

        # price（NOT NULL）: TOBE 優先→ASIS→0
        tobe = pd.to_numeric(df["offering_price_TOBE"], errors="coerce")
        asis = pd.to_numeric(df["offering_price_ASIS"], errors="coerce")
        df["price"] = tobe.where(tobe > 0).combine_first(asis.where(asis > 0)).fillna(0.0)

        df = df.fillna(0.0)

        sql = (
            "INSERT INTO scenario_result_node "
            "(run_id, product_name, node_name, "
            " price, offering_price_ASIS, offering_price_TOBE, "
            " revenue, profit, cost, "
            " logistics_costs, warehouse_cost, manufacturing_overhead, "
            " direct_materials_costs, tax_portion) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        )
        for r in df.to_dict("records"):
            con.execute(sql, (
                run_id,
                r["product_name"], r["node_name"],
                float(r.get("price", 0.0)),
                float(r.get("offering_price_ASIS", 0.0)),
                float(r.get("offering_price_TOBE", 0.0)),
                float(r.get("revenue", 0.0)),
                float(r.get("profit", 0.0)),
                float(r.get("cost", 0.0)),
                float(r.get("logistics_costs", 0.0)),
                float(r.get("warehouse_cost", 0.0)),
                float(r.get("manufacturing_overhead", 0.0)),
                float(r.get("direct_materials_costs", 0.0)),
                float(r.get("tax_portion", 0.0)),
            ))

        con.commit()
        return run_id
    finally:
        con.close()


# pysi/scenario/store.py から抜粋（関数全体を置き換え）
#from __future__ import annotations
#import sqlite3, datetime as dt
#from typing import Optional, List, Tuple
#import pandas as pd
#
#from pysi.evaluate.offering_price import build_offering_price_frame
#from pysi.evaluate.cost_df_loader import build_cost_df_from_sql

def _safe_sum_series(s: pd.Series) -> float:
    try:
        return float(pd.to_numeric(s, errors="coerce").fillna(0.0).sum())
    except Exception:
        return 0.0

def _sum_col(df: pd.DataFrame, candidates: List[str]) -> float:
    for c in candidates:
        if c in getattr(df, "columns", []):
            return _safe_sum_series(df[c])
    return 0.0

def _pick_first_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    for c in candidates:
        if c in getattr(df, "columns", []):
            return c
    return None

def save_run_results(db_path: str,
                     scenario_id: Optional[str],
                     label: Optional[str]=None,
                     note: Optional[str]=None,
                     # ← 追加：GUI から直接渡すためのオーバーライド
                     cost_df_override: Optional[pd.DataFrame]=None) -> str:
    con = sqlite3.connect(db_path)
    try:
        # run ヘッダ行の作成（あなたの create_run を利用）
        run_id = create_run(con, scenario_id, label=label, note=note)

        # 価格フレーム
        price_df = build_offering_price_frame(db_path, scenario_id=scenario_id)

        # コスト/数量フレーム（優先順：override → SQL）
        if cost_df_override is not None and isinstance(cost_df_override, pd.DataFrame) and not cost_df_override.empty:
            cost_df = cost_df_override.copy()
        else:
            try:
                cost_df = build_cost_df_from_sql(db_path, scenario_id=scenario_id)
            except Exception:
                cost_df = pd.DataFrame()

        # ========== Summary ==========
        # 列名のバリエーションを吸収
        rev = _sum_col(cost_df, ["revenue", "total_revenue",
                                 "sales_revenue",
                                 "price_sales_shipped", "cs_price_sales_shipped"])
        cst = _sum_col(cost_df, ["total_cost", "cost", "full_cost", "cs_cost_total"])
        prf = _sum_col(cost_df, ["profit", "gross_profit", "cs_profit"])

        # 末端ノードの売上だけでも拾う（revenue が 0 の場合）
        if rev == 0.0:
            node_col = _pick_first_col(cost_df, ["node_name", "node"])
            if node_col:
                try:
                    mask_cs = cost_df[node_col].astype(str).str.upper().str.startswith("CS_")
                    rev_cs = _sum_col(cost_df.loc[mask_cs], ["price_sales_shipped", "cs_price_sales_shipped"])
                    if rev_cs > 0:
                        rev = rev_cs
                        if prf == 0.0 and cst > 0.0:
                            prf = max(0.0, rev - cst)
                except Exception:
                    pass

        # 利益が 0 で rev/cst が取れているなら差分で
        if prf == 0.0 and (rev > 0.0 or cst > 0.0):
            prf = rev - cst

        prr = (prf / rev) if rev > 0 else 0.0

        con.execute(
            "INSERT INTO scenario_result_summary(run_id,total_revenue,total_cost,total_profit,profit_ratio) "
            "VALUES(?,?,?,?,?)",
            (run_id, rev, cst, prf, prr)
        )

        # ========== Node 明細 ==========
        # price_df から基本列
        base_cols = ["product_name","node_name","offering_price_ASIS","offering_price_TOBE"]
        df = price_df[base_cols].copy() if not price_df.empty else pd.DataFrame(columns=base_cols)

        # cost_df から拾えるものを正規化してマージ
        def _pick_to(df_cost: pd.DataFrame, rep: str, candidates: List[str]) -> pd.DataFrame:
            if df_cost is None or df_cost.empty:
                return pd.DataFrame(columns=["product_name","node_name", rep])
            for nm in candidates:
                if nm in getattr(df_cost, "columns", []):
                    part = df_cost[["product_name","node_name", nm]].rename(columns={nm: rep}).copy()
                    part[rep] = pd.to_numeric(part[rep], errors="coerce").fillna(0.0)
                    return part
            # 無いときは空
            return pd.DataFrame(columns=["product_name","node_name", rep])

        WANT = {
            "revenue":                ["revenue","price_sales_shipped","cs_price_sales_shipped"],
            "profit":                 ["profit","cs_profit","gross_profit"],
            "cost":                   ["cost","total_cost","full_cost","cs_cost_total"],
            "logistics_costs":        ["logistics_costs","cs_logistics_costs"],
            "warehouse_cost":         ["warehouse_cost","cs_warehouse_cost"],
            "manufacturing_overhead": ["manufacturing_overhead","mfg_overhead","cs_mfg_overhead"],
            "direct_materials_costs": ["direct_materials_costs","materials_costs","cs_direct_materials_costs","direct_materials"],
            "tax_portion":            ["tax_portion","tariff_portion","cs_tax_portion"],
        }

        for rep, cands in WANT.items():
            part = _pick_to(cost_df, rep, cands)
            if part.empty and not df.empty:
                # 0.0 の列を作る
                part = df[["product_name","node_name"]].copy()
                part[rep] = 0.0
            df = df.merge(part, on=["product_name","node_name"], how="left") if not df.empty else part

        # 保存用の price 列（NOT NULL を満たす）
        tobe = pd.to_numeric(df.get("offering_price_TOBE", pd.Series()), errors="coerce")
        asis = pd.to_numeric(df.get("offering_price_ASIS", pd.Series()), errors="coerce")
        price = tobe.where(tobe > 0).combine_first(asis.where(asis > 0)).fillna(0.0)
        df["price"] = price

        df = df.fillna(0.0)

        sql = (
            "INSERT INTO scenario_result_node "
            "(run_id, product_name, node_name, "
            " price, offering_price_ASIS, offering_price_TOBE, "
            " revenue, profit, cost, "
            " logistics_costs, warehouse_cost, manufacturing_overhead, "
            " direct_materials_costs, tax_portion) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        )
        for r in df.to_dict("records"):
            con.execute(sql, (
                run_id,
                r.get("product_name",""), r.get("node_name",""),
                float(r.get("price", 0.0)),
                float(r.get("offering_price_ASIS", 0.0)),
                float(r.get("offering_price_TOBE", 0.0)),
                float(r.get("revenue", 0.0)),
                float(r.get("profit", 0.0)),
                float(r.get("cost", 0.0)),
                float(r.get("logistics_costs", 0.0)),
                float(r.get("warehouse_cost", 0.0)),
                float(r.get("manufacturing_overhead", 0.0)),
                float(r.get("direct_materials_costs", 0.0)),
                float(r.get("tax_portion", 0.0)),
            ))

        con.commit()
        return run_id
    finally:
        con.close()
