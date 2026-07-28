"""主流程：解析 → 去重 → 可达性检测 → 写 hosts.txt。"""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dnsprobe._bootstrap import register_builtin_providers
from dnsprobe.config import AppConfig
from dnsprobe.reachability import filter_reachable
from dnsprobe.registry import discover_plugins, get
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError
from dnsprobe.writer import write_hosts_file


def _log(msg: str) -> None:
    print(msg)


def _build_resolver_instances(
    providers, plugins_dir: Path | None
) -> list[tuple[BaseResolver, ResolverConfig]]:
    register_builtin_providers()
    if plugins_dir is not None:
        discover_plugins(plugins_dir)

    out: list[tuple[BaseResolver, ResolverConfig]] = []
    for p in providers:
        if not p.enabled:
            continue
        try:
            cls = get(p.name)
            cfg = ResolverConfig(
                name=p.name,
                upstream_dns=list(p.upstream_dns),
                extra=dict(p.extra),
            )
            out.append((cls(cfg), cfg))
        except Exception as e:
            _log(f"[!] provider {p.name} unavailable: {e}")
            continue
    return out


def _resolve_domain(
    domain: str,
    resolvers: list[tuple[BaseResolver, ResolverConfig]],
) -> list[str]:
    """解析单个域名（多 resolver 串行），返回所有 IP。异常吞掉。"""
    out: list[str] = []
    for resolver, rcfg in resolvers:
        try:
            ips = resolver.resolve(domain, rcfg)
        except ResolverError as e:
            _log(f"[!] {resolver.name} on {domain}: {e}")
            continue
        except Exception as e:
            _log(f"[!] {resolver.name} on {domain}: unexpected error: {e}")
            continue
        out.extend(ips)
    return out


def run(config: AppConfig, plugins_dir: Path | None = None) -> int:
    """执行完整流程，返回退出码（0=至少一有结果，1=全部失败）。

    外层用 ThreadPoolExecutor 并发处理 N 个域名（`config.concurrency`）。
    provider 内部仍各自并发查 DNS（两层并发，总并发数 ≈ N × 各 provider 的 max_workers）。
    """
    resolvers = _build_resolver_instances(config.providers, plugins_dir)

    raw: dict[str, list[str]] = defaultdict(list)
    if config.domains:
        with ThreadPoolExecutor(max_workers=max(1, config.concurrency)) as pool:
            futures = {pool.submit(_resolve_domain, d, resolvers): d for d in config.domains}
            for fut, domain in futures.items():
                ips = fut.result()
                if ips:
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