# calendar_iso_check.py
# python -m pysi.scripts.calendar_iso_check --db var\psi.sqlite
import argparse, sqlite3, pathlib
def main(db="var/psi.sqlite"):
    dbp = pathlib.Path(db)
    con = sqlite3.connect(dbp)
    cur = con.cursor()
    n = cur.execute("SELECT COUNT(*) FROM calendar_iso").fetchone()[0]
    first = cur.execute(
        "SELECT iso_year,iso_week FROM calendar_iso ORDER BY week_index LIMIT 1"
    ).fetchone()
    last  = cur.execute(
        "SELECT iso_year,iso_week FROM calendar_iso ORDER BY week_index DESC LIMIT 1"
    ).fetchone()
    print({
        "db": str(dbp.resolve()),
        "weeks": n,
        "first": f"{first[0]}-W{first[1]:02d}" if first else None,
        "last":  f"{last[0]}-W{last[1]:02d}"  if last  else None,
    })
    con.close()
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="var/psi.sqlite")
    args = ap.parse_args()
    main(args.db)
