# pysi/core/plugin_loader.py
from __future__ import annotations
import importlib
import importlib.metadata as md
import os
from typing import Optional
from pysi.core.hooks.core import autoload_plugins

def discover_and_register(bus, plugins_dir: Optional[str] = None, api_version: str = "1.0") -> None:
    """
    プラグインを発見し、register(bus) を呼ぶ。
    1) ローカル plugins/ ディレクトリ
    2) entry_points group="psi_plugins"
    3) pysi.plugins.* の自動 import（decorator登録系）
    """
    log = getattr(bus, "logger", None)

    # 1) ローカル plugins/ ディレクトリを走査
    if plugins_dir and os.path.isdir(plugins_dir):
        for root, _, files in os.walk(plugins_dir):
            if "plugin.py" in files:
                # 例: plugins/rice_pack/plugin.py -> plugins.rice_pack.plugin
                mod_path = root.replace(os.sep, ".").strip(".")
                try:
                    mod = importlib.import_module(mod_path + ".plugin")
                    if hasattr(mod, "register"):
                        mod.register(bus)
                        log and log.info(f"[plugins] registered: {mod_path}")
                except Exception as e:
                    log and log.exception(f"[plugins] load failed: {mod_path}: {e}")

    # 2) Python entry_points（外部配布プラグイン）
    try:
        for ep in md.entry_points(group="psi_plugins"):
            try:
                ep.load()(bus)  # register(bus)
                log and log.info(f"[plugins] entry_point registered: {ep.name}")
            except Exception as e:
                log and log.exception(f"[plugins] EP load failed: {ep.name}: {e}")
    except Exception:
        # entry_points が無い環境でも問題なくスキップ
        pass

    # 3) pysi.plugins.* を自動 import（@action/@filter デコレータ登録系）
    try:
        autoload_plugins("pysi.plugins")
    except Exception as e:
        log and log.info(f"[plugins] autoload skipped: {e}")
