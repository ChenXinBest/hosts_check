"""DNS-over-HTTPS resolver：用 dnspython 构造/解析 DNS 报文，requests 走 HTTPS 传输。

支持 A（IPv4）和 AAAA（IPv6）记录查询，可按大洲/国家配置上游 DoH 端点，
可设权重，所有 DNS 并行查询取结果并集。美国权威 DNS 默认走 HTTP 代理（绕过 GFW）。
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlencode

import dns.message
import dns.rdatatype
import requests

from dnsprobe.registry import register
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError

_TIMEOUT = 10

# 支持的记录类型：A = IPv4, AAAA = IPv6
_SUPPORTED_RDTYPES = {"A", "AAAA"}


def _rdtype_from_str(s: str) -> int:
    """字符串 → dnspython rdtype 常量。"""
    return dns.rdatatype.from_text(s.upper())


def _build_query(domain: str, rdtype: int) -> bytes:
    """构造指定记录类型查询的 DNS 报文（wire format）。"""
    return dns.message.make_query(domain, rdtype).to_wire()


def _parse_response(wire: bytes, rdtype: int) -> list[str]:
    """从 DoH 响应报文提取指定记录类型的地址列表。"""
    try:
        msg = dns.message.from_wire(wire)
    except Exception:
        return []
    addresses: list[str] = []
    for rrset in msg.answer:
        if rrset.rdtype == rdtype:
            for rdata in rrset:
                addresses.append(rdata.address)
    return addresses


def _doh_get(
    name: str, url: str, domain: str, rdtype: int, http_proxy: str = ""
) -> list[str]:
    """通过 DoH GET 方式查询一个端点。失败时打印调试信息。"""
    proxies = {"http": http_proxy, "https": http_proxy} if http_proxy else None
    qdata = base64.urlsafe_b64encode(_build_query(domain, rdtype)).rstrip(b"=").decode()
    full_url = f"{url.rstrip('/')}?{urlencode({'dns': qdata})}"
    try:
        resp = requests.get(
            full_url,
            headers={"Accept": "application/dns-message"},
            timeout=_TIMEOUT,
            proxies=proxies,
        )
        if resp.status_code != 200:
            print(f"[!] {name}: HTTP {resp.status_code}")
            return []
        return _parse_response(resp.content, rdtype)
    except Exception as e:
        print(f"[!] {name}: {e}")
        return []


def _default_servers() -> list[dict[str, Any]]:
    """默认 DNS 列表：国内主流（直连）+ 美国权威（走代理，权重更高）。"""
    return [
        # ─── 国内主流（直连）────────────────────────────────
        {"name": "阿里云 DoH",   "url": "https://dns.alidns.com/dns-query",         "country": "cn", "weight": 1.0, "proxy": False},
        {"name": "DNSPod DoH",   "url": "https://doh.pub/dns-query",               "country": "cn", "weight": 1.0, "proxy": False},
        # ─── 美国权威（走代理，权重更高）────────────────────
        {"name": "Google DoH",         "url": "https://dns.google/dns-query",          "country": "us", "weight": 2.0, "proxy": True},
        {"name": "Cloudflare DoH",     "url": "https://cloudflare-dns.com/dns-query",  "country": "us", "weight": 2.0, "proxy": True},
        {"name": "Quad9 DoH",          "url": "https://dns.quad9.net/dns-query",       "country": "us", "weight": 2.0, "proxy": True},
        {"name": "OpenDNS DoH",        "url": "https://doh.opendns.com/dns-query",     "country": "us", "weight": 1.5, "proxy": True},
    ]


def _collect_servers(cfg: ResolverConfig) -> list[dict[str, Any]]:
    """从 cfg.extra.dns_servers 收集 DNS 列表（缺省用 _default_servers()）。"""
    servers = cfg.extra.get("dns_servers")
    if not servers or not isinstance(servers, list):
        return _default_servers()
    out: list[dict[str, Any]] = []
    for s in servers:
        if isinstance(s, dict) and s.get("url"):
            out.append({
                "name": s.get("name", s["url"]),
                "url": s["url"],
                "country": s.get("country", ""),
                "weight": float(s.get("weight", 1.0) or 1.0),
                "proxy": bool(s.get("proxy", False)),
            })
    return out


def _collect_record_types(cfg: ResolverConfig) -> list[int]:
    """从 cfg.extra.record_types 收集要查询的记录类型（缺省 [A]）。"""
    raw = cfg.extra.get("record_types", ["A"])
    if not isinstance(raw, list):
        raw = ["A"]
    out: list[int] = []
    for r in raw:
        s = str(r).upper()
        if s in _SUPPORTED_RDTYPES:
            out.append(_rdtype_from_str(s))
    return out or [dns.rdatatype.A]


@register("doh")
class DoHResolver(BaseResolver):
    """DNS-over-HTTPS resolver，并行查所有 DoH 端点，按 weight 排序合并结果。

    支持 A（IPv4）和 AAAA（IPv6）记录查询。

    配置 `extra.dns_servers`（list[dict]），每项字段：
      - name: str        显示名
      - url: str         DoH endpoint（如 https://dns.google/dns-query）
      - country: str     国家代码（cn/us/...）
      - weight: float    权重（默认 1.0；高权重排前面）
      - proxy: bool      是否走 HTTP 代理（境外权威 DNS 通常 True）

    配置 `extra.record_types`（list[str]）选择查询的记录类型：
      - ["A"]            仅 IPv4（默认）
      - ["AAAA"]         仅 IPv6
      - ["A", "AAAA"]    双栈

    配置 `extra.http_proxy` 走 HTTP 代理 URL。
    """

    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        servers = _collect_servers(cfg)
        if not servers:
            raise ResolverError("doh: no DNS servers configured")

        record_types = _collect_record_types(cfg)
        http_proxy = cfg.extra.get("http_proxy", "") or ""
        # 按 weight 降序排（高权重先看）
        servers_sorted = sorted(servers, key=lambda s: s["weight"], reverse=True)

        # 构建 (server, rdtype) 任务列表：每个 server × 每个 record_type
        tasks: list[tuple[dict, int]] = []
        for s in servers_sorted:
            for rdtype in record_types:
                tasks.append((s, rdtype))

        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            futures = []
            for s, rdtype in tasks:
                proxy = http_proxy if s["proxy"] else ""
                futures.append(
                    (s, rdtype, pool.submit(_doh_get, s["name"], s["url"], domain, rdtype, proxy))
                )

            # 按 weight 顺序收集结果（高权重在前，A 在 AAAA 前）
            per_task_ips: list[tuple[dict, int, list[str]]] = []
            for s, rdtype, fut in futures:
                per_task_ips.append((s, rdtype, fut.result()))

        seen: set[str] = set()
        out: list[str] = []
        for _s, _rdtype, ips in per_task_ips:
            for ip in ips:
                if ip not in seen:
                    seen.add(ip)
                    out.append(ip)

        if not out:
            servers_summary = ", ".join(s["name"] for s in servers_sorted)
            rt_summary = ", ".join(dns.rdatatype.to_text(rt) for rt in record_types)
            raise ResolverError(
                f"doh resolve failed for {domain}: all {len(servers_sorted)} servers "
                f"returned no results for [{rt_summary}] ({servers_summary})"
            )
        return out
