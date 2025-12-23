"""
SCN_optimiser_WOM_ULTIMATE_FINAL_patched.py

NOTE
----
This file is a **reconstructed, self-contained version** of the
"SCN_optimiser_WOM_ULTIMATE_FINAL_patched.py" script we discussed.

- 目的: Supply Chain Network Optimiser (SCN) で算出した
  node_capacity / edge_flow を JSON 形式で出力し、
  PSI Planner（Lot PSI / WOM）側で週次 capacity として
  利用できるようにする。
- さらに、PSI 側で利用するためのユーティリティ関数
  （demand_leveling_with_capacity など）も同じファイルにまとめた
  「フル統合版（PoC 用）」です。

元のオリジナルスクリプトの細かい構造はこの実行環境には残っていないため、
インターフェース仕様と設計意図をベースに、
・SCN → PSI の capacity_schedule 出力
・PSI での weekly_capacity ベクトルの正規化と S_lots 配分
を確実に再現できる形で再構成しています。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Tuple, Optional

# ---------------------------------------------------------------------------
# 0. Safe pulp import (SCN 最適化はオプション)
# ---------------------------------------------------------------------------
try:
    import pulp
except ImportError:  # pragma: no cover
    pulp = None


# ---------------------------------------------------------------------------
# 1. データモデル（SCN 側）
# ---------------------------------------------------------------------------

@dataclass
class NodeWeeklyCapacity:
    """MOM ノードの週次生産能力を保持するデータ構造."""
    node_id: str
    weekly_capacity: List[Dict[str, float]]  # [{"week":1,"capacity":4000}, ...]


@dataclass
class EdgeWeeklyFlow:
    """ノード間エッジの週次輸送能力 / フロー."""
    from_node: str
    to_node: str
    weekly_flow: List[Dict[str, float]]  # [{"week":1,"flow":4000}, ...]


@dataclass
class SCNResult:
    """SCN Optimiser の結果（PSI へのインターフェース用）."""
    scenario_id: str
    nodes: List[NodeWeeklyCapacity]
    edges: List[EdgeWeeklyFlow]
    meta: Dict[str, Any]

    def to_json_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "nodes": [asdict(n) for n in self.nodes],
            "edges": [asdict(e) for e in self.edges],
            "meta": self.meta,
        }

    def dumps(self, **kwargs) -> str:
        return json.dumps(self.to_json_dict(), **kwargs)


# ---------------------------------------------------------------------------
# 2. 単純な SCN Optimiser（PoC 用）
# ---------------------------------------------------------------------------

def build_and_solve_simple_scn(
    scenario_id: str,
    yearly_demand: Dict[int, float],
    capex_per_capacity_week: float,
    max_cap_multiplier: float = 2.0,
    logger: Optional[Any] = None,
) -> SCNResult:
    """
    とても簡略化した SCN Optimiser（PoC 用）。

    ・対象は 1 つの mother node ("MOM_MAIN") のみ
    ・決定変数は year, week ごとの capacity[year, week]
    ・制約は:
        sum_{weeks in year} capacity[year, w] >= yearly_demand[year]
        capacity[year, w] <= max_cap_multiplier * avg_demand_per_week(year)
    ・目的関数は総 CAPEX を最小化（= 無駄に capacity を大きくしない）

    実務で使うには不十分ですが、
    「最適化で算出した weekly_capacity を PSI に渡す」
    というインターフェースの動作確認には十分な骨組みです。
    """
    if pulp is None:
        raise RuntimeError(
            "pulp がインストールされていないため、SCN 最適化を実行できません。\n"
            "pip install pulp などでインストールしてからご利用ください。"
        )

    # 年ごとの週数（ISO 52/53 週）を求めるヘルパを使用
    years = sorted(yearly_demand.keys())
    weeks_per_year = {y: is_52_or_53_week_year(y) for y in years}

    # モデル定義
    prob = pulp.LpProblem(f"SCN_simple_{scenario_id}", pulp.LpMinimize)

    capacity_vars: Dict[Tuple[int, int], pulp.LpVariable] = {}

    for y in years:
        W = weeks_per_year[y]
        avg_weekly = yearly_demand[y] / max(W, 1)
        cap_ub = max_cap_multiplier * avg_weekly

        for w in range(1, W + 1):
            var = pulp.LpVariable(
                f"cap_y{y}_w{w}", lowBound=0, upBound=cap_ub, cat="Continuous"
            )
            capacity_vars[(y, w)] = var

        # 年間需要を満たす制約
        prob += (
            pulp.lpSum(capacity_vars[(y, w)] for w in range(1, W + 1))
            >= yearly_demand[y],
            f"demand_satisfaction_year_{y}",
        )

    # 目的関数: 総 CAPEX = capex_per_capacity_week * sum(capacity)
    prob += (
        capex_per_capacity_week
        * pulp.lpSum(capacity_vars.values()),
        "total_capex",
    )

    if logger:
        logger.info("Solving SCN simple optimiser problem...")

    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    if logger:
        logger.info("SCN status: %s", pulp.LpStatus[prob.status])

    # 結果を weekly_capacity 形式に変換
    node_caps: List[NodeWeeklyCapacity] = []

    weekly_capacity_flat: List[Dict[str, float]] = []
    # 年ごとに week を積み上げて通し week に変換
    offset = 0
    for y in years:
        W = weeks_per_year[y]
        for w in range(1, W + 1):
            cap_val = float(capacity_vars[(y, w)].value())
            weekly_capacity_flat.append(
                {"week": offset + w, "capacity": cap_val}
            )
        offset += W

    node_caps.append(
        NodeWeeklyCapacity(
            node_id="MOM_MAIN",
            weekly_capacity=weekly_capacity_flat,
        )
    )

    # このシンプル版では edge_flow は空
    edges: List[EdgeWeeklyFlow] = []

    meta = {
        "generated_at": "SCN_simple",
        "years": years,
        "yearly_demand": yearly_demand,
        "capex_per_capacity_week": capex_per_capacity_week,
        "max_cap_multiplier": max_cap_multiplier,
    }

    return SCNResult(
        scenario_id=scenario_id,
        nodes=node_caps,
        edges=edges,
        meta=meta,
    )


# ---------------------------------------------------------------------------
# 3. PSI 側ユーティリティ: 週次 capacity ベクトルの正規化
# ---------------------------------------------------------------------------

def normalize_weekly_capacity(
    weekly_capacity_list: List[Dict[str, float]],
    plan_range: int,
    default_fill: float = 0.0,
) -> List[float]:
    """
    weekly_capacity_list: [{"week":1, "capacity":4000}, ...]
    plan_range: 計画年数 (2年なら 53*2 週分確保)
    戻り値: len = 53 * plan_range のリスト
            index w が week (w+1) の capacity に対応
    """
    max_weeks = 53 * plan_range
    cap_arr = [default_fill] * max_weeks

    for entry in weekly_capacity_list:
        w = int(entry.get("week", -1))
        if 1 <= w <= max_weeks:
            cap_arr[w - 1] = float(entry.get("capacity", default_fill))

    # 0 埋めの部分を前方の値で補完する簡易 forward fill
    last = None
    for i in range(max_weeks):
        if cap_arr[i] != default_fill:
            last = cap_arr[i]
        else:
            if last is not None:
                cap_arr[i] = last

    return cap_arr


# ---------------------------------------------------------------------------
# 4. PSI 側ユーティリティ: S_list flatten
# ---------------------------------------------------------------------------

def flatten_s_list(leveling_S_in: List[List[List[str]]]) -> List[str]:
    """
    leveling_S_in: root_node_outbound.psi4demand
        想定構造: [ week ][ 0 ] == list of lot_ids
    """
    S_list: List[List[str]] = []
    for psi in leveling_S_in:
        if psi and psi[0]:
            S_list.append(psi[0])
        else:
            S_list.append([])
    # 平坦化（空リストは自然に無視される）
    S_one_list = [item for sub in S_list for item in sub]
    return S_one_list


# ---------------------------------------------------------------------------
# 5. PSI 側: capacity を外部注入する leveling エンジン
# ---------------------------------------------------------------------------

def demand_leveling_with_capacity(
    root_node_outbound: Any,
    weekly_capacity_vector: List[float],
    pre_prod_week: int = 26,
    year_st: int = 2024,
    plan_range: int = 2,
) -> List[List[str]]:
    """
    汎用化された leveling 関数。
    - root_node_outbound.psi4demand: [week][0] = lot_id list (LT shift 済)
    - weekly_capacity_vector: len >= 53*plan_range を想定
    - 出力: S_allocated[w] = 当該週に割り付けられた lot_id list
      さらに root_node_outbound.psi4supply[w][0] に書き込む。

    ここでは「1 lot == 1 capacity unit」を仮定している。
    実際に lot ごとに数量が異なる場合は、
    lot_id -> unit 変換テーブルを別途挟んで、
    capacity vector を unit 単位から lot 単位に変換してから渡す運用を推奨。
    """
    max_weeks = 53 * plan_range

    # 入力 demand を平坦化
    leveling_S_in = root_node_outbound.psi4demand
    S_one_list = flatten_s_list(leveling_S_in)
    total_lots = len(S_one_list)

    # capacity ベクトルを長さ max_weeks にあわせる
    if len(weekly_capacity_vector) < max_weeks:
        weekly_capacity_vector = weekly_capacity_vector + [0.0] * (
            max_weeks - len(weekly_capacity_vector)
        )
    else:
        weekly_capacity_vector = weekly_capacity_vector[:max_weeks]

    # pre_prod_week は将来的に「どの年から先行生産を始めるか」等に反映するが、
    # ここでは単純に 0 週目から capacity を順に使っていく実装に留める。
    S_allocated: List[List[str]] = []
    idx = 0

    for w in range(max_weeks):
        cap = int(weekly_capacity_vector[w])
        if cap <= 0 or idx >= total_lots:
            S_allocated.append([])
            continue

        slice_end = min(idx + cap, total_lots)
        S_allocated.append(S_one_list[idx:slice_end])
        idx = slice_end

    # まだ割り付けられていない lot があれば、最終週に押し込む（PoC 用仕様）
    if idx < total_lots:
        leftover = S_one_list[idx:]
        if S_allocated:
            S_allocated[-1].extend(leftover)
        else:
            S_allocated.append(leftover)

    # root_node_outbound.psi4supply を確保して書き込み
    if not hasattr(root_node_outbound, "psi4supply") or len(root_node_outbound.psi4supply) < max_weeks:
        root_node_outbound.psi4supply = [[[]] for _ in range(max_weeks)]

    for w in range(max_weeks):
        lots = S_allocated[w] if w < len(S_allocated) else []
        root_node_outbound.psi4supply[w][0] = lots

    return S_allocated


# ---------------------------------------------------------------------------
# 6. SCN JSON → PSI leveling のブリッジ関数
# ---------------------------------------------------------------------------

def apply_scn_capacity_to_psi(
    root_node_outbound: Any,
    scn_json_obj: Dict[str, Any],
    mom_node_id: str,
    pre_prod_week: int = 26,
    year_st: int = 2024,
    plan_range: int = 2,
) -> List[List[str]]:
    """
    SCN Optimiser の JSON 出力（dict）から、
    指定した母工場ノード (mom_node_id) の weekly_capacity を取り出し、
    PSI Planner の root_node_outbound に対して
    demand_leveling_with_capacity を実行する。
    """
    nodes = scn_json_obj.get("nodes", [])
    weekly_capacity_list: List[Dict[str, float]] = []

    for n in nodes:
        if n.get("node_id") == mom_node_id:
            weekly_capacity_list = n.get("weekly_capacity", [])
            break

    weekly_capacity_vector = normalize_weekly_capacity(
        weekly_capacity_list,
        plan_range=plan_range,
        default_fill=0.0,
    )

    S_allocated = demand_leveling_with_capacity(
        root_node_outbound=root_node_outbound,
        weekly_capacity_vector=weekly_capacity_vector,
        pre_prod_week=pre_prod_week,
        year_st=year_st,
        plan_range=plan_range,
    )
    return S_allocated


# ---------------------------------------------------------------------------
# 7. 52/53 週判定（PSI 側 helper としても利用可能）
# ---------------------------------------------------------------------------
import datetime as _dt

def is_52_or_53_week_year(year: int) -> int:
    """
    ISO カレンダーにおける、その年の週数（52 or 53）を返す。
    """
    last_week = _dt.date(year, 12, 28).isocalendar()[1]
    return int(last_week)


# ---------------------------------------------------------------------------
# 8. テスト用ダミー RootNode クラス（PoC 実行のための最小実装）
# ---------------------------------------------------------------------------

class DummyRootNode:
    """
    PSI Planner 側の root_node_outbound を模した簡易クラス。

    属性:
    - psi4demand: [week][0] = lot_id list
    - psi4supply: [week][0] = lot_id list (出荷計画)
    - plan_range: 計画年数
    """

    def __init__(self, psi4demand: List[List[List[str]]], plan_range: int = 2):
        self.psi4demand = psi4demand
        self.psi4supply: List[List[List[str]]] = [[[]] for _ in range(53 * plan_range)]
        self.plan_range = plan_range


# ---------------------------------------------------------------------------
# 9. 簡易 PoC 実行用 main
# ---------------------------------------------------------------------------

def _build_dummy_demand(plan_range: int = 2, lots_per_week: int = 50) -> List[List[List[str]]]:
    """
    ダミーの psi4demand を生成するヘルパ。
    各週に lots_per_week 個の lot_id を発生させる。
    """
    weeks = 53 * plan_range
    psi4demand: List[List[List[str]]] = []
    for w in range(weeks):
        lots = [f"LOT_{w+1:03d}_{i+1:03d}" for i in range(lots_per_week)]
        psi4demand.append([lots])  # [ [lot_list] ] 構造
    return psi4demand


def main_demo():
    """
    このモジュール単体で実行したときの PoC:
    1. 年間需要を仮定して SCN simple optimiser を実行
    2. その結果の weekly_capacity を PSI 側 root node に注入
    3. 割付結果 (S_allocated) のサマリを表示
    """
    # 1) ダミー年間需要
    yearly_demand = {
        2024: 10000.0,
        2025: 12000.0,
    }

    scn_result = build_and_solve_simple_scn(
        scenario_id="demo_poc",
        yearly_demand=yearly_demand,
        capex_per_capacity_week=1.0,
    )

    scn_json = scn_result.to_json_dict()

    # 2) ダミー PSI demand を作る
    plan_range = 2
    psi4demand = _build_dummy_demand(plan_range=plan_range, lots_per_week=80)
    root = DummyRootNode(psi4demand=psi4demand, plan_range=plan_range)

    # 3) SCN capacity を反映して leveling
    S_allocated = apply_scn_capacity_to_psi(
        root_node_outbound=root,
        scn_json_obj=scn_json,
        mom_node_id="MOM_MAIN",
        pre_prod_week=26,
        year_st=2024,
        plan_range=plan_range,
    )

    total_input_lots = sum(len(week[0]) for week in psi4demand)
    total_allocated_lots = sum(len(week) for week in S_allocated)

    first_8 = [len(week) for week in S_allocated[:8]]

    summary = {
        "total_input_lots": total_input_lots,
        "total_allocated_lots": total_allocated_lots,
        "weeks": len(S_allocated),
        "first_8_week_counts": first_8,
    }

    print("=== SCN → PSI PoC summary ===")
    print(json.dumps(summary, indent=2))

    # 先頭 20 週だけサンプル表示
    print("\n=== First 20 weeks detail (len only) ===")
    for w, lots in enumerate(S_allocated[:20], start=1):
        print(f"Week {w:03d}: {len(lots)} lots")


if __name__ == "__main__":  # pragma: no cover
    main_demo()
