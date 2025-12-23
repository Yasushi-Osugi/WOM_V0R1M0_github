# pysi/gui/node_selector.py
from __future__ import annotations
from typing import Any, Callable, Optional, List, Tuple
try:
    import tkinter as tk
    from tkinter import ttk
except Exception:
    tk = None
    ttk = None

def _children(node: Any) -> List[Any]:
    kids = getattr(node, "children", None)
    if kids is None:
        kids = getattr(node, "child_nodes", None)
    if kids is None:
        return []
    if isinstance(kids, dict):
        return list(kids.values())
    if isinstance(kids, (list, tuple, set)):
        return list(kids)
    return [kids]

def _name(node: Any) -> str:
    for k in ("name", "node_name", "id"):
        v = getattr(node, k, None)
        if isinstance(v, str) and v:
            return v
    return str(node)

class NodeSelectorDialog:
    """
    V0R7風：Tree構造で全ノードを選ぶ。
    ダブルクリック or Enter で on_select(node_name) を呼ぶ。
    """
    def __init__(
        self,
        parent: Any,
        env: Any,
        product_name: str,
        *,
        on_select: Callable[[str], None],
        title: str = "Select Node",
    ) -> None:
        if tk is None or ttk is None:
            raise RuntimeError("Tkinter is not available.")

        self.env = env
        self.product_name = product_name
        self.on_select = on_select

        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.geometry("420x520")

        self.tree = ttk.Treeview(self.win, show="tree")
        self.tree.pack(fill="both", expand=True)

        # roots
        root_ot = getattr(env, "prod_tree_dict_OT", {}).get(product_name)
        root_in = getattr(env, "prod_tree_dict_IN", {}).get(product_name)

        top = self.tree.insert("", "end", text="root", open=True)

        if root_ot is not None:
            ot_id = self.tree.insert(top, "end", text="[OT] outbound", open=True)
            self._insert_subtree(ot_id, root_ot)

        if root_in is not None:
            in_id = self.tree.insert(top, "end", text="[IN] inbound", open=True)
            self._insert_subtree(in_id, root_in)

        self.tree.bind("<Double-1>", self._on_activate)
        self.tree.bind("<Return>", self._on_activate)

    def _insert_subtree(self, parent_id: str, node: Any) -> None:
        nm = _name(node)
        this_id = self.tree.insert(parent_id, "end", text=nm, open=False)
        for c in _children(node):
            self._insert_subtree(this_id, c)

    def _on_activate(self, event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        text = self.tree.item(sel[0], "text")
        # [OT]/[IN]行や root は除外
        if text.startswith("[") or text == "root":
            return
        try:
            self.on_select(text)
        finally:
            self.win.destroy()

def open_node_selector(parent: Any, env: Any, product_name: str, *, on_select: Callable[[str], None]) -> None:
    NodeSelectorDialog(parent, env, product_name, on_select=on_select)
