"""HTTP HEAD 测连通（迁移自 DailyJob.py:43-67）。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import requests

from dnsprobe.config import ReachabilityConfig


def _proxies(http_proxy: Optional[str]) -> Optional[dict[str, str]]:
    return {"http": http_proxy, "https": http_proxy} if http_proxy else None


def _format_host_for_url(ip: str) -> str:
    """IPv6 地址加方括号（URL 格式要求），IPv4 原样返回。"""
    if ":" in ip:
        return f"[{ip}]"
    return ip


def check_ip_reachable(
    ip: str,
    domain: str,
    timeout: float = 5.0,
    method: str = "http_head",
    http_proxy: str = "",
) -> bool:
    """通过 HTTP HEAD 检查 IP 是否可达。`method: "none"` 直接返回 True（跳过验证）。"""
    if method == "none":
        return True
    if method != "http_head":
        raise ValueError(f"unsupported reachability method: {method!r}")

    try:
        response = requests.head(
            f"http://{_format_host_for_url(ip)}",
            headers={"Host": domain},
            timeout=timeout,
            allow_redirects=True,
            proxies=_proxies(http_proxy),
        )
        reachable = 200 <= response.status_code < 400
        print(
            f"[{'OK' if reachable else '×'}] IP:{ip} ({domain}) "
            f"{'可达' if reachable else '不可达'} [HTTP {response.status_code}]"
        )
        return reachable
    except requests.exceptions.Timeout:
        print(f"[×] IP:{ip} ({domain}) 连接超时")
        return False
    except requests.exceptions.ConnectionError:
        print(f"[×] IP:{ip} ({domain}) 连接被拒绝")
        return False
    except Exception as e:
        print(f"[×] IP:{ip} ({domain}) 检查异常: {e}")
        return False


def filter_reachable(
    ips: list[str], domain: str, cfg: ReachabilityConfig, http_proxy: str = ""
) -> list[str]:
    """过滤出可达的 IP，按原顺序保留。并发检查以加速。"""
    if not ips:
        return []

    # 并发检查所有 IP，保持原顺序
    with ThreadPoolExecutor(max_workers=min(len(ips), 8)) as pool:
        futures = [
            pool.submit(check_ip_reachable, ip, domain, cfg.timeout, cfg.method, http_proxy)
            for ip in ips
        ]
        results = [fut.result() for fut in futures]

    return [ip for ip, reachable in zip(ips, results) if reachable]
