from __future__ import annotations

from pathlib import Path

import pytest

from dnsprobe.config import (
    AppConfig,
    OutputConfig,
    ProviderConfig,
    ReachabilityConfig,
    load_config,
)


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_load_config_minimal(tmp_path: Path):
    _write(
        tmp_path / "config.yml",
        "providers:\n  - name: doh\n",
    )
    _write(
        tmp_path / "domains.yml",
        "domains:\n  - a.example\n  - b.example\n",
    )

    cfg = load_config(tmp_path / "config.yml")

    assert isinstance(cfg, AppConfig)
    assert cfg.providers == [ProviderConfig(name="doh")]
    assert cfg.domains == ["a.example", "b.example"]
    assert cfg.output == OutputConfig()
    assert cfg.reachability == ReachabilityConfig()


def test_load_config_enabled_defaults_true(tmp_path: Path):
    _write(
        tmp_path / "config.yml",
        "providers:\n  - name: doh\n    upstream_dns: [1.1.1.1]\n",
    )
    _write(tmp_path / "domains.yml", "domains: []\n")

    cfg = load_config(tmp_path / "config.yml")

    p = cfg.providers[0]
    assert p.enabled is True
    assert p.upstream_dns == ["1.1.1.1"]
    assert p.extra == {}


def test_load_config_explicit_enabled_false(tmp_path: Path):
    _write(
        tmp_path / "config.yml",
        "providers:\n  - name: doh\n    enabled: false\n",
    )
    _write(tmp_path / "domains.yml", "domains: []\n")

    cfg = load_config(tmp_path / "config.yml")

    assert cfg.providers[0].enabled is False


def test_load_config_empty_domains_does_not_raise(tmp_path: Path):
    _write(tmp_path / "config.yml", "providers: []\n")
    _write(tmp_path / "domains.yml", "domains: []\n")

    cfg = load_config(tmp_path / "config.yml")

    assert cfg.domains == []


def test_load_config_output_and_reachability_overrides(tmp_path: Path):
    _write(
        tmp_path / "config.yml",
        (
            "providers: []\n"
            "output:\n"
            "  path: out/hosts.txt\n"
            "  keep_old_section: false\n"
            "reachability:\n"
            "  method: http_head\n"
            "  timeout: 3.5\n"
        ),
    )
    _write(tmp_path / "domains.yml", "domains: []\n")

    cfg = load_config(tmp_path / "config.yml")

    assert cfg.output == OutputConfig(path="out/hosts.txt", keep_old_section=False)
    assert cfg.reachability == ReachabilityConfig(method="http_head", timeout=3.5)


def test_load_config_missing_domains_file_raises(tmp_path: Path):
    _write(tmp_path / "config.yml", "providers: []\n")

    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "config.yml")


def test_load_config_custom_domains_path(tmp_path: Path):
    _write(tmp_path / "config.yml", "providers: []\n")
    _write(
        tmp_path / "domains.yml",
        "domains:\n  - default.example\n",
    )
    _write(
        tmp_path / "custom_domains.yml",
        "domains:\n  - custom1.example\n  - custom2.example\n",
    )

    cfg = load_config(
        tmp_path / "config.yml",
        domains_path=tmp_path / "custom_domains.yml",
    )

    assert cfg.domains == ["custom1.example", "custom2.example"]


def test_load_config_concurrency_defaults_to_8(tmp_path: Path):
    _write(tmp_path / "config.yml", "providers: []\n")
    _write(tmp_path / "domains.yml", "domains: []\n")

    cfg = load_config(tmp_path / "config.yml")

    assert cfg.concurrency == 8


def test_load_config_concurrency_override(tmp_path: Path):
    _write(
        tmp_path / "config.yml",
        "providers: []\nconcurrency: 16\n",
    )
    _write(tmp_path / "domains.yml", "domains: []\n")

    cfg = load_config(tmp_path / "config.yml")

    assert cfg.concurrency == 16


def test_load_config_http_proxy_defaults_to_empty(tmp_path: Path):
    _write(tmp_path / "config.yml", "providers: []\n")
    _write(tmp_path / "domains.yml", "domains: []\n")

    cfg = load_config(tmp_path / "config.yml")

    assert cfg.http_proxy == ""


def test_load_config_http_proxy_override(tmp_path: Path):
    _write(
        tmp_path / "config.yml",
        "providers: []\nhttp_proxy: http://proxy.example.com:8080\n",
    )
    _write(tmp_path / "domains.yml", "domains: []\n")

    cfg = load_config(tmp_path / "config.yml")

    assert cfg.http_proxy == "http://proxy.example.com:8080"


def test_load_config_http_proxy_strips_whitespace(tmp_path: Path):
    _write(
        tmp_path / "config.yml",
        "providers: []\nhttp_proxy: '  http://proxy.example.com:8080  '\n",
    )
    _write(tmp_path / "domains.yml", "domains: []\n")

    cfg = load_config(tmp_path / "config.yml")

    assert cfg.http_proxy == "http://proxy.example.com:8080"
