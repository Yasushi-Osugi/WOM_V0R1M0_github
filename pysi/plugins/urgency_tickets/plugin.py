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
        if horizon <= 0:
            horizon = 1  # ゼロ割り回避

        out = {}     # week -> [tickets]
        tid = 0

        for (node, prod), weeks in demand_map.items():
            for w, q in weeks.items():
                if q <= 0:
                    continue
                w_i = int(w)
                # 線形減衰: 近い週ほど高い（0..1）
                u = (horizon - w_i) / float(horizon)
                # 念のためクリップ
                if u < 0.0: u = 0.0
                if u > 1.0: u = 1.0

                tid += 1
                out.setdefault(w_i, []).append({
                    "ticket_id": f"T{tid:06d}",
                    "node": str(node),
                    "product": str(prod),
                    "week": w_i,
                    "qty": float(q),
                    "urgency": float(u),
                    "meta": {"horizon": horizon},
                })
        return out

    bus.add_filter("demand:tickets:build", build_tickets, priority=50)
