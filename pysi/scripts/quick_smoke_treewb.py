# pysi/scripts/quick_smoke_treewb.py
# Starter
#
#リポジトリ直下で モジュール実行（推奨）
# python -m pysi.scripts.quick_smoke_treewb
#
#必要に応じて指定：
# python -m pysi.scripts.quick_smoke_treewb --db var\psi.sqlite --scenario Baseline --node CS_CAL --product CAL_RICE_1
#
#直接実行
# python pysi\scripts\quick_smoke_treewb.py --db var\psi.sqlite --scenario Baseline --node CS_CAL --product CAL_RICE_1
#
#メモ
# ModuleNotFoundError: pysi が出たら、リポジトリ直下で実行しているか確認（または pip install -e . 済みか確認）。
# --db を省略すると <repo>/var/psi.sqlite を自動推定します（他レイアウトなら --db を明示してください）。
import argparse, sqlite3, inspect
from pathlib import Path
from pysi.io import tree_writeback as tw
def get_sid(con: sqlite3.Connection, name: str) -> int:
    row = con.execute("SELECT id FROM scenario WHERE name=?", (name,)).fetchone()
    if not row:
        raise SystemExit(f"[ERR] scenario not found: {name}")
    return int(row[0])
def main():
    ap = argparse.ArgumentParser(description="smoke test for tree_writeback")
    ap.add_argument("--db", help="SQLite DB path (default: <repo>/var/psi.sqlite)")
    ap.add_argument("--scenario", default="Baseline")
    ap.add_argument("--node", default="CS_CAL")
    ap.add_argument("--product", default="CAL_RICE_1")
    args = ap.parse_args()
    # デフォルトDBは <repo>/var/psi.sqlite を推定（このファイルが pysi/scripts 配下にある前提）
    default_db = Path(__file__).resolve().parents[2] / "var" / "psi.sqlite"
    db_path = Path(args.db) if args.db else default_db
    print("module path:", tw.__file__)
    print("has write_both_layers_for_pair:", hasattr(tw, "write_both_layers_for_pair"))
    print("has compute_leaf_S_for_pair   :", hasattr(tw, "compute_leaf_S_for_pair"))
    print("signature:", inspect.signature(tw.write_both_layers_for_pair))
    con = sqlite3.connect(str(db_path))
    try:
        sid = get_sid(con, args.scenario)
        print({"db": str(db_path.resolve()), "scenario": args.scenario, "sid": sid,
               "node": args.node, "product": args.product})
        res = tw.write_both_layers_for_pair(con, sid, args.node, args.product)
        print("result:", res)
    finally:
        con.close()
if __name__ == "__main__":
    main()
