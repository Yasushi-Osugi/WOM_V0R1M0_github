# plugins/tickets_simple/plugin.py
def register(bus):
    def build_tickets(default, **ctx):
        demand_map = ctx.get("demand_map", {})  # {(node,prod): {week: qty}}
        calendar   = ctx.get("calendar", {})    # {"weeks": N, ...}
        weeks = int(calendar["weeks"] if isinstance(calendar, dict) else 0)

        # 週ごとのチケットリストを作る: {week_idx: [ticket, ...]}
        out = {w: [] for w in range(weeks)}
        for (node, prod), by_week in (demand_map or {}).items():
            for w, qty in by_week.items():
                if not (0 <= int(w) < weeks): 
                    continue
                q = float(qty)
                if q <= 0:
                    continue

                # ★簡易ルール：近い週ほど高いurgency（例）
                #   今週:0.8 / 1週先:0.5 / 2週先以降:0.2
                dist = 0  # ここでは “当該週のチケット” を作るので距離0とみなす
                if dist <= 0:
                    u = 0.8
                elif dist == 1:
                    u = 0.5
                else:
                    u = 0.2

                out[int(w)].append({
                    "node": node,
                    "product": prod,
                    "qty": q,
                    "urgency": u,
                    # 任意: ここに lot_id 群や顧客注文IDなども付けられる
                })
        return out

    bus.add_filter("demand:tickets:build", build_tickets, priority=50)

