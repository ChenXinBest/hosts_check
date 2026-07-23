"""HTTP HEAD 测连通（迁移自 DailyJob.py:43-67）。"""
from __future__ import annotations

import requests

from hosts_check.config import ReachabilityConfig


def check_ip_reachable(ip: str, domain: str, timeout: float = 5.0) -> bool:
    """通过 HTTP HEAD 检查 IP 是否可达。

    使用 IP 直连，Host header 指明域名（用于虚拟主机场景）。
    2xx/3xx 视为可达。
    """
    try:
        response = requests.head(
            f"http://{ip}",
            headers={"Host": domain},
            timeout=timeout,
            allow_redirects=True,
        )
        return 200 <= response.status_code < 400
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        return False
    except Exception:
        return False


def filter_reachable(
    ips: list[str], domain: str, cfg: ReachabilityConfig
) -> list[str]:
    """过滤出可达的 IP，按原顺序保留。"""
    return [ip for ip in ips if check_ip_reachable(ip, domain, cfg.timeout)]