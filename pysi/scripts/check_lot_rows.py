# pysi/scripts/check_lot_rows.py
# starter
# python -m pysi.scripts.check_lot_rows --db var\psi.sqlite --scenario Baseline --node CS_CAL --product CAL_RICE_1
import argparse, sqlite3, pathlib
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="var/psi.sqlite")
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--node", required=True)
    ap.add_argument("--product", required=True)
    args = ap.parse_args()
    p = pathlib.Path(args.db).resolve()
    con = sqlite3.connect(str(p))
    con.row_factory = sqlite3.Row
    sid = con.execute("SELECT id FROM scenario WHERE name=?", (args.scenario,)).fetchone()
    nid = con.execute("SELECT id FROM node WHERE name=?", (args.node,)).fetchone()
    pid = con.execute("SELECT id FROM product WHERE name=?", (args.product,)).fetchone()
    if not sid or not nid or not pid:
        print("[ERR] sid/nid/pid not found:", sid, nid, pid)
        return
    sid, nid, pid = int(sid[0]), int(nid[0]), int(pid[0])
    n_lot = con.execute(
        "SELECT COUNT(*) FROM lot WHERE scenario_id=? AND node_id=? AND product_id=?",
        (sid, nid, pid),
    ).fetchone()[0]
    print({"db": str(p), "scenario": args.scenario, "node": args.node, "product": args.product,
           "lot_rows": n_lot})
    if n_lot:
        rows = con.execute(
            """SELECT iso_year, iso_week, substr(lot_id,1,40) AS lot_id
               FROM lot
               WHERE scenario_id=? AND node_id=? AND product_id=?
               ORDER BY iso_year, iso_week, lot_id LIMIT 5""",
            (sid, nid, pid)
        ).fetchall()
        for r in rows:
            print("  sample:", dict(r))
    con.close()
if __name__ == "__main__":
    main()
