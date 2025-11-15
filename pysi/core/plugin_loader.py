# pysi/core/plugin_loader.py
from __future__ import annotations
import importlib
import importlib.util
import importlib.machinery
import importlib.metadata as md
import os
import pkgutil
from types import ModuleType
from typing import Optional

def _call_register(mod: ModuleType, bus) -> bool:
    """module内に register(bus) があれば呼ぶ。成功→True"""
    reg = getattr(mod, "register", None)
    if callable(reg):
        reg(bus)
        return True
    return False

def _import_module_from_path(module_name: str, file_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module from {file_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod

def discover_and_register(bus, plugins_dir: Optional[str] = None, api_version: str = "1.0") -> None:
    seen = set()

    # 1) ローカル ./plugins/**/plugin.py
    if plugins_dir and os.path.isdir(plugins_dir):
        for root, _, files in os.walk(plugins_dir):
            if "plugin.py" in files:
                # 例: plugins/educ_pack/plugin.py -> module名は "plugins.educ_pack.plugin"
                pkg_root = os.path.basename(plugins_dir.rstrip(os.sep))
                rel = os.path.relpath(os.path.join(root, "plugin.py"), start=os.path.dirname(plugins_dir))
                mod_name = rel.replace(os.sep, ".").rsplit(".py", 1)[0]
                if mod_name.startswith("."):
                    mod_name = mod_name[1:]
                try:
                    # パッケージ化済みなら importlib.import_module が楽だが、
                    # 未パッケージでも読みたいので path import も許容
                    try:
                        mod = importlib.import_module(mod_name)
                    except Exception:
                        mod = _import_module_from_path(mod_name, os.path.join(root, "plugin.py"))
                    _call_register(mod, bus)
                    seen.add(mod_name)
                    bus.logger and bus.logger.info(f"[hooks] loaded plugin: {mod_name}")
                except Exception as e:
                    bus.logger and bus.logger.exception(f"[hooks] load failed: {mod_name}: {e}")

    # 2) パッケージ配下 pysi.plugins.*
    try:
        pkg = importlib.import_module("pysi.plugins")
        for m in pkgutil.iter_modules(pkg.__path__):  # type: ignore
            mod_name = f"pysi.plugins.{m.name}"
            if mod_name in seen:
                continue
            try:
                mod = importlib.import_module(mod_name)
                # サブモジュールの中に plugin.py がある場合にも対応
                called = _call_register(mod, bus)
                if not called:
                    # よくある構成: pysi.plugins.educ_pack.plugin.register
                    sub_name = f"{mod_name}.plugin"
                    try:
                        sub = importlib.import_module(sub_name)
                        _call_register(sub, bus)
                        mod_name = sub_name
                    except Exception:
                        pass
                bus.logger and bus.logger.info(f"[hooks] loaded plugin: {mod_name}")
            except Exception as e:
                bus.logger and bus.logger.exception(f"[hooks] import failed: {mod_name}: {e}")
    except Exception:
        # pysi.plugins が無い環境も許容
        pass

    # 3) entry_points (任意)
    try:
        for ep in md.entry_points(group="psi_plugins"):
            try:
                reg = ep.load()
                if callable(reg):
                    reg(bus)  # register(bus) 形式を想定
                bus.logger and bus.logger.info(f"[hooks] loaded entry_point: {ep.name}")
            except Exception as e:
                bus.logger and bus.logger.exception(f"[hooks] EP failed: {ep.name}: {e}")
    except Exception:
        pass
