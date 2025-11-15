# plugins/log_moves_csv/plugin.py
from __future__ import annotations
import csv
from pathlib import Path

def register(bus):

    def _export_moves(result, **ctx):
        out_dir = ctx.get("out_dir") or "out"
        root = (result or {}).get("root", {})
        state = root.get("state", {}) if isinstance(root, dict) else {}
        moves = state.get("move_log", []) or []

        p = Path(out_dir)
        p.mkdir(parents=True, exist_ok=True)
        out_path = p / "moves.csv"

        # ヘッダ：可変フィールドもなるべく吸収
        fieldnames = [
            "week_idx","kind","src","dst","node","product","qty",
            "avg_urgency","urgency","ticket_id","lot_ids"
        ]
        with out_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for m in moves:
                rec = {k: m.get(k) for k in fieldnames}
                # list の lot_ids は "A|B|C" などに連結
                if isinstance(rec.get("lot_ids"), (list, tuple)):
                    rec["lot_ids"] = "|".join(map(str, rec["lot_ids"]))
                w.writerow(rec)

    # report:exporters に exporter を追加
    def add_exporter(default_exporters, **ctx):
        return list(default_exporters) + [_export_moves]

    bus.add_filter("report:exporters", add_exporter, priority=90)
