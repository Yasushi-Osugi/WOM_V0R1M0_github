# psi_db_view_test.py
import sqlite3, json
import matplotlib.pyplot as plt
from collections import deque
from typing import Dict, Tuple
from pysi.network.node_base import Node  # 既存の Node を利用
NULL_LIKES = {None, "", "None", "NULL"}  # 親なし扱いの値
# --- 基本ユーティリティ ---
def _count_leaves(n: Node) -> int:
    if not getattr(n, "children", []):
        return 1
    return sum(_count_leaves(c) for c in n.children)
def _assign_positions(n: Node, x: int, y_cursor: list[int], pos: Dict[Node, Tuple[float,float]]) -> float:
    if not getattr(n, "children", []):
        y = y_cursor[0]
        pos[n] = (x, y)
        y_cursor[0] += 1
        return y
    ys = []
    for c in n.children:
        ys.append(_assign_positions(c, x+1, y_cursor, pos))
    y = sum(ys)/len(ys)
    pos[n] = (x, y)
    return y
def compute_positions(root: Node) -> Dict[Node, Tuple[float,float]]:
    pos: Dict[Node, Tuple[float,float]] = {}
    _assign_positions(root, x=0, y_cursor=[0], pos=pos)
    ys = [p[1] for p in pos.values()]
    ymin, ymax = (min(ys), max(ys)) if ys else (0, 1)
    scale = (ymax - ymin) or 1.0
    pos = {n: (x, (y - ymin)/scale) for n, (x, y) in pos.items()}
    return pos
def print_bfs(root: Node):
    q = deque([(root, 0)])
    seen = set()
    while q:
        n, d = q.popleft()
        if id(n) in seen:
            continue
        seen.add(id(n))
        print(f"[BFS d={d}] {n.name} -> {[c.name for c in getattr(n,'children',[])]}")
        for c in getattr(n, "children", []):
            q.append((c, d+1))
def draw_tree_matplotlib(root: Node, figsize=(10, 6), title: str | None = None):
    pos = compute_positions(root)
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_axis_off()
    ax.set_title(title or f"Supply Chain Tree: {root.name}", fontsize=12)
    # エッジ
    for parent, (x, y) in pos.items():
        for child in getattr(parent, "children", []) or []:
            (xc, yc) = pos[child]
            ax.plot([x, xc], [y, yc], color="#999", linewidth=1.5, zorder=1)
    # ノード（葉は色分け）
    for n, (x, y) in pos.items():
        is_leaf = not getattr(n, "children", [])
        color = "#007ACC" if not is_leaf else "#2E8B57"
        ax.scatter([x], [y], s=250, color=color, zorder=2)
        ax.text(x, y, n.name, ha="center", va="center", color="white",
                fontsize=9, fontweight="bold", zorder=3)
    # 余白調整
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    if xs and ys:
        ax.set_xlim(min(xs)-0.5, max(xs)+0.5)
        ax.set_ylim(min(ys)-0.05, max(ys)+0.05)
    plt.tight_layout()
    plt.show()
# --- DB -> 製品別フォレスト復元 ---
def load_forest_from_db(db_path: str) -> dict[str, Node]:
    """
    返り値: {product_name: root_node}
    - node_product で product ごとのノード集合を確定
    - supply_point が集合内にあればそれを root に（最優先）
    - それ以外は「親が NULLライク or 親が集合外」のノードから root を決定
      （複数候補があれば supply_point 優先 → 次に子を持つノード優先 → 任意の1件）
    """
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        # 1) node属性を読み込む（全体）
        node_rows = {r["node_name"]: r for r in con.execute("SELECT * FROM node")}
        if not node_rows:
            return {}
        # 2) product ごとのノード集合
        prod_nodes: dict[str, set[str]] = {}
        for r in con.execute("SELECT node_name, product_name FROM node_product"):
            prod_nodes.setdefault(r["product_name"], set()).add(r["node_name"])
        if not prod_nodes:
            return {}
        # 3) 製品ごとに Node インスタンス生成＆属性反映
        product_roots: dict[str, Node] = {}
        for product, node_names in prod_nodes.items():
            # インスタンスプール（製品ごとに独立）
            nodes: dict[str, Node] = {}
            # 3-1) 属性を反映
            for name in node_names:
                base = node_rows.get(name)
                if not base:
                    continue
                n = nodes.setdefault(name, Node(name))
                n.leadtime = int(base["leadtime"] or 0)
                n.SS_days  = int(base["ss_days"] or 0)
                lv = base["long_vacation_weeks"]
                try:
                    n.long_vacation_weeks = json.loads(lv) if lv else []
                except Exception:
                    n.long_vacation_weeks = []
            # 3-2) 親子リンク（親が「同一productスコープ内」にある場合のみ接続）
            for name in node_names:
                base = node_rows.get(name)
                if not base:
                    continue
                parent_name = base["parent_name"]
                if parent_name in NULL_LIKES:
                    parent_name = None
                if parent_name and parent_name in node_names:
                    parent = nodes.setdefault(parent_name, Node(parent_name))
                    child  = nodes[name]
                    parent.add_child(child)
            # 3-3) root 選定
            # 候補: 親が集合内にいないノード（親がNULL or 親名が集合外）
            # SQL無しで、node_rowsの親名を参照して判定
            candidate_names = []
            for name in node_names:
                base = node_rows.get(name)
                if not base:
                    continue
                parent_name = base["parent_name"]
                if parent_name in NULL_LIKES or (parent_name and parent_name not in node_names):
                    candidate_names.append(name)
            # supply_point 優先
            root_name = None
            if "supply_point" in node_names:
                root_name = "supply_point"
            elif candidate_names:
                # 子を持つノード優先（より“ハブ”らしい）
                with_children = [nm for nm in candidate_names if getattr(nodes[nm], "children", [])]
                root_name = with_children[0] if with_children else candidate_names[0]
            else:
                # フォールバック: 任意のノード（ありえない想定だが保険）
                root_name = next(iter(node_names))
            product_roots[product] = nodes[root_name]
        return product_roots
# --- まとめて実行 ---
def psi_db_view_test(db_path: str):
    forest = load_forest_from_db(db_path)
    if not forest:
        print("[WARN] no roots found for any product.")
        return
    for product_name, root in forest.items():
        print(f"[INFO] product: {product_name}, root: {root.name}")
        print_bfs(root)
        draw_tree_matplotlib(root, title=f"{product_name}: Root={root.name}")
# 直接実行テスト
if __name__ == "__main__":
    DB_PATH = r"C:\Users\ohsug\PySI_V0R8_SQL_010\data\pysi.sqlite3"
    psi_db_view_test(DB_PATH)
