# pysi/app/run_once.py

#@POINT
#1. set_global(bus) を discover_and_register() より前に呼ぶ
#2. SQLAdapter のとき db_path = cfg.input.dsn、CSV のとき db_path = cfg.input.root
#3. Pipeline(hooks=bus, ...) と bus を渡す（hooks ではなく）

from pysi.core.hooks.core import HookBus, set_global
from pysi.core.plugin_loader import discover_and_register
from pysi.core.pipeline import Pipeline
from pysi.io_adapters.sql_adapter import SQLAdapter
from pysi.io_adapters.csv_adapter import CSVAdapter
from pysi.utils.util import make_logger, make_calendar

#@ADD
import uuid


def run_once(cfg):

    #@ADD run_id
    run_id = str(uuid.uuid4())[:8]

    logger = make_logger(cfg)

    #@ADD run_id
    logger.info(f"run_id={run_id} start")
    
    
    bus = HookBus(logger=logger)

    # ★ここが重要：グローバル hooks を差し替える
    set_global(bus)

    # その後で、plugins/ ディレクトリ、entry_points、autoload の順で読み込む
    discover_and_register(bus, plugins_dir=getattr(cfg, "plugins_dir", None), api_version="1.0")

    # I/Oアダプタ選択
    #schema は getattr(cfg.input, "schema", None) にしておくと、CSV でも同じコードが動きます。
    if cfg.input.kind == "sql":
        io = SQLAdapter(dsn=cfg.input.dsn, schema=getattr(cfg.input, "schema", None), logger=logger)
        db_path = cfg.input.dsn
    else:
        io = CSVAdapter(root=cfg.input.root, logger=logger)
        db_path = cfg.input.root

    # カレンダ（ISO週→ week_idx）
    calendar = make_calendar(cfg.calendar)

    # ※ timebase フックは Pipeline 内で適用します（ここでは未適用のままでOK）

    # Pipeline に渡す共通メタ (ctx に展開されるよう pipeline 側で使う)
    calendar["run_id"] = run_id
    result = Pipeline(hooks=bus, io=io, logger=logger).run(
        db_path=db_path, scenario_id=cfg.scenario_id, calendar=calendar,
        out_dir=getattr(cfg, "output_dir", "out"),
    )
    logger.info(f"run_id={run_id} done")
    return result

    #@STOP
    #pipe = Pipeline(hooks=bus, io=io, logger=logger)
    #return pipe.run(db_path=db_path, scenario_id=cfg.scenario_id, calendar=calendar)

    #@STOP
    #pipe = Pipeline(hooks=hooks, io=io, logger=logger)
    #return pipe.run(db_path=cfg.input.db_path, scenario_id=cfg.scenario_id, calendar=calendar)
