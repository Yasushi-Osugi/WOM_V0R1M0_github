# pysi/scripts/db_optimize.py
# starter
# python -m pysi.scripts.db_optimize --db var\psi.sqlite
import argparse, sqlite3, pathlib
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="var/psi.sqlite")
    args = ap.parse_args()
    p = pathlib.Path(args.db).resolve()
    con = sqlite3.connect(str(p))
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("ANALYZE;")
    con.execute("PRAGMA optimize;")
    con.close()
    print(f"[OK] ANALYZE/optimize: {p}")
if __name__ == "__main__":
    main()
