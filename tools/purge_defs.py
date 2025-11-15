# tools/purge_defs.py

# starter
#python -X utf8 tools\purge_defs.py --root .\pysi --diff --verbose --pattern "_BK" --regex-fallback > 251005_bk.diff.txt
#python -X utf8 tools\purge_defs.py --root .\pysi --apply --verbose --pattern "_BK" --regex-fallback

#python -X utf8 tools\purge_defs.py --root .\pysi --diff --verbose > 251005_bk.diff.txt
#python -X utf8 tools\purge_defs.py --root .\pysi --apply --verbose --collapse-blank

# tools/purge_defs.py
#
# 使い方（乾燥走行 / 実適用）:
#   python -X utf8 tools\purge_defs.py --root .\pysi --diff --verbose --pattern "_BK" --regex-fallback > 251005_bk.diff.txt
#   python -X utf8 tools\purge_defs.py --root .\pysi --apply --verbose --pattern "_BK" --regex-fallback --collapse-blank
#
from __future__ import annotations
import argparse, re, sys, difflib
from pathlib import Path
import libcst as cst

DEFAULT_IGNORE = {".git", "venv", ".venv", "__pycache__", "node_modules", "build", "dist"}

def _read_text_safely(path: Path) -> tuple[str, str]:
    """return (text, newline_style) where newline_style is '\r\n' or '\n'"""
    b = path.read_bytes()
    # detect newline style
    newline = "\r\n" if b.count(b"\r\n") > 0 and b.count(b"\n") == b.count(b"\r\n") else "\n"
    # encodings with BOM
    if b.startswith(b"\xff\xfe"):
        s = b.decode("utf-16-le")
    elif b.startswith(b"\xfe\xff"):
        s = b.decode("utf-16-be")
    elif b.startswith(b"\xef\xbb\xbf"):
        s = b.decode("utf-8-sig")
    else:
        for enc in ("utf-8", "cp932", "latin-1"):
            try:
                s = b.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            s = b.decode("utf-8", errors="replace")
    # normalize to '\n' for CST
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s, newline

def _write_text(path: Path, text: str, newline_style: str):
    txt = text.replace("\n", newline_style)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(txt)

class DropOldDefs(cst.CSTTransformer):
    def __init__(self, rx: re.Pattern, verbose: bool):
        self.rx = rx
        self.verbose = verbose
        self.matched: list[str] = []

    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef):
        name = original_node.name.value
        if self.rx.search(name):
            if self.verbose:
                self.matched.append(f"def {name}")
            return cst.RemoveFromParent()
        return updated_node

    def leave_AsyncFunctionDef(self, original_node: cst.AsyncFunctionDef, updated_node: cst.AsyncFunctionDef):
        name = original_node.name.value
        if self.rx.search(name):
            if self.verbose:
                self.matched.append(f"async def {name}")
            return cst.RemoveFromParent()
        return updated_node

def iter_py_files(root: Path, ignore: set[str]):
    for p in root.rglob("*.py"):
        if any(part in ignore for part in p.parts):
            continue
        yield p

def _collapse_blank_runs(s: str, max_run: int = 1) -> str:
    # 3行以上の連続空行を max_run に縮める
    return re.sub(r"\n{"+str(max_run+1)+r",}", "\n"*max_run, s)

# -------- regex fallback (CSTがパースできないファイル用) --------
_DEF_RE = re.compile(r'^(\s*)(?:async\s+def|def)\s+([A-Za-z_]\w*)\s*\([^)]*\)\s*:\s*(#.*)?$')
_DECOR_RE = re.compile(r'^(\s*)@')

def _indent_width(line: str) -> int:
    # tabsは4幅想定で展開
    return len(line.replace("\t", "    ")) - len(line.replace("\t", "    ").lstrip())

def _regex_drop_functions(text: str, rx: re.Pattern, verbose: bool) -> tuple[str, list[str]]:
    """
    def/async def のシグネチャ行と、その直上のデコレータ行群、そして
    同じ/浅いインデントに戻る直前までのブロックをまるごと削除。
    """
    lines = text.splitlines(True)
    n = len(lines)
    i = 0
    removed_names: list[str] = []
    out: list[str] = []

    while i < n:
        m = _DEF_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue

        def_indent = _indent_width(m.group(0))
        func_name = m.group(2)

        if not rx.search(func_name):
            # この関数は対象外
            out.append(lines[i])
            i += 1
            continue

        # 対象: 直上のデコレータ群も巻き取る
        start = i
        j = i - 1
        while j >= 0:
            dm = _DECOR_RE.match(lines[j])
            if not dm:
                break
            # 同じインデントのデコレータだけ巻き取る
            if _indent_width(lines[j]) == def_indent:
                start = j
                j -= 1
            else:
                break

        # ブロック終了行（次の非空行でインデント <= def_indent）を探す
        k = i + 1
        while k < n:
            if lines[k].strip() == "":
                k += 1
                continue
            if _indent_width(lines[k]) <= def_indent:
                break
            k += 1

        if verbose:
            removed_names.append(func_name)
        # start..k-1 までスキップ（=削除）
        i = k

    return "".join(out), removed_names
# ---------------------------------------------------------------

def process_file(path: Path, rx: re.Pattern, apply: bool, show_diff: bool,
                 verbose: bool, collapse_blank: bool, regex_fallback: bool) -> bool:
    src, nl = _read_text_safely(path)

    # まずCSTで試みる
    try:
        mod = cst.parse_module(src)
        tr = DropOldDefs(rx, verbose)
        new = mod.visit(tr)
        out = new.code
        matched = tr.matched[:]
        cst_ok = True
    except Exception as e:
        if verbose:
            print(f"[WARN] CST parse failed: {path} ({e})", file=sys.stderr)
        cst_ok = False
        out = src
        matched = []

    # CSTでダメ & フォールバックONなら正規表現で削除
    if (not cst_ok) and regex_fallback:
        out, names = _regex_drop_functions(src, rx, verbose)
        matched.extend([f"def {n}" for n in names])

    if collapse_blank and out != src:
        out = _collapse_blank_runs(out, max_run=1)

    if out == src:
        # マッチゼロでも verbose ならヒット名を表示
        if verbose and matched:
            print(f"[INFO] {path} matched but no textual diff?", file=sys.stderr)
        return False

    if show_diff or not apply:
        diff = difflib.unified_diff(
            src.splitlines(keepends=True),
            out.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path) + " (updated)",
        )
        sys.stdout.writelines(diff)

    if verbose and matched:
        print(f"[HIT] {path}: " + ", ".join(matched), file=sys.stderr)

    if apply:
        _write_text(path, out, nl)
    return True

def main():
    ap = argparse.ArgumentParser(description="Remove *_OLD / *_BK functions safely (LibCST + regex fallback).")
    ap.add_argument("--root", default=".", help="project root or file path")
    # 末尾に数字やアンダースコアが続くケースも拾う既定パターン（例: setup_ui_BK250925）
    ap.add_argument("--pattern", default=r"_(?:OLD|BK)(?:$|[_\d])", help="regex for names to remove")
    ap.add_argument("--apply", action="store_true", help="write changes to files")
    ap.add_argument("--diff", action="store_true", help="print unified diff")
    ap.add_argument("--ignore", nargs="*", default=list(DEFAULT_IGNORE), help="dirs to ignore")
    ap.add_argument("--verbose", action="store_true", help="print matched names / warnings")
    ap.add_argument("--collapse-blank", action="store_true", help="shrink long blank runs")
    ap.add_argument("--regex-fallback", action="store_true", help="use regex fallback on CST parse failures")
    args = ap.parse_args()

    target = Path(args.root).resolve()
    files = [target] if target.is_file() else list(iter_py_files(target, set(args.ignore)))
    rx = re.compile(args.pattern)

    touched = 0
    for f in files:
        changed = process_file(
            f, rx,
            apply=args.apply,
            show_diff=(args.diff or (not args.apply)),
            verbose=args.verbose,
            collapse_blank=args.collapse_blank,
            regex_fallback=args.regex_fallback,
        )
        if changed:
            touched += 1
    print(f"[OK] files changed: {touched}")

if __name__ == "__main__":
    main()
