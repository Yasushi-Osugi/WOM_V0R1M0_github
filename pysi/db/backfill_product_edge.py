
# pysi\db\backfill_product_edge.py
# starter
## 1) まずはスキーマ追加（済み）
#python pysi\db\add_product_edge.py --db "C:\Users\ohsug\...\data\pysi.sqlite3" --verbose
#
## 2) バックフィル実行（初回は --wipe を推奨）
#python pysi\db\backfill_product_edge.py --db "C:\Users\ohsug\...\data\pysi.sqlite3" --wipe --verbose
# backfill_product_edge.py
from __future__ import annotations
import argparse, sqlite3, sys, os
from collections import defaultdict
def fetch_products(con):
    cur = con.execute("SELECT DISTINCT product_name FROM node_product")
    return [r[0] for r in cur.fetchall()]
def fetch_node_set(con, product):
    cur = con.execute("SELECT node_name FROM node_product WHERE product_name=?", (product,))
    return {r[0] for r in cur.fetchall()}
def fetch_edges_for_nodes(con, node_set):
    """
    node テーブルから (parent -> child) を取り出す。
    child が node_set 内、かつ parent も node_set 内のものだけ採用。
    """
    if not node_set:
        return []
    # プレースホルダ生成
    qmarks = ",".join(["?"] * len(node_set))
    cur = con.execute(
        f"SELECT parent_name, node_name FROM node WHERE node_name IN ({qmarks})",
        tuple(node_set),
    )
    edges = []
    for parent, child in cur.fetchall():
        # parent が NULL / スコープ外は除外
        if parent is None or str(parent).strip() == "" or parent not in node_set:
            continue
        edges.append((parent, child))
    return edges
def build_children_map(edges):
    ch = defaultdict(list)
    for p, c in edges:
        ch[p].append(c)
    return ch
def dfs_subtree(start_nodes, children):
    """start_nodes から到達できるノード集合（自分自身含む）"""
    seen = set()
    stack = list(start_nodes)
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(children.get(n, []))
    return seen
def choose_root(node_set, edges):
    """優先: supply_point、無ければ 親を持たない候補から先頭"""
    if "supply_point" in node_set:
        return "supply_point"
    # 親集合・子集合から root 候補
    parents = {p for p, _ in edges}
    childs  = {c for _, c in edges}
    candidates = list((node_set - childs) | {"supply_point"})  # 念のため
    return candidates[0] if candidates else (next(iter(node_set)) if node_set else None)
def classify_edges_by_bound(product, edges, children, root):
    """
    ルート直下の DAD*/MOM* からサブツリーを取り、child が属する側で bound を決める。
    ・child ∈ DAD側サブツリー → OUT
    ・child ∈ MOM側サブツリー → IN
    ・両方/どちらでもない → 未分類（warn）
    """
    # 直下の子
    direct_kids = children.get(root, [])
    dad_heads = [n for n in direct_kids if str(n).upper().startswith("DAD")]
    mom_heads = [n for n in direct_kids if str(n).upper().startswith("MOM")]
    sub_out = dfs_subtree(dad_heads, children) if dad_heads else set()
    sub_in  = dfs_subtree(mom_heads, children) if mom_heads else set()
    out_edges, in_edges, unknown = [], [], []
    for p, c in edges:
        if c in sub_out and c not in sub_in:
            out_edges.append((p, c))
        elif c in sub_in and c not in sub_out:
            in_edges.append((p, c))
        elif c in sub_out and c in sub_in:
            # 通常あり得ないが、守りで unknown 扱い
            unknown.append((p, c, "BOTH"))
        else:
            # DAD/MOM 以外の分岐（データの都合であり得る）。supply_point 直下が未命名など
            unknown.append((p, c, "NONE"))
    return out_edges, in_edges, unknown, dad_heads, mom_heads
def backfill(con, wipe=False, verbose=False):
    products = fetch_products(con)
    if verbose:
        print(f"[INFO] products: {products}")
    # INSERT 準備
    ins_sql = "INSERT OR IGNORE INTO product_edge(product_name, parent_name, child_name, bound) VALUES (?,?,?,?)"
    with con:
        for prod in products:
            nodes = fetch_node_set(con, prod)
            edges = fetch_edges_for_nodes(con, nodes)
            children = build_children_map(edges)
            root = choose_root(nodes, edges)
            if not root:
                if verbose: print(f"[WARN] {prod}: no root resolved; skip.")
                continue
            out_edges, in_edges, unknown, dad_heads, mom_heads = classify_edges_by_bound(prod, edges, children, root)
            if wipe:
                con.execute("DELETE FROM product_edge WHERE product_name=?", (prod,))
            # 挿入
            con.executemany(ins_sql, [(prod, p, c, "OUT") for (p, c) in out_edges])
            con.executemany(ins_sql, [(prod, p, c, "IN")  for (p, c) in in_edges])
            if verbose:
                print(f"[OK] {prod}: OUT={len(out_edges)} IN={len(in_edges)} unknown={len(unknown)} "
                      f"| root={root} DAD={dad_heads} MOM={mom_heads}")
            # 未分類エッジがある場合はヒントを出す
            if unknown and verbose:
                heads = set(children.get(root, []))
                sample = ", ".join([f"{p}->{c}({why})" for p, c, why in unknown[:6]])
                print(f"      [HINT] Unknown edges: {len(unknown)} (show 6) {sample}")
                if not dad_heads and not mom_heads:
                    print("      [HINT] supply_point 直下に DAD*/MOM* が無いか、命名規則が異なっています。")
def main():
    ap = argparse.ArgumentParser(description="Backfill product_edge from node/node_product using DAD/MOM split.")
    ap.add_argument("--db", "-d", required=True, help="Path to SQLite DB (e.g., .../data/pysi.sqlite3)")
    ap.add_argument("--wipe", action="store_true", help="Delete existing rows per product before inserting")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()
    if not os.path.isfile(args.db):
        print(f"[ERR ] DB not found: {args.db}", file=sys.stderr); sys.exit(1)
    con = sqlite3.connect(args.db)
    try:
        # テーブル存在チェック
        cur = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='product_edge'")
        if not cur.fetchone():
            print("[ERR ] table product_edge does not exist. Run add_product_edge.py first.", file=sys.stderr)
            sys.exit(2)
        backfill(con, wipe=args.wipe, verbose=args.verbose)
    finally:
        con.close()
    # 検証（サマリ）
    con = sqlite3.connect(args.db)
    try:
        rows = list(con.execute(
            "SELECT product_name, bound, COUNT(*) FROM product_edge GROUP BY product_name, bound ORDER BY product_name, bound"))
        print("\n[SUMMARY] product_edge counts:")
        for prod, bnd, cnt in rows:
            print(f"  - {prod:20s} {bnd}: {cnt}")
    finally:
        con.close()
if __name__ == "__main__":
    main()
