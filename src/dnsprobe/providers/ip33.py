"""调用 http://www.ip33.com/ 的接口解析域名。"""
from __future__ import annotations

import json
from typing import Any

import requests

from dnsprobe.registry import register
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError

_API = "http://api.ip33.com/dns/resolver"
_TIMEOUT = 10
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


@register("ip33")
class Ip33Resolver(BaseResolver):
    """通过 ip33.com HTTP 接口解析 A 记录。

    策略：对 cfg.upstream_dns 逐个查询并合并所有 IP 列表，
    不去重（去重由主流程统一处理）。
    """

    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        ips: list[str] = []
        errors: list[str] = []
        for dns in cfg.upstream_dns:
            try:
                resp = requests.post(
                    _API,
                    data={"domain": domain, "type": "A", "dns": dns},
                    headers=_HEADERS,
                    timeout=_TIMEOUT,
                )
                resp.raise_for_status()
                payload: dict[str, Any] = json.loads(resp.text)
                ips.extend(record["ip"] for record in payload.get("record", []))
            except Exception as e:
                errors.append(f"{dns}: {e}")
                continue

        if not ips:
            raise ResolverError(
                f"ip33 resolve failed for {domain} (all upstreams failed): {errors}"
            )
        return ips
