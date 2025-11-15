# headless_run.py
''' GUIなしで回す最小コード（例：ジョブやCIで）
将来のGUI差し替えイメージ
Tkinter → Web(React/Next.js) or Qt：GUIは orchestrator（CLI/関数） を叩くだけ。
ローカル → サーバー：orchestrator を FastAPI でラップすればREST化も容易。
ネットワークの組み方が変わる：--network の factory を差し替えるだけでOK（コアには無影響）。
結論：PySI coreが“中立の背骨”、GUIは着せ替え。
今の分離で、コアは単体実行・CLI化・サーバー化のどれにも即応できます。👍
 '''
from pysi.db.apply_schema import apply_schema
from pysi.db.calendar_sync import sync_calendar_iso
from pysi.io.psi_io_adapters import _open, get_scenario_id, load_leaf_S_and_compute, write_both_layers
from pysi.etl.etl_monthly_to_lots import run_etl
from pysi.network.factory import factory  # あなたのネットワークビルダ
from pysi.plan.run_pass import run_idempotent_demand_pass
DB = "var/psi.sqlite"
SCENARIO = "Baseline"
CSV = "data/S_month_data.csv"
# 1) スキーマ＆ETL＆calendar同期
apply_schema(DB, "pysi/db/schema.sql")
run_etl(DB, CSV, SCENARIO, default_lot_size=50)
conn = _open(DB)
weeks = sync_calendar_iso(conn, scenario_name=SCENARIO, csv_path=CSV)
sid = get_scenario_id(conn, SCENARIO)
# 2) ツリー生成（製品指定はfactory側で）
root = factory(data_dir="data", product_name=None, direction="outbound")
# 3) 葉へS注入→冪等パス→書戻し
for leaf in [n for n in getattr(root, "children", []) or [] if not n.children]:
    load_leaf_S_and_compute(conn, scenario_id=sid, node_obj=leaf, product_name=leaf.sku.product_name if hasattr(leaf, "sku") else "RICE")
run_idempotent_demand_pass(root)
write_both_layers(conn, scenario_id=sid, node_obj=root, product_name="RICE", replace_slice=True)
print("DONE")
