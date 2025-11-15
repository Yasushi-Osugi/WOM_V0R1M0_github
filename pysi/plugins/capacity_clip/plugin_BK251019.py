# plugins/capacity_clip/plugin.py
def register_OLD(bus):
    """
    各週、葉ノードの需要を「直前エッジの容量」でクリップして配船する最小ロジック。
    - エッジ属性: capacity（edges.csvの列）
    - 在庫は見ない/複数段供給は未対応（まずは“器”として）
    """
    def clip_allocator(base_alloc, graph=None, calendar=None, **ctx):
        G = graph["graph"]
        leafs = graph["state"]["leafs"]

        def alloc(root, week_idx, demand_map):
            shipments, receipts = {}, {}

            # 葉ノード向け需要（当週）を集計
            remaining = {}  # {(leaf, prod): qty}
            for (node, prod), by_week in demand_map.items():
                if node in leafs:
                    qty = float(by_week.get(week_idx, 0.0))
                    if qty > 0:
                        remaining[(node, prod)] = qty

            # 需要を直前エッジの capacity で“手前から順に”埋める（最小実装）
            for (leaf, prod), rem in list(remaining.items()):
                if rem <= 0:
                    continue
                for pred in G.predecessors(leaf):
                    edge = G[pred][leaf]
                    cap = float(edge.get("capacity", 0.0) or 0.0)
                    if cap <= 0:
                        continue
                    q = min(cap, rem)
                    if q <= 0:
                        continue
                    shipments[(pred, leaf, prod)] = shipments.get((pred, leaf, prod), 0.0) + q
                    receipts[leaf] = receipts.get(leaf, 0.0) + q
                    rem -= q
                    if rem <= 0:
                        break
                remaining[(leaf, prod)] = rem  # 余ったら欠品扱い（今回はKPI化しない）

            # base_alloc は今は空器だが、将来合成したくなった場合に備えてマージ
            base = {"shipments": {}, "receipts": {}, "demand_map": demand_map}
            out = {
                "shipments": {**base.get("shipments", {}), **shipments},
                "receipts":  {**base.get("receipts",  {}), **receipts },
                "demand_map": demand_map,
            }
            return out
        return alloc

    # 既定 allocator を包む
    bus.add_filter("plan:allocate:capacity", clip_allocator, priority=70)




# plugins/capacity_clip/plugin.py
def register(bus):
    def alloc(default_allocator, **ctx):
        """
        plan:allocate:capacity フィルタ
        - default_allocator を差し替えて、毎週の割当て関数 _fn を返す
        - graph/state/demand_map を使って shipments/receipts を作る
        """
        root = ctx.get("graph")
        logger = ctx.get("logger")
        if not isinstance(root, dict) or "graph" not in root:
            # グラフ未構築ならフォールバック
            return default_allocator

        G = root["graph"]
        state = root.get("state", {})
        leafs = state.get("leafs", set()) or set()

        def _fn(root, week_idx, demand_map):
            shipments = {}  # {(src,dst,prod): qty}
            receipts  = {}  # {node: qty}

            # 各 leaf について、その週の需要合計を計算
            for leaf in leafs:
                dem = 0.0
                for (node, prod), by_week in (demand_map or {}).items():
                    if node == leaf:
                        dem += float(by_week.get(week_idx, 0.0))

                if dem <= 0:
                    continue

                # 直前（inbound）のエッジから供給（最初の1本だけ使う簡易版）
                for pred in G.predecessors(leaf):
                    e = G[pred][leaf]
                    cap = float(e.get("capacity") or 0.0)
                    prod = e.get("product") or e.get("product_id")
                    qty = min(cap, dem)
                    if qty > 0:
                        shipments[(str(pred), str(leaf), str(prod))] = qty
                        receipts[leaf] = receipts.get(leaf, 0.0) + qty
                        break  # まずは1本だけ（簡易）

            if logger:
                s_total = sum(shipments.values()) if shipments else 0.0
                r_total = sum(receipts.values()) if receipts else 0.0
                logger.debug(f"[alloc] week={week_idx} ship_total={s_total} recv_total={r_total}")

            # run_one_step() が解釈できる形で返す
            return {
                "shipments": shipments,
                "receipts" : receipts,
                "demand_map": demand_map,
            }

        return _fn

    # default_allocator を差し替える（優先度はお好みで）
    bus.add_filter("plan:allocate:capacity", alloc, priority=80)

