# pysi/plugins/capacity_allocator/plugin.py
# SCN Optimiser ↔ PSI Planner 完全連携プラグイン（2025.11.21 確定版）
# weekly_constraints.json を自動で読み込み、能力制約を厳守した割当を行う

# pysi/plugins/capacity_allocator/plugin.py
# SCN Optimiser ↔ PSI Planner 完全連携プラグイン（2025.11.21 確定版）

import json
import os
from typing import Dict, Any

def _load_constraints() -> Dict[str, Any]:
    json_path = "weekly_constraints.json"
    if not os.path.exists(json_path):
        print("[Capacity Allocator] weekly_constraints.json が見つかりません。無制限で動作します。")
        return {}
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"[Capacity Allocator] 制約を読み込みました（week {data.get('valid_from_week', '?')}〜{data.get('valid_to_week', '?')}）")
        return data
    except Exception as e:
        print(f"[Capacity Allocator] JSON読み込み失敗: {e}")
        return {}

def register_hooks(hook_bus):
    @hook_bus.filter("plan:allocate:capacity")
    def capacity_allocator(graph, week_idx: int, demand_map, tickets=None, **ctx) -> Dict[str, Any]:
        constraints = _load_constraints()
        node_cap = {str(k): float(v) for k, v in constraints.get("node_capacity", {}).items()}
        edge_cap = {}
        for k, v in constraints.get("edge_flow", {}).items():
            try:
                arc = eval(k) if k.startswith("(") else tuple(k.strip("()").replace("'", "").split(", "))
                edge_cap[arc] = float(v)
            except:
                continue

        proposed = ctx.get("proposed_shipments", {})
        actual = {}
        used_node = {n: 0.0 for n in node_cap}
        used_edge = {arc: 0.0 for arc in edge_cap}

        for (src, dst, prod), val in proposed.items():
            qty = float(val.get("qty", 0) if isinstance(val, dict) else val)
            if qty <= 0: continue

            # 拠点能力
            src_limit = node_cap.get(src, float("inf"))
            remain_node = max(0.0, src_limit - used_node.get(src, 0.0))

            # レーン能力
            arc = (src, dst)
            lane_limit = edge_cap.get(arc, float("inf"))
            remain_edge = max(0.0, lane_limit - used_edge.get(arc, 0.0))

            allowed = min(qty, remain_node, remain_edge)
            if allowed > 0:
                actual[(src, dst, prod)] = {"qty": allowed}
                used_node[src] = used_node.get(src, 0.0) + allowed
                used_edge[arc] = used_edge.get(arc, 0.0) + allowed

        return {
            "shipments": actual,
            "receipts": {},
            "demand_map": demand_map,
            "tickets": tickets or [],
        }

    return hook_bus
