
# pysi/db/sync_sqlite.py
# starter
#python .\tools\sync_sqlite.py `
#  --src "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\data\pysi.sqlite3" `
#  --dst "C:\Users\ohsug\PySI_V0R8_SQL_040_test_GUI_switch2\var\psi.sqlite"
#python .\main.py --backend sql --skip-orchestrate
# tools/sync_sqlite.py # GPT generated name
import argparse, datetime, os, shutil, sqlite3
from pathlib import Path
def _backup_path(p: Path) -> Path:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return p.with_name(p.name + f".bak_{ts}")
def clone_sqlite(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        bk = _backup_path(dst)
        shutil.copy2(dst, bk)
        print(f"[INFO] backup created: {bk}")
    with sqlite3.connect(str(src)) as s, sqlite3.connect(str(dst)) as d:
        s.backup(d)
    with sqlite3.connect(str(dst)) as d:
        ok = d.execute("PRAGMA integrity_check;").fetchone()[0]
        print(f"[CHECK] integrity_check: {ok}")
    print(f"[DONE] cloned {src} -> {dst}")
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    args = ap.parse_args()
    clone_sqlite(Path(args.src), Path(args.dst))
