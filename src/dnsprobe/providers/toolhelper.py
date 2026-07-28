"""调用 https://www.toolhelper.cn/Http/DNSCheck 解析域名。"""
from __future__ import annotations

import random
import time
from typing import Any
from urllib.parse import urlencode

import requests

from dnsprobe.registry import register
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError

_API = "https://www.toolhelper.cn/Http/DNSCheck"
_TIMEOUT = 10
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Origin": "https://www.toolhelper.cn",
    "Referer": "https://www.toolhelper.cn/Http/DNSCheck",
    "X-Requested-With": "XMLHttpRequest",
}


def _build_query() -> str:
    """生成 cache-busting query string（gts=epoch_ms, gv=334, r_=random）。"""
    return urlencode(
        {
            "gts": str(int(time.time() * 1000)),
            "gv": 334,
            "r_": f"{random.random():.16f}",
        }
    )


@register("toolhelper")
class ToolhelperResolver(BaseResolver):
    """通过 toolhelper.cn DNSCheck 接口解析 A 记录。

    响应 `Data.A` 是用 `<br>` 分隔的 IP 字符串（HTML 分隔符，不是 JSON 数组）。
    """

    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        ips: list[str] = []
        errors: list[str] = []
        try:
            resp = requests.post(
                f"{_API}?{_build_query()}",
                data={"host": domain},
                headers=_HEADERS,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            payload: dict[str, Any] = resp.json()
            tag = payload.get("Tag")
            if tag == 1:
                data = payload.get("Data") or {}
                a_records = data.get("A") or ""
                ips.extend(
                    ip.strip()
                    for ip in a_records.split("<br>")
                    if ip.strip()
                )
            else:
                errors.append(
                    f"Tag={tag}, Message={payload.get('Message')!r}"
                )
        except Exception as e:
            errors.append(str(e))

        if not ips:
            raise ResolverError(
                f"toolhelper resolve failed for {domain}: {errors}"
            )
        return ips
