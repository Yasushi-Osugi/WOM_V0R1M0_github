# tools/normalize_ws.py

# starter
#1.まず差分確認（書き込みなし）
#python -X utf8 tools\normalize_ws.py --root .\pysi --max-blank 2 --after-def 1 --after-class 1
#2.反映（2 行までに縮約）
#python -X utf8 tools\normalize_ws.py --root .\pysi --apply --max-blank 2 --after-def 1 --after-class 1
#3.もっと詰めたい場合（1 行まで）
#python -X utf8 tools\normalize_ws.py --root .\pysi --apply --max-blank 1 --after-def 1 --after-class 1
#4.単一ファイルだけ試す
#python -X utf8 tools\normalize_ws.py --root .\pysi\gui\app.py --apply --max-blank 1


from __future__ import annotations
import argparse, re, sys, io
from pathlib import Path

DEFAULT_IGNORE = {".git", "venv", ".venv", "__pycache__", "node_modules", "build", "dist"}

def _read_text_safely(path: Path) -> tuple[str, str]:
    b = path.read_bytes()
    # keep original newline style
    newline = "\r\n" if b.count(b"\r\n") and b.count(b"\n") == b.count(b"\r\n") else "\n"
    # BOM / enc
    if b.startswith(b"\xff\xfe"):
        s = b.decode("utf-16-le")
    elif b.startswith(b"\xfe\xff"):
        s = b.decode("utf-16-be")
    elif b.startswith(b"\xef\xbb\xbf"):
        s = b.decode("utf-8-sig")
    else:
        for enc in ("utf-8", "cp932", "latin-1"):
            try:
                s = b.decode(enc); break
            except UnicodeDecodeError:
                continue
        else:
            s = b.decode("utf-8", errors="replace")
    # normalize to \n for processing
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s, newline

def _write_text(path: Path, text: str, newline_style: str):
    text = text.replace("\n", newline_style)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)

def iter_py_files(target: Path, ignore: set[str]):
    if target.is_file():
        yield target
        return
    for p in target.rglob("*.py"):
        if any(part in ignore for part in p.parts):
            continue
        yield p

def normalize_text(src: str, max_blank: int, after_def: int, after_class: int) -> str:
    out = src

    # 1) strip trailing spaces/tabs
    out = re.sub(r"[ \t]+(\n)", r"\1", out)

    # 2) collapse long blank runs (3+ -> max_blank)
    out = re.sub(r"(?:[ \t]*\n){%d,}" % (max_blank + 1), "\n" * max_blank, out)

    # 3) after def/class headers: keep at most N blank lines
    if after_def is not None:
        out = re.sub(
            r"(^[ \t]*def\b[^\n]*\n)(?:[ \t]*\n){%d,}" % (after_def + 1),
            r"\1" + ("\n" * after_def),
            out,
            flags=re.M,
        )
    if after_class is not None:
        out = re.sub(
            r"(^[ \t]*class\b[^\n]*\n)(?:[ \t]*\n){%d,}" % (after_class + 1),
            r"\1" + ("\n" * after_class),
            out,
            flags=re.M,
        )

    return out

def main():
    ap = argparse.ArgumentParser(description="Normalize blank lines/trailing spaces safely.")
    ap.add_argument("--root", default=".", help="file or directory")
    ap.add_argument("--apply", action="store_true", help="write changes")
    ap.add_argument("--max-blank", type=int, default=2, help="allow at most this many consecutive blank lines")
    ap.add_argument("--after-def", type=int, default=1, help="blank lines allowed right after a def header")
    ap.add_argument("--after-class", type=int, default=1, help="blank lines allowed right after a class header")
    ap.add_argument("--ignore", nargs="*", default=list(DEFAULT_IGNORE))
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    target = Path(args.root).resolve()
    touched = 0

    for f in iter_py_files(target, set(args.ignore)):
        src, nl = _read_text_safely(f)
        out = normalize_text(src, args.max_blank, args.after_def, args.after_class)
        if out != src:
            touched += 1
            if args.apply:
                _write_text(f, out, nl)
            if args.verbose and not args.apply:
                sys.stdout.write(f"--- {f}\n")

    print(f"[OK] files changed: {touched}")

if __name__ == "__main__":
    main()

