# pysi/utils/util.py
from __future__ import annotations
import logging
from typing import Dict, Any, Optional

#def make_logger(cfg: Optional[object] = None):
#    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
#    return logging.getLogger("pysi")

# 使い方：LOGLEVEL=DEBUG python -m pysi.app.entry_csv ... で週次ログが出ます。
def make_logger(cfg: Optional[object] = None):
    import os, logging
    level_name = os.getenv("LOGLEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")
    return logging.getLogger("pysi")




def make_calendar(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """ISO週を律速軸としたシンプルなカレンダ辞書を返す。"""
    iso_year_start = int(cfg.get("iso_year_start", 2025))
    iso_week_start = int(cfg.get("iso_week_start", 1))
    weeks = int(cfg.get("weeks", 5))
    return {"iso_year_start": iso_year_start, "iso_week_start": iso_week_start, "weeks": weeks}

# 互換のための“委譲”版 discover_and_register
# app/run_once.py が `from pysi.util import discover_and_register` と書いても動くように、
# 実体は core.plugin_loader に委譲します。

#@STOP
#def discover_and_register(bus, plugins_dir: Optional[str] = None, api_version: str = "1.0") -> None:
#    from pysi.core.plugin_loader import discover_and_register as _impl
#    return _impl(bus, plugins_dir=plugins_dir, api_version=api_version)
