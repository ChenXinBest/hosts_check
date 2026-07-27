"""Example resolver plugin.

演示如何写一个 DNS resolver plugin。要切换到真实协议，把
``resolve()` 里的循环换成 HTTP/DoH/socket/dig 子进程调用即可。

启用方式（零配置即可工作）：

    providers:
      - name: example
        enabled: true
        upstream_dns:
          - 8.8.8.8
        extra: {}              # 不配置 fake_ips 时使用默认演示 IP

如果想让示例返回自定义 IP，在 ``extra`` 里写入 ``fake_ips``：

    extra:
      fake_ips:
        - 1.2.3.4
        - 5.6.7.8
"""
from __future__ import annotations

from dnsprobe.registry import register
from dnsprobe.resolver import BaseResolver, ResolverConfig


@register("example")
class ExampleResolver(BaseResolver):
    """示例 resolver：返回 ``cfg.extra['fake_ips']``，缺省回落到固定演示 IP。

    仅作模板/调试用，**不可用于生产**。
    """

    _DEFAULT_IPS: list[str] = ["93.184.216.34"]

    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        return list(cfg.extra.get("fake_ips", self._DEFAULT_IPS))