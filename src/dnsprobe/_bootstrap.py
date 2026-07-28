"""显式注册内置 provider。

避免散落的 side-effect import：在 pipeline.run() / __main__.main() 入口显式调用
register_builtin_providers()，让内置 ip33 注册进 _REGISTRY。幂等。
"""
from __future__ import annotations


def register_builtin_providers() -> None:
    """触发内置 provider 的 @register 副作用。幂等。"""
    from dnsprobe.providers import toolhelper  # noqa: F401  # 触发 @register("toolhelper")