# pysi/scenario/loader.py
from __future__ import annotations
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple

ScenarioType = Literal["BL", "EC", "MI"]


@dataclass
class ScenarioRecord:
    """ディスク上の JSON 1本分のメタ情報＋中身."""
    type: ScenarioType      # "BL" / "EC" / "MI"
    id: str                 # scenario_meta.scenario_id
    label: str              # scenario_meta.label
    path: str               # ファイルパス
    payload: Dict[str, Any] # JSON 全体


# ---- 内部ヘルパ -------------------------------------------------------------

def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _detect_type(payload: Dict[str, Any]) -> ScenarioType:
    sv = str(payload.get("schema_version", ""))
    if sv.startswith("WOM_BL_scenario"):
        return "BL"
    if sv.startswith("WOM_EC_scenario"):
        return "EC"
    if sv.startswith("WOM_MI_scenario"):
        return "MI"

    # schema_version が無い／古い場合のフォールバック
    if "calendar" in payload and "scope" in payload and "kpi_targets" in payload:
        return "BL"
    if "external_drivers" in payload and "mapping_to_WOM" in payload:
        return "EC"
    if "references" in payload and "kpi_targets_final" in payload:
        return "MI"

    raise ValueError(f"Could not detect scenario type (schema_version={sv!r}).")


def _require_keys(payload: Dict[str, Any], keys: List[str], where: str) -> None:
    missing = [k for k in keys if k not in payload]
    if missing:
        raise ValueError(f"{where}: missing required keys: {missing}")


# ---- 軽量なバリデーション ---------------------------------------------------

def validate_bl_scenario(payload: Dict[str, Any]) -> None:
    _require_keys(payload, ["schema_version", "scenario_meta", "calendar", "scope", "kpi_targets"], "BL_scenario")
    meta = payload["scenario_meta"]
    _require_keys(meta, ["scenario_id", "label"], "BL_scenario.scenario_meta")


def validate_ec_scenario(payload: Dict[str, Any]) -> None:
    _require_keys(payload, ["schema_version", "scenario_meta", "external_drivers", "mapping_to_WOM"], "EC_scenario")
    meta = payload["scenario_meta"]
    _require_keys(meta, ["scenario_id", "label"], "EC_scenario.scenario_meta")


def validate_mi_scenario(payload: Dict[str, Any]) -> None:
    _require_keys(payload, ["schema_version", "scenario_meta", "references", "kpi_targets_final"], "MI_scenario")
    meta = payload["scenario_meta"]
    _require_keys(meta, ["scenario_id", "label"], "MI_scenario.scenario_meta")


def validate_scenario(payload: Dict[str, Any]) -> ScenarioType:
    stype = _detect_type(payload)
    if stype == "BL":
        validate_bl_scenario(payload)
    elif stype == "EC":
        validate_ec_scenario(payload)
    elif stype == "MI":
        validate_mi_scenario(payload)
    return stype


# ---- 単一ファイルロード ------------------------------------------------------

def load_scenario_file(path: str) -> ScenarioRecord:
    """1 本の *_scenario.json をロード＋バリデーション."""
    payload = _load_json(path)
    stype = validate_scenario(payload)
    meta = payload.get("scenario_meta", {})
    sid = str(meta.get("scenario_id", os.path.basename(path)))
    label = str(meta.get("label", sid))
    return ScenarioRecord(type=stype, id=sid, label=label, path=path, payload=payload)


# ---- ディレクトリ内のシナリオ探索 -------------------------------------------

def discover_scenarios(base_dir: str) -> Dict[ScenarioType, List[ScenarioRecord]]:
    """
    base_dir 配下の *_scenario.json を片っ端から読む。
    成功したものだけ返す（失敗したものは print してスキップ）。
    """
    result: Dict[ScenarioType, List[ScenarioRecord]] = {"BL": [], "EC": [], "MI": []}
    if not os.path.isdir(base_dir):
        print(f"[scenario] base_dir not found: {base_dir}")
        return result

    for fname in os.listdir(base_dir):
        if not fname.endswith("_scenario.json"):
            continue
        path = os.path.join(base_dir, fname)
        try:
            rec = load_scenario_file(path)
        except Exception as e:
            print(f"[scenario] skip {fname}: {e}")
            continue
        result[rec.type].append(rec)

    # scenario_id でソートしておくと扱いやすい
    for t in result:
        result[t].sort(key=lambda r: r.id)
    return result


# ---- 簡単な検索ヘルパ -------------------------------------------------------

def find_scenario_by_id(index: Dict[ScenarioType, List[ScenarioRecord]],
                        stype: ScenarioType,
                        scenario_id: str) -> Optional[ScenarioRecord]:
    for rec in index.get(stype, []):
        if rec.id == scenario_id:
            return rec
    return None
