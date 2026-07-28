"""加载 YAML 配置 + domains，统一为 AppConfig。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ProviderConfig:
    name: str
    enabled: bool = True
    upstream_dns: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class OutputConfig:
    path: str = "hosts.txt"
    keep_old_section: bool = True


@dataclass
class ReachabilityConfig:
    method: str = "http_head"
    timeout: float = 5.0


@dataclass
class AppConfig:
    providers: list[ProviderConfig]
    output: OutputConfig
    reachability: ReachabilityConfig
    domains: list[str]
    concurrency: int = 8  # 外层：同时处理 N 个域名；provider 内仍各自并发查 DNS
    http_proxy: str = ""   # HTTP 代理 URL（形如 http://host:port）；空表示直连


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def _parse_providers(raw: list[dict[str, Any]] | None) -> list[ProviderConfig]:
    out: list[ProviderConfig] = []
    for item in raw or []:
        out.append(
            ProviderConfig(
                name=item["name"],
                enabled=item.get("enabled", True),
                upstream_dns=list(item.get("upstream_dns", []) or []),
                extra=dict(item.get("extra", {}) or {}),
            )
        )
    return out


def load_config(
    config_path: Path,
    domains_path: Path | None = None,
) -> AppConfig:
    """加载 config.yml + domains.yml，合并成 AppConfig。

    domains_path 未指定时，使用 config_path 同目录下的 domains.yml。
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"config file not found: {config_path}")

    if domains_path is None:
        domains_path = config_path.parent / "domains.yml"
    domains_path = Path(domains_path)
    if not domains_path.exists():
        raise FileNotFoundError(f"domains file not found: {domains_path}")

    cfg_raw = _load_yaml(config_path)
    dom_raw = _load_yaml(domains_path)

    return AppConfig(
        providers=_parse_providers(cfg_raw.get("providers")),
        output=OutputConfig(**(cfg_raw.get("output") or {})),
        reachability=ReachabilityConfig(**(cfg_raw.get("reachability") or {})),
        domains=list(dom_raw.get("domains", []) or []),
        concurrency=max(1, int(cfg_raw.get("concurrency", 8) or 8)),
        http_proxy=str(cfg_raw.get("http_proxy", "") or "").strip(),
    )
