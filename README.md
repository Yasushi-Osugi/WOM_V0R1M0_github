# WOM V0R1M0 (Multi-Product / CSV Edition)
Weekly Operation Model – Weekly PSI Planning & Simulation (Educational OSS)

## はじめに
WOM（Weekly Operation Model）は、経営の意思決定と現場オペレーションを  
**「週次」** という共通リズムで接続するための実行モデルです。

本リポジトリ（V0R1M0）は、**複数製品（multi-product）** を対象に、  
CSVで定義された需要・供給・在庫構造を入力として、

- 需要入力  
- 制約反映（能力・LT・lot）  
- 配分・確定  
- 週次PSI（Production / Ship / Inventory）  
- 可視化・KPI出力  

という一連の流れを **最後まで通して確認できる** 最小構成の教材OSSです。

ここで重要なのは「最適解」を求めることではありません。  
**意思決定（需要・制約・配分ルール）が、週次オペレーションとしてどう現れるかを、
実行結果として最後まで確認できること**が目的です。

V0R1M0 の公開版では、  
**CSV入力のみを正式サポート**し、SQLバックエンドは扱いません。

---

## クイックスタート（CSV版・cockpit UI）

### 0) 前提
- Python 3.10+
- 本リポジトリを clone した状態

### 1) 実行コマンド（唯一の正式起動方法）
リポジトリ直下で、以下を実行してください。

```bash
python main.py --backend mvp --skip-orchestrate --csv data --scenario Baseline --ui cockpit
2) このコマンドの意味
•	--backend mvp
o	教材用の軽量実行バックエンドを使用
•	--skip-orchestrate
o	シナリオ一括実行は行わず、単一シナリオを直接実行
•	--csv data
o	入力データは data/ 配下の CSV を使用
•	--scenario Baseline
o	Baseline シナリオを実行
•	--ui cockpit
o	cockpit（GUI）を起動して結果を可視化
3) 入力データ
•	CSV入力データ：data/
o	サプライチェーン構造（inbound / outbound）
o	製品別需要・コスト・能力・関税 等
•	multi-product 前提で読み込まれます
4) 出力データ
•	実行結果（KPI・系列データ）：out/
o	kpi.csv, series.csv など
•	再現可能な状態保存：plan_data/psi_state/
o	psi_events.parquet
o	metadata.json, parameters.json 等
これらの出力により、同一条件での再実行・検証が可能です。
5) 動作確認の目安
•	cockpit UI が起動する
•	PSIグラフが表示される
•	out/ と plan_data/psi_state/ が更新される

### プラグインについて
WOM の挙動は `pysi/plugins/` 配下のプラグインで制御されます。  
需要の与え方、能力制約の反映方法、不足時の配分ルールなどは、プラグインを差し替えることで変更できます。  
最適化や独自ルールの追加は、コアを変更せずにプラグインとして実装できます。
________________________________________
（補足）
•	本公開版では SQL / DB 実行経路は対象外です。
•	実行ロジックの中核は pysi/ 配下（pipeline / plugins / gui）にあります。
