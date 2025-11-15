# plugins/capacity_clip/plugin.py
from __future__ import annotations
from collections import defaultdict

def register(bus):
    def clip(alloc: dict, **ctx) -> dict:
        """
        plan:allocation:mutate 用の“加工”プラグイン。
        入力: alloc = {
            "shipments": {(src,dst,prod): {qty, lot_ids?, avg_urgency?} | number},
            "receipts": {node: qty}, ...}
        出力: 上記を容量(capacity)でクリップしたもの（lot_ids 等の付加情報は維持）
        """
        graph   = ctx.get("graph") or {}
        G       = graph.get("graph")
        logger  = ctx.get("logger")
        week    = int(ctx.get("week_idx", 0))

        if not isinstance(alloc, dict):
            return alloc

        ships_in = alloc.get("shipments", {}) or {}
        ships    = {}

        # エッジ容量で shipments をクリップ
        for (src, dst, prod), rec in ships_in.items():
            # rec は数値または dict を許容
            if isinstance(rec, dict):
                q_orig = float(rec.get("qty", 0.0))
                # lot_ids / avg_urgency など温存
                meta   = {k: v for k, v in rec.items() if k != "qty"}
            else:
                q_orig = float(rec)
                meta   = {}

            cap = None
            if G is not None and G.has_edge(src, dst):
                attr = G.get_edge_data(src, dst) or {}
                cap = attr.get("capacity", None)

            q_clip = min(q_orig, float(cap)) if cap is not None else q_orig
            ships[(src, dst, prod)] = {"qty": q_clip, **meta} if meta else q_clip

        # receipts を shipments から再集計（数量整合）
        recv = defaultdict(float)
        for (src, dst, prod), rec in ships.items():
            q = float(rec["qty"] if isinstance(rec, dict) else rec)
            recv[dst] += q

        out = dict(alloc)
        out["shipments"] = ships
        out["receipts"]  = dict(recv)

        if logger:
            ship_total = sum(float(r["qty"] if isinstance(r, dict) else r) for r in ships.values())
            logger.debug(f"[cap_clip] w={week} ship_total={ship_total:.2f}")
        return out

    # ★ 生成ではなく“加工フェーズ”に登録
    bus.add_filter("plan:allocation:mutate", clip, priority=50)
