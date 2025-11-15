
# pysi/evaluate/offering_price.py
import os
import sqlite3
import numpy as np
import pandas as pd
from typing import Iterable, Optional, Sequence, Tuple, Dict
from pysi.evaluate.cost_df_loader import build_cost_df_from_sql
# offering_price.py 先頭か本関数の上あたりに追記
from datetime import datetime
#import os
#import pandas as pd
def _dump_df(df: pd.DataFrame,
             name: str = "offering_price",
             modes=("console", "csv"),
             outdir: str = "exports") -> None:
    """
    DataFrame を可視化/保存するデバッガ。
    modes: "console" | "csv" | "md" のタプル/リストで複数指定可
    outdir: 保存ディレクトリ（自動作成）
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    modes = tuple(modes) if isinstance(modes, (list, tuple)) else (modes,)
    if "console" in modes:
        with pd.option_context("display.max_rows", None,
                               "display.max_columns", None,
                               "display.width", 180):
            print(f"\n[{name}] shape={df.shape}")
            print(df.to_string(index=False))
    if "csv" in modes:
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, f"{name}_{ts}.csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"[dump] CSV saved -> {path}")
    if "md" in modes:
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, f"{name}_{ts}.md")
        try:
            md = df.to_markdown(index=False)
        except Exception:
            # pandas<1.5互換
            md = df.head(200).to_string(index=False)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"[dump] Markdown saved -> {path}")
# =========================================
#  offering price frame builder
# =========================================
def _fetch_df(conn: sqlite3.Connection, sql: str, params: Iterable=()) -> pd.DataFrame:
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    cur.close()
    return pd.DataFrame(rows, columns=[c[0] for c in cur.description]) if rows else pd.DataFrame()
def _root_price_map(conn: sqlite3.Connection) -> pd.DataFrame:
    q = """
    SELECT product_name,
           MAX(CASE WHEN tag='ASIS' THEN price END) AS asis_root,
           MAX(CASE WHEN tag='TOBE' THEN price END) AS tobe_root
      FROM price_tag
     WHERE node_name='supply_point'
     GROUP BY product_name;
    """
    return pd.read_sql_query(q, conn).set_index("product_name")
def _node_depths_outbound(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    OUTネットを supply_point から辿った深さ（0..）を製品別に算出。
    供給グラフが無い製品や、グラフ外ノードは後で補完する。
    """
    q = """
    WITH RECURSIVE
    roots AS (
      SELECT DISTINCT product_name
        FROM price_tag
       WHERE node_name='supply_point'
    ),
    walk(product_name, node_name, depth) AS (
      SELECT pt.product_name, pt.node_name, 0
        FROM price_tag pt
       WHERE pt.node_name='supply_point'
      UNION
      SELECT pe.product_name, pe.child_name, walk.depth + 1
        FROM product_edge pe
        JOIN walk ON walk.product_name = pe.product_name
               AND walk.node_name    = pe.parent_name
       WHERE pe.bound='OUT'
    )
    SELECT product_name, node_name, MIN(depth) AS depth
      FROM walk
     GROUP BY product_name, node_name;
    """
    df = pd.read_sql_query(q, conn)
    # depth は int として扱いたい
    if not df.empty:
        df["depth"] = pd.to_numeric(df["depth"], errors="coerce").fillna(0).astype(int)
    return df
def _all_nodes_for_products(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    当該DBで登場する (product,node) の全集合を作る。
    - node_product（モデリングの主テーブル）
    - product_edge（OUT/IN 双方の親子）
    - price_tag（ASIS/TOBE の個別登録があれば拾う）
    """
    q = """
    WITH np AS (
      SELECT DISTINCT product_name, node_name FROM node_product
    ),
    pe AS (
      SELECT DISTINCT product_name, parent_name AS node_name FROM product_edge
      UNION
      SELECT DISTINCT product_name, child_name  AS node_name FROM product_edge
    ),
    pt AS (
      SELECT DISTINCT product_name, node_name FROM price_tag
    ),
    all_pairs AS (
      SELECT * FROM np
      UNION SELECT * FROM pe
      UNION SELECT * FROM pt
    )
    SELECT DISTINCT product_name, node_name FROM all_pairs
    WHERE product_name IS NOT NULL AND node_name IS NOT NULL;
    """
    return pd.read_sql_query(q, conn)
# =========================================
#  plotting helpers (Matplotlib)
# =========================================
import matplotlib
matplotlib.use("Agg")  # GUI側で使う時は FigureCanvasTkAgg を使うのでOK
import matplotlib.pyplot as plt
def plot_offering_price_grid(
    df: pd.DataFrame,
    products: Optional[Sequence[str]] = None,
    ncols: int = 2,
    height_per_row: float = 3.2,
    width: float = 12.0,
    rotate: int = 35,
) -> plt.Figure:
    """
    製品ごとの offering_price_ASIS/TOBE を全ノード並べで描く。
    - 並び順は depth -> node_name
    """
    # 対象製品リスト
    if products is None:
        products = list(df["product_name"].unique())
    products = list(products)
    if not products:
        raise ValueError("No products to plot.")
    # レイアウト
    n = len(products)
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(
        nrows, ncols,
        figsize=(width, height_per_row * nrows),
        squeeze=False
    )
    axes = axes.flatten()
    for ax, prod in zip(axes, products):
        # 該当製品のデータを並べ替え（depth -> node_name）
        sub = df[df["product_name"] == prod].copy().sort_values(["depth", "node_name"], kind="mergesort")
        # データが無い製品用のフォールバック
        if sub.empty:
            ax.set_title(str(prod), fontsize=11)
            ax.axis("off")
            continue
        x = np.arange(len(sub))
        w = 0.42  # 棒の幅（ASIS/TOBEが重ならないよう少し太め）
        asis = sub["offering_price_ASIS"].astype(float).values
        tobe = sub["offering_price_TOBE"].astype(float).values
        # 0 しかない列でも “バーは描く” （zorder 調整で見やすく）
        b1 = ax.bar(x - w/2, asis, width=w, label="offering_price_ASIS",
                    color="#4e79a7", zorder=3)
        b2 = ax.bar(x + w/2, tobe, width=w, label="offering_price_TOBE",
                    color="#f28e2b", zorder=3)
        ax.set_title(str(prod), fontsize=11)
        ax.set_xticks(x)
        ax.set_xticklabels(sub["node_name"].tolist(), rotation=rotate, ha="right", fontsize=9)
        ax.grid(axis="y", linestyle="--", alpha=0.35, zorder=0)
        ax.legend(fontsize=8, loc="upper left")
        # 上に数値（大きい時だけ）
        def _annotate(bars):
            for r in bars:
                h = float(r.get_height())
                if h <= 0:
                    continue
                ax.annotate(
                    f"{int(round(h)):,}",
                    xy=(r.get_x() + r.get_width() / 2, h),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                    color="#333"
                )
        _annotate(b1)
        _annotate(b2)
    # 余白の空サブプロットを消す
    for j in range(len(products), len(axes)):
        fig.delaxes(axes[j])
    fig.tight_layout()
    return fig

def build_offering_price_frame_OLD(
    db_path: str,
    prefer_calc_as_is: bool = True,
    tobe_mode: str = "root_scale"  # 'none' | 'root_scale'
) -> pd.DataFrame:
    import sqlite3
    import numpy as np
    import pandas as pd
    from pysi.evaluate.cost_df_loader import build_cost_df_from_sql
    conn = sqlite3.connect(db_path)
    # 1) 全 (product,node)
    pairs  = _all_nodes_for_products(conn)
    # 2) depth（OUT 親→子）
    depths = _node_depths_outbound(conn)
    # 3) price_tag（ASIS/TOBE）
    q_pt = """
    SELECT product_name, node_name,
           MAX(CASE WHEN tag='ASIS' THEN price END) AS offering_price_ASIS_pt,
           MAX(CASE WHEN tag='TOBE' THEN price END) AS offering_price_TOBE_pt
      FROM price_tag
     GROUP BY product_name, node_name;
    """
    pt = pd.read_sql_query(q_pt, conn)
    # 4) 計算由来の ASIS（nodeごとの price_sales_shipped）
    cost_df = build_cost_df_from_sql(db_path)
    calc = cost_df[["product_name","node_name","price_sales_shipped"]].copy()
    # 5) root の倍率（TOBE/ASIS）
    root = _root_price_map(conn)  # index = product_name
    conn.close()
    # === マージ ===
    df = pairs.merge(depths, on=["product_name","node_name"], how="left")
    df = df.merge(pt,   on=["product_name","node_name"], how="left")
    df = df.merge(calc, on=["product_name","node_name"], how="left")
    # depth 補完：不明は 999（最後尾）
    df["depth"] = pd.to_numeric(df["depth"], errors="coerce").fillna(999).astype(int)
    # -----------------------------
    # ASIS の決定（優先順位を切替可能）
    # -----------------------------
    asis_pt   = pd.to_numeric(df["offering_price_ASIS_pt"], errors="coerce")
    asis_calc = pd.to_numeric(df["price_sales_shipped"],   errors="coerce")
    # 0 や負値は欠損扱い（自然なフォールバックのため）
    asis_pt   = asis_pt.where(asis_pt  > 0)
    asis_calc = asis_calc.where(asis_calc > 0)
    def _root_asis(prod: str) -> float:
        if prod in root.index:
            v = root.loc[prod, "asis_root"]
            return float(v) if pd.notna(v) and float(v) > 0 else 0.0
        return 0.0
    asis_root = df["product_name"].map(_root_asis)
    if prefer_calc_as_is:
        # ✅ 計算値を最優先 → pt → root
        asis = asis_calc.combine_first(asis_pt).combine_first(asis_root)
    else:
        # 旧優先順位：pt → 計算 → root
        asis = asis_pt.combine_first(asis_calc).combine_first(asis_root)
    df["offering_price_ASIS"] = asis.fillna(0.0).astype(float)
    # -----------------------------
    # TOBE の決定（既存→補完）
    # -----------------------------
    tobe_pt = pd.to_numeric(df["offering_price_TOBE_pt"], errors="coerce")
    df["offering_price_TOBE"] = tobe_pt
    if tobe_mode == "root_scale":
        # root の倍率（TOBE/ASIS）で補完（rootに TOBE が無い場合は倍率=1.0）
        mult = {}
        for prod in df["product_name"].unique():
            if prod in root.index:
                ra = float(root.loc[prod]["asis_root"] or 0.0)
                rt = float(root.loc[prod]["tobe_root"] or 0.0)
                mult[prod] = (rt / ra) if ra > 0 else 1.0
            else:
                mult[prod] = 1.0
        scale = df["product_name"].map(mult).astype(float)
        # 既存 TOBE を優先、欠損は ASIS×倍率
        df["offering_price_TOBE"] = df["offering_price_TOBE"].combine_first(
            df["offering_price_ASIS"] * scale
        )
    # 可視ログ：ASIS=0 の候補（データ整備ヒント）
    zero_rows = df.index[df["offering_price_ASIS"] <= 0.0].tolist()
    if zero_rows:
        bad = df.loc[zero_rows, ["product_name","node_name"]].astype(str).agg(" / ".join, axis=1).tolist()
        print(f"[offering_price] ASIS==0 nodes (fallback後も0): {bad}")
    # 仕上げ
    df = df[[
        "product_name","node_name","depth",
        "offering_price_ASIS","offering_price_TOBE","price_sales_shipped"
    ]].copy()
    df = df.sort_values(["product_name","depth","node_name"], kind="mergesort").reset_index(drop=True)
    return df


#from __future__ import annotations
#from typing import Optional

def build_offering_price_frame(
    db_path: str,
    prefer_calc_as_is: bool = True,
    tobe_mode: str = "root_scale",  # 'none' | 'root_scale'
    scenario_id: Optional[str] = None,  # ★ 追加：シナリオID（Noneなら通常読み）
) -> "pd.DataFrame":
    """
    製品×ノードの offering_price（ASIS/TOBE）を組み立てて返す。
    - 並び順：depth（OUT 親→子）→ node_name
    - price_tag は、scenario_id が与えられたとき scenario_price_tag を優先する
      “オーバーレイ”で読み込む
    """

    import sqlite3
    import numpy as np  # noqa: F401（将来的な数値処理で使用可）
    import pandas as pd
    from pysi.evaluate.cost_df_loader import build_cost_df_from_sql

    conn = sqlite3.connect(db_path)

    # 1) 全 (product,node)
    pairs = _all_nodes_for_products(conn)

    # 2) depth（OUT 親→子）
    depths = _node_depths_outbound(conn)

    # 3) price_tag（ASIS/TOBE）
    base_q_pt = """
        SELECT product_name, node_name,
               MAX(CASE WHEN tag='ASIS' THEN price END) AS offering_price_ASIS_pt,
               MAX(CASE WHEN tag='TOBE' THEN price END) AS offering_price_TOBE_pt
          FROM price_tag
         GROUP BY product_name, node_name;
    """

    overlay_q_pt = """
        WITH M AS (
          -- シナリオ上書きを優先（prio=1）
          SELECT product_name, node_name, tag, price, 1 AS prio
            FROM scenario_price_tag
           WHERE scenario_id = :sid
          UNION ALL
          -- ベースの price_tag（prio=0）
          SELECT product_name, node_name, tag, price, 0 AS prio
            FROM price_tag
        )
        SELECT product_name, node_name,
               COALESCE(MAX(CASE WHEN tag='ASIS' AND prio=1 THEN price END),
                        MAX(CASE WHEN tag='ASIS' AND prio=0 THEN price END)) AS offering_price_ASIS_pt,
               COALESCE(MAX(CASE WHEN tag='TOBE' AND prio=1 THEN price END),
                        MAX(CASE WHEN tag='TOBE' AND prio=0 THEN price END)) AS offering_price_TOBE_pt
          FROM M
         GROUP BY product_name, node_name;
    """

    try:
        if scenario_id:
            pt = pd.read_sql_query(overlay_q_pt, conn, params={"sid": scenario_id})
        else:
            pt = pd.read_sql_query(base_q_pt, conn)
    except Exception as e:
        # シナリオテーブル未作成などのケースはベースにフォールバック
        print(f"[offering_price] scenario overlay failed -> fallback base: {e}")
        pt = pd.read_sql_query(base_q_pt, conn)

    # 4) 計算由来の ASIS（nodeごとの price_sales_shipped）
    cost_df = build_cost_df_from_sql(db_path)
    calc = cost_df[["product_name", "node_name", "price_sales_shipped"]].copy()

    # 5) root の倍率（TOBE/ASIS）
    root = _root_price_map(conn)  # index = product_name

    conn.close()

    # === マージ ===
    df = pairs.merge(depths, on=["product_name", "node_name"], how="left")
    df = df.merge(pt,   on=["product_name", "node_name"], how="left")
    df = df.merge(calc, on=["product_name", "node_name"], how="left")

    # depth 補完：不明は 999（最後尾）
    import pandas as pd  # for type checkers inside function scope
    df["depth"] = pd.to_numeric(df["depth"], errors="coerce").fillna(999).astype(int)

    # -----------------------------
    # ASIS の決定（優先順位を切替可能）
    # -----------------------------
    asis_pt   = pd.to_numeric(df["offering_price_ASIS_pt"], errors="coerce")
    asis_calc = pd.to_numeric(df["price_sales_shipped"],   errors="coerce")

    # 0 や負値は欠損扱い（自然なフォールバックのため）
    asis_pt   = asis_pt.where(asis_pt > 0)
    asis_calc = asis_calc.where(asis_calc > 0)

    def _root_asis(prod: str) -> float:
        if prod in root.index:
            v = root.loc[prod, "asis_root"]
            try:
                fv = float(v)
                return fv if fv > 0 else 0.0
            except Exception:
                return 0.0
        return 0.0

    asis_root = df["product_name"].map(_root_asis)

    if prefer_calc_as_is:
        # ✅ 計算値を最優先 → pt → root
        asis = asis_calc.combine_first(asis_pt).combine_first(asis_root)
    else:
        # 旧優先順位：pt → 計算 → root
        asis = asis_pt.combine_first(asis_calc).combine_first(asis_root)

    df["offering_price_ASIS"] = asis.fillna(0.0).astype(float)

    # -----------------------------
    # TOBE の決定（既存→補完）
    # -----------------------------
    tobe_pt = pd.to_numeric(df["offering_price_TOBE_pt"], errors="coerce")
    df["offering_price_TOBE"] = tobe_pt

    if tobe_mode == "root_scale":
        # root の倍率（TOBE/ASIS）で補完（rootに TOBE が無い場合は倍率=1.0）
        mult = {}
        for prod in df["product_name"].unique():
            if prod in root.index:
                try:
                    ra = float(root.loc[prod]["asis_root"] or 0.0)
                except Exception:
                    ra = 0.0
                try:
                    rt = float(root.loc[prod]["tobe_root"] or 0.0)
                except Exception:
                    rt = 0.0
                mult[prod] = (rt / ra) if ra > 0 else 1.0
            else:
                mult[prod] = 1.0

        scale = df["product_name"].map(mult).astype(float)

        # 既存 TOBE を優先、欠損は ASIS×倍率
        df["offering_price_TOBE"] = df["offering_price_TOBE"].combine_first(
            df["offering_price_ASIS"] * scale
        )

    # 可視ログ：ASIS=0 の候補（データ整備ヒント）
    zero_rows = df.index[df["offering_price_ASIS"] <= 0.0].tolist()
    if zero_rows:
        bad = df.loc[zero_rows, ["product_name", "node_name"]].astype(str).agg(" / ".join, axis=1).tolist()
        print(f"[offering_price] ASIS==0 nodes (fallback後も0): {bad}")

    # 仕上げ
    df = df[[
        "product_name", "node_name", "depth",
        "offering_price_ASIS", "offering_price_TOBE", "price_sales_shipped"
    ]].copy()

    df = df.sort_values(["product_name", "depth", "node_name"], kind="mergesort").reset_index(drop=True)

    #@251010 ADD for Hook and Plugin
    from pysi.hooks.core import hooks
    # df を返す直前
    df = hooks.apply_filters(
        "offering_price_df", df,
        db_path=db_path, scenario_id=scenario_id, source="build_offering_price_frame"
    )


    return df
