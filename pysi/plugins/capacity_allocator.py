# pysi/plugins/capacity_allocator.py
# SCN Optimiser ↔ PSI Planner 完全連携プラグイン（2025.11.21 確定版）
# weekly_constraints.json を自動で読み込み、能力制約を厳守した割当を行う

import json
from typing import Dict, Any, Tuple
import os

def _load_constraints() -> Tuple[Dict[str, float], Dict[Tuple[str, str], float]]:
    """
    weekly_constraints.json を読み込み
    node_capacity と edge_flow を返す
    """
    json_path = "weekly_constraints.json"
    if not os.path.exists(json_path):
        print("[Capacity Allocator] weekly_constraints.json が見つかりません。無制限で動作します。")
        return {}, {}

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        node_cap = {str(k): float(v) for k, v in data.get("node_capacity", {}).items()}
        edge_cap = {}
        for k, v in data.get("edge_flow", {}).items():
            # '('MOMJPN', 'PADJPN')' → ('MOMJPN', 'PADJPN')
            if k.startswith("("):
                arc = eval(k)
            else:
                arc = tuple(k.strip("()").replace("'", "").split(", "))
            edge_cap[arc] = float(v)

        print(f"[Capacity Allocator] 制約を読み込みました（node: {len(node_cap)}拠点, edge: {len(edge_cap)}レーン）")
        return node_cap, edge_cap

    except Exception as e:
        print(f"[Capacity Allocator] JSON読み込み失敗: {e}。無制限で動作します。")
        return {}, {}

def capacity_constraint_allocator(
    graph, week_idx: int, demand_map, tickets=None, **ctx
) -> Dict[str, Any]:
    """
    SCN Optimiserから渡された容量制約を厳守するallocator
    Hook: plan:allocate:capacity で登録される
    """
    # 1. 制約読み込み（毎週再読込で最新を反映）
    node_cap, edge_cap = _load_constraints()

    # 2. 提案された出荷（PSI Planner本体のallocatorが生成したもの）を取得
    # ctx["proposed_shipments"] が標準的なキー（なければ空）
    proposed_shipments = ctx.get("proposed_shipments", {})

    # 3. 制約適用後の実出荷量を計算
    actual_shipments = {}
    node_used = {node: 0.0 for node in node_cap}   # 今週の使用量累計（拠点）
    edge_used = {arc: 0.0 for arc in edge_cap}     # 今週の使用量累計（レーン）

    for (src, dst, prod), val in proposed_shipments.items():
        qty = float(val.get("qty", 0) if isinstance(val, dict) else val)
        if qty <= 0:
            continue

        # 拠点能力制約（出発地）
        src_limit = node_cap.get(src, float("inf"))
        remaining_node = max(0.0, src_limit - node_used.get(src, 0.0))

        # レーン能力制約
        arc = (src, dst)
        lane_limit = edge_cap.get(arc, float("inf"))
        remaining_edge = max(0.0, lane_limit - edge_used.get(arc, 0.0))

        # 実際に流せる量
        allowed = min(qty, remaining_node, remaining_edge)
        if allowed > 0:
            actual_shipments[(src, dst, prod)] = {
                "qty": allowed,
                "original_qty": qty,
                "constrained": allowed < qty
            }

            # 使用量更新
            node_used[src] = node_used.get(src, 0.0) + allowed
            edge_used[arc] = edge_used.get(arc, 0.0) + allowed

    print(f"[Week {week_idx}] 能力制約適用後：出荷量 {sum(v['qty'] for v in actual_shipments.values()):.1f}（制約で削減された量: {sum(v.get('original_qty',0)-v['qty'] for v in actual_shipments.values() if v.get('constrained')):.1f}）")

    return {
        "shipments": actual_shipments,
        "receipts": {},                     # 入荷は別途処理
        "demand_map": demand_map,
        "tickets": tickets or [],
    }