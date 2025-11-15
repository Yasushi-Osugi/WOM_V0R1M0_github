# pysi/app/narrative_compiler.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import re, sys, yaml
"""
超シンプルなパターンで narrative.txt を YAML DSL に変換
入力例（行頭"- "推奨）:
- Increase demand for RICE at TOKYO by 10% from 2026-W10 to 2026-W20
- Shutdown PLANT_A during 2026-W30..2026-W32
- Set leadtime of RICE at PORT_JP to 3w
"""
def parse_line(line: str):
    s = line.strip("- ").strip()
    m = re.match(r"Increase demand for (\S+) at (\S+) by ([\d\.]+)% from (\d{4}-W\d{2}) to (\d{4}-W\d{2})", s, re.I)
    if m:
        prod,node,pct,wf,wt = m.groups()
        return {"type":"demand_scale","product":prod,"node":node,"from":wf,"to":wt,"factor":1+float(pct)/100.0}
    m = re.match(r"Shutdown (\S+) during (\d{4}-W\d{2})\.\.(\d{4}-W\d{2})", s, re.I)
    if m:
        node, w1, w2 = m.groups()
        # 展開（簡易）：Wxx連番前提。厳密には calendar_iso 参照が好ましいが最小版として実装
        y1, W1 = int(w1[:4]), int(w1[-2:])
        y2, W2 = int(w2[:4]), int(w2[-2:])
        weeks=[]
        if y1==y2:
            for w in range(W1, W2+1):
                weeks.append(f"{y1}-W{w:02d}")
        else:
            # 年跨ぎの簡易ケース：W1..53 + 次年1..W2
            for w in range(W1, 54): weeks.append(f"{y1}-W{w:02d}")
            for w in range(1, W2+1): weeks.append(f"{y2}-W{w:02d}")
        return {"type":"shutdown_weeks","node":node,"weeks":weeks}
    m = re.match(r"Set leadtime of (\S+) at (\S+) to (\d+)w", s, re.I)
    if m:
        prod,node,weeks = m.groups()
        return {"type":"leadtime_set","product":prod,"node":node,"leadtime":int(weeks)}
    return None
def compile_narrative_to_yaml(narr_path: str, scenario: str, db: str) -> str:
    actions=[]
    for line in open(narr_path, "r", encoding="utf-8"):
        if not line.strip(): continue
        act = parse_line(line)
        if act: actions.append(act)
    cfg = {
        "scenario": scenario,
        "db": db,
        "mode": "leaf",
        "actions": actions,
        "report": {
            "outdir": "var/report",
            "fmt": "png",
            "targets": []
        }
    }
    y = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
    return y
if __name__ == "__main__":
    # 使い方: python -m pysi.app.narrative_compiler narrative.txt Baseline var/psi.sqlite > scenario.yaml
    if len(sys.argv) < 4:
        print("usage: narrative_compiler.py <narrative.txt> <scenario_name> <db_path>", file=sys.stderr)
        sys.exit(1)
    print(compile_narrative_to_yaml(sys.argv[1], sys.argv[2], sys.argv[3]))
