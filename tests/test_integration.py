from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from dnsprobe.config import load_config
from dnsprobe.pipeline import run
from dnsprobe.registry import _REGISTRY, discover_plugins


@pytest.fixture(autouse=True)
def _reset_registry():
    """保证测试间 registry 状态隔离（避免跨测试污染）。"""
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()


def test_full_pipeline_with_third_party_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """完整工作流: 第三方 plugin 落盘 → discover → load_config → run → 写文件。

    spec §9 验收标准 4: 第三方插件能挂入主流程并产出 hosts.txt。
    """
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / "doh_plugin.py").write_text(
        textwrap.dedent(
            """\
            from dnsprobe.registry import register
            from dnsprobe.resolver import BaseResolver, ResolverConfig

            @register("doh_plugin")
            class DohPlugin(BaseResolver):
                def resolve(self, domain, cfg):
                    return ["7.7.7.7", "8.8.8.8"]
            """
        ),
        encoding="utf-8",
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    discover_plugins(plugins)
    assert "doh_plugin" in _REGISTRY

    cfg_text = textwrap.dedent(
        f"""\
        providers:
          - name: doh_plugin
            enabled: true
            upstream_dns: [1.1.1.1]
        output:
          path: {tmp_path.as_posix()}/hosts.txt
          keep_old_section: false
        reachability:
          method: http_head
          timeout: 5.0
        """
    )
    (tmp_path / "config.yml").write_text(cfg_text, encoding="utf-8")
    (tmp_path / "domains.yml").write_text(
        "domains:\n  - a.example\n  - b.example\n", encoding="utf-8"
    )

    import dnsprobe.pipeline as pl

    monkeypatch.setattr(pl, "filter_reachable", lambda ips, domain, cfg, http_proxy="": ips)

    cfg = load_config(tmp_path / "config.yml")
    rc = run(cfg, plugins_dir=plugins)
    assert rc == 0

    content = (tmp_path / "hosts.txt").read_text(encoding="utf-8")
    assert "7.7.7.7\ta.example" in content
    assert "7.7.7.7\tb.example" in content
    assert "8.8.8.8\ta.example" in content
    assert "8.8.8.8\tb.example" in content


def test_pipeline_dedupes_ips_preserving_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """多个 resolver 返回重复 IP 时,主流程保序去重。

    spec §9 验收标准 4 延伸: 验证去重语义。
    """
    plugin = tmp_path / "plugins"
    plugin.mkdir()
    (plugin / "r1.py").write_text(
        textwrap.dedent(
            """\
            from dnsprobe.registry import register
            from dnsprobe.resolver import BaseResolver, ResolverConfig

            @register("r1")
            class R1(BaseResolver):
                def resolve(self, domain, cfg):
                    return ["1.1.1.1", "2.2.2.2"]
            """
        ),
        encoding="utf-8",
    )
    (plugin / "r2.py").write_text(
        textwrap.dedent(
            """\
            from dnsprobe.registry import register
            from dnsprobe.resolver import BaseResolver, ResolverConfig

            @register("r2")
            class R2(BaseResolver):
                def resolve(self, domain, cfg):
                    return ["2.2.2.2", "3.3.3.3"]
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    cfg_text = textwrap.dedent(
        f"""\
        providers:
          - name: r1
            enabled: true
            upstream_dns: [1.1.1.1]
          - name: r2
            enabled: true
            upstream_dns: [1.1.1.1]
        output:
          path: {tmp_path.as_posix()}/hosts.txt
          keep_old_section: false
        reachability:
          method: http_head
          timeout: 5.0
        """
    )
    (tmp_path / "config.yml").write_text(cfg_text, encoding="utf-8")
    (tmp_path / "domains.yml").write_text(
        "domains:\n  - x.example\n", encoding="utf-8"
    )

    import dnsprobe.pipeline as pl

    monkeypatch.setattr(pl, "filter_reachable", lambda ips, domain, cfg, http_proxy="": ips)

    cfg = load_config(tmp_path / "config.yml")
    rc = run(cfg, plugins_dir=plugin)
    assert rc == 0

    content = (tmp_path / "hosts.txt").read_text(encoding="utf-8")
    lines = [line for line in content.split("\n") if line and not line.startswith("###")]
    assert lines == [
        "1.1.1.1\tx.example",
        "2.2.2.2\tx.example",
        "3.3.3.3\tx.example",
    ]