#psi.plan.validators.py
# =========================
# 6) 追加: バリデーション
# =========================
# pysi/plan/validators.py
from __future__ import annotations
import re
from typing import Dict, Iterable, List, Optional, Pattern, Tuple, Union
# =========================================================
# Lot ID 仕様
#  - 旧:  NODE + YYYYWWNNNN
#  - 新:  NODE-PRODUCT-YYYYWWNNNN  （区切りは LOT_SEP = "-"）
# どちらも「末尾10桁が数値(YYYYWWNNNN)」という共通性を利用する。
# =========================================================
LOT_SEP = "-"  # 新フォーマットの区切り: NODE-PRODUCT-YYYYWWNNNN
# 末尾10桁（YYYYWWNNNN）に名前付きグループを持つパターン
# → 新旧どちらの接頭部でもマッチしつつ、year/week/seq を取り出せる
DEFAULT_LOT_ID_PATTERN = r".*(?P<year>\d{4})(?P<week>\d{2})(?P<seq>\d{4})$"
DEFAULT_LOT_ID_RE: Pattern[str] = re.compile(DEFAULT_LOT_ID_PATTERN)
# 新フォーマットを厳密チェックしたい場合
STRICT_LOT_ID_RE: Pattern[str] = re.compile(r"^[^-]+-[^-]+-\d{10}$")
# 旧実装が使っていた「末尾10桁からグループ抽出」の別名（残しておくと楽）
LEGACY_TAIL_GROUPS_RE: Pattern[str] = DEFAULT_LOT_ID_RE
# =========================================================
# GUI/ユーティリティの置き換え（旧 extract_node_name）
#旧来の「末尾9/10文字をバッサリ切る」関数は卒業し、パーサ経由で取得する
# =========================================================
#置き換えたいファイルで import を追加（or 変更）
#from pysi.plan.validators import extract_node_name, extract_product_name
# あるいは parse_lot_id を直接使うなら:
# from pysi.plan.validators import parse_lot_id
#既存のスライスや自作関数を差し替え
# 旧: node = lot_id[:-10] といったスライス/自作関数
# 新:
#node = extract_node_name(lot_id)
#product = extract_product_name(lot_id) or ""   # 旧フォーマットだと None になるのでフォールバック
#検索置換の目安
#[:-9], [:-10], extract_node_name( などで grep して、対象箇所を洗い出すと置き換え漏れを防げます。
#型ヒントの注意（Python バージョン）
#str | None は Python 3.10+。それ以前なら Optional[str] を使うか、from __future__ import annotations をファイル先頭に入れてください。
#「いますぐ全箇所を改修する必要はないけど、該当箇所を見つけたら新関数に寄せていく」がベストです。
def extract_node_name(lot_id: str) -> str:
    node, _, _, _, _ = parse_lot_id(lot_id)
    return node
def extract_product_name(lot_id: str) -> Optional[str]:
    _, product, _, _, _ = parse_lot_id(lot_id)
    return product
# =========================================================
# ツリー走査ユーティリティ
# =========================================================
def _iter_tree_nodes(root) -> Iterable[object]:
    """単一ルートから深さ優先でノードを列挙"""
    stack = [root]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(getattr(n, "children", []) or [])
def _iter_all_nodes(prod_tree_dict: Dict[str, object]) -> Iterable[object]:
    """{product_name: root} から全ノードを列挙"""
    for root in prod_tree_dict.values():
        yield from _iter_tree_nodes(root)
# =========================================================
# Lot ID パーサ
# =========================================================
def parse_lot_id(lot_id: str, sep: str = LOT_SEP) -> Tuple[str, Optional[str], int, int, int]:
    """
    新正式版パーサ（推奨）:
      戻り値 = (node, product_or_None, year, iso_week, seq)
    - 新フォーマット: NODE-PRODUCT-YYYYWWNNNN  → product を返す
    - 旧フォーマット: NODEYYYYWWNNNN          → product は None
    """
    tail = lot_id[-10:]
    if not tail.isdigit():
        raise ValueError(f"invalid lot tail: {lot_id!r}")
    year = int(tail[:4])
    week = int(tail[4:6])
    seq  = int(tail[6:])
    head = lot_id[:-10]
    if sep in head:
        parts = head.split(sep)
        node = parts[0]
        product = parts[1] if len(parts) >= 2 else None
    else:
        node, product = head, None
    return node, product, year, week, seq
def parse_lot_id_legacy(
    lot_id: str,
    pattern: Optional[Union[str, Pattern[str]]] = None,
) -> Optional[dict]:
    """
    旧API互換: dict を返す版。
      戻り値 = {"prefix": <node[-product]部>, "year": int, "week": int, "seq": int}
    - pattern を渡さない場合は「末尾10桁が数字」を DEFAULT_LOT_ID_RE で判定。
    - 年/週/連番は LEGACY_TAIL_GROUPS_RE で抽出。
    """
    regex = DEFAULT_LOT_ID_RE if pattern is None else (re.compile(pattern) if isinstance(pattern, str) else pattern)
    if not regex.match(lot_id):
        return None
    m = LEGACY_TAIL_GROUPS_RE.search(lot_id)
    if not m:
        return None
    return {
        "prefix": lot_id[:-10],  # NODE[-PRODUCT] 部分（旧来の prefix と互換）
        "year": int(m.group("year")),
        "week": int(m.group("week")),
        "seq":  int(m.group("seq")),
    }
# =========================================================
# Lot ID の形式チェック（単一ルート向け・プリント出力）
# =========================================================
def validate_lot_format_all(root, use_strict: bool = False, limit_print: int = 30) -> None:
    """
    lot_id の形式検査。新/旧両対応。
    - use_strict=True なら新フォーマット(NODE-PRODUCT-YYYYWWNNNN)だけ許可。
    - 形式NGを見つけた場合は先頭 limit_print 件まで表示。
    """
    pat = STRICT_LOT_ID_RE if use_strict else DEFAULT_LOT_ID_RE
    bad: List[Tuple[str, int, int, str]] = []
    def _walk(n):
        # psi4demand = [[S, CO, I, P], [S, CO, I, P], ...] を想定
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
# =========================================================
# Lot ID の形式/重複チェック（辞書全体を走査・結果を返す）
# =========================================================
def check_lot_id_format(
    prod_tree_dict: Dict[str, object],
    pattern: Optional[Union[str, Pattern[str]]] = None,
    source: str = "psi4demand",
    layer_index: int = 0,
    limit: int = 20,
) -> Tuple[int, int, List[Tuple[str, str]]]:
    """
    {product_name: root} 全体で lot_id の文字列形式を検査。
    - pattern が None の場合は DEFAULT_LOT_ID_RE を使用（末尾10桁が数字か）。
    - 戻り値: (総lot数, 不一致数, 先頭からlimit件の (node_name, lot_id))
    """
    regex = DEFAULT_LOT_ID_RE if pattern is None else (re.compile(pattern) if isinstance(pattern, str) else pattern)
    bad: List[Tuple[str, str]] = []
    total = 0
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
def assert_unique_lot_ids(
    prod_tree_dict: Dict[str, object],
    source: str = "psi4demand",
    layer_index: int = 0,
    limit: Optional[int] = None,
) -> Tuple[int, int, List[Tuple[str, str]]]:
    """
    {product_name: root} 全体から重複 lot_id を検出。
    戻り値: (総lot数, 重複数, 先頭からlimit件の (node_name, lot_id))
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
# --- 伝播後用：ノード内ユニークネス検査  -------------------------------
## （任意）ノード内重複の検査に切替
#total, dup_cnt, _ = assert_no_intra_node_duplicates(root)
#print(f"[{prod}] intra-node uniqueness: total={total}, dup={dup_cnt}")
def assert_no_intra_node_duplicates(root) -> tuple[int, int, list]:
    """
    ツリーを走査し、同一 node/bucket の中で重複した lot_id を検出。
    返り: (総lot数, 重複数, 先頭サンプル)
    """
    def traverse(n):
        st=[n]
        while st:
            x=st.pop()
            yield x
            for c in getattr(x, "children", []) or []:
                st.append(c)
    dups = []
    total = 0
    LABELS = ("S","CO","I","P")
    for nd in traverse(root):
        psi = getattr(nd, "psi4demand", None)
        if not isinstance(psi, list):
            continue
        W = len(psi)
        for w in range(W):
            for b_idx, label in enumerate(LABELS):
                lots = psi[w][b_idx]
                total += len(lots)
                seen = set()
                for lot in lots:
                    if lot in seen:
                        dups.append((nd.name, label, w, lot))
                    else:
                        seen.add(lot)
    if dups:
        print(f"[WARN] intra-node dup lot_ids: {len(dups)} (show 20)")
        for rec in dups[:20]:
            print("  - node,bucket,week,lot:", rec)
    else:
        print("[OK] no intra-node duplicate lot_ids.")
    return total, len(dups), dups[:20]
def show_cross_node_sharing(root, limit=10):
    def traverse(n):
        st=[n]
        while st:
            x=st.pop()
            yield x
            for c in getattr(x, "children", []) or []:
                st.append(c)
    first_seen = {}  # lot_id -> (node, bucket, week)
    cross = []
    LABELS=("S","CO","I","P")
    for nd in traverse(root):
        psi = nd.psi4demand
        for w in range(len(psi)):
            for b_idx, label in enumerate(LABELS):
                for lot in psi[w][b_idx]:
                    key = lot
                    loc = (nd.name, label, w)
                    if key in first_seen and first_seen[key][0] != nd.name:
                        cross.append((key, first_seen[key], loc))
                        if len(cross) >= limit:
                            print("[sample] cross-node sharing:", cross[:limit])
                            return
                    else:
                        first_seen[key] = loc
    print("[sample] cross-node sharing: <none within limit>")
# =========================================================
# デバッグ出力（週次DFのダンプ）
# =========================================================
def dump_weekly_lots_csv(df_weekly, out_path: str) -> bool:
    """df_weekly が非空のときCSV出力。成功なら True。"""
    try:
        if df_weekly is not None and hasattr(df_weekly, "empty") and not df_weekly.empty:
            df_weekly.to_csv(out_path, index=False, encoding="utf-8-sig")
            return True
        return False
    except Exception:
        return False
