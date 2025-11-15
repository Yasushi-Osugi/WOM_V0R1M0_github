
了解！ここまでの合意・設計・手順を“そのまま貼って使える”形でまとめた seed prompt を用意しました。リポジトリの `docs/SEED_PROMPT.md` や VS Code のワークスペースノートにコピペしてお使いください。

---

# PySI / PSI Planner Seed Prompt（現状合意）

## 目的

* ISO 8601 週（Monday start, 1..53）を**唯一の正本**にしたグローバル週次 PSI Planner を構築。
* データは SQLite を正本（DDL/ETL/I/O/可視化まで一貫）。
* PySI core は **CLI単体でヘッドレス稼働**、GUI(Tkinter+matplotlib)はフロントとして**差し替え可能**。

## 原則（不変条件）

* 週の正本: `calendar_iso(week_index, iso_year, iso_week, week_start, week_end)`
  → 以後あらゆる PSI 配列長は `COUNT(*) FROM calendar_iso` に一致させる。
* 週キー: `(iso_year, iso_week)`、内部インデックス: `week_index(0..N-1)`。
* **冪等性**: DDL/ETL/I-O/演算は再実行しても同じ状態（INSERT…ON CONFLICT / 置換 / 再構成）。
* lot\_id: `NODE-PROD-YYYYWWNNNN`（週ごとに 0001 リセット、`lot_id` は UNIQUE）。

## 推奨ディレクトリ構成（合意）

```
your-repo/
├─ pysi/
│  ├─ db/           # DDL & カレンダ
│  │  ├─ schema_core_only.sql
│  │  ├─ apply_schema.py
│  │  ├─ calendar_iso.py
│  │  └─ calendar_sync.py      # sync_calendar_iso を“ユニバーサル”化
│  ├─ etl/
│  │  └─ etl_monthly_to_lots.py # CSV→週→lot（冪等）
│  ├─ io/
│  │  └─ psi_io_adapters.py     # DB↔PSI 注入/書戻し
│  ├─ plan/
│  │  ├─ engine_hardening.py    # 冪等 S→P/I 再構成
│  │  └─ run_pass.py            # post-order 冪等実行
│  ├─ report/
│  │  └─ psi_report.py          # 週次 S/CO/I/P 集計とグラフ
│  ├─ app/
│  │  └─ orchestrator.py        # CLIの顔
│  ├─ network/                  # PlanNode 等（既存）
│  └─ scripts/
│     ├─ iso_calendar_sync_on_scenario.py
│     └─ calendar_iso_check.py
├─ data/                        # 入力CSV（例：S_month_data.csv など）
├─ var/                         # 生成物（DB・レポート）
│  └─ psi.sqlite
├─ tests/                       # pytest（冪等/休暇/集約テスト）
└─ main.py                      # GUI起動（依存注入）
```

## コア機能（ステップ別）

1. \#カレンダ: `pysi/db/calendar_iso.py`

   * `ensure_calendar_iso(conn, plan_year_st, plan_range) -> rows`
2. \#DDL: `pysi/db/schema_core_only.sql`（core テーブルのみ）
3. \#ETL: `pysi/etl/etl_monthly_to_lots.py`

   * CSV 正規化（列ゆれ吸収）→ 日次化 → ISO週集計
   * `node/product/scenario` を ensure、`weekly_demand` と `lot` に UPSERT
   * `lot_size` 参照、`S_lot=ceil(value/lot_size)`、`lot_id` 生成
4. \#I/O: `pysi/io/psi_io_adapters.py`

   * DB→PSI: `load_leaf_S_and_compute(...)`（lot→S, S→P, demand→supply）
   * PSI→DB: `write_both_layers(...)`（`lot_bucket` へ冪等書戻し）
   * `get_scenario_id/get_scenario_bounds`、week\_map の提供あり
5. \#整合テスト: `scripts/psi_consistency_tests.py`（任意）
6. \#可視化: `pysi/report/psi_report.py`（集計 CSV & PNG/SVG/PDF）
7. \#エンジン冪等: `pysi/plan/{engine_hardening, run_pass}.py`

   * **毎回 P/I を再構成**、CO/I/P を事前クリア、休暇週ポリシーに従う
   * 親集約は replace & dedup、post-order で安定

## Orchestrator（CLI）

* 場所: `pysi/app/orchestrator.py`
* 役割: **スキーマ適用 → ETL → カレンダ同期 → 計算（leaf or tree）→ 書戻し → レポート**
* 主要オプション（代表）

  * `--db var\psi.sqlite`
  * `--schema pysi\db\schema_core_only.sql`
  * `--csv data\S_month_data.csv`
  * `--scenario Baseline`
  * `--mode leaf|tree`
  * `--network pysi.network.factory:factory`（tree モード時）
  * `--report`（可視化出力）
  * `--skip-etl / --skip-calendar`（必要に応じて）
  * `--plan-year-st / --plan-range`（明示上書き可）

## カレンダ同期（関数仕様：ユニバーサル版）

* `pysi/db/calendar_sync.py` の `sync_calendar_iso(...)` は以下どれでもOK：

  * `sync_calendar_iso(conn, scenario_id=SID)`
  * `sync_calendar_iso(conn, plan_year_st=YYYY, plan_range=N)`
  * 引数なしの場合は、DB先頭シナリオから境界を解決
* orchestrator はこの関数で `calendar_iso` を**冪等更新**。

## 実行方法（安定パターン）

* ルートで実行 & import 安定化：

  * **推奨**: `pip install -e .`（editable install）
  * もしくは一時的に `set PYTHONPATH=%cd%`（CMD） / `$env:PYTHONPATH="$pwd"`（PowerShell）
* 代表コマンド：

  ```bat
  REM 1) DDL（coreのみ）
  python -c "from pysi.db.apply_schema import apply_schema; apply_schema('var/psi.sqlite','pysi/db/schema_core_only.sql')"

  REM 2) ETL
  python -m pysi.etl.etl_monthly_to_lots --db var\psi.sqlite --csv data\S_month_data.csv --scenario Baseline --default-lot-size 50

  REM 3) カレンダ同期（シナリオ基準）
  python -m pysi.scripts.iso_calendar_sync_on_scenario --db var\psi.sqlite --scenario Baseline

  REM 4) Orchestrator（leafモード例）
  python -m pysi.app.orchestrator --db var\psi.sqlite --scenario Baseline --mode leaf --report

  REM 5) カレンダ確認
  python -m pysi.scripts.calendar_iso_check --db var\psi.sqlite
  ```

## GUI との関係

* `main.py` は **依存注入**で `SqlPlanEnv` を受け取り起動。
* GUI は pysi を**利用者**として扱い、pysi 側は GUI を知らない（循環依存なし）。
* 将来は GUI 側も **DB→PSI 注入**（`psi_io_adapters`）へ寄せて、完全一元化。

## ナラティブ → YAML → 実行 の道筋（将来拡張）

* ナラティブテキスト（口語）→ YAML（正規化）→ orchestrator / ETL / run\_pass の各ステップへ適用。
* YAML（例）:

  ```yaml
  scenario: "Baseline"
  calendar:
    plan_year_st: 2026
    plan_range: 5
  demand:
    csv: "data/S_month_data.csv"
    default_lot_size: 50
  policies:
    vacation:
      parent: "shift_to_next_open"
      leaf:   "backward_to_last_open"
  output:
    report: true
    outdir: "var/report"
  ```
* これにより「サプライチェーンの変化シナリオ」を**口語→YAML→CLI**で再現可能。

## トラブルシュート（既知事象と対処）

* `ModuleNotFoundError`（相対 import）→ **完全修飾 import**に統一（`from pysi.db...`）
* `unable to open database` → `var\` 作成 & パス確認
* `no such table:` → DDL 未適用 → `apply_schema` を先に
* レガシー列/外部キー問題 → `ensure_core_tables.py` / `repair_fk_legacy_refs_v2.py` / `cleanup_legacy_tables.py` を順に実行
* `sync_calendar_iso(...)` 引数違い → **ユニバーサル版**に差し替え（本 seed の仕様）

## 目標状態チェックリスト

* [ ] `calendar_iso`: 期待週数・先頭/末尾週がシナリオに一致
* [ ] `scenario/node/product`: ID 主体で運用
* [ ] `weekly_demand/lot`: ETL 済（冪等）
* [ ] `lot_bucket`: 計算結果が書戻される（冪等）
* [ ] レポート PNG/CSV が生成され KPI 表示が出る
* [ ] GUI 起動時も DB→PSI ルートで挙動一致

---

この seed をベースに、**CLI中心の安定稼働**と **GUI切替のしやすさ**を両立して進められます。必要になったら、この seed に差分を追記していくだけで、設計・運用の“正本”として使えます。
