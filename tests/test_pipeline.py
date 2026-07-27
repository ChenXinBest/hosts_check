from __future__ import annotations

import datetime
from pathlib import Path

from dnsprobe.config import (
    AppConfig,
    OutputConfig,
    ProviderConfig,
    ReachabilityConfig,
)
from dnsprobe.pipeline import run


def _make_cfg(tmp_path: Path, domains: list[str]) -> AppConfig:
    return AppConfig(
        providers=[ProviderConfig(name="fake", upstream_dns=["1.1.1.1"])],
        output=OutputConfig(path=str(tmp_path / "hosts.txt"), keep_old_section=False),
        reachability=ReachabilityConfig(method="http_head", timeout=5.0),
        domains=domains,
    )


def test_pipeline_returns_zero_when_at_least_one_domain_works(tmp_path, mocker):
    from dnsprobe import registry

    class FakeResolver:
        name = "fake"

        def __init__(self, cfg):
            self.cfg = cfg

        def resolve(self, domain, cfg):
            return ["1.1.1.1"]

    registry._REGISTRY["fake"] = FakeResolver
    mocker.patch(
        "dnsprobe.pipeline.filter_reachable",
        return_value=["1.1.1.1"],
    )

    cfg = _make_cfg(tmp_path, ["a.example", "b.example"])
    rc = run(cfg, plugins_dir=None)

    assert rc == 0
    content = (tmp_path / "hosts.txt").read_text(encoding="utf-8")
    assert "1.1.1.1\ta.example" in content
    assert "1.1.1.1\tb.example" in content


def test_pipeline_returns_one_when_all_domains_fail(tmp_path, mocker):
    from dnsprobe import registry

    class FakeResolver:
        name = "fake"

        def __init__(self, cfg):
            self.cfg = cfg

        def resolve(self, domain, cfg):
            return []

    registry._REGISTRY["fake"] = FakeResolver
    mocker.patch("dnsprobe.pipeline.filter_reachable", return_value=[])

    cfg = _make_cfg(tmp_path, ["a.example"])
    rc = run(cfg, plugins_dir=None)

    assert rc == 1


def test_pipeline_skips_disabled_providers(tmp_path, mocker):
    from dnsprobe import registry

    calls = []

    class FakeResolver:
        name = "fake"

        def __init__(self, cfg):
            self.cfg = cfg

        def resolve(self, domain, cfg):
            calls.append(domain)
            return ["1.1.1.1"]

    registry._REGISTRY["fake"] = FakeResolver
    mocker.patch(
        "dnsprobe.pipeline.filter_reachable",
        return_value=["1.1.1.1"],
    )

    cfg = AppConfig(
        providers=[
            ProviderConfig(name="fake", enabled=False, upstream_dns=["1.1.1.1"]),
        ],
        output=OutputConfig(path=str(tmp_path / "hosts.txt"), keep_old_section=False),
        reachability=ReachabilityConfig(),
        domains=["a.example"],
    )
    rc = run(cfg, plugins_dir=None)

    assert rc == 1
    assert calls == []  # 禁用 provider 不会调用


def test_pipeline_continues_when_one_resolver_raises(tmp_path, mocker):
    from dnsprobe import registry
    from dnsprobe.resolver import ResolverError

    class BrokenResolver:
        name = "broken"

        def __init__(self, cfg):
            self.cfg = cfg

        def resolve(self, domain, cfg):
            raise ResolverError("nope")

    class GoodResolver:
        name = "good"

        def __init__(self, cfg):
            self.cfg = cfg

        def resolve(self, domain, cfg):
            return ["2.2.2.2"]

    registry._REGISTRY["broken"] = BrokenResolver
    registry._REGISTRY["good"] = GoodResolver
    mocker.patch(
        "dnsprobe.pipeline.filter_reachable",
        return_value=["2.2.2.2"],
    )

    cfg = AppConfig(
        providers=[
            ProviderConfig(name="broken", upstream_dns=["1.1.1.1"]),
            ProviderConfig(name="good", upstream_dns=["3.3.3.3"]),
        ],
        output=OutputConfig(path=str(tmp_path / "hosts.txt"), keep_old_section=False),
        reachability=ReachabilityConfig(),
        domains=["a.example"],
    )
    rc = run(cfg, plugins_dir=None)

    assert rc == 0
    content = (tmp_path / "hosts.txt").read_text(encoding="utf-8")
    assert "2.2.2.2\ta.example" in content
    assert "1.1.1.1" not in content


def test_pipeline_skips_provider_when_resolve_raises_unexpected_error(
    tmp_path, mocker
):
    from dnsprobe import registry

    class FakeResolver:
        name = "fake-unexpected"

        def __init__(self, cfg):
            self.cfg = cfg

        def resolve(self, domain, cfg):
            if domain == "a.example":
                raise RuntimeError("boom")
            return ["2.2.2.2"]

    registry._REGISTRY["fake-unexpected"] = FakeResolver
    mocker.patch(
        "dnsprobe.pipeline.filter_reachable",
        side_effect=lambda ips, domain, config: ips,
    )
    cfg = AppConfig(
        providers=[
            ProviderConfig(name="fake-unexpected", upstream_dns=["1.1.1.1"]),
        ],
        output=OutputConfig(path=str(tmp_path / "hosts.txt"), keep_old_section=False),
        reachability=ReachabilityConfig(),
        domains=["a.example", "b.example"],
    )

    rc = run(cfg, plugins_dir=None)

    assert rc == 0
    content = (tmp_path / "hosts.txt").read_text(encoding="utf-8")
    assert "2.2.2.2\tb.example" in content
    assert "a.example" not in content


def test_pipeline_handles_plugin_failure_gracefully(tmp_path, mocker):
    from dnsprobe import registry

    class GoodResolver:
        name = "good-after-unavailable"

        def __init__(self, cfg):
            self.cfg = cfg

        def resolve(self, domain, cfg):
            return ["3.3.3.3"]

    registry._REGISTRY["good-after-unavailable"] = GoodResolver
    mocker.patch(
        "dnsprobe.pipeline.filter_reachable",
        return_value=["3.3.3.3"],
    )
    cfg = AppConfig(
        providers=[
            ProviderConfig(name="unavailable-provider"),
            ProviderConfig(name="good-after-unavailable"),
        ],
        output=OutputConfig(path=str(tmp_path / "hosts.txt"), keep_old_section=False),
        reachability=ReachabilityConfig(),
        domains=["a.example"],
    )

    rc = run(cfg, plugins_dir=None)

    assert rc == 0
    content = (tmp_path / "hosts.txt").read_text(encoding="utf-8")
    assert "3.3.3.3\ta.example" in content
