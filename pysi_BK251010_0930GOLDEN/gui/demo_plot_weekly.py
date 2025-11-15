# pysi/gui/demo_plot_weekly.py
#起動例（Anaconda Prompt／プロジェクトルートで）
#python -m pysi.gui.demo_plot_weekly ^
#  --db var\psi.sqlite ^
#  --scenario Baseline ^
#  --node CS_JPN ^
#  --product JPN_RICE_1 ^
#  --layer demand ^
#  --style stack ^
#  --out report\demo_weekly.png
#
#（--out を外すとウィンドウ表示します）
import argparse
import matplotlib.pyplot as plt
from pysi.gui.lotbucket_adapter import _open, fetch_weekly_buckets, plot_weekly
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--node", required=True)
    ap.add_argument("--product", required=True)
    ap.add_argument("--layer", choices=["demand", "supply"], default="demand")
    ap.add_argument("--style", choices=["stack", "line"], default="stack")
    ap.add_argument("--out", help="保存先PNG（未指定なら表示）")
    args = ap.parse_args()
    con = _open(args.db)
    series = fetch_weekly_buckets(
        con,
        scenario=args.scenario, node=args.node, product=args.product, layer=args.layer
    )
    fig, ax = plt.subplots(figsize=(10, 4))
    plot_weekly(series,
                title=f"{args.scenario} / {args.layer} / {args.node} / {args.product}",
                style=args.style, ax=ax)
    if args.out:
        fig.savefig(args.out, dpi=150, bbox_inches="tight")
        print("[saved]", args.out)
    else:
        plt.show()
    con.close()
if __name__ == "__main__":
    main()
