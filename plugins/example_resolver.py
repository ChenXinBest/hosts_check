"""Example resolver plugin.

演示如何写一个 DNS resolver plugin。要切换到真实协议，把
``resolve()` 里的循环换成 HTTP/DoH/socket/dig 子进程调用即可。

启用方式：在 config.yml 的 providers 列表中添加：

    - name: example
      enabled: true
      upstream_dns:
        - 8.8.8.8
      extra: {}
"""
from __future__ import annotations

from hosts_check.registry import register
from hosts_check.resolver import BaseResolver, ResolverConfig, ResolverError


@register("example")
class ExampleResolver(BaseResolver):
    """示例 resolver：直接返回 cfg.extra 里的固定 IP 列表（仅用于演示）。"""

    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        ips = cfg.extra.get("fake_ips")
        if not ips:
            raise ResolverError(
                "example resolver requires cfg.extra['fake_ips'] to be set"
            )
        return list(ips)