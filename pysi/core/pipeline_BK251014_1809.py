# pysi/core/pipeline.py

from __future__ import annotations
from typing import Any, Dict
from pysi.core.hooks.core import HookBus

def default_allocator(graph, week_idx: int, demand_map):
    """最小のフォールバック：需要マップをそのまま返す。"""
    return demand_map

def run_one_step(root, week_idx: int, allocation, params) -> bool:
    """最小の器：実PSI更新ロジックに差し替え前提。"""
    return True

class Pipeline:
    """ジオラマ的・段階型パイプライン。全Hookはここを通る。"""
    def __init__(self, hooks: HookBus, io, logger=None):
        self.hooks, self.io, self.logger = hooks, io, logger

    def run(self, db_path: str, scenario_id: str, calendar: Dict[str, Any]):
        # ---- Timebase ----
        calendar = self.hooks.apply_filters(
            "timebase:calendar:build", calendar,
            db_path=db_path, scenario_id=scenario_id, logger=self.logger
        )

        # ---- Data Load ----
        self.hooks.do_action("before_data_load",
                             db_path=db_path, scenario_id=scenario_id, logger=self.logger)
        spec = {"db_path": db_path, "scenario_id": scenario_id}
        spec = self.hooks.apply_filters("scenario:preload", spec,
                                        db_path=db_path, scenario_id=scenario_id, logger=self.logger)
        raw = self.io.load_all(spec)
        self.hooks.do_action("after_data_load",
                             db_path=db_path, scenario_id=scenario_id, raw=raw, logger=self.logger)

        # ---- Tree Build ----
        self.hooks.do_action("before_tree_build",
                             db_path=db_path, scenario_id=scenario_id, raw=raw, logger=self.logger)
        root = self.io.build_tree(raw)
        root = self.hooks.apply_filters("plan:graph:build", root,
                                        db_path=db_path, scenario_id=scenario_id, raw=raw, logger=self.logger)
        root = self.hooks.apply_filters("opt:network_design", root,
                                        db_path=db_path, scenario_id=scenario_id, logger=self.logger)
        self.hooks.do_action("after_tree_build",
                             db_path=db_path, scenario_id=scenario_id, root=root, logger=self.logger)

        # ---- PSI Build ----
        self.hooks.do_action("before_psi_build",
                             db_path=db_path, scenario_id=scenario_id, root=root, logger=self.logger)
        params = self.io.derive_params(raw)
        params = self.hooks.apply_filters("plan:params", params,
                                          db_path=db_path, scenario_id=scenario_id, root=root, logger=self.logger)
        params = self.hooks.apply_filters("opt:capacity_plan", params,
                                          db_path=db_path, scenario_id=scenario_id, root=root, logger=self.logger)
        self.hooks.do_action("after_psi_build",
                             db_path=db_path, scenario_id=scenario_id, params=params, logger=self.logger)

        # ---- Plan / Allocate ----
        self.hooks.do_action("plan:pre",
                             db_path=db_path, scenario_id=scenario_id, calendar=calendar, logger=self.logger)
        allocator_fn = self.hooks.apply_filters("plan:allocate:capacity", default_allocator,
                                                graph=root, calendar=calendar, scenario_id=scenario_id, logger=self.logger)
        demand_map = self.io.build_initial_demand(raw, params)
        weeks = calendar["weeks"] if isinstance(calendar, dict) else getattr(calendar, "weeks", 0)
        for week_idx in range(int(weeks)):
            allocation = allocator_fn(root, week_idx, demand_map)
            run_one_step(root, week_idx, allocation, params)

        # ---- Collect / Adjust ----
        result = self.io.collect_result(root, params)
        result = self.hooks.apply_filters("opt:postplan_adjust", result,
                                          db_path=db_path, scenario_id=scenario_id, logger=self.logger)

        # ---- Output ----
        series_df = self.io.to_series_df(result)
        series_df = self.hooks.apply_filters("viz:series", series_df,
                                             db_path=db_path, scenario_id=scenario_id, logger=self.logger)
        exporters = self.hooks.apply_filters("report:exporters", [self.io.export_csv],
                                             db_path=db_path, scenario_id=scenario_id, logger=self.logger)
        for ex in exporters:
            try:
                ex(result)
            except Exception as e:
                self.logger and self.logger.exception(f"exporter failed: {e}")

        self.hooks.do_action("after_scenario_run",
                             db_path=db_path, scenario_id=scenario_id,
                             kpis=result.get("kpis") if isinstance(result, dict) else None,
                             logger=self.logger)
        return result
