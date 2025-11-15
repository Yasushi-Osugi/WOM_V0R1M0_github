# plugins/capacity_clip/plugin.py

def register(bus):
    def alloc(default_allocator, **outer_ctx):
        def _fn(graph, week_idx, demand_map, tickets=None, calendar=None, logger=None, **ctx):
            G = graph["graph"]; state = graph["state"]
            leafs = state.get("leafs", set())

            # 1) 今週の需要量（チケットがあれば優先）
            if tickets:
                tot_demand = sum(float(t.get("qty", 0.0)) for t in tickets)
                # 数量重み平均urgency
                tot_qty = tot_demand
                avg_u = (
                    sum(float(t.get("urgency", t.get("priority", 0.0))) * float(t.get("qty", 0.0))
                        for t in tickets) / tot_qty
                ) if tot_qty > 0 else None
            else:
                tot_demand = 0.0
                for (n, _p), by_week in demand_map.items():
                    if n in leafs:
                        tot_demand += float(by_week.get(week_idx, 0.0))
                avg_u = None

            # 2) 葉ノードへの直前エッジ群の“合計キャパ”
            #    （最小モデル：各 leaf に入る1本のエッジがある前提で、その capacity を寄せ集める）
            cap_edges = []   # [(src, dst, prod, cap), ...]
            cap_sum = 0.0
            for leaf in leafs:
                in_edges = list(G.in_edges(leaf, data=True))
                if not in_edges:
                    continue
                src, dst, d = in_edges[0]
                cap = float(d.get("capacity", float("inf")) or float("inf"))
                prod = d.get("product_id") or d.get("product")
                cap_edges.append((src, dst, prod, cap))
                if cap != float("inf"):
                    cap_sum += cap

            # 3) 今週の“出荷できる量”＝ 需要 と 合計capacity の小さい方
            ship_qty = min(tot_demand, cap_sum) if cap_sum > 0 else tot_demand

            # 4) capacity 比例で各 inbound edge へ配分
            shipments = {}   # {(src, dst, prod): {"qty": q, "avg_urgency": u}}
            receipts  = {}   # {dst: qty}
            if ship_qty > 0 and cap_sum > 0:
                for (src, dst, prod, cap) in cap_edges:
                    share = ship_qty * (float(cap) / cap_sum) if cap_sum > 0 else 0.0
                    shipments[(src, dst, prod)] = {"qty": share, "avg_urgency": avg_u}
                    receipts[dst] = receipts.get(dst, 0.0) + share

            if logger:
                logger.debug(f"[cap_clip] w={week_idx} demand={tot_demand:.2f} cap_sum={cap_sum:.2f} ship={ship_qty:.2f}")

            return {
                "shipments": shipments,
                "receipts": receipts,
                "demand_map": demand_map,
                "tickets": tickets or [],
            }
        return _fn
    bus.add_filter("plan:allocate:capacity", alloc, priority=50)
