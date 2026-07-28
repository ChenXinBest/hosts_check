from __future__ import annotations

import sys

import pytest
import requests

from dnsprobe._bootstrap import register_builtin_providers
from dnsprobe.providers.dnschecked import DnscheckedResolver
from dnsprobe.registry import register, get, discover_plugins, _REGISTRY
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError


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
    cfg = ResolverConfig(name="dnschecked", upstream_dns=["1.1.1.1"], extra={"k": "v"})
    assert cfg.name == "dnschecked"
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
    """每个测试前清空注册表与 dnschecked 模块缓存，避免污染。"""
    _REGISTRY.clear()
    sys.modules.pop("dnsprobe.providers.dnschecked", None)
    providers_pkg = sys.modules.get("dnsprobe.providers")
    if providers_pkg is not None:
        providers_pkg.__dict__.pop("dnschecked", None)
    yield
    _REGISTRY.clear()
    sys.modules.pop("dnsprobe.providers.dnschecked", None)
    providers_pkg = sys.modules.get("dnsprobe.providers")
    if providers_pkg is not None:
        providers_pkg.__dict__.pop("dnschecked", None)


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


def test_dnschecked_resolver_returns_ips_on_success(mocker):
    """单个 DNS 200 + results 非空 → 返回 IP 列表。"""
    cfg = ResolverConfig(name="dnschecked", upstream_dns=[], extra={"continents": ["asia"]})
    mocker.patch(
        "dnsprobe.providers.dnschecked.requests.post",
        return_value=mocker.Mock(
            status_code=200,
            json=lambda: {"status_code": 200, "domain": "github.com", "record_type": "A",
                          "dns_server": "223.5.5.5", "results": ["140.82.116.4"]},
        ),
    )
    r = DnscheckedResolver(cfg)
    assert r.resolve("github.com", cfg) == ["140.82.116.4"]


def test_dnschecked_resolver_posts_json_body_and_headers(mocker):
    """POST json={"domain", "record_type": "A", "dns_server"} + headers 含 Origin/Referer。"""
    cfg = ResolverConfig(name="dnschecked", upstream_dns=[], extra={"continents": ["asia"]})
    mock_post = mocker.patch(
        "dnsprobe.providers.dnschecked.requests.post",
        return_value=mocker.Mock(status_code=200, json=lambda: {"status_code": 200, "results": []}),
    )
    r = DnscheckedResolver(cfg)
    # 全部 DNS 都返回空，会抛 ResolverError——但调用已经发完，可以检查 call_args_list
    with pytest.raises(ResolverError):
        r.resolve("avatars.githubusercontent.com", cfg)

    # 取任意一个 call 验证 body 结构 + headers
    assert len(mock_post.call_args_list) > 0
    call = mock_post.call_args_list[0]
    body = call.kwargs["json"]
    assert body["domain"] == "avatars.githubusercontent.com"
    assert body["record_type"] == "A"
    assert body["dns_server"] in {"223.5.5.5", "202.46.34.75", "115.178.96.2"}  # asia 大洲里的某个 DNS
    headers = call.kwargs["headers"]
    assert headers["Origin"] == "https://dnschecked.com"
    assert headers["Referer"] == "https://dnschecked.com/"


def test_dnschecked_resolver_unions_results_from_multiple_dns(mocker):
    """多个 DNS 都 200 → 返回所有 results 并集（保序去重）。"""
    cfg = ResolverConfig(
        name="dnschecked", upstream_dns=[],
        extra={"continents": [], "countries": ["cn", "us"]},
    )
    # 第一次调用（cn）返回 1 个 IP，第二次（us）返回 1 个不同 IP
    responses = [
        mocker.Mock(status_code=200, json=lambda: {"status_code": 200, "results": ["1.1.1.1"]}),
        mocker.Mock(status_code=200, json=lambda: {"status_code": 200, "results": ["2.2.2.2"]}),
    ]
    mocker.patch("dnsprobe.providers.dnschecked.requests.post", side_effect=responses)
    r = DnscheckedResolver(cfg)
    # 并行无序，所以检查集合（不去重后用 == 比较）
    result = r.resolve("github.com", cfg)
    assert sorted(result) == ["1.1.1.1", "2.2.2.2"]


def test_dnschecked_resolver_skips_failed_dns(mocker):
    """单个 DNS 4xx 失败，其他 DNS 成功 → 只返回成功的结果。"""
    cfg = ResolverConfig(name="dnschecked", upstream_dns=[], extra={"countries": ["cn", "us"]})
    responses = [
        mocker.Mock(status_code=404, json=lambda: {"detail": "The DNS query name does not exist"}),
        mocker.Mock(status_code=200, json=lambda: {"status_code": 200, "results": ["8.8.8.8"]}),
    ]
    mocker.patch("dnsprobe.providers.dnschecked.requests.post", side_effect=responses)
    r = DnscheckedResolver(cfg)
    assert r.resolve("github.com", cfg) == ["8.8.8.8"]


def test_dnschecked_resolver_raises_when_all_dns_fail(mocker):
    """所有 DNS 都失败（异常 + 4xx）→ 抛 ResolverError。"""
    cfg = ResolverConfig(name="dnschecked", upstream_dns=[], extra={"countries": ["cn", "us"]})
    mocker.patch(
        "dnsprobe.providers.dnschecked.requests.post",
        side_effect=requests.exceptions.ConnectionError(),
    )
    r = DnscheckedResolver(cfg)
    with pytest.raises(ResolverError):
        r.resolve("github.com", cfg)


def test_dnschecked_resolver_is_registered():
    from dnsprobe.providers.dnschecked import DnscheckedResolver  # fixture pop sys.modules 后本地重绑，保证 is 同一对象
    assert get("dnschecked") is DnscheckedResolver


def test_dnschecked_resolver_uses_http_proxy_when_configured(mocker):
    """cfg.extra.http_proxy 设置时，requests.post 应带 proxies 参数。"""
    cfg = ResolverConfig(
        name="dnschecked", upstream_dns=[],
        extra={"continents": ["asia"], "http_proxy": "http://proxy.example.com:8080"},
    )
    mock_post = mocker.patch(
        "dnsprobe.providers.dnschecked.requests.post",
        return_value=mocker.Mock(
            status_code=200,
            json=lambda: {"status_code": 200, "results": ["1.1.1.1"]},
        ),
    )
    r = DnscheckedResolver(cfg)
    r.resolve("github.com", cfg)

    call = mock_post.call_args
    assert call.kwargs["proxies"] == {
        "http": "http://proxy.example.com:8080",
        "https": "http://proxy.example.com:8080",
    }


def test_dnschecked_resolver_no_proxy_when_not_configured(mocker):
    """cfg.extra.http_proxy 不设置时，proxies 应为 None（直连）。"""
    cfg = ResolverConfig(
        name="dnschecked", upstream_dns=[],
        extra={"continents": ["asia"]},  # 不设 http_proxy
    )
    mock_post = mocker.patch(
        "dnsprobe.providers.dnschecked.requests.post",
        return_value=mocker.Mock(
            status_code=200,
            json=lambda: {"status_code": 200, "results": ["1.1.1.1"]},
        ),
    )
    r = DnscheckedResolver(cfg)
    r.resolve("github.com", cfg)

    call = mock_post.call_args
    assert call.kwargs["proxies"] is None


def test_register_builtin_providers_adds_dnschecked_to_registry():
    """显式调用 register_builtin_providers() 后 _REGISTRY 含 dnschecked。"""
    _REGISTRY.pop("dnschecked", None)  # 先清理（防 fixture 残留）
    register_builtin_providers()
    assert "dnschecked" in _REGISTRY
    assert _REGISTRY["dnschecked"].__name__ == "DnscheckedResolver"


def test_register_builtin_providers_is_idempotent():
    """重复调用不抛错、不重复注册。"""
    register_builtin_providers()
    register_builtin_providers()
    # 同一 class object 仍在 _REGISTRY
    assert _REGISTRY["dnschecked"].__name__ == "DnscheckedResolver"
