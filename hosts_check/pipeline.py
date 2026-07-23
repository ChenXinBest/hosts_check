"""主流程：解析 → 去重 → 可达性检测 → 写 hosts.txt。"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from hosts_check.config import AppConfig
from hosts_check.reachability import filter_reachable
from hosts_check.registry import discover_plugins, get
from hosts_check.resolver import BaseResolver, ResolverConfig, ResolverError
from hosts_check.writer import write_hosts_file

import hosts_check.providers  # noqa: F401  # 触发 @register("ip33") 副作用


def _log(msg: str) -> None:
    print(msg)


def _build_resolver_instances(
    providers, plugins_dir: Path | None
) -> list[tuple[BaseResolver, ResolverConfig]]:
    if plugins_dir is not None:
        discover_plugins(plugins_dir)

    out: list[tuple[BaseResolver, ResolverConfig]] = []
    for p in providers:
        if not p.enabled:
            continue
        cls = get(p.name)
        cfg = ResolverConfig(
            name=p.name,
            upstream_dns=list(p.upstream_dns),
            extra=dict(p.extra),
        )
        out.append((cls(cfg), cfg))
    return out


def run(config: AppConfig, plugins_dir: Path | None = None) -> int:
    """执行完整流程，返回退出码（0=至少一有结果，1=全部失败）。"""
    resolvers = _build_resolver_instances(config.providers, plugins_dir)

    raw: dict[str, list[str]] = defaultdict(list)
    for domain in config.domains:
        for resolver, rcfg in resolvers:
            try:
                ips = resolver.resolve(domain, rcfg)
            except ResolverError as e:
                _log(f"[!] {resolver.name} on {domain}: {e}")
                continue
            raw[domain].extend(ips)

    filtered: dict[str, list[str]] = {}
    for domain, ips in raw.items():
        unique = list(dict.fromkeys(ips))
        reachable = filter_reachable(unique, domain, config.reachability)
        if reachable:
            filtered[domain] = reachable

    write_hosts_file(filtered, config.output)

    if not filtered:
        _log("[×] 所有域名解析失败")
        return 1
    _log(f"[OK] 完成: {len(filtered)}/{len(config.domains)} 个域名有可用 IP")
    return 0