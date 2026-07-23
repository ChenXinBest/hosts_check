"""Resolver 注册表：装饰器 + 插件目录扫描。"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Callable

from hosts_check.resolver import BaseResolver

_REGISTRY: dict[str, type[BaseResolver]] = {}


def register(name: str) -> Callable[[type[BaseResolver]], type[BaseResolver]]:
    """把 Resolver 子类挂到全局注册表。"""

    def deco(cls: type[BaseResolver]) -> type[BaseResolver]:
        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return deco


def discover_plugins(plugins_dir: Path) -> None:
    """扫描 plugins_dir 下所有 .py，import 触发 @register 副作用。

    调用者需确保 `plugins_dir` 的父目录在 sys.path 上（通常通过 __main__.py
    在启动时 sys.path.insert(0, "."))。
    """
    for py in plugins_dir.glob("*.py"):
        if py.name.startswith("_"):
            continue
        importlib.import_module(f"plugins.{py.stem}")


def get(name: str) -> type[BaseResolver]:
    """按 name 查 Provider 类。未注册抛 KeyError。"""
    if name not in _REGISTRY:
        raise KeyError(f"resolver '{name}' not registered")
    return _REGISTRY[name]