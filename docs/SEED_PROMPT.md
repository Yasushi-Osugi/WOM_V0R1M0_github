Master Seed Prompt — Global Weekly Psi Planner (2025-09-04)
Global Weekly PSI Planner — Master SEED Prompt (DB/CLI/GUI 一体)

版: vNext (2025-09-04)
対象: PSI Planner SQL 版（PySI_V0R8_SQL 系）
目的: この 1 枚を docs/SEED_PROMPT.md に置けば、次回以降はコピペで「同じ前提・同じ手順」に即時復帰できる。

1) 目的 / 世界観

ISO 8601 週を唯一の時間軸（Monday start, 1..53）。

SQLite を正本 (SoT)。DDL → ETL → 計算 → 書戻し → レポートまで DB 一貫。

CLI/モジュールが中核（ヘッドレス）。GUI（Tkinter+matplotlib/Cartopy）は表示層で依存注入。

ネットワークはハンモック構造：Inbound(MOM*/procurement_office) ⇄ supply_point ⇄ Outbound(DAD*/sales_office)。

2) 不変条件（Invariants）

週軸: calendar_iso(week_index, iso_year, iso_week, week_start, week_end) が正本。

週配列長: あらゆる PSI 配列長 = COUNT(*) FROM calendar_iso。

週キー: (iso_year, iso_week)、内部 index: week_index(0..N-1)。

冪等性: DDL/ETL/I-O/計算/書戻しは再実行で同値（INSERT … ON CONFLICT / REPLACE / 再構成）。

lot_id: NODE-PROD-YYYYWWNNNN（週ごとに 0001 リセット、UNIQUE）。

DB が正本：GUI・CLI・ETL は DB を読む/書く。GUI は DB の利用者。

3) ディレクトリ規約 / 主要モジュール
repo/
├─ pysi/
│  ├─ app/orchestrator.py           # CLI：DDL→ETL→カレンダ→計算→書戻し→レポート
│  ├─ db/
│  │  ├─ schema_core_only.sql
│  │  ├─ apply_schema.py
│  │  ├─ calendar_iso.py, calendar_sync.py
│  ├─ etl/etl_monthly_to_lots.py    # 月次CSV→週次→weekly_demand/lot
│  ├─ io/
│  │  ├─ psi_io_adapters.py         # DB↔PSI（keyword-only）
│  │  └─ tree_writeback.py          # “薄い書戻し”シム（唯一の入口）
│  ├─ network/
│  │  ├─ network_factory.py         # 計算用 PlanNode ツリー生成
│  │  └─ factory.py                 # CLIラッパ（--network 用）
│  ├─ report/psi_report.py          # 集計 & 可視化
│  ├─ gui/lotbucket_adapter.py      # GUI直結：lot_bucket→週次描画
│  └─ scripts/                      # 点検・最適化ユーティリティ
├─ data/                             # CSV（sku_S_month_data.csv, product_tree_*.csv 等）
├─ var/                              # 生成物（DB/レポート等）
│  └─ psi.sqlite
└─ tests/                            # pytest（冪等/配列長/合計一致）
4) 実行フロー（2ルート）
A) DBファースト（完成度高 / 標準）

DDL

python -c "from pysi.db.apply_schema import apply_schema; apply_schema('var/psi.sqlite','pysi/db/schema_core_only.sql')"

ETL（月次→週次）

python -m pysi.etl.etl_monthly_to_lots --db var\psi.sqlite --csv data\sku_S_month_data.csv --scenario Baseline --default-lot-size 1000

カレンダ同期（シナリオ基準 or 明示年/期間）

python -m pysi.scripts.iso_calendar_sync_on_scenario --db var\psi.sqlite --scenario Baseline

計算＋書戻し（leaf 例）

python -m pysi.app.orchestrator --db var\psi.sqlite --scenario Baseline --mode leaf --write-all-nodes --report
B) ネットワーク（CSV）ファースト（tree）
python -m pysi.app.orchestrator --db var\psi.sqlite --scenario Baseline \
  --mode tree --network pysi.network.factory:factory --data-dir data \
  --write-all-nodes --product JPN_RICE_1 --report

factory(data_dir, product_name, direction) で製品別 PlanNode ルートを生成。

DB の scenario/weekly_demand/calendar_iso を正本に書戻し。

5) I/O 中核（唯一の入口）

使う関数は 1 つだけ：

from pysi.io.tree_writeback import write_both_layers_for_pair
write_both_layers_for_pair(conn, scenario_id, node_name, product_name) -> {"d_rows":int, "s_rows":int, "weeks":int}

内部で load_leaf_S_and_compute() → write_both_layers() を呼び、 S 生成 → S→P/I/CO 計算 → demand/supply 両レイヤ書戻しを一気通貫。

依存関数は keyword-only（positional 呼び出し禁止）：

load_leaf_S_and_compute(conn, *, scenario_id:int, node_obj, product_name:str, layer:str='demand')
write_both_layers(conn, *, scenario_id:int, node_obj, product_name:str, replace_slice:bool=True)

psi_io_adapters は 安全なバケツ化実装済み（週数合わせパディング、範囲外を空扱い）。

6) ETL（CSV契約）

需要月次 CSV は data/sku_S_month_data.csv（S_month_data.csv ではない）。

列ゆれ吸収→日次化→ISO 週集計→weekly_demand/lot に UPSERT。

node_product.lot_size は pysi.scripts.update_lot_size で一括更新可。

7) Orchestrator CLI（要点）

共通引数：--db var\psi.sqlite --scenario Baseline --mode leaf|tree [--report]。

--write-all-nodes：leaf=DB 内の全ペア、tree=ネットワークと DB の交差ペアを処理。

orchestrator は write_both_layers_for_pair() だけを呼ぶ。 余計な内部 API には依存しない。

8) GUI / 可視化

pysi.gui.lotbucket_adapter：

from pysi.gui.lotbucket_adapter import _open, fetch_weekly_buckets, plot_weekly
con = _open('var/psi.sqlite')
series = fetch_weekly_buckets(con, scenario='Baseline', node='CS_JPN', product='JPN_RICE_1', layer='demand')
plot_weekly(series, title='Baseline / demand / CS_JPN / JPN_RICE_1', style='stack')
con.close()

World Map（軽量運用 / 既定）: PlateCarree(central_longitude=180)、描画は OCEAN/LAND/COASTLINE/BORDERS のみ。ENABLE_ADMIN_OVERLAYS=False。

9) Inbound Layer（SQL）※段階導入

目的：psi_inbound を SoT に、LT/容量/受側 backlog を踏まえた週次計画を実行し inbound_results に保存。

GUI Tools: Import Inbound CSV → Build & Plan Inbound → Run E2E Plan（Inbound→Outbound）。

10) チェック & 最適化（Scripts）

点検：

python -m pysi.scripts.check_scenario --db var\psi.sqlite --scenario Baseline
python -m pysi.scripts.calendar_iso_check --db var\psi.sqlite
python -m pysi.scripts.quick_pair_check --db var\psi.sqlite --scenario Baseline --node CS_JPN --product JPN_RICE_1

性能：

python -m pysi.scripts.add_perf_indexes --db var\psi.sqlite
python -m pysi.scripts.analyze_optimize --db var\psi.sqlite
11) 品質ゲート（Quality Gates）

配列長一致：全ノードで len(psi) == COUNT(calendar_iso)。

合計一致：sum(leaf P) ≈ sum(root S)（端溢れ除く）。

冪等：同一パラメタで再実行して差分ゼロ（書戻し件数/値）。

FK 整合：PRAGMA foreign_key_check がクリーン。

12) 既知の落とし穴 / 回避

load_leaf_S_and_compute / write_both_layers を positional で呼ばない（keyword-only）。

sku_S_month_data.csv の ファイル名を取り違えない。

node/product/node_product が不足する場合は ETL 前に ensure（UPSERT）。

長時間運用：WAL + synchronous=NORMAL、週次の PRAGMA optimize を定常化。

13) KPI / シナリオ比較（次フェーズ P0-1）

テーブル（最小）：kpi_results(scenario_id,kpi_key,value) / scenario_diff(...)。

関数：calc_kpis(sid) → 保存、compare_scenarios([ids]) → 差分整形。

GUI ステータスに sum(leaf P) / sum(root S) / service_ratio を常時表示。

14) 代表ワンライナー（最短ルート）
REM DDL→ETL→カレンダ→leaf 書戻し→レポート（最短）
python -c "from pysi.db.apply_schema import apply_schema; apply_schema('var/psi.sqlite','pysi/db/schema_core_only.sql')"
python -m pysi.etl.etl_monthly_to_lots --db var\psi.sqlite --csv data\sku_S_month_data.csv --scenario Baseline --default-lot-size 1000
python -m pysi.scripts.iso_calendar_sync_on_scenario --db var\psi.sqlite --scenario Baseline
python -m pysi.app.orchestrator --db var\psi.sqlite --scenario Baseline --mode leaf --write-all-nodes --report
15) トラブルシュート

ModuleNotFoundError: ルートで -m 実行 / 完全修飾 import（from pysi...）。

no such table: DDL 未適用 → 先に apply_schema。

unable to open database: var/ 作成 & パス確認、WAL を有効化。

カレンダ範囲ずれ: sync_calendar_iso(...)（シナリオ or 明示年/期間）。

グラフ引数揺れ: orchestrator._report_one() のラッパで吸収。

16) リポジトリ運用（推奨）
git init
"var/*.sqlite`n__pycache__/`n*.pyc`nreport/*" | Out-File -Encoding ascii .gitignore
git add .
git commit -m "PSI Planner baseline"
conda env export --no-builds > environment.yml
付録: 用語

S/CO/I/P = 需要 / 繰越 / 在庫 / 供給（lot 単位）

leaf/tree = 単一ペアでの書戻し / ネットワーク計算を伴う書戻し

SoT = System of Truth（唯一の正本）
