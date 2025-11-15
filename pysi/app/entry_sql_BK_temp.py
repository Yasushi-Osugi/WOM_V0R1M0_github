# app/entry_sql.py
from app.config import load_config
from app.run_once import run_once
from util.db import with_connection_pool   # 任意

def main():
    cfg = load_config(source="cli+env")  # dsn/schema/scenario_id/plugins_dir等
    # ここで接続プールやトランザクションポリシを決める（必要なら）
    # with_connection_pool(cfg.input.dsn):  # 任意
    result = run_once(cfg)
    # SQL向けに、結果のアップサート・監査を追加でやりたいなら Action/Exporter ではなく「Exporter Hook」に寄せる
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
