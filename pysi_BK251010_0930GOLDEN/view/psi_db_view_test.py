# psi_db_view_test.py
import sqlite3, json
import matplotlib.pyplot as plt
from collections import deque
from typing import Dict, Tuple
from pysi.network.node_base import Node  # 既存の Node を利用
# --- DB -> ツリー復元 ---
def load_tree_from_db(db_path: str) -> dict[str, Node]:
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        nodes: dict[str, Node] = {}
        # ノード属性
        for r in con.execute("SELECT * FROM node"):
            n = nodes.setdefault(r["node_name"], Node(r["node_name"]))
            n.leadtime = int(r["leadtime"] or 0)
            n.SS_days  = int(r["ss_days"] or 0)
            lv = r["long_vacation_weeks"]
            try:
                n.long_vacation_weeks = json.loads(lv) if lv else []
            except Exception:
                n.long_vacation_weeks = []
        # 親子リンク
        for r in con.execute("SELECT node_name, parent_name FROM node"):
            child = nodes[r["node_name"]]
            parent_name = r["parent_name"]
            if parent_name and parent_name in nodes:
                nodes[parent_name].add_child(child)  # add_child の中で child.parent が入る前提
        # ルート抽出（親を持たない）
        has_parent = {
            r["node_name"] for r in con.execute(
                "SELECT node_name FROM node WHERE parent_name IS NOT NULL"
            )
        }
        roots = {name: n for name, n in nodes.items() if name not in has_parent}
        return roots  # {root_name: Node}
# --- 位置計算（シンプルな tidy tree）---
def _count_leaves(n: Node) -> int:
    if not getattr(n, "children", []):
        return 1
    return sum(_count_leaves(c) for c in n.children)
def _assign_positions(n: Node, x: int, y_cursor: list[int], pos: Dict[Node, Tuple[float,float]]) -> float:
    """
    深さxをX座標に、Yは葉を下から 0,1,2... と詰めて、親は子のY平均に配置。
    戻り: 自ノードのY
    """
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
    # 正規化（Yを0..1に）
    ys = [p[1] for p in pos.values()]
    ymin, ymax = (min(ys), max(ys)) if ys else (0, 1)
    scale = (ymax - ymin) or 1.0
    pos = {n: (x, (y - ymin)/scale) for n, (x, y) in pos.items()}
    return pos
# --- BFSダンプ（任意の確認用）---
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
# --- 描画 ---
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
# --- まとめて実行 ---
def psi_db_view_test(db_path: str):
    roots = load_tree_from_db(db_path)
    if not roots:
        print("[WARN] no roots found.")
        return
    # ルートが複数ある場合は順に表示（一般には supply_point ひとつ）
    for root_name, root in roots.items():
        print(f"[INFO] root: {root_name}")
        print_bfs(root)  # 構造確認出力
        draw_tree_matplotlib(root, title=f"Root={root_name}")
# 直接実行テスト
if __name__ == "__main__":
    DB_PATH = r"C:\Users\ohsug\PySI_V0R8_SQL_010\data\pysi.sqlite3"
    psi_db_view_test(DB_PATH)
