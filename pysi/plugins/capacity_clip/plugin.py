# plugins/capacity_clip/plugin.py

from __future__ import annotations
from collections import defaultdict

def register(bus):
    def clip(alloc: dict, **ctx) -> dict:
        """
        plan:allocation:mutate 用の“加工”プラグイン。
        - 入力: alloc = {
            "shipments": {(src,dst,prod): {qty, lot_ids?, avg_urgency?} | number},
            "receipts":  {node: qty},  # 無くてもOK（再計算する）
            ...}
        - 役割:
            1) ネットワークの edge.capacity で shipments をクリップ
            2) lot_ids / avg_urgency など付加情報は維持
            3) クリップ後の quantities から receipts を再集計
        - 出力: 上記仕様の dict
        """
        graph   = ctx.get("graph") or {}
        G       = graph.get("graph")
        logger  = ctx.get("logger")
        week    = int(ctx.get("week_idx", 0))

        # 想定外の入力なら素通し
        if not isinstance(alloc, dict):
            return alloc

        ships_in = alloc.get("shipments", {}) or {}
        ships    = {}

        # --- 1) capacity で shipments をクリップ（lot情報は温存） ---
        for (src, dst, prod), rec in ships_in.items():
            # rec は数値 or dict を許容
            if isinstance(rec, dict):
                q_orig = float(rec.get("qty", 0.0))
                meta   = {k: v for k, v in rec.items() if k != "qty"}  # lot_ids / avg_urgency など
            else:
                q_orig = float(rec)
                meta   = {}

            cap = None
            if G is not None and G.has_edge(src, dst):
                edge_attr = G.get_edge_data(src, dst) or {}
                cap = edge_attr.get("capacity", None)

            q_clip = min(q_orig, float(cap)) if cap is not None else q_orig
            # 非負に丸め（念のため）
            q_clip = max(0.0, q_clip)

            ships[(src, dst, prod)] = {"qty": q_clip, **meta} if meta else q_clip

        # --- 2) receipts を shipments から再集計（数量整合） ---
        recv = defaultdict(float)
        for (_src, dst, _prod), rec in ships.items():
            q = float(rec["qty"] if isinstance(rec, dict) else rec)
            recv[dst] += q

        # --- 出力合成 ---
        out = dict(alloc)
        out["shipments"] = ships
        out["receipts"]  = dict(recv)

        if logger:
            ship_total = sum(float(r["qty"] if isinstance(r, dict) else r) for r in ships.values())
            logger.debug(f"[cap_clip] w={week} ship_total={ship_total:.2f}")
        return out

    # ★ 生成フェーズではなく“加工フェーズ”に登録
    bus.add_filter("plan:allocation:mutate", clip, priority=50)
