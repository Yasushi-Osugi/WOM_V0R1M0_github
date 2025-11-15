# pysi/core/hooks/core.py

# 使い方の要点：
#run_once(cfg) の先頭で bus = HookBus(logger=logger) を作成 → set_global(bus) を呼ぶ → その後にプラグインをロード。
#これにより、デコレータ方式（@action/@filter）と register(bus)方式のプラグインが同じBusに集まります。

from __future__ import annotations
import importlib, pkgutil, traceback, sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

# ---- HookBus ---------------------------------------------------------------

Callback = Callable[..., Any]

@dataclass(order=True)
class _CB:
    priority: int
    fn: Callback = field(compare=False)
    src: str = field(compare=False)

class HookBus:
    """WordPress風の Action/Filter を極小実装。例外は握り潰してコアを止めない。"""
    def __init__(self, logger=None) -> None:
        self._actions: Dict[str, List[_CB]] = {}
        self._filters: Dict[str, List[_CB]] = {}
        self.logger = logger

    # -- register -------------------------------------------------------------
    def add_action(self, name: str, fn: Callback, priority: int = 50) -> None:
        self._actions.setdefault(name, []).append(_CB(priority, fn, _src_of(fn)))
        self._actions[name].sort()

    def add_filter(self, name: str, fn: Callback, priority: int = 50) -> None:
        self._filters.setdefault(name, []).append(_CB(priority, fn, _src_of(fn)))
        self._filters[name].sort()

    # -- run ------------------------------------------------------------------
    def do_action(self, name: str, **ctx: Any) -> None:
        for cb in self._actions.get(name, []):
            try:
                cb.fn(**ctx)
            except Exception:
                _print_exc(f"[hooks] action '{name}' failed in {cb.src}", logger=self.logger)

    def apply_filters(self, name: str, value: Any, **ctx: Any) -> Any:
        out = value
        for cb in self._filters.get(name, []):
            try:
                out = cb.fn(out, **ctx)
            except Exception:
                _print_exc(f"[hooks] filter '{name}' failed in {cb.src}", logger=self.logger)
        return out

# ---- decorators ------------------------------------------------------------

def action(name: str, priority: int = 50) -> Callable[[Callback], Callback]:
    def _wrap(fn: Callback) -> Callback:
        hooks.add_action(name, fn, priority=priority)
        return fn
    return _wrap

def filter(name: str, priority: int = 50) -> Callable[[Callback], Callback]:
    def _wrap(fn: Callback) -> Callback:
        hooks.add_filter(name, fn, priority=priority)
        return fn
    return _wrap

# ---- loader ----------------------------------------------------------------

def autoload_plugins(package: str = "pysi.plugins") -> None:
    """pysi.plugins 以下を import して register 実行。"""
    try:
        pkg = importlib.import_module(package)
    except Exception:
        _print_exc(f"[hooks] cannot import package: {package}", logger=getattr(hooks, "logger", None))
        return

    for m in pkgutil.iter_modules(pkg.__path__):  # type: ignore
        full = f"{package}.{m.name}"
        try:
            importlib.import_module(full)
            print(f"[hooks] loaded plugin: {full}")
        except Exception:
            _print_exc(f"[hooks] failed to import: {full}", logger=getattr(hooks, "logger", None))

# ---- utils -----------------------------------------------------------------

def _src_of(fn: Callback) -> str:
    mod = getattr(fn, "__module__", "?")
    name = getattr(fn, "__name__", "?")
    return f"{mod}:{name}"

def _print_exc(msg: str, logger=None) -> None:
    if logger is not None:
        logger.exception(msg)
    else:
        print(msg, file=sys.stderr)
        traceback.print_exc()

# global singleton
hooks = HookBus()

def set_global(bus: HookBus) -> None:
    """
    ランタイムでグローバル 'hooks' を差し替える。
    run_once(cfg) などで生成した HookBus をここに渡すと、
    @action/@filter デコレータも同じ Bus に登録される。
    """
    global hooks
    hooks = bus
