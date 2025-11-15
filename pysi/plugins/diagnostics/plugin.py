# plugins/diagnostics/plugin.py
def register(bus):
    def show_leafs(root=None, **ctx):
        # root は pipeline.build_tree() の返り値（dict想定）
        state = root.get("state", {}) if isinstance(root, dict) else {}
        leafs = state.get("leafs")
        log = ctx.get("logger")
        if log and leafs is not None:
            log.info(f"[diag] leaf_nodes={sorted(list(leafs))}")
    bus.add_action("after_tree_build", show_leafs, priority=90)


def register_OLD(bus):
    def show_leafs(root=None, **ctx):
        state = getattr(root, "get", lambda k, d=None: d)("state", {}) if isinstance(root, dict) else {}
        leafs = (state or {}).get("leafs")
        log = ctx.get("logger")
        if log and leafs is not None:
            log.info(f"[diag] leaf_nodes={sorted(list(leafs))}")
    bus.add_action("after_tree_build", show_leafs, priority=90)