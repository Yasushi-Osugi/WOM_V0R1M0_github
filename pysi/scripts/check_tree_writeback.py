# pysi/scripts/check_tree_writeback.py
# starter
# python -m pysi.scripts.check_tree_writeback
import inspect
import sys
try:
    from pysi.io import tree_writeback as tw
except Exception as e:
    print("[ERR] cannot import pysi.io.tree_writeback:", e)
    sys.exit(1)
def main():
    print("module path:", getattr(tw, "__file__", "<unknown>"))
    has_write = hasattr(tw, "write_both_layers_for_pair")
    has_compute = hasattr(tw, "compute_leaf_S_for_pair")
    print("has write_both_layers_for_pair:", has_write)
    print("has compute_leaf_S_for_pair   :", has_compute)
    if has_write:
        try:
            print("signature:", inspect.signature(tw.write_both_layers_for_pair))
        except Exception as e:
            print("[WARN] cannot inspect signature:", e)
if __name__ == "__main__":
    main()
