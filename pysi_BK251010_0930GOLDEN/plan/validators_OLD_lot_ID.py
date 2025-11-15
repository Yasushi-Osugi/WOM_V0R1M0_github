#psi.plan.validators.py
# =========================
# 6) 追加: バリデーション
# =========================
# pysi/plan/validators.py
from __future__ import annotations
import re
from typing import Dict, Iterable, List, Optional, Pattern, Tuple, Union
def validate_lot_format_all(root, use_strict: bool = False, limit_print: int = 30) -> None:
    """
    lot_id の形式検査。新/旧両対応。use_strict=True で新フォーマットを強制チェック。
    """
    pat = STRICT_LOT_ID_RE if use_strict else DEFAULT_LOT_ID_RE
    bad = []
    def _walk(n):
        for w, buckets in enumerate(getattr(n, "psi4demand", []), start=1):
            for b_idx, bucket in enumerate(buckets):
                for lot in bucket:
                    if not pat.match(lot):
                        bad.append((n.name, w, b_idx, lot))
        for c in getattr(n, "children", []):
            _walk(c)
    _walk(root)
    if bad:
        print(f"[WARN] lot_id format NG count={len(bad)} (show first {limit_print})")
        for i, (node, wk, bi, lot) in enumerate(bad[:limit_print], start=1):
            print(f"  {i:>3}  {node} w{wk} b{bi}: {lot}")
    else:
        print("[OK] lot_id format verified.")
# --- デフォルトの LotID ルール: PREFIX + YYYY + WW + NNNN ---
DEFAULT_LOT_ID_PATTERN = r"^[A-Za-z0-9_]+(?P<year>\d{4})(?P<week>\d{2})(?P<seq>\d{4})$"
DEFAULT_LOT_ID_RE: Pattern[str] = re.compile(DEFAULT_LOT_ID_PATTERN)
def _iter_tree_nodes(root) -> Iterable[object]:
    stack = [root]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(getattr(n, "children", []) or [])
def _iter_all_nodes(prod_tree_dict: Dict[str, object]) -> Iterable[object]:
    for root in prod_tree_dict.values():
        yield from _iter_tree_nodes(root)
def assert_unique_lot_ids(
    prod_tree_dict: Dict[str, object],
    source: str = "psi4demand",
    layer_index: int = 0,
    limit: Optional[int] = None,
) -> Tuple[int, int, List[Tuple[str, str]]]:
    """
    全ノードの PSI（list形式）から lot_id を走査して重複を検出。
    戻り値: (総lot数, 重複数, 先頭からlimit件の (node_name, lot_id) )
    """
    seen, dup = set(), []
    total = 0
    for n in _iter_all_nodes(prod_tree_dict):
        psi = getattr(n, source, None)
        if not isinstance(psi, list):
            continue
        for wk in psi:
            lots = wk[layer_index] if layer_index < len(wk) else []
            for lot in lots:
                total += 1
                if lot in seen:
                    dup.append((n.name, lot))
                    if limit and len(dup) >= limit:
                        return total, len(dup), dup
                else:
                    seen.add(lot)
    return total, len(dup), dup
def check_lot_id_format(
    prod_tree_dict: Dict[str, object],
    pattern: Optional[Union[str, Pattern[str]]] = None,
    source: str = "psi4demand",
    layer_index: int = 0,
    limit: int = 20,
) -> Tuple[int, int, List[Tuple[str, str]]]:
    """
    lot_id の文字列形式を検査。pattern が None の場合は DEFAULT_LOT_ID_RE を使用。
    戻り値: (総lot数, 不一致数, 先頭からlimit件の (node_name, lot_id))
    """
    regex = DEFAULT_LOT_ID_RE if pattern is None else (re.compile(pattern) if isinstance(pattern, str) else pattern)
    bad, total = [], 0
    for n in _iter_all_nodes(prod_tree_dict):
        psi = getattr(n, source, None)
        if not isinstance(psi, list):
            continue
        for wk in psi:
            lots = wk[layer_index] if layer_index < len(wk) else []
            for lot in lots:
                total += 1
                if not regex.match(lot):
                    bad.append((n.name, lot))
                    if limit and len(bad) >= limit:
                        return total, len(bad), bad
    return total, len(bad), bad
def parse_lot_id(
    lot_id: str,
    pattern: Optional[Union[str, Pattern[str]]] = None,
) -> Optional[dict]:
    """
    LotID を year/week/seq に分解（prefix は末尾10桁を除いたもの）。
    合わなければ None を返す。
    """
    regex = DEFAULT_LOT_ID_RE if pattern is None else (re.compile(pattern) if isinstance(pattern, str) else pattern)
    m = regex.match(lot_id)
    if not m:
        return None
    return {
        "prefix": lot_id[:-10],  # YYYY(4)+WW(2)+NNNN(4) = 10桁
        "year": int(m.group("year")),
        "week": int(m.group("week")),
        "seq":  int(m.group("seq")),
    }
def dump_weekly_lots_csv(df_weekly, out_path: str) -> bool:
    """df_weekly が非空のときCSV出力。成功なら True。"""
    try:
        if df_weekly is not None and hasattr(df_weekly, "empty") and not df_weekly.empty:
            df_weekly.to_csv(out_path, index=False, encoding="utf-8-sig")
            return True
        return False
    except Exception:
        return False
