# pysi/core/wom_pipeline251115.py

#
#動作確認のヒント：
#
#pysi.core.hooks.core の HookBus, set_global, autoload_plugins が正しく実装されていることを確認してください。
#
#pysi.utils.config.Config と pysi.wom_main.WOMEnv の import パスがプロジェクトと一致するように必要なら修正してください（エラーメッセージはその点を指摘するようになっています）。
#
#プラグインは pysi.plugins 以下（__init__.py を含むパッケージ）に置き、モジュール内に register(bus) を定義しておくと自動で呼ばれます。デコレーター方式のフックも使えるよう autoload_plugins を呼び出しています。
#
#CLI 実行例：python -m pysi.core.wom_pipeline -d path/to/csv_dir -p PRODUCT_A -s scenario01
#
#必要なら、このファイルを既存の Pipeline 実装（pysi/core/pipeline.py）と整合させるための差分パッチ（git diff 形式）や、pysi.plugins 用のテンプレートプラグイン register(bus) のサンプルを作ってお渡しします。どちらが欲しいですか？
#





"""
WOM Pipeline runner that uses the project's HookBus and supports register(bus) plugins.
Save as pysi/core/wom_pipeline.py and run like:
  python -m pysi.core.wom_pipeline --data_dir path/to/csv_dir

Features:
 - set up HookBus and set it global (so @action/@filter still work)
 - autoload plugins (import) and call register(bus) if present
 - WOMIOAdapter wraps WOMEnv to provide build_tree/collect_result
 - Pipeline runner triggers hooks at key points
"""
from __future__ import annotations
import argparse
import importlib
import logging
import pkgutil
import sys
from typing import Any, Dict, Optional

# use project hook implementation if available
from pysi.core.hooks.core import HookBus, set_global, autoload_plugins, hooks as global_hooks

logger = logging.getLogger(__name__)

# Project classes (adjust path if necessary)
try:
    from pysi.utils.config import Config
except Exception as e:
    raise ImportError("Cannot import Config from pysi.utils.config — adjust path") from e

try:
    # Adjust this import path if your WOMEnv lives elsewhere
    from pysi.wom_main import WOMEnv
except Exception as e:
    raise ImportError("Cannot import WOMEnv from pysi.wom_main; adjust import path.") from e


def call_register_if_present(package: str, bus: HookBus) -> None:
    """
    After importing plugin modules via autoload_plugins, call register(bus) on each module
    if it defines it. This enforces the register(bus) convention.
    """
    try:
        pkg = importlib.import_module(package)
    except Exception:
        logger.exception("call_register_if_present: cannot import plugin package %s", package)
        return

    for m in pkgutil.iter_modules(pkg.__path__):
        full = f"{package}.{m.name}"
        try:
            mod = importlib.import_module(full)
        except Exception:
            # if autoload_plugins already imported, failures here are logged by autoload_plugins;
            # still try to continue to other modules.
            logger.exception("Failed to import plugin module %s", full)
            continue

        reg = getattr(mod, "register", None)
        if callable(reg):
            try:
                reg(bus)
                logger.info("[plugins] called register(bus) on %s", full)
            except Exception:
                logger.exception("[plugins] register(bus) failed for %s", full)


class WOMIOAdapter:
    """
    Wrap WOMEnv to provide build_tree / collect_result for pipeline runner.
    Keeps a reference to the created env for later use by plugins.
    """
    def __init__(self, data_dir: Optional[str] = None, product: Optional[str] = None):
        self.data_dir = data_dir
        self.product = product
        self._env: Optional[WOMEnv] = None

    def build_tree(self, spec: Dict[str, Any]) -> Any:
        """
        Create Config, instantiate WOMEnv, call load_data_files(), and return a root object
        suitable for downstream planning. Attaches env reference to the returned root for plugins.
        """
        cfg = Config()
        # prefer explicit adapter data_dir if present
        if self.data_dir:
            try:
                setattr(cfg, "DATA_DIRECTORY", self.data_dir)
            except Exception:
                logger.debug("Config object has no DATA_DIRECTORY attribute; skipping set")

        # Allow incoming spec to override
        if spec.get("data_dir"):
            try:
                setattr(cfg, "DATA_DIRECTORY", spec.get("data_dir"))
            except Exception:
                pass

        env = WOMEnv(cfg)
        # load CSVs / DBs etc.
        env.load_data_files()
        self._env = env

        # optionally pick a product
        if self.product:
            if hasattr(env, "product_name_list") and self.product in getattr(env, "product_name_list"):
                setattr(env, "product_selected", self.product)
            else:
                logger.warning("Product '%s' not found in env; ignoring selection", self.product)

        # Try to return a per-product outbound root if available; else return env
        root = None
        try:
            prod = getattr(env, "product_selected", None)
            if prod and hasattr(env, "prod_tree_dict_OT") and prod in env.prod_tree_dict_OT:
                root = env.prod_tree_dict_OT[prod]
                setattr(root, "_wom_env", env)
            else:
                # fallback: if there is a top-level root node, use it
                root_candidate = getattr(env, "root_node_outbound", None)
                if root_candidate is not None:
                    root = root_candidate
                    setattr(root, "_wom_env", env)
        except Exception:
            logger.exception("Error while selecting product root; falling back to env")
            root = None

        if root is None:
            # last resort: return env itself
            setattr(env, "_wom_env", env)
            return env

        return root

    def collect_result(self, root: Any) -> Dict[str, Any]:
        """
        Collector: assemble a simple result dict for exporters/visualizers/plugins.
        Extend as needed to include metrics you want available to plugins.
        """
        env = self._env
        res: Dict[str, Any] = {
            "root": root,
            "env": env,
            "product_selected": getattr(env, "product_selected", None) if env else None,
            "total_revenue": getattr(env, "total_revenue", None) if env else None,
            "total_profit": getattr(env, "total_profit", None) if env else None,
        }
        return res


class WOMPipelineRunner:
    """
    The pipeline runner orchestrates the flow and exposes hook points for plugins.
    """
    def __init__(self, bus: Optional[HookBus] = None, io_adapter: Optional[WOMIOAdapter] = None, plugin_package: str = "pysi.plugins"):
        self.bus = bus or HookBus(logger=logging.getLogger("hooks"))
        # set global hooks so decorator-based plugins also hook into this bus
        set_global(self.bus)

        # import plugins (this prints and registers decorator-style hooks),
        # then explicitly call register(bus) on any plugin modules that provide it.
        try:
            autoload_plugins(plugin_package)
        except Exception:
            logger.exception("autoload_plugins failed; continuing")

        # call register(bus) where present to honor your preferred pattern
        try:
            call_register_if_present(plugin_package, self.bus)
        except Exception:
            logger.exception("call_register_if_present failed; continuing")

        self.io = io_adapter or WOMIOAdapter()
        self.logger = logging.getLogger("wom_pipeline")

    def run(self, data_dir: str, product: Optional[str] = None, scenario_id: str = "default") -> Dict[str, Any]:
        # prepare spec and allow plugins to modify it
        spec = {"data_dir": data_dir, "scenario_id": scenario_id, "product": product}
        spec = self.bus.apply_filters("pipeline:spec", spec)

        # build tree
        self.logger.info("Building plan tree (data_dir=%s, product=%s)", spec.get("data_dir"), spec.get("product"))
        self.io.data_dir = spec.get("data_dir", self.io.data_dir)
        self.io.product = spec.get("product", self.io.product)
        root = self.io.build_tree(spec)

        # after build hook
        self.bus.do_action("pipeline:after_build", root=root, env=getattr(self.io, "_env", None))

        # ensure we have env
        env = getattr(self.io, "_env", None)
        if env is None:
            # maybe root is env-like
            if hasattr(root, "load_data_files"):
                env = root
                self.io._env = env

        if env is None:
            raise RuntimeError("WOMEnv instance not available after build; cannot proceed")

        # planning steps with hooks
        try:
            self.bus.do_action("pipeline:before_planning", env=env, root=root)

            if hasattr(env, "demand_planning4multi_product"):
                env.demand_planning4multi_product()
                self.bus.do_action("pipeline:after_demand_planning", env=env, root=root)
            else:
                self.logger.warning("env missing demand_planning4multi_product")

            if hasattr(env, "demand_leveling4multi_prod"):
                env.demand_leveling4multi_prod()
                self.bus.do_action("pipeline:after_demand_leveling", env=env, root=root)
            else:
                self.logger.warning("env missing demand_leveling4multi_prod")

            if hasattr(env, "supply_planning4multi_product"):
                env.supply_planning4multi_product()
                self.bus.do_action("pipeline:after_supply_planning", env=env, root=root)
            else:
                self.logger.warning("env missing supply_planning4multi_product")

            # optional pre-collect
            self.bus.do_action("pipeline:before_collect", env=env, root=root)
        except Exception:
            logger.exception("Planning steps failed")
            raise

        # collect result and allow result filters (visualize/export etc.)
        result = self.io.collect_result(root)
        result = self.bus.apply_filters("pipeline:result", result)
        self.bus.do_action("pipeline:after_run", result=result)

        return result


# CLI entrypoint
def main_cli():
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description="Run WOM pipeline (Hook/Plugin style)")
    ap.add_argument("--data_dir", "-d", required=True, help="data directory (CSV etc.)")
    ap.add_argument("--product", "-p", required=False, help="product to plan (optional)")
    ap.add_argument("--scenario", "-s", required=False, help="scenario id (optional)", default="default")
    args = ap.parse_args()

    runner = WOMPipelineRunner()
    res = runner.run(data_dir=args.data_dir, product=args.product, scenario_id=args.scenario)
    print("WOM pipeline finished. result keys:", list(res.keys()))

if __name__ == "__main__":
    main_cli()

