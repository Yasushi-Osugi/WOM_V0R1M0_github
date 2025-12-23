# WOM V0R1M0 (Multi-Product / CSV Edition)
Weekly Operation Model – Weekly PSI Planning & Simulation (Educational OSS)

> **English (Summary)**
>
> WOM (Weekly Operation Model) is an executable model designed to connect management decisions and supply chain operations on a weekly basis.
> This repository provides a minimal, CSV-based, multi-product PSI (Production / Ship / Inventory) planning and simulation environment.
> 
> The focus of WOM is not on finding an optimal solution, but on making decision impacts visible by running demand, constraints, and allocation rules through a complete weekly operation loop.


WOMの設計思想と背景は note 記事の下記URLを参照してください。
https://note.com/osuosu1123/n/n37e8b53c5b07

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


## node_name の予約語ルールについて

WOM では、サプライチェーン構造を CSV で定義する際、`node_name` にいくつかの予約語（接頭語）を使用します。
これは命名規則ではなく、PSI 計画ロジックにおける **ノードの役割（視点）** を明示するための仕様です。

### 共通ルール
- `supply_point` は inbound / outbound の両 supply chain に共通する論理ルートです。
- `node_name` の接頭語により、ノードの役割が判別されます。

### inbound supply chain（供給側）
root → `supply_point` → `MOM`xxxx → child nodes
- `MOM`xxxx: `MOM`は接頭語。xxxxは任意。  
  生産・供給の起点となるノード（Mother Of Manufacturing）  
  PSI 計画では供給（PUSH）側の起点として扱われます。

### outbound supply chain（需要側）

- `DAD`yyyy: `DAD`は接頭語。yyyyは任意。  
  需要・販売チャネルの集約ノード（Demand Aggregation on Distribution）  
  PSI 計画では需要（PULL）側の起点として扱われます。
root → `supply_point` → `DAD`yyyy → child nodes
これらの予約語により、WOM は inbound / outbound を同一の計画ロジックで扱いながら、
供給と需要の視点を明確に切り替えています。


### プラグインについて
WOM の挙動は `pysi/plugins/` 配下のプラグインで制御されます。  
需要の与え方、能力制約の反映方法、不足時の配分ルールなどは、プラグインを差し替えることで変更できます。  
最適化や独自ルールの追加は、コアを変更せずにプラグインとして実装できます。
________________________________________
（補足）
•	本公開版では SQL / DB 実行経路は対象外です。
•	実行ロジックの中核は pysi/ 配下（pipeline / plugins / gui）にあります。
