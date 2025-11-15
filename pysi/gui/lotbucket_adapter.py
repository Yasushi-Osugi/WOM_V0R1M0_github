# pysi/gui/lotbucket_adapter.py
# -*- coding: utf-8 -*-
"""
GUI から lot_bucket を直接集計 → 週次の S/CO/I/P を描画するための超シンプル・アダプタ
主な提供関数
- fetch_weekly_buckets(conn, *, scenario, node, product, layer="demand")
    → 週インデックス順に S/CO/I/P の個数（lot数）を返す（不足週は 0 で埋める）
- plot_weekly(series, *, title="", style="lines", ax=None)
    → matplotlib で簡単に可視化（lines or stack）
CLI テスト例
python -m pysi.gui.lotbucket_adapter --db var/psi.sqlite --scenario Baseline \
  --node CS_JPN --product JPN_RICE_1 --layer demand --out report.png
"""
from __future__ import annotations
import argparse
import sqlite3
from typing import Dict, List, Tuple, Optional
BUCKETS = ("S", "CO", "I", "P")
# ------------------------
# DB helpers
# ------------------------
def _open(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON;")
    return con
def _one(con: sqlite3.Connection, sql: str, args=()):
    cur = con.execute(sql, args)
    return cur.fetchone()
def _get_ids(con: sqlite3.Connection, scenario: str, node: str, product: str) -> Tuple[int,int,int]:
    sid = _one(con, "SELECT id FROM scenario WHERE name=?", (scenario,))
    if not sid: raise ValueError(f"scenario not found: {scenario}")
    nid = _one(con, "SELECT id FROM node WHERE name=?", (node,))
    if not nid: raise ValueError(f"node not found: {node}")
    pid = _one(con, "SELECT id FROM product WHERE name=?", (product,))
    if not pid: raise ValueError(f"product not found: {product}")
    return int(sid[0]), int(nid[0]), int(pid[0])
def _scenario_week_seq(con: sqlite3.Connection, scenario_id: int) -> List[Tuple[int,int,int]]:
    """対象シナリオの計画年範囲に入る calendar_iso の週並び (week_index, iso_year, iso_week)。"""
    row = _one(con, "SELECT plan_year_st, plan_range FROM scenario WHERE id=?", (scenario_id,))
    if not row: raise ValueError(f"scenario id not found: {scenario_id}")
    y0, pr = int(row[0]), int(row[1]); y1 = y0 + pr - 1
    seq = con.execute(
        "SELECT week_index, iso_year, iso_week FROM calendar_iso "
        "WHERE iso_year BETWEEN ? AND ? ORDER BY week_index",
        (y0, y1)
    ).fetchall()
    if not seq:
        seq = con.execute(
            "SELECT week_index, iso_year, iso_week FROM calendar_iso ORDER BY week_index"
        ).fetchall()
    return [(int(r["week_index"]), int(r["iso_year"]), int(r["iso_week"])) for r in seq]
# ------------------------
# Public API
# ------------------------
def fetch_weekly_buckets(
    con: sqlite3.Connection,
    *,
    scenario: str,
    node: str,
    product: str,
    layer: str = "demand",
) -> List[Dict]:
    """
    lot_bucket を (scenario,node,product,week_index,bucket) で集計。
    返り値は 週順 list[dict] で、各要素に S/CO/I/P を必ず含む（無ければ 0）。
    """
    if layer not in ("demand", "supply"):
        raise ValueError("layer must be 'demand' or 'supply'")
    sid, nid, pid = _get_ids(con, scenario, node, product)
    weeks = _scenario_week_seq(con, sid)
    # 初期化（全週が必ず入る）
    base = {wi: {"week_index": wi, "iso_year": y, "iso_week": w, **{b:0 for b in BUCKETS}} for wi, y, w in weeks}
    rows = con.execute(
        """
        SELECT lb.week_index, lb.bucket, COUNT(*) AS cnt
          FROM lot_bucket lb
         WHERE lb.scenario_id=? AND lb.node_id=? AND lb.product_id=?
           AND lb.layer=?
         GROUP BY lb.week_index, lb.bucket
        """, (sid, nid, pid, layer)
    ).fetchall()
    for r in rows:
        wi = int(r["week_index"]); b = r["bucket"]; c = int(r["cnt"])
        if wi in base and b in BUCKETS:
            base[wi][b] = c
    # 週インデックス昇順に整形
    series = [base[wi] for wi, *_ in weeks]
    # total（任意）
    for s in series:
        s["total"] = sum(s[b] for b in BUCKETS)
        s["label"] = f'{s["iso_year"]}-W{s["iso_week"]:02d}'
    return series
def to_dataframe(series: List[Dict]):
    """pandas があれば DataFrame に（無ければそのまま返す）。"""
    try:
        import pandas as pd
        return pd.DataFrame(series)
    except Exception:
        return series
def plot_weekly(
    series: List[Dict],
    *,
    title: str = "",
    style: str = "lines",   # "lines" or "stack"
    ax=None,
    show: bool = False,
    out: Optional[str] = None,
):
    """
    matplotlib で簡易可視化。GUI 側では ax を渡して再利用可。
    """
    import matplotlib.pyplot as plt
    import numpy as np
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 4))
    labels = [s["label"] for s in series]
    x = np.arange(len(series))
    data = {b: np.array([s[b] for s in series], dtype=float) for b in BUCKETS}
    if style == "stack":
        bottom = np.zeros_like(x, dtype=float)
        colors = {"S":"tab:blue", "CO":"tab:orange", "I":"tab:green", "P":"tab:red"}
        for b in BUCKETS:
            ax.bar(x, data[b], bottom=bottom, label=b, color=colors.get(b, None), width=1.0)
            bottom += data[b]
    else:
        # lines
        colors = {"S":"tab:blue", "CO":"tab:orange", "I":"tab:green", "P":"tab:red"}
        for b in BUCKETS:
            ax.plot(x, data[b], label=b, color=colors.get(b, None), linewidth=1.3)
    ax.set_title(title or "Weekly lots by bucket")
    ax.set_ylabel("lots")
    ax.set_xlim(0, len(x)-1 if len(x) else 0)
    # X 軸ラベルは間引き
    if len(labels) > 0:
        step = max(1, len(labels)//12)
        ax.set_xticks(x[::step], labels[::step], rotation=0, fontsize=8)
    ax.grid(True, alpha=0.25, linestyle="--")
    ax.legend()
    if out:
        plt.tight_layout()
        plt.savefig(out)
    if show:
        plt.show()
    if ax is None:
        plt.close()
# ------------------------
# CLI for quick test
# ------------------------
def _main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--node", required=True)
    ap.add_argument("--product", required=True)
    ap.add_argument("--layer", default="demand", choices=["demand","supply"])
    ap.add_argument("--style", default="lines", choices=["lines","stack"])
    ap.add_argument("--out", help="save to image file")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()
    con = _open(args.db)
    series = fetch_weekly_buckets(con, scenario=args.scenario, node=args.node,
                                  product=args.product, layer=args.layer)
    title = f'{args.scenario} / {args.layer} / {args.node} / {args.product}'
    plot_weekly(series, title=title, style=args.style, out=args.out, show=args.show)
    con.close()
    print(f"[OK] points={len(series)}", ("saved -> " + args.out) if args.out else "")
if __name__ == "__main__":
    _main()
