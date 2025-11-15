# pysi/evaluate/pmpl_propagate.py
# starter
#shell
## OUT/IN 両方を更新、既存は保持（0の所だけ埋める）
#python -m pysi.evaluate.pmpl_propagate --db .\var\psi.sqlite --mode both
#
## すべて上書き（CSVの矛盾を消してクリーンにしたい時）
#python -m pysi.evaluate.pmpl_propagate --db .\var\psi.sqlite --mode both --overwrite
#GUI 側では build_cost_df_from_sql() の前に 一行呼べばOK：
#from pysi.evaluate.pmpl_propagate import rebuild_pmpl
#rebuild_pmpl(db_path, mode="both", overwrite=False)
#self.cost_df = build_cost_df_from_sql(db_path)
#このversionで解決できること
#bom_qty が無いDBでもエラーにならない（参照自体を避ける）
#INネットは「数量=1.0」の簡易集約で回る（BOM導入は任意）
#将来BOMを導入したら、列を追加するだけで即活用可能
#将来BOM対応する場合のDDL（必要になった時だけ実行）：
#ALTER TABLE product_edge ADD COLUMN bom_qty REAL NOT NULL DEFAULT 1.0;
#もし “IN 伝播を今は完全に切る” なら
#GUI側の _ensure_cost_df() で一時的に：
#from pysi.evaluate.pmpl_propagate import rebuild_pmpl
#rebuild_pmpl(db_path, mode="out", overwrite=False)  # ← 'both' から 'out' に
#self.cost_df = build_cost_df_from_sql(db_path)
#でもOKです（よりシンプル）。
# pysi/evaluate/pmpl_propagate.py
import sqlite3
import argparse
from typing import Iterable, Tuple, Dict, Any
def _exec(conn: sqlite3.Connection, sql: str, args: Iterable[Tuple]=()):
    cur = conn.cursor()
    if args:
        cur.executemany(sql, args)
    else:
        cur.execute(sql)
    conn.commit()
    cur.close()
def _fetchall(conn: sqlite3.Connection, sql: str, params: Tuple=()) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows
def _ensure_tables(conn: sqlite3.Connection):
    need = ["price_tag","product_edge","tariff","price_money_per_lot"]
    cur = conn.cursor()
    for t in need:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,))
        if not cur.fetchone():
            raise RuntimeError(f"[PMPL] missing table: {t}")
    cur.close()
def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    cur.close()
    return column in cols
def _upsert_pmpl(conn: sqlite3.Connection, rows: Iterable[Tuple[str,str,float,float]], overwrite: bool):
    """
    rows: (node_name, product_name, dm_money, tariff_money)
    overwrite=False: 既存が正(>0)なら維持
    """
    cur = conn.cursor()
    for node, prod, dm, tf in rows:
        cur.execute("""
            SELECT direct_materials_costs, tariff_cost
              FROM price_money_per_lot
             WHERE node_name=? AND product_name=?
        """, (node, prod))
        rec = cur.fetchone()
        if rec is None:
            cur.execute("""
                INSERT INTO price_money_per_lot(node_name, product_name, direct_materials_costs, tariff_cost)
                VALUES (?,?,?,?)
            """, (node, prod, float(dm), float(tf)))
        else:
            old_dm = rec[0] or 0.0
            old_tf = rec[1] or 0.0
            new_dm = float(dm) if (overwrite or old_dm <= 0.0) else old_dm
            new_tf = float(tf) if (overwrite or old_tf <= 0.0) else old_tf
            if (new_dm != old_dm) or (new_tf != old_tf):
                cur.execute("""
                    UPDATE price_money_per_lot
                       SET direct_materials_costs=?, tariff_cost=?
                     WHERE node_name=? AND product_name=?
                """, (new_dm, new_tf, node, prod))
    conn.commit()
    cur.close()
def propagate_outbound(conn: sqlite3.Connection, overwrite: bool=False) -> int:
    """
    OUTネットの規則：
      子の購買 = 親ASIS
      子の関税 = 親ASIS × tariff_rate(parent->child)
    """
    sql = """
    SELECT
      pe.product_name          AS product_name,
      pe.parent_name           AS parent_name,
      pe.child_name            AS child_name,
      COALESCE(ptp.price, 0.0) AS parent_asis,
      COALESCE(t.tariff_rate, 0.0) AS tariff_rate
    FROM product_edge pe
    LEFT JOIN price_tag ptp
      ON ptp.product_name = pe.product_name
     AND ptp.node_name    = pe.parent_name
     AND ptp.tag          = 'ASIS'
    LEFT JOIN tariff t
      ON t.product_name = pe.product_name
     AND t.from_node    = pe.parent_name
     AND t.to_node      = pe.child_name
    WHERE pe.bound='OUT';
    """
    rows = _fetchall(conn, sql)
    upserts = []
    for r in rows:
        prod = r["product_name"]
        child = r["child_name"]
        p = float(r["parent_asis"] or 0.0)
        rate = float(r["tariff_rate"] or 0.0)
        dm = p               # 親ASISが子DM
        tf = p * rate        # 関税
        upserts.append((child, prod, dm, tf))
    _upsert_pmpl(conn, upserts, overwrite=overwrite)
    return len(upserts)
def propagate_inbound(conn: sqlite3.Connection, overwrite: bool=False) -> int:
    """
    INネットの規則（BOM集約）：
      親の購買 = Σ (子ASIS × bom_qty)      ※bom_qty列が無い場合は 1.0 で代用（ノーBOM運用）
      親の関税 = Σ (子ASIS × tariff(child->parent) × bom_qty)
    """
    has_bom = _table_has_column(conn, "product_edge", "bom_qty")
    if has_bom:
        sql = """
        SELECT
          pe.product_name  AS product_name,
          pe.parent_name   AS node_name,
          SUM( COALESCE(ptc.price,0.0) * COALESCE(pe.bom_qty,1.0) ) AS dm_money,
          SUM( COALESCE(ptc.price,0.0) * COALESCE(tr.tariff_rate,0.0) * COALESCE(pe.bom_qty,1.0) ) AS tariff_money
        FROM product_edge pe
        LEFT JOIN price_tag ptc
          ON ptc.product_name = pe.product_name
         AND ptc.node_name    = pe.child_name
         AND ptc.tag          = 'ASIS'
        LEFT JOIN tariff tr
          ON tr.product_name = pe.product_name
         AND tr.from_node    = pe.child_name
         AND tr.to_node      = pe.parent_name
        WHERE pe.bound='IN'
        GROUP BY pe.product_name, pe.parent_name;
        """
    else:
        # ★ bom_qty が無い場合のノーBOM版（全て 1.0 として集約）
        sql = """
        SELECT
          pe.product_name  AS product_name,
          pe.parent_name   AS node_name,
          SUM( COALESCE(ptc.price,0.0) ) AS dm_money,
          SUM( COALESCE(ptc.price,0.0) * COALESCE(tr.tariff_rate,0.0) ) AS tariff_money
        FROM product_edge pe
        LEFT JOIN price_tag ptc
          ON ptc.product_name = pe.product_name
         AND ptc.node_name    = pe.child_name
         AND ptc.tag          = 'ASIS'
        LEFT JOIN tariff tr
          ON tr.product_name = pe.product_name
         AND tr.from_node    = pe.child_name
         AND tr.to_node      = pe.parent_name
        WHERE pe.bound='IN'
        GROUP BY pe.product_name, pe.parent_name;
        """
    rows = _fetchall(conn, sql)
    upserts = []
    for r in rows:
        prod = r["product_name"]
        node = r["node_name"]
        dm = float(r["dm_money"] or 0.0)
        tf = float(r["tariff_money"] or 0.0)
        upserts.append((node, prod, dm, tf))
    _upsert_pmpl(conn, upserts, overwrite=overwrite)
    return len(upserts)
def rebuild_pmpl(db_path: str, mode: str="both", overwrite: bool=False) -> Dict[str, Any]:
    """
    mode: 'out' | 'in' | 'both'
    overwrite: 既存PMPLを上書きするか（Falseなら空/0のみ更新）
    """
    conn = sqlite3.connect(db_path)
    try:
        _ensure_tables(conn)
        cnt_out = cnt_in = 0
        if mode in ("out","both"):
            cnt_out = propagate_outbound(conn, overwrite=overwrite)
        if mode in ("in","both"):
            cnt_in = propagate_inbound(conn, overwrite=overwrite)
        return {"updated_out": cnt_out, "updated_in": cnt_in}
    finally:
        conn.close()
# ---------- CLI ----------
def _parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="Path to psi.sqlite")
    p.add_argument("--mode", default="both", choices=["out","in","both"])
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing PMPL values")
    return p.parse_args()
if __name__ == "__main__":
    args = _parse_args()
    res = rebuild_pmpl(args.db, mode=args.mode, overwrite=args.overwrite)
    print(f"[PMPL] done. OUT={res['updated_out']}, IN={res['updated_in']}")
