"""调用 https://api.dnschecked.com/query_dns 解析域名。

支持按大洲/国家批量配置上游 DNS，并行查所有 DNS 后合并 results 取并集。
DNS 列表内置，数据源：https://dnschecked.com/_next/static/chunks/913-5c5215ba2da48371.js
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests

from dnsprobe.registry import register
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError

_API = "https://api.dnschecked.com/query_dns"
_TIMEOUT = 10
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://dnschecked.com",
    "Referer": "https://dnschecked.com/",
}


# 大洲 → DNS 列表（"global" 不是真大洲，是前端"全部"页的聚合）
CONTINENT_DNS: dict[str, list[str]] = {
    "global": [
        "8.8.8.8", "208.67.222.220", "9.9.9.9", "204.117.214.10",
        "64.6.64.6", "185.228.169.9", "156.154.70.64",
        "208.91.112.53", "65.39.166.132",
        "223.5.5.5", "202.46.34.75",
        "1.1.1.1", "61.8.0.113",
        "195.46.39.39", "77.88.8.8",
        "212.98.231.69",
        "115.178.96.2",
        "148.235.82.66",
        "5.11.11.5",
        "38.54.96.87",
        "38.54.57.69",
        "38.54.8.230", "38.54.13.84",
        "80.196.100.209",
        "194.145.241.6",
        "80.80.81.81", "80.80.80.80",
        "212.230.255.1",
        "80.67.169.40",
        "38.54.23.99",
        "38.54.88.61",
        "38.54.119.67",
        "209.150.154.1",
        "83.137.41.9",
        "185.228.168.9",
        "122.56.107.86",
        "185.83.212.30",
    ],
    "asia": [
        "223.5.5.5", "202.46.34.75",
        "115.178.96.2", "103.194.240.35", "103.99.150.10",
        "112.133.219.34", "164.100.138.248", "112.133.192.89",
        "38.54.96.87", "211.25.206.147",
        "38.54.8.230",
        "38.54.23.99",
        "38.54.88.61", "202.248.37.74", "202.248.20.133", "210.227.116.101",
        "38.54.119.67", "139.59.219.245", "103.86.99.100",
        "209.150.154.1", "125.209.116.22",
        "202.46.34.75", "168.126.63.1",
        "114.130.5.6", "103.157.237.34",
        "212.98.231.69",
    ],
    "africa": ["5.11.11.5", "196.15.170.131"],
    "antarctica": [],
    "europe": [
        "80.67.169.40", "83.145.86.7", "46.105.55.84", "80.67.169.12",
        "82.96.64.2", "81.27.162.100", "195.243.214.4", "194.172.160.4",
        "139.18.25.33", "82.193.241.125",
        "194.145.241.6", "194.145.240.6",
        "80.80.81.81", "193.58.204.59", "185.107.80.84", "80.80.80.80",
        "87.213.100.113", "213.125.105.234",
        "194.209.157.109",
        "212.230.255.1", "89.29.128.250", "62.81.238.230", "195.235.225.10",
        "84.236.142.130",
        "83.137.41.9",
        "185.228.168.9",
        "185.83.212.30",
        "195.46.39.39", "176.103.130.130", "213.135.113.250", "212.122.4.2",
        "77.88.8.8", "212.96.218.97", "213.248.45.60", "83.149.17.52", "176.114.200.193",
        "80.196.100.209",
    ],
    "north-america": [
        "8.8.8.8", "38.60.205.207", "38.54.6.178",
        "208.67.222.220", "9.9.9.9", "204.117.214.10",
        "64.6.64.6", "185.228.169.9", "205.171.202.66", "156.154.70.64",
        "208.91.112.53", "65.39.166.132",
        "148.235.82.66", "200.56.224.11",
    ],
    "oceania": [
        "1.1.1.1", "61.8.0.113", "139.130.4.4",
        "223.165.64.97", "122.56.107.86",
    ],
    "south-america": [
        "38.54.57.69", "187.6.84.178", "200.221.11.101", "189.125.18.5",
        "189.126.192.4",
    ],
}


# 国家代码 → DNS 列表
COUNTRY_DNS: dict[str, list[str]] = {
    "us": ["8.8.8.8", "38.60.205.207", "38.54.6.178", "208.67.222.220", "9.9.9.9",
           "204.117.214.10", "64.6.64.6", "185.228.169.9", "205.171.202.66", "156.154.70.64"],
    "cn": ["223.5.5.5", "202.46.34.75"],
    "ru": ["195.46.39.39", "176.103.130.130", "213.135.113.250", "212.122.4.2",
           "77.88.8.8", "212.96.218.97", "213.248.45.60", "83.149.17.52", "176.114.200.193"],
    "tr": ["212.98.231.69"],
    "in": ["115.178.96.2", "103.194.240.35", "103.99.150.10", "112.133.219.34",
           "164.100.138.248", "112.133.192.89"],
    "mx": ["148.235.82.66", "200.56.224.11"],
    "za": ["5.11.11.5", "196.15.170.131"],
    "my": ["38.54.96.87", "211.25.206.147"],
    "br": ["38.54.57.69", "187.6.84.178", "200.221.11.101", "189.125.18.5", "189.126.192.4"],
    "ae": ["38.54.8.230"],
    "de": ["38.54.13.84", "82.96.64.2", "81.27.162.100", "195.243.214.4",
           "194.172.160.4", "139.18.25.33", "82.193.241.125"],
    "hk": ["38.54.23.99"],
    "jp": ["38.54.88.61", "202.248.37.74", "202.248.20.133", "210.227.116.101"],
    "sg": ["38.54.119.67", "139.59.219.245", "103.86.99.100"],
    "ca": ["208.91.112.53", "65.39.166.132"],
    "pk": ["209.150.154.1", "125.209.116.22"],
    "kr": ["202.46.34.75", "168.126.63.1"],
    "bd": ["114.130.5.6", "103.157.237.34"],
    "dk": ["80.196.100.209"],
    "gb": ["194.145.241.6", "194.145.240.6"],
    "nl": ["80.80.81.81", "193.58.204.59", "185.107.80.84", "80.80.80.80",
           "87.213.100.113", "213.125.105.234"],
    "fr": ["80.67.169.40", "83.145.86.7", "46.105.55.84", "80.67.169.12"],
    "at": ["83.137.41.9"],
    "ie": ["185.228.168.9"],
    "nz": ["223.165.64.97", "122.56.107.86"],
    "pt": ["185.83.212.30"],
    "es": ["212.230.255.1", "89.29.128.250", "62.81.238.230", "195.235.225.10", "84.236.142.130"],
    "ch": ["194.209.157.109"],
}


def _collect_dns(cfg: ResolverConfig) -> list[str]:
    """从 cfg.extra.continents + cfg.extra.countries 收集 DNS 列表（去重保序）。"""
    continents = cfg.extra.get("continents") or ["north-america"]
    countries = cfg.extra.get("countries") or []
    if not isinstance(continents, list) or not isinstance(countries, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for ip in (CONTINENT_DNS.get(c, []) for c in continents):
        for x in ip:
            if x not in seen:
                seen.add(x)
                out.append(x)
    for ip in (COUNTRY_DNS.get(c, []) for c in countries):
        for x in ip:
            if x not in seen:
                seen.add(x)
                out.append(x)
    return out


def _query_one(dns_server: str, domain: str) -> list[str]:
    """调用 API 查询一个 DNS，返回 results IP 列表（失败返回空）。"""
    try:
        resp = requests.post(
            _API,
            json={"domain": domain, "record_type": "A", "dns_server": dns_server},
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        payload: dict[str, Any] = resp.json()
        return list(payload.get("results") or [])
    except Exception:
        return []


@register("dnschecked")
class DnscheckedResolver(BaseResolver):
    """通过 dnschecked.com query_dns API 解析 A 记录。

    配置 `extra.continents` 和 `extra.countries` 选择要并行查询的 DNS。
    默认 `continents=["north-america"]`（8.8.8.8 / Cloudflare / OpenDNS / Quad9 / VeriSign 等美区权威 DNS）。
    所有 DNS 并行查，结果取并集 + 去重。
    """

    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        dns_list = _collect_dns(cfg)
        if not dns_list:
            raise ResolverError(
                f"dnschecked: no DNS configured (continents={cfg.extra.get('continents')!r}, "
                f"countries={cfg.extra.get('countries')!r})"
            )

        with ThreadPoolExecutor(max_workers=len(dns_list)) as pool:
            futures = [pool.submit(_query_one, dns, domain) for dns in dns_list]
            per_dns_ips = [f.result() for f in futures]

        seen: set[str] = set()
        out: list[str] = []
        for ips in per_dns_ips:
            for ip in ips:
                if ip not in seen:
                    seen.add(ip)
                    out.append(ip)

        if not out:
            raise ResolverError(
                f"dnschecked resolve failed for {domain}: all {len(dns_list)} DNS returned no results"
            )
        return out
