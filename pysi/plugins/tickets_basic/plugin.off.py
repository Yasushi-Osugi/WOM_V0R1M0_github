# plugins/tickets_basic/plugin.py
from __future__ import annotations

def register(bus):
    """
    demand_map {(node,prod): {week: qty}} → tickets_by_week {w: [ticket,...]}
    まずは urgency=1.0 の定数で可視化確認。後から自由に変えられます。
    """
    def build_tickets(default, demand_map=None, calendar=None, logger=None, **kw):
        weeks = int(calendar.get("weeks", 0)) if isinstance(calendar, dict) else int(getattr(calendar, "weeks", 0) or 0)
        out = {w: [] for w in range(weeks)}

        for (node, prod), by_week in (demand_map or {}).items():
            for w, qty in by_week.items():
                qty = float(qty)
                if qty > 0:
                    out.setdefault(int(w), []).append({
                        "node": node,
                        "product": prod,
                        "qty": qty,
                        "urgency": 1.0,   # ★まずは定数で可視化
                    })
        return out

    bus.add_filter("demand:tickets:build", build_tickets, priority=50)

