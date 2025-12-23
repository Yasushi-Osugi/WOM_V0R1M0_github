# pysi/scenario/index.py
from dataclasses import dataclass
from pathlib import Path
import json
from typing import Dict, List


@dataclass
class ScenarioRecord:
    id: str
    file_name: str
    kind: str   # "BL" / "EC" / "MI"
    label: str
    path: Path


def discover_scenarios(scenario_dir: Path) -> Dict[str, List[ScenarioRecord]]:

    # ★ ここがデバッグ用の print を入れる場所
    print("[discover] scanning:", scenario_dir)
    files = list(scenario_dir.glob("*_scenario.json"))
    print("[discover] files:", [f.name for f in files])
    result = {"BL": [], "EC": [], "MI": []}

    if not scenario_dir.exists():
        return result

    for path in scenario_dir.glob("*_scenario.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            print(f"[discover] skip {path.name}: JSON error -> {e}")
            continue

        kind = data.get("scenario_type")  # "BL" / "EC" / "MI"
        if kind not in result:
            continue
        rec = ScenarioRecord(
            id=data.get("scenario_id", path.stem),
            file_name=path.name,
            kind=kind,
            label=data.get("label", data.get("name", path.stem)),
            path=path,
        )
        result[kind].append(rec)

        #@251129 CHECK
        print("result[kind].append(rec)", result)

    return result


def find_scenario_by_id(index: Dict[str, List[ScenarioRecord]],
                        kind: str,
                        scenario_id: str) -> ScenarioRecord | None:
    for rec in index.get(kind, []):
        if rec.id == scenario_id:
            return rec
    return None
