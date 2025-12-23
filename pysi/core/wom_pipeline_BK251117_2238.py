# pysi/core/wom_pipeline.py
"""
WOM Pipeline runner that uses the project's HookBus.
Place this file under pysi/core/ and run like:
  python -m pysi.core.wom_pipeline --data_dir path/to/data

This adapts the procedural wom_main.main() into a HOOK/PLUGIN/PIPELINE flow.
"""

from __future__ import annotations
import argparse
import logging
from typing import Any, Dict, Optional

# Hook system (your implementation)
from pysi.core.hooks.core import HookBus, set_global, autoload_plugins, hooks as global_hooks

logger = logging.getLogger(__name__)

# Import Config and WOMEnv from your project. Adjust path if your layout differs.
try:
    from pysi.utils.config import Config
except Exception:
    # fallback if utils.config lives elsewhere; keeps failure explicit
    raise


try:
    # WOMEnv is expected to be defined in your wom_main.py or similar module.
    # Adjust the import if WOMEnv is located at a different module path.
    from pysi.wom_main import WOMEnv
except Exception as e:
    raise ImportError("Cannot import WOMEnv from pysi.wom_main; adjust import path.") from e


class WOMIOAdapter:
    """Wrap WOMEnv to provide build_tree / collect_result for pipeline runner."""
    def __init__(self, data_dir: Optional[str] = None, product: Optional[str] = None):
        self.data_dir = data_dir
        self.product = product
        self._env: Optional[WOMEnv] = None

    def build_tree(self, spec: Dict[str, Any]) -> Any:
        """
        Build the plan tree using WOMEnv. Mirrors original main():
          cfg = Config(); env = WOMEnv(cfg); env.load_data_files()
        Return a 'root' plan node (or env) so downstream code / plugins can inspect.
        """
        cfg = Config()
        if self.data_dir:
            # prefer explicit adapter data_dir
            try:
                setattr(cfg, "DATA_DIRECTORY", self.data_dir)
            except Exception:
                # ignore if Config doesn't accept this attribute
                logger.debug("Config has no DATA_DIRECTORY attribute; continuing")

        # Instantiate WOMEnv and load data (CSV etc.)
        env = WOMEnv(cfg)
        # user original main() used: wo.load_data_files()
        env.load_data_files()
        self._env = env

        # optionally set product_selected if requested and exists
        if self.product:
            if hasattr(env, "product_name_list") and self.product in getattr(env, "product_name_list"):
                setattr(env, "product_selected", self.product)
            else:
                logger.warning("Product '%s' not found in env; ignoring", self.product)

        # Prefer returning per-product outbound root if available, else env
        root = None
        try:
            if hasattr(env, "prod_tree_dict_OT") and getattr(env, "product_selected", None):
                prod = getattr(env, "product_selected")
                root = env.prod_tree_dict_OT.get(prod)
                if root:
                    # attach reference to env for plugin convenience
                    setattr(root, "_wom_env", env)
            if root is None:
                # fallback: return env itself (plugins can read env)
                root = env
        except Exception as e:
            logger.exception("Failed to build tree: %s", e)
            raise
        return root

    def collect_result(self, root: Any) -> Dict[str, Any]:
        """Collect results after planning. Return simple dict for exporters/visualizers."""
        env = self._env
        res = {
            "root": root,
            "env": env,
            "product_selected": getattr(env, "product_selected", None) if env else None,
            # keep common metrics if exist (extend as needed)
            "total_revenue": getattr(env, "total_revenue", None) if env else None,
            "total_profit": getattr(env, "total_profit", None) if env else None,
        }
        return res


class WOMPipelineRunner:
    """
    Minimal pipeline runner that:
      - creates HookBus and sets it global
      - autoloads plugins (decorator/register style)
      - builds tree via WOMIOAdapter
      - runs the planning steps in order
      - triggers hooks at important points
    """
    def __init__(self, bus: Optional[HookBus] = None, io_adapter: Optional[WOMIOAdapter] = None):
        self.bus = bus or HookBus(logger=logging.getLogger("hooks"))
        # set global for decorator-based plugins to register to this bus
        set_global(self.bus)
        # autoload plugins now so decorator/@action registrations and register(bus) can run
        autoload_plugins("pysi.plugins")

        self.io = io_adapter or WOMIOAdapter()
        self.logger = logging.getLogger("wom_pipeline")

    def run(self, data_dir: str, product: Optional[str] = None, scenario_id: str = "default") -> Dict[str, Any]:
        # pre-run hook: allow plugins to mutate inputs
        spec = {"data_dir": data_dir, "scenario_id": scenario_id, "product": product}
        spec = self.bus.apply_filters("pipeline:spec", spec)

        # build tree / load data
        self.logger.info("Building plan tree (data_dir=%s, product=%s)", data_dir, product)
        self.io.data_dir = spec.get("data_dir", data_dir)
        self.io.product = spec.get("product", product)
        root = self.io.build_tree(spec)

        # allow plugins to inspect/modify the built tree
        self.bus.do_action("pipeline:after_build", root=root, env=getattr(self.io, "_env", None))

        # run planning logic (same sequence as original main)
        env = getattr(self.io, "_env", None)
        if env is None:
            # If build_tree returned an env-like object as root, accept that
            if hasattr(root, "load_data_files"):
                env = root

        if env is None:
            raise RuntimeError("WOMEnv instance not available; cannot run planning steps")

        try:
            # pre-step hook
            self.bus.do_action("pipeline:before_planning", env=env, root=root)

            # demand planning
            if hasattr(env, "demand_planning4multi_product"):
                env.demand_planning4multi_product()
                self.bus.do_action("pipeline:after_demand_planning", env=env, root=root)
            else:
                logger.warning("env missing demand_planning4multi_product")

            # demand leveling
            if hasattr(env, "demand_leveling4multi_prod"):
                env.demand_leveling4multi_prod()
                self.bus.do_action("pipeline:after_demand_leveling", env=env, root=root)
            else:
                logger.warning("env missing demand_leveling4multi_prod")

            # supply planning
            if hasattr(env, "supply_planning4multi_product"):
                env.supply_planning4multi_product()
                self.bus.do_action("pipeline:after_supply_planning", env=env, root=root)
            else:
                logger.warning("env missing supply_planning4multi_product")

            # finalize / hooks for post-processing
            self.bus.do_action("pipeline:before_collect", env=env, root=root)
        except Exception:
            logger.exception("Planning steps failed")
            raise

        # collect results and allow filter chain for visualization/export
        result = self.io.collect_result(root)
        result = self.bus.apply_filters("pipeline:result", result)
        self.bus.do_action("pipeline:after_run", result=result)

        return result


# CLI entrypoint
def main_cli():
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(description="Run WOM pipeline")
    ap.add_argument("--data_dir", "-d", required=True, help="data directory or path (CSV etc.)")
    ap.add_argument("--product", "-p", required=False, help="product to plan (optional)")
    ap.add_argument("--scenario", "-s", required=False, help="scenario id (optional)", default="default")
    args = ap.parse_args()

    runner = WOMPipelineRunner()
    res = runner.run(data_dir=args.data_dir, product=args.product, scenario_id=args.scenario)
    print("WOM pipeline finished. result keys:", list(res.keys()))


if __name__ == "__main__":
    main_cli()

