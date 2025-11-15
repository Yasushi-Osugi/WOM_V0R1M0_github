# plugins/alloc_urgency/plugin.py
from __future__ import annotations
from collections import defaultdict
from typing import List

def register(bus):
    # ---- Lot ユーティリティ（簡易版） ---------------------------------------
    def pop_lots(state: dict, node: str, product: str, need_qty: float, *,
                 synth_prefix: str | None = None, synth_ok: bool = True) -> List[str]:
        """
        在庫 lot プールから先頭取り（FIFO/FEFO は別途拡張）。
        足りない分は（許可時）合成 lot_id で埋めて可視化を継続。
        state 構造: state["lots"][node][product] = [lot_id, ...]
        """
        lots_root = state.setdefault("lots", {})
        lots_node = lots_root.setdefault(node, {})
        pool: list[str] = lots_node.setdefault(product, [])

        take = max(1, int(round(need_qty)))
        taken: List[str] = []

        # 実在 pool から pop
        while pool and len(taken) < take:
            taken.append(pool.pop(0))

        # 不足ぶんは合成 lot_id（可視化用の便宜）
        if synth_ok and len(taken) < take:
            prefix = synth_prefix or f"{product}"
            remain = take - len(taken)
            base_idx = len(taken)
            taken.extend([f"{prefix}-SYN-{i:04d}" for i in range(1, remain + 1)])

        return taken

    # def push_lots(state: dict, node: str, product: str, lot_ids: List[str]):
    #     """受領側に lot を積む（必要になったら有効化）。"""
    #     lots_root = state.setdefault("lots", {})
    #     lots_node = lots_root.setdefault(node, {})
    #     pool: list[str] = lots_node.setdefault(product, [])
    #     pool.extend(lot_ids)

    # ------------------------------------------------------------------------

    def alloc(default_allocator, **ctx):
        """
        ctx:
          - graph: root(dict) を想定（root["graph"] は nx.DiGraph）
          - tickets: 当週の demand チケット [{node, product, qty, urgency, ...}, ...]
        戻り値:
          {
            "shipments": {(src,dst,prod): {"qty": q, "lot_ids": [...], "avg_urgency": u}},
            "receipts":  {node: qty_total},  # ← run_one_step が数値前提のため numeric
            "demand_map": ...                # 後方互換
          }
        """
        root    = ctx.get("graph") or {}
        G       = root.get("graph") if isinstance(root, dict) else None
        state   = root.get("state", {}) if isinstance(root, dict) else {}
        tickets = ctx.get("tickets") or []
        week    = int(ctx.get("week_idx", 0))

        if G is None:
            # グラフがなければフォールバック
            return default_allocator(**ctx)

        # shipments/receipts の器
        shipments = defaultdict(lambda: {"qty": 0.0, "lot_ids": [], "urg_sum": 0.0, "count": 0.0})
        receipts  = defaultdict(float)

        # urgency 降順で割当
        tickets_sorted = sorted(tickets, key=lambda t: t.get("urgency", 0.0), reverse=True)

        for t in tickets_sorted:
            node = t.get("node"); prod = t.get("product"); need = float(t.get("qty", 0.0))
            if not node or not prod or need <= 0:
                continue

            in_edges = list(G.in_edges(node, data=True))
            if not in_edges:
                # 入荷元が無い場合は今回はスキップ（将来：製造/調達で生成など）
                continue

            # 簡易ポリシー：コスト最小の 1 本
            src, dst, attr = min(in_edges, key=lambda e: (e[2].get("cost") or 0.0))
            capacity = float(attr.get("capacity") or 0.0)

            # 既予約
            booked = shipments[(src, dst, prod)]["qty"]
            room   = max(0.0, capacity - booked)
            ship   = min(need, room)

            if ship > 0:
                # lot を source 側から取り出して添付
                lot_ids = pop_lots(
                    state, src, prod, ship,
                    synth_prefix=f"{prod}-W{week:02d}", synth_ok=True
                )

                rec = shipments[(src, dst, prod)]
                rec["qty"]      += ship
                rec["lot_ids"]  += lot_ids
                rec["urg_sum"]  += float(t.get("urgency", 0.0)) * ship
                rec["count"]    += ship

                receipts[dst]   += ship
                need            -= ship

            # 簡易版なので 1 本だけで終了（将来：複数分配）

        # avg_urgency を付与し、出力整形
        for k, rec in shipments.items():
            tot = rec["count"] or 1.0
            rec["avg_urgency"] = rec["urg_sum"] / tot
            rec.pop("urg_sum", None)
            rec.pop("count", None)

        return {
            "shipments": dict(shipments),
            # run_one_step が数値で受け取る仕様なので receipts は数量のみ（lot_ids は ship 側にあり moves.csv に出ます）
            "receipts": dict(receipts),
            "demand_map": ctx.get("demand_map"),
            "tickets": tickets,  # pipeline のログ出力用
        }

    # plan:allocate:capacity のフィルタとして登録
    bus.add_filter("plan:allocate:capacity", alloc, priority=60)
