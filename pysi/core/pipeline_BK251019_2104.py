# pysi/core/pipeline.py

from __future__ import annotations
from typing import Any, Dict
from pysi.core.hooks.core import HookBus



def default_allocator(graph, week_idx: int, demand_map):
    """最小フォールバック：配送/入荷はゼロ、需要だけ run_one_step に渡す。"""
    return {
        "shipments": {},           # {(src, dst, prod): qty}
        "receipts": {},            # {node: qty}
        "demand_map": demand_map,  # {(node, prod): {week: qty}}
    }



#def run_one_step(root, week_idx: int, allocation, params) -> bool:
#    """最小の器：実PSI更新ロジックに差し替え前提。"""
#    return True
def run_one_step_OLD(root, week_idx: int, allocation, params) -> bool:
    G = root["graph"]; state = root["state"]
    inv = state["inventory"]

    # 1) 入荷の反映（今回は割り当てをまだ使わないので 0 とする）
    #    後で allocator が作る {edge: qty} を足し込む想定
    #    まずは何もしない（拡張ポイント）

    # 2) 需要の控除（leafノードだけ）
    #    CSVAdapter.build_initial_demand の構造を流用
    demand_map = allocation  # ← 今は “week_idxの需要辞書” を渡している前提
    for (node, _prod), by_week in demand_map.items():
        qty = float(by_week.get(week_idx, 0.0))
        if qty > 0:
            inv[node] = max(0.0, inv.get(node, 0.0) - qty)
    return True



def run_one_step_OLD2(root, week_idx: int, allocation, params) -> bool:
    G = root["graph"]; state = root["state"]
    inv = state["inventory"]

    shipments = allocation.get("shipments", {})  # {(src,dst,prod): qty}
    receipts  = allocation.get("receipts",  {})  # {node: qty}
    demand_map = allocation.get("demand_map", {})  # {(node, prod): {week: qty}}

    # 1) 入荷反映
    for node, qty in receipts.items():
        inv[node] = inv.get(node, 0.0) + float(qty)

    # 2) 出荷反映（元ノードから在庫を引く）
    for (src, _dst, _prod), qty in shipments.items():
        inv[src] = max(0.0, inv.get(src, 0.0) - float(qty))

    # 3) 需要控除（葉）
    for (node, _prod), by_week in demand_map.items():
        qty = float(by_week.get(week_idx, 0.0))
        if qty > 0:
            inv[node] = max(0.0, inv.get(node, 0.0) - qty)

    return True


# pysi/core/pipeline.py （あなたの run_one_step に追記）

def run_one_step(root, week_idx: int, allocation, params) -> bool:
    G = root["graph"]; state = root["state"]
    inv = state["inventory"]

    shipments  = allocation.get("shipments", {})
    receipts   = allocation.get("receipts",  {})
    demand_map = allocation.get("demand_map", {})

    # 1) 入荷反映
    for node, qty in receipts.items():
        inv[node] = inv.get(node, 0.0) + float(qty)

    # 2) 出荷反映（将来用：器だけ）
    for (src, _dst, _prod), qty in shipments.items():
        inv[src] = max(0.0, inv.get(src, 0.0) - float(qty))

    # 3) 需要控除（葉）
    leafs = state.get("leafs", set())
    for (node, _prod), by_week in demand_map.items():
        if node in leafs:
            qty = float(by_week.get(week_idx, 0.0))
            if qty > 0:
                inv[node] = max(0.0, inv.get(node, 0.0) - qty)

    # 4) 在庫履歴を記録（可視化用）
    #    - inventory: 葉ノードの合計（葉が無ければ全ノード合計）
    #    - inventory_total: 全ノード合計（デバッグ向け）
    inv_leaf = sum(inv[n] for n in (leafs or inv.keys()))
    inv_total = sum(inv.values())

    hist = state.setdefault("hist", {"week": [], "inventory": [], "inventory_total": []})
    hist["week"].append(int(week_idx))
    hist["inventory"].append(float(inv_leaf))
    hist["inventory_total"].append(float(inv_total))
    return True






class Pipeline:
    """ジオラマ的・段階型パイプライン。全Hookはここを通る。"""
    def __init__(self, hooks: HookBus, io, logger=None):
        self.hooks, self.io, self.logger = hooks, io, logger

    def run(self, db_path: str, scenario_id: str, calendar: Dict[str, Any], out_dir: str = "out"):
    #def run(self, db_path: str, scenario_id: str, calendar: Dict[str, Any]):
        # ---- Timebase ----
        calendar = self.hooks.apply_filters(
            "timebase:calendar:build", calendar,
            db_path=db_path, scenario_id=scenario_id, logger=self.logger, run_id=calendar.get("run_id")
            #@STOP
            #db_path=db_path, scenario_id=scenario_id, logger=self.logger
        )

        # ---- Data Load ----
        self.hooks.do_action("before_data_load",
                             db_path=db_path, scenario_id=scenario_id, logger=self.logger, run_id=calendar.get("run_id")
                            )
                            #@STOP
                            #db_path=db_path, scenario_id=scenario_id, logger=self.logger)

        spec = {"db_path": db_path, "scenario_id": scenario_id}
        spec = self.hooks.apply_filters("scenario:preload", spec,
                                        db_path=db_path, scenario_id=scenario_id, logger=self.logger, run_id=calendar.get("run_id"))
                                        #@STOP
                                        #db_path=db_path, scenario_id=scenario_id, logger=self.logger)
        raw = self.io.load_all(spec)
        self.hooks.do_action("after_data_load",
                             db_path=db_path, scenario_id=scenario_id, raw=raw, logger=self.logger, run_id=calendar.get("run_id"))
                            #@STOP
                            #db_path=db_path, scenario_id=scenario_id, raw=raw, logger=self.logger)

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


            # Plan / Allocate ループ内、run_one_step の直前あたりに追加（任意）
            # デバッグを見たいときは、ロガーを DEBUG に
            # （例：make_logger で環境変数 LOGLEVEL=DEBUG を読んで反映、など）。
            if self.logger:
                leafs = root.get("state", {}).get("leafs", set())
                dem_leaf = 0.0
                for (n, p), by_week in demand_map.items():
                    if n in leafs:
                        dem_leaf += float(by_week.get(week_idx, 0.0))
                self.logger.debug(f"[week {week_idx}] demand_leaf={dem_leaf:.2f} inv_RET_01={root['state']['inventory'].get('RET_01')}")


            run_one_step(root, week_idx, allocation, params)






        # ---- Collect / Adjust ----
        result = self.io.collect_result(root, params)
        result = self.hooks.apply_filters("opt:postplan_adjust", result,
                                          db_path=db_path, scenario_id=scenario_id, logger=self.logger)




        # ---- Output ----
        #series_df = self.io.to_series_df(result)

        #@STOP
        ## weeks（地平）を把握
        #weeks = int(calendar["weeks"] if isinstance(calendar, dict) else getattr(calendar, "weeks", 0))
        #series_df = self.io.to_series_df(result, horizon=weeks)
        #
        #series_df = self.hooks.apply_filters("viz:series", series_df,
        #                                     #db_path=db_path, scenario_id=scenario_id, logger=self.logger)
        #                                     db_path=db_path, scenario_id=scenario_id,
        #                                     logger=self.logger, out_dir=out_dir)



        # ---- Output ----
        weeks = int(calendar["weeks"] if isinstance(calendar, dict) else getattr(calendar, "weeks", 0))
        series_df = self.io.to_series_df(result, horizon=weeks)

        series_df = self.hooks.apply_filters(
            "viz:series", series_df,
            db_path=db_path, scenario_id=scenario_id,
            logger=self.logger, out_dir=out_dir
        )

        # Exporter で参照できるように結果に添付
        if isinstance(result, dict):
            result["series_df"] = series_df

            # ★フォールバックの週次 psi_df を自動作成（プラグインが用意してなければ）
            #if "psi_df" not in result or result["psi_df"] is None:

            # ★フォールバックの週次 psi_df を自動作成
            #    既存 psi_df が week_idx を持たない（=スナップショット）場合も上書きする
            if (
                "psi_df" not in result
                or result["psi_df"] is None
                or not hasattr(result["psi_df"], "columns")
                or "week_idx" not in result["psi_df"].columns
            ):
        
                result["psi_df"] = (
                    series_df.rename(columns={"demand_total": "demand"})
                            .assign(node_id="ALL", product_id="*")
                            [["week_idx", "node_id", "product_id", "inventory", "demand"]]
                )







                result["psi_df"] = (
                    series_df.rename(columns={"demand_total": "demand"})
                            .assign(node_id="ALL", product_id="*")
                            [["week_idx", "node_id", "product_id", "inventory", "demand"]]
                )



        ## Exporter で参照できるように結果に添付
        #if isinstance(result, dict):
        #    result["series_df"] = series_df


        exporters = self.hooks.apply_filters(
            "report:exporters",
            [self.io.export_csv],
            db_path=db_path,
            scenario_id=scenario_id,
            logger=self.logger,
            out_dir=out_dir,
        )


        #exporters = self.hooks.apply_filters("report:exporters", [self.io.export_csv],
        #                                     db_path=db_path, scenario_id=scenario_id,
        #                                     logger=self.logger, out_dir=out_dir)
        
        #exporters = self.hooks.apply_filters("report:exporters", [self.io.export_csv],
        #                                     db_path=db_path, scenario_id=scenario_id,
        #                                     out_dir=out_dir, logger=self.logger)                                             
        #                                     #db_path=db_path, scenario_id=scenario_id, logger=self.logger)

        self.logger and self.logger.info(f"[debug] exporters={len(exporters)} out_dir={out_dir}")

        #for ex in exporters:
        #    try:
        #        ex(result)
        #    except Exception as e:
        #        self.logger and self.logger.exception(f"exporter failed: {e}")

        export_ctx = {
            "db_path": db_path,
            "scenario_id": scenario_id,
            "logger": self.logger,
            "out_dir": out_dir,
        }
        for ex in exporters:
            try:
                # 新API: **export_ctx を受け取るExporter
                ex(result, **export_ctx)
            except TypeError:
                # 後方互換: 旧Exporter（引数 result のみ）
                ex(result)
            except Exception as e:
                self.logger and self.logger.exception(f"exporter failed: {e}")








        self.hooks.do_action("after_scenario_run",
                             db_path=db_path, scenario_id=scenario_id,
                             kpis=result.get("kpis") if isinstance(result, dict) else None,
                             logger=self.logger, run_id=calendar.get("run_id"))  #@ADD run_id
        return result


