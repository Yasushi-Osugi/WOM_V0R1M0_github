# tools/migrate_results_schema.py

#starter
#python -X utf8 tools\migrate_results_schema.py

#checker
#python -c "import sqlite3;con=sqlite3.connect(r'var\\psi.sqlite');print(con.execute('PRAGMA table_info(scenario_result_summary)').fetchall());con.close()"


from __future__ import annotations
import sqlite3

DB = r"var/psi.sqlite"

def cols(con, table):
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]

def ensure_col(con, table, col, decl):
    if col not in cols(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

def main():
    con = sqlite3.connect(DB)

    # scenario_run: label, note（保険）
    ensure_col(con, "scenario_run", "label", "TEXT")
    ensure_col(con, "scenario_run", "note",  "TEXT")

    # scenario_result_summary: total_cost を追加
    # 既存: run_id, total_revenue, total_profit, profit_ratio …というDBがある想定
    ensure_col(con, "scenario_result_summary", "total_cost", "REAL DEFAULT 0.0")

    # scenario_result_node: KPI 列が無い場合は追加
    ensure_col(con, "scenario_result_node", "revenue", "REAL DEFAULT 0.0")
    ensure_col(con, "scenario_result_node", "cost",    "REAL DEFAULT 0.0")
    ensure_col(con, "scenario_result_node", "profit",  "REAL DEFAULT 0.0")


    # 既存の ensure_col(...) 群の直後に追加
    ensure_col(con, "scenario_result_node", "offering_price_ASIS", "REAL DEFAULT 0.0")
    ensure_col(con, "scenario_result_node", "offering_price_TOBE", "REAL DEFAULT 0.0")


    con.commit()

    print("[OK] migrated")
    print("scenario_run         =>", cols(con, "scenario_run"))
    print("scenario_result_summary =>", cols(con, "scenario_result_summary"))
    print("scenario_result_node =>", cols(con, "scenario_result_node"))

    con.close()

if __name__ == "__main__":
    main()
