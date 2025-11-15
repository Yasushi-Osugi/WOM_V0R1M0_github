# plugins/urgency_tickets/plugin.py
from __future__ import annotations

def register(bus):
    def build_tickets(default: dict, **ctx):
        """
        demand_map: {(node, prod): {week: qty}}
        出力: tickets_by_week: {week: [ticket,...]}
        ticket = {ticket_id, node, product, week, qty, urgency, meta}
        """
        demand_map = ctx.get("demand_map") or {}
        cal = ctx.get("calendar")
        horizon = (
            int(cal.get("weeks", 0)) if isinstance(cal, dict)
            else int(getattr(cal, "weeks", 0))
        )

        out = {}     # week -> [tickets]
        tid = 0

        for (node, prod), weeks in demand_map.items():
            for w, q in weeks.items():
                if q <= 0:
                    continue
                w_i = int(w)
                # 期限が近いほど高いu（例：3週残で1.0、以遠は上限1.0でクリップ）
                rem = max(1, horizon - w_i)
                u = min(1.0, 1.0 / rem * 3.0)

                tid += 1
                out.setdefault(w_i, []).append({
                    "ticket_id": f"T{tid:06d}",
                    "node": str(node),
                    "product": str(prod),
                    "week": w_i,
                    "qty": float(q),
                    "urgency": float(u),
                    "meta": {"rem_weeks": rem},
                })
        return out

    # demand:tickets:build フィルタに差し込む（他のチケット生成より前後させたい場合は priority を調整）
    bus.add_filter("demand:tickets:build", build_tickets, priority=50)
