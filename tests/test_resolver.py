from __future__ import annotations

import sys

import pytest

from dnsprobe.registry import register, get, discover_plugins, _REGISTRY
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError
from dnsprobe.providers.ip33 import Ip33Resolver


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
    """每个测试前清空注册表与 ip33 模块缓存，避免污染。"""
    _REGISTRY.clear()
    sys.modules.pop("dnsprobe.providers.ip33", None)
    providers_pkg = sys.modules.get("dnsprobe.providers")
    if providers_pkg is not None:
        providers_pkg.__dict__.pop("ip33", None)
    yield
    _REGISTRY.clear()
    sys.modules.pop("dnsprobe.providers.ip33", None)
    providers_pkg = sys.modules.get("dnsprobe.providers")
    if providers_pkg is not None:
        providers_pkg.__dict__.pop("ip33", None)


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
        "from dnsprobe.resolver import BaseResolver, ResolverConfig\n"
        "from dnsprobe.registry import register\n"
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
        "from dnsprobe.resolver import BaseResolver, ResolverConfig\n"
        "from dnsprobe.registry import register\n"
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


from dnsprobe.providers.ip33 import Ip33Resolver


def test_ip33_resolver_merges_results_from_multiple_upstream(mocker):
    cfg = ResolverConfig(
        name="ip33",
        upstream_dns=["1.1.1.1", "2.2.2.2"],
        extra={},
    )

    fake_responses = [
        mocker.Mock(text='{"record": [{"ip": "9.9.9.9"}, {"ip": "8.8.8.8"}]}'),
        mocker.Mock(text='{"record": [{"ip": "7.7.7.7"}]}'),
    ]
    mocker.patch("dnsprobe.providers.ip33.requests.post", side_effect=fake_responses)

    r = Ip33Resolver(cfg)
    assert r.resolve("example.com", cfg) == ["9.9.9.9", "8.8.8.8", "7.7.7.7"]


def test_ip33_resolver_raises_resolvererror_on_http_failure(mocker):
    cfg = ResolverConfig(name="ip33", upstream_dns=["1.1.1.1"], extra={})

    mocker.patch(
        "dnsprobe.providers.ip33.requests.post",
        side_effect=RuntimeError("net down"),
    )

    r = Ip33Resolver(cfg)
    with pytest.raises(ResolverError):
        r.resolve("example.com", cfg)


def test_ip33_resolver_is_registered():
    assert Ip33Resolver.name == "ip33"


def test_ip33_resolver_continues_when_first_upstream_fails(mocker):
    cfg = ResolverConfig(
        name="ip33",
        upstream_dns=["1.1.1.1", "2.2.2.2"],
        extra={},
    )
    successful_response = mocker.Mock(text='{"record": [{"ip": "7.7.7.7"}]}')
    mocker.patch(
        "dnsprobe.providers.ip33.requests.post",
        side_effect=[RuntimeError("first failed"), successful_response],
    )

    assert Ip33Resolver(cfg).resolve("example.com", cfg) == ["7.7.7.7"]


def test_ip33_resolver_returns_partial_results(mocker):
    cfg = ResolverConfig(
        name="ip33",
        upstream_dns=["1.1.1.1", "2.2.2.2"],
        extra={},
    )
    responses = [
        mocker.Mock(text='{"record": [{"ip": "9.9.9.9"}]}'),
        mocker.Mock(text='{"record": [{"ip": "7.7.7.7"}]}'),
    ]
    mocker.patch("dnsprobe.providers.ip33.requests.post", side_effect=responses)

    assert Ip33Resolver(cfg).resolve("example.com", cfg) == ["9.9.9.9", "7.7.7.7"]


def test_ip33_resolver_raises_when_all_upstreams_fail(mocker):
    cfg = ResolverConfig(
        name="ip33",
        upstream_dns=["1.1.1.1", "2.2.2.2"],
        extra={},
    )
    mocker.patch(
        "dnsprobe.providers.ip33.requests.post",
        side_effect=[RuntimeError("first failed"), RuntimeError("second failed")],
    )

    with pytest.raises(ResolverError) as exc_info:
        Ip33Resolver(cfg).resolve("example.com", cfg)

    message = str(exc_info.value)
    assert "1.1.1.1: first failed" in message
    assert "2.2.2.2: second failed" in message


from dnsprobe._bootstrap import register_builtin_providers


def test_register_builtin_providers_adds_ip33_to_registry():
    """显式调用 register_builtin_providers() 后 _REGISTRY 含 ip33。"""
    _REGISTRY.pop("ip33", None)  # 先清理（防 fixture 残留）
    register_builtin_providers()
    assert "ip33" in _REGISTRY
    assert _REGISTRY["ip33"].__name__ == "Ip33Resolver"


def test_register_builtin_providers_is_idempotent():
    """重复调用不抛错、不重复注册。"""
    register_builtin_providers()
    register_builtin_providers()
    # 同一 class object 仍在 _REGISTRY
    assert _REGISTRY["ip33"].__name__ == "Ip33Resolver"
