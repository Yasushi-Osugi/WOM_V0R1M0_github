# tools/purge_old_defs.py

# starter
#
#cd C:\Users\ohsug\PySI_V0R8_SQL_050_hook
#python tools\purge_old_defs.py --root .\pysi --diff
#
#python tools\purge_old_defs.py --root .\pysi --apply

from __future__ import annotations
import argparse, re, sys, difflib
from pathlib import Path
import libcst as cst
import libcst.matchers as m


# 先頭付近の import 群の近くに追加
from pathlib import Path

# 追加: どんな .py でもなるべく正しく読む関数
def _read_text_safely(path: Path) -> str:
    b = path.read_bytes()
    # BOM 判定
    if b.startswith(b"\xff\xfe"):
        return b.decode("utf-16-le")
    if b.startswith(b"\xfe\xff"):
        return b.decode("utf-16-be")
    if b.startswith(b"\xef\xbb\xbf"):
        return b.decode("utf-8-sig")
    # 候補順にトライ
    for enc in ("utf-8", "cp932", "latin-1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    # 最後は置換で読み切る（破損は ? に）
    return b.decode("utf-8", errors="replace")



DEFAULT_IGNORE = {".git", "venv", ".venv", "__pycache__", "node_modules", "build", "dist"}

class DropOldDefs(cst.CSTTransformer):
    def __init__(self, pattern: str):
        self.rx = re.compile(pattern)

    # def / async def を削除
    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef):
        if self.rx.search(original_node.name.value):
            return cst.RemoveFromParent()
        return updated_node

    def leave_AsyncFunctionDef(self, original_node: cst.AsyncFunctionDef, updated_node: cst.AsyncFunctionDef):
        if self.rx.search(original_node.name.value):
            return cst.RemoveFromParent()
        return updated_node

    # ついでに *_OLD なクラスも消したい場合（コメントアウトを外して使う）
    # def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef):
    #     if self.rx.search(original_node.name.value):
    #         return cst.RemoveFromParent()
    #     return updated_node

def iter_py_files(root: Path, ignore: set[str]):
    for p in root.rglob("*.py"):
        if any(part in ignore for part in p.parts):
            continue
        yield p

def process_file(path: Path, rx: str, apply: bool, show_diff: bool) -> bool:

    #@STOP
    #src = path.read_text(encoding="utf-8")
    
    src = _read_text_safely(path)
    
    try:
        mod = cst.parse_module(src)
    except Exception:
        # パース不能ファイルはスキップ
        return False
    new = mod.visit(DropOldDefs(rx))
    out = new.code
    if out == src:
        return False
    if show_diff or not apply:
        diff = difflib.unified_diff(
            src.splitlines(keepends=True),
            out.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path) + " (updated)",
        )
        sys.stdout.writelines(diff)
    if apply:
        path.write_text(out, encoding="utf-8")
    return True

def main():
    ap = argparse.ArgumentParser(description="Remove *_OLD functions safely using LibCST.")
    ap.add_argument("--root", default=".", help="project root")
    ap.add_argument("--pattern", default=r"_OLD\b", help="regex for names to remove")
    ap.add_argument("--apply", action="store_true", help="write changes to files")
    ap.add_argument("--diff", action="store_true", help="print unified diff")
    ap.add_argument("--ignore", nargs="*", default=list(DEFAULT_IGNORE), help="dirs to ignore")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    touched = 0
    for f in iter_py_files(root, set(args.ignore)):
        changed = process_file(f, args.pattern, args.apply, args.diff or not args.apply)
        if changed:
            touched += 1

    print(f"[OK] files changed: {touched}")

if __name__ == "__main__":
    main()
