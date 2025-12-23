# pysi/core/pipeline.py


from __future__ import annotations
from typing import Any, Dict
from pysi.core.hooks.core import HookBus

# plugin: 
from pysi.plugins.capacity_allocator import capacity_constraint_allocator


def default_allocator(graph, week_idx: int, demand_map, tickets=None, **ctx):
    """最小フォールバック：配送/入荷はゼロ、需要だけ run_one_step に渡す。"""
    return {
        "shipments": {},            # {(src, dst, prod): {"qty": ...}}
        "receipts": {},             # {node: qty}
        "demand_map": demand_map,   # {(node, prod): {week: qty}}
        "tickets": tickets or [],   # 週の需要チケット（あれば）
    }


def run_one_step(root, week_idx: int, allocation, params) -> bool:
    """週ごとの反映：receipts → shipments → demand(leaf) → 履歴ログ(+ avg_urgency)"""
    G = root["graph"]; state = root["state"]
    inv = state["inventory"]

    shipments  = allocation.get("shipments", {})
    receipts   = allocation.get("receipts",  {})
    demand_map = allocation.get("demand_map", {})

    # 1) 入荷反映
    for node, qty in receipts.items():
        if isinstance(qty, dict):
            q = float(qty.get("qty", 0.0))
        else:
            q = float(qty)
        inv[node] = inv.get(node, 0.0) + q

    # 2) 出荷反映（値が dict({"qty":..}) でも数値でもOK）
    for (src, _dst, _prod), val in shipments.items():
        q = float(val["qty"] if isinstance(val, dict) else val)
        inv[src] = max(0.0, inv.get(src, 0.0) - q)

    # 3) 需要控除（葉）
    leafs = state.get("leafs", set())
    for (node, _prod), by_week in demand_map.items():
        if node in leafs:
            qty = float(by_week.get(week_idx, 0.0))
            if qty > 0:
                inv[node] = max(0.0, inv.get(node, 0.0) - qty)

    # 4) 在庫履歴を記録（可視化用）＋ 平均urgency（数量重み）
    inv_leaf = sum(inv[n] for n in (leafs or inv.keys()))
    inv_total = sum(inv.values())

    # 平均urgency（shipments が dict 形式なら拾う）
    tot_qty = 0.0
    num_u = 0.0
    for v in shipments.values():
        if isinstance(v, dict):
            q = float(v.get("qty", 0.0))
            u = v.get("avg_urgency", None)
            tot_qty += q
            if u is not None:
                num_u += q * float(u)
    avg_u = (num_u / tot_qty) if tot_qty > 0 else None

    hist = state.setdefault("hist", {
        "week": [], "inventory": [], "inventory_total": [], "avg_urgency": []
    })
    hist["week"].append(int(week_idx))
    hist["inventory"].append(float(inv_leaf))
    hist["inventory_total"].append(float(inv_total))
    hist["avg_urgency"].append(avg_u if avg_u is not None else None)
    return True


class Pipeline:
    """ジオラマ的・段階型パイプライン。全Hookはここを通る。"""
    def __init__(self, hooks: HookBus, io, logger=None):
        self.hooks, self.io, self.logger = hooks, io, logger

    def run(self, db_path: str, scenario_id: str, calendar: Dict[str, Any], out_dir: str = "out"):
        # ---- Timebase ----
        calendar = self.hooks.apply_filters(
            "timebase:calendar:build", calendar,
            db_path=db_path, scenario_id=scenario_id, logger=self.logger, run_id=calendar.get("run_id")
        )

        # ---- Data Load ----
        self.hooks.do_action("before_data_load",
                             db_path=db_path, scenario_id=scenario_id, logger=self.logger, run_id=calendar.get("run_id"))
        spec = {"db_path": db_path, "scenario_id": scenario_id}
        spec = self.hooks.apply_filters("scenario:preload", spec,
                                        db_path=db_path, scenario_id=scenario_id, logger=self.logger, run_id=calendar.get("run_id"))
        raw = self.io.load_all(spec)
        self.hooks.do_action("after_data_load",
                             db_path=db_path, scenario_id=scenario_id, raw=raw, logger=self.logger, run_id=calendar.get("run_id"))

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

        # ---- Allocator plugin is this ----

        allocator_fn = self.hooks.apply_filters(
            "plan:allocate:capacity",
            
            capacity_constraint_allocator,   # ← ここで完全連携 
            
            #@STOP
            #default_allocator,

            graph=root, calendar=calendar, scenario_id=scenario_id, logger=self.logger
        )
        # ---- 

        demand_map = self.io.build_initial_demand(raw, params)

        # ★ tickets を作る（デフォルト実装 or プラグイン実装に委ねる）
        tickets_by_week = self.hooks.apply_filters(
            "demand:tickets:build",
            {},                               # 既定値は空
            demand_map=demand_map,            # {(node,prod):{week:qty}}
            calendar=calendar,
            logger=self.logger,
        )

        weeks = int(calendar["weeks"] if isinstance(calendar, dict) else getattr(calendar, "weeks", 0))
        for week_idx in range(int(weeks)):
            week_tickets = tickets_by_week.get(week_idx, [])

            #allocation = allocator_fn(
            #    root, week_idx, demand_map,
            #    tickets=week_tickets, calendar=calendar, logger=self.logger
            #)


            allocation = allocator_fn(
                root, week_idx, demand_map,
                tickets=week_tickets, calendar=calendar, logger=self.logger
            )

            # --- 追加：割当の“加工”フェーズ（容量クリップ等） ---
            allocation = self.hooks.apply_filters(
                "plan:allocation:mutate",
                allocation,
                graph=root, calendar=calendar, scenario_id=scenario_id,
                week_idx=week_idx, logger=self.logger,
            )


            # 直後に shipments / receipts を取り出して共通で使う
            ships = allocation.get("shipments", {}) or {}
            recs  = allocation.get("receipts",  {}) or {}




            # ---- 可視ログ（デバッグ）: ship/recv 合計と平均urgency ----
            if self.logger:
                # 合計数量
                try:
                    ship_total = sum((v["qty"] if isinstance(v, dict) else float(v)) for v in ships.values())
                except Exception:
                    ship_total = 0.0
                try:
                    recv_total = sum((v["qty"] if isinstance(v, dict) else float(v)) for v in recs.values())
                except Exception:
                    recv_total = 0.0
                # 平均urgency（数量重み）
                avg_u = None
                try:
                    num = sum((v["qty"] if isinstance(v, dict) else float(v)) for v in ships.values())
                    if num > 0:
                        avg_u = sum(
                            ((v.get("avg_urgency", 0.0) if isinstance(v, dict) else 0.0) *
                             (v["qty"] if isinstance(v, dict) else float(v)))
                            for v in ships.values()
                        ) / num
                except Exception:
                    pass
                self.logger.debug(f"[week {week_idx}] ship_total={ship_total:.2f} recv_total={recv_total:.2f} avg_u={avg_u}")

                # 既存の leaf 需要/在庫の簡易ログ
                leafs = root.get("state", {}).get("leafs", set())
                dem_leaf = 0.0
                for (n, p), by_week in demand_map.items():
                    if n in leafs:
                        dem_leaf += float(by_week.get(week_idx, 0.0))
                self.logger.debug(
                    f"[week {week_idx}] tickets={len(week_tickets)} demand_leaf={dem_leaf:.2f} "
                    f"inv_RET_01={root['state']['inventory'].get('RET_01')}"
                )

            # --- 週の move ログ（lot 単位でも集計でもOK）を state に追記 ---
            movelog = root.setdefault("state", {}).setdefault("move_log", [])

            # shipments: key = (src, dst, prod) / val = dict or number
            for k, v in (ships or {}).items():
                src, dst, prod = k
                if isinstance(v, dict):
                    qty = float(v.get("qty", 0.0))
                    avg_u = v.get("avg_urgency")
                    lot_ids = v.get("lot_ids")  # あれば list[str]
                else:
                    qty = float(v)
                    avg_u = None
                    lot_ids = None
                movelog.append({
                    "week_idx": int(week_idx),
                    "kind": "ship",
                    "src": src, "dst": dst, "product": prod,
                    "qty": qty,
                    "avg_urgency": avg_u,
                    "lot_ids": list(lot_ids) if isinstance(lot_ids, (list, tuple)) else None,
                })

            # receipts: key = node / val = dict or number
            for node, v in (recs or {}).items():
                if isinstance(v, dict):
                    qty = float(v.get("qty", 0.0))
                    lot_ids = v.get("lot_ids")
                else:
                    qty = float(v)
                    lot_ids = None
                movelog.append({
                    "week_idx": int(week_idx),
                    "kind": "recv",
                    "node": node,
                    "qty": qty,
                    "lot_ids": list(lot_ids) if isinstance(lot_ids, (list, tuple)) else None,
                })

            # 需要チケット（参考ログ）
            for t in (week_tickets or []):
                # t = {ticket_id,node,product,week,qty,urgency,...}
                movelog.append({
                    "week_idx": int(week_idx),
                    "kind": "ticket",
                    "node": t.get("node"),
                    "product": t.get("product"),
                    "qty": float(t.get("qty", 0.0)),
                    "urgency": float(t.get("urgency", 0.0)),
                    "ticket_id": t.get("ticket_id"),
                })

            # 実反映
            run_one_step(root, week_idx, allocation, params)

        # ---- Collect / Adjust ----
        result = self.io.collect_result(root, params)
        result = self.hooks.apply_filters("opt:postplan_adjust", result,
                                          db_path=db_path, scenario_id=scenario_id, logger=self.logger)

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

        exporters = self.hooks.apply_filters(
            "report:exporters",
            [self.io.export_csv],
            db_path=db_path,
            scenario_id=scenario_id,
            logger=self.logger,
            out_dir=out_dir,
        )
        self.logger and self.logger.info(f"[debug] exporters={len(exporters)} out_dir={out_dir}")

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
                             logger=self.logger, run_id=calendar.get("run_id"))
        return result
