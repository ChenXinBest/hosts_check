"""调用 https://www.ip33.com/api/ip/search 解析域名。"""
from __future__ import annotations

from typing import Any

import requests

from dnsprobe.registry import register
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError

_API = "https://www.ip33.com/api/ip/search"
_TIMEOUT = 10
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Origin": "https://www.ip33.com",
    "Referer": "https://www.ip33.com/",
    "X-Requested-With": "XMLHttpRequest",
}


@register("ip33")
class Ip33Resolver(BaseResolver):
    """通过 ip33 新 API 解析 A 记录。

    新协议不再接 dns 参数；上游 DNS 由 ip33 内部池化。
    """

    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        ips: list[str] = []
        errors: list[str] = []
        try:
            resp = requests.post(
                _API,
                data={"s": domain},
                headers=_HEADERS,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            payload: dict[str, Any] = resp.json()
            if payload.get("type") == 3:
                ips.extend(record["ip"] for record in payload.get("ips", []))
            else:
                errors.append(f"type={payload.get('type')}")
        except Exception as e:
            errors.append(str(e))

        if errors:
            raise ResolverError(
                f"ip33 resolve failed for {domain}: {errors}"
            )
        return ips
