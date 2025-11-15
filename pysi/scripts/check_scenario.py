# pysi/scripts/check_scenario.py
# 起動方法
## lot_sizeの状況確認
#python -m pysi.scripts.check_lot_size --db var\psi.sqlite
#
## 一括更新（例：1000に）
#python -m pysi.scripts.update_lot_size --db var\psi.sqlite --value 1000
#
## 再確認
#python -m pysi.scripts.check_lot_size --db var\psi.sqlite
#このあとで
# python -m pysi.app.orchestrator --mode leaf --write-all-nodes
#  を流すと、lot分割が粗くなって rows がグッと減る
import argparse, sqlite3
from pathlib import Path
def resolve_db_path(arg: str | None) -> Path:
    candidates = []
    if arg:
        p = Path(arg)
        candidates.append(p if p.is_absolute() else Path.cwd() / p)
    # repo root の var/psi.sqlite をフォールバック候補に
    candidates.append(Path(__file__).resolve().parents[1] / "var" / "psi.sqlite")
    for c in candidates:
        if c.exists():
            return c
    # 最後の候補を返す（存在しなくてもエラーとして落ちる）
    return candidates[0]
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", help="SQLite DB path (e.g. var/psi.sqlite)")
    ap.add_argument("--scenario", default="Baseline")
    args = ap.parse_args()
    db_path = resolve_db_path(args.db)
    print(f"[info] DB = {db_path}")
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON;")
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "scenario" not in tables:
        print("[ERR] 'scenario' テーブルが見つかりません。schema_core_only.sql を適用しましたか？")
        return 2
    row = con.execute(
        "SELECT id, plan_year_st, plan_range FROM scenario WHERE name=?",
        (args.scenario,)
    ).fetchone()
    if not row:
        print(f"[ERR] scenario が見つかりません: {args.scenario}")
        return 3
    sid = row["id"]
    cal_weeks = con.execute("SELECT COUNT(*) FROM calendar_iso").fetchone()[0]
    weekly_rows = con.execute(
        "SELECT COUNT(*) FROM weekly_demand WHERE scenario_id=?", (sid,)
    ).fetchone()[0]
    lotb_rows = con.execute(
        "SELECT COUNT(*) FROM lot_bucket WHERE scenario_id=?", (sid,)
    ).fetchone()[0]
    nodes = [r[0] for r in con.execute(
        """SELECT DISTINCT n.name
           FROM weekly_demand w JOIN node n ON n.id=w.node_id
           WHERE w.scenario_id=?""", (sid,))]
    prods = [r[0] for r in con.execute(
        """SELECT DISTINCT p.name
           FROM weekly_demand w JOIN product p ON p.id=w.product_id
           WHERE w.scenario_id=?""", (sid,))]
    print({
        "scenario": args.scenario,
        "id": sid,
        "plan_year_st": row["plan_year_st"],
        "plan_range": row["plan_range"],
        "calendar_weeks": cal_weeks,
        "weekly_rows": weekly_rows,
        "lot_bucket_rows": lotb_rows,
        "nodes": nodes,
        "products": prods,
    })
if __name__ == "__main__":
    main()
