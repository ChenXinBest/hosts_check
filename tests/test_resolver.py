from __future__ import annotations

import pytest

from hosts_check.registry import _REGISTRY, discover_plugins, get, register
from hosts_check.resolver import BaseResolver, ResolverConfig, ResolverError


def test_base_resolver_cannot_be_instantiated_directly():
    cfg = ResolverConfig(name="dummy", upstream_dns=[], extra={})
    with pytest.raises(TypeError):
        BaseResolver(cfg)  # type: ignore[abstract]


def test_base_resolver_subclass_must_implement_resolve():
    class IncompleteResolver(BaseResolver):
        pass

    cfg = ResolverConfig(name="dummy", upstream_dns=[], extra={})
    with pytest.raises(TypeError):
        IncompleteResolver(cfg)  # type: ignore[abstract]


def test_resolver_config_holds_fields():
    cfg = ResolverConfig(name="ip33", upstream_dns=["1.1.1.1"], extra={"k": "v"})
    assert cfg.name == "ip33"
    assert cfg.upstream_dns == ["1.1.1.1"]
    assert cfg.extra == {"k": "v"}


def test_base_resolver_default_init_saves_cfg():
    class StubResolver(BaseResolver):
        def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
            return []

    cfg = ResolverConfig(name="stub", upstream_dns=["1.1.1.1"], extra={})
    r = StubResolver(cfg)
    assert r.cfg is cfg


def test_resolver_error_is_exception():
    assert issubclass(ResolverError, Exception)


@pytest.fixture(autouse=True)
def _clean_registry():
    """每个测试前清空注册表，避免污染。"""
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()


def test_register_decorator_registers_class():
    @register("stub_register")
    class StubResolver(BaseResolver):
        def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
            return []

    assert StubResolver.name == "stub_register"
    assert get("stub_register") is StubResolver


def test_get_unknown_name_raises():
    with pytest.raises(KeyError):
        get("never_registered")


def test_discover_plugins_imports_module_and_triggers_register(tmp_path, monkeypatch):
    # 写一个临时 plugin 文件
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    plugin_file = plugin_dir / "my_plugin.py"
    plugin_file.write_text(
        "from hosts_check.resolver import BaseResolver, ResolverConfig\n"
        "from hosts_check.registry import register\n"
        "\n"
        "@register('my_plugin_for_test')\n"
        "class MyPlugin(BaseResolver):\n"
        "    def resolve(self, domain, cfg):\n"
        "        return ['1.2.3.4']\n"
    )

    # 让 plugins.<stem> 这种 import 能 work：把 tmp_path 加到 sys.path
    monkeypatch.syspath_prepend(str(tmp_path))

    discover_plugins(plugin_dir)

    assert "my_plugin_for_test" in _REGISTRY
    cls = get("my_plugin_for_test")
    cfg = ResolverConfig(name="my_plugin_for_test", upstream_dns=[], extra={})
    assert cls(cfg).resolve("x", cfg) == ["1.2.3.4"]


def test_discover_plugins_skips_underscore_files(tmp_path, monkeypatch):
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "_skip_me.py").write_text("# should be ignored")
    (plugin_dir / "real.py").write_text(
        "from hosts_check.resolver import BaseResolver, ResolverConfig\n"
        "from hosts_check.registry import register\n"
        "\n"
        "@register('real_plugin')\n"
        "class RealPlugin(BaseResolver):\n"
        "    def resolve(self, domain, cfg):\n"
        "        return []\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    discover_plugins(plugin_dir)

    assert "real_plugin" in _REGISTRY
    assert "skip_me" not in _REGISTRY