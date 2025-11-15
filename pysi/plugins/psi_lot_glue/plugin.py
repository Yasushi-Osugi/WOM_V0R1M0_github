# plugins/psi_lot_glue/plugin.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple
import pandas as pd

# あなたの operations から必要な関数を使う
from pysi.plan.planning_operation import (
    _build_iso_week_index_map,
    _make_lot_id_list_slots_iso,
    set_df_Slots2psi4demand,   # LEAFにS投入→S→P、非LEAFは子P集約→S→P→供給へコピー
)
# もしくは pysi.plan.operations.* の呼び方に合わせて import 名を調整


def register(bus):
    # 需要DF -> lot_id 生成（週ごと）
    def make_weekly_lots(raw: Dict[str, pd.DataFrame], **ctx) -> Dict[str, Any]:
        dem = raw.get("demand", pd.DataFrame())
        if dem.empty:
            return raw
        dem = dem.copy()
        # 1qty=1lot の素朴生成。lot_id: NODE-PROD-YYYYWW-#### 形式
        if "iso_year" not in dem.columns or "iso_week" not in dem.columns:
            # iso_year/iso_week が無い前提なら、week_idx から 2025/WW を仮生成
            dem["iso_year"] = ctx.get("calendar", {}).get("iso_year_start", 2025)
            dem["iso_week"] = dem["week_idx"].astype(int) + ctx.get("calendar", {}).get("iso_week_start", 1)
        out_rows = []

        for _, r in dem.iterrows():
            node = str(r["node_id"]); prod = str(r["product_id"])
            y = int(r["iso_year"]); ww = f"{int(r['iso_week']):02d}"
            q = int(float(r["qty"]))
            lots = [f"{node}-{prod}-{y}{ww}-{i:04d}" for i in range(1, q+1)]
            out_rows.append({"node_name": node, "product_name": prod,
                             "iso_year": y, "iso_week": ww, "S_lot": q, "lot_id_list": lots})
        weekly = pd.DataFrame(out_rows)
        raw["weekly_lots"] = weekly
        return raw

    # raw を差し替え（scenario:preload 後、load_all 直後）
    def after_data_load(**ctx):
        raw = ctx.get("raw")
        if raw is None:
            return
        updated = make_weekly_lots(raw, **ctx)
        raw.update(updated)

    bus.add_action("after_data_load", after_data_load, priority=50)



#operations.py にあるユーティリティ（ISO週インデクス化・スロット作成・S→P 変換など）を使う

#CSVAdapter.build_tree() 後に、「葉ノードへ S を投入 → S→P → 親へ P 集約（LT前倒し）」のポストオーダを
#1本のフックで流す

# set_df_Slots2psi4demand、_build_iso_week_index_map、_make_lot_id_list_slots_iso は、
# lot リストを週スロットに正規化する中心関数。operations

# “S→P”や“子P→親S（LT前倒し）”などの PSI 演算は、
# tree.py / operations.py にあるロジックをそのまま流用（calcS2P 等）

    def after_tree_build(root=None, **ctx):
        if root is None:
            return
        raw = root.get("raw", {})
        weekly = raw.get("weekly_lots", pd.DataFrame())
        if weekly.empty:
            return

        # Node 側の PSI 配列長（weeks_count）に合わせて S を投入
        # set_df_Slots2psi4demand が木全体（LEAF→ROOT）を処理してくれる実装なら、それを1発呼びでOK
        # ここでは root["node"] があればそれを使い、無ければ root["graph"] から最下流→上流の順で node-like を走査する等の橋渡しを用意
        node_like = root.get("node_obj") or root  # プロト段階の擬似
        try:
            set_df_Slots2psi4demand(node_like, weekly)  # 内部で _build_iso_week_index_map 等を使用
        except Exception as e:
            ctx.get("logger") and ctx["logger"].exception(f"set_df_Slots2psi4demand failed: {e}")

        # series.csv 用の “需要合計(=lot数)” を result に添付できるよう、root 側に覚えさせる
        # ここでは単純に葉の lot を合算（週別）
        try:
            wmax = len(getattr(node_like, "psi4demand", []))
            total = [0]*wmax
            # 葉ノード列挙（out_degree==0）
            leafs = root.get("state", {}).get("leafs", set())
            for leaf in leafs or []:
                # node_lookup はあなたの Node 辞書に合わせて取得
                n = getattr(node_like, "lookup", lambda k: None)(leaf) or node_like
                for w in range(wmax):
                    total[w] += len(n.psi4demand[w][0])  # S バケツの lot 数
            # demand_total_series を後段の to_series_df へ渡す
            root.setdefault("state", {}).setdefault("lot_view", {})["demand_total_series"] = total
        except Exception:
            pass

    bus.add_action("after_tree_build", after_tree_build, priority=80)


