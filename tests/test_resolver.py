from __future__ import annotations

import sys

import pytest
import requests
import dns.message
import dns.rdatatype
import dns.rrset

from dnsprobe._bootstrap import register_builtin_providers
from dnsprobe.providers.doh import DoHResolver, _build_query, _parse_response
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
    cfg = ResolverConfig(name="doh", upstream_dns=["1.1.1.1"], extra={"k": "v"})
    assert cfg.name == "doh"
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
    """每个测试前清空注册表与 doh 模块缓存，避免污染。"""
    _REGISTRY.clear()
    sys.modules.pop("dnsprobe.providers.doh", None)
    providers_pkg = sys.modules.get("dnsprobe.providers")
    if providers_pkg is not None:
        providers_pkg.__dict__.pop("doh", None)
    yield
    _REGISTRY.clear()
    sys.modules.pop("dnsprobe.providers.doh", None)
    providers_pkg = sys.modules.get("dnsprobe.providers")
    if providers_pkg is not None:
        providers_pkg.__dict__.pop("doh", None)


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


# ── helper: 构造一个 DoH 响应 wire bytes ──────────────────────────
def _build_doh_response(domain: str, ips: list[str], rcode=0) -> bytes:
    # 用绝对名（带 trailing dot）确保 wire 转换能成功
    fqdn = domain if domain.endswith(".") else domain + "."
    q = dns.message.make_query(fqdn, dns.rdatatype.A)
    msg = dns.message.make_response(q)
    msg.rcode = rcode
    for ip in ips:
        rrset = dns.rrset.from_text(fqdn, 300, dns.rdataclass.IN, dns.rdatatype.A, ip)
        msg.answer.append(rrset)
    return msg.to_wire()


def test_doh_resolver_returns_ips_on_success(mocker):
    """单个 DoH 端点返回 A 记录 → 解析 IP 列表。"""
    cfg = ResolverConfig(
        name="doh", upstream_dns=[],
        extra={"dns_servers": [
            {"name": "mock", "url": "https://mock.dns/dns-query", "country": "us", "weight": 1.0, "proxy": False},
        ]},
    )
    response_wire = _build_doh_response("github.com", ["1.1.1.1", "2.2.2.2"])
    mocker.patch(
        "dnsprobe.providers.doh.requests.get",
        return_value=mocker.Mock(status_code=200, content=response_wire),
    )

    r = DoHResolver(cfg)
    assert r.resolve("github.com", cfg) == ["1.1.1.1", "2.2.2.2"]


def test_doh_resolver_posts_dns_param_and_headers(mocker):
    """DoH GET: URL 包含 ?dns=<base64url>，header Accept: application/dns-message。"""
    cfg = ResolverConfig(
        name="doh", upstream_dns=[],
        extra={"dns_servers": [
            {"name": "mock", "url": "https://mock.dns/dns-query", "country": "us", "weight": 1.0, "proxy": False},
        ]},
    )
    response_wire = _build_doh_response("github.com", ["1.1.1.1"])
    mock_get = mocker.patch(
        "dnsprobe.providers.doh.requests.get",
        return_value=mocker.Mock(status_code=200, content=response_wire),
    )

    r = DoHResolver(cfg)
    r.resolve("avatars.githubusercontent.com", cfg)

    call = mock_get.call_args
    assert call.args[0].startswith("https://mock.dns/dns-query?dns=")
    assert "dns=" in call.args[0]
    assert call.kwargs["headers"]["Accept"] == "application/dns-message"
    assert call.kwargs["timeout"] == 10


def test_doh_resolver_uses_proxy_when_server_marks_proxy_true(mocker):
    """server.proxy=true 时，requests.get 应带 proxies 参数。"""
    cfg = ResolverConfig(
        name="doh", upstream_dns=[],
        extra={
            "dns_servers": [
                {"name": "google", "url": "https://dns.google/dns-query", "country": "us", "weight": 2.0, "proxy": True},
            ],
            "http_proxy": "http://proxy.example.com:8080",
        },
    )
    response_wire = _build_doh_response("github.com", ["8.8.8.8"])
    mock_get = mocker.patch(
        "dnsprobe.providers.doh.requests.get",
        return_value=mocker.Mock(status_code=200, content=response_wire),
    )

    r = DoHResolver(cfg)
    r.resolve("github.com", cfg)

    call = mock_get.call_args
    assert call.kwargs["proxies"] == {
        "http": "http://proxy.example.com:8080",
        "https": "http://proxy.example.com:8080",
    }


def test_doh_resolver_no_proxy_when_server_marks_proxy_false(mocker):
    """server.proxy=false 时（即使顶层有 http_proxy），proxies=None。"""
    cfg = ResolverConfig(
        name="doh", upstream_dns=[],
        extra={
            "dns_servers": [
                {"name": "aliyun", "url": "https://dns.alidns.com/dns-query", "country": "cn", "weight": 1.0, "proxy": False},
            ],
            "http_proxy": "http://proxy.example.com:8080",
        },
    )
    response_wire = _build_doh_response("github.com", ["223.5.5.5"])
    mock_get = mocker.patch(
        "dnsprobe.providers.doh.requests.get",
        return_value=mocker.Mock(status_code=200, content=response_wire),
    )

    r = DoHResolver(cfg)
    r.resolve("github.com", cfg)

    call = mock_get.call_args
    assert call.kwargs["proxies"] is None


def test_doh_resolver_unions_results_from_multiple_servers(mocker):
    """多个 DoH 端点都返回 → 取并集（按 weight 顺序）。"""
    cfg = ResolverConfig(
        name="doh", upstream_dns=[],
        extra={"dns_servers": [
            {"name": "low",  "url": "https://low.dns/q",  "country": "cn", "weight": 1.0, "proxy": False},
            {"name": "high", "url": "https://high.dns/q", "country": "us", "weight": 3.0, "proxy": True},
        ]},
    )
    # 用 URL 区分响应：low 端点返回 1.1.1.1，high 端点返回 2.2.2.2
    url_to_ip = {
        "low.dns": "1.1.1.1",
        "high.dns": "2.2.2.2",
    }

    def dispatch(url, *a, **kw):
        # 从 url 提取 host
        host = url.split("/")[2]
        ip = url_to_ip[host]
        return mocker.Mock(status_code=200, content=_build_doh_response("github.com", [ip]))

    mocker.patch("dnsprobe.providers.doh.requests.get", side_effect=dispatch)

    r = DoHResolver(cfg)
    result = r.resolve("github.com", cfg)

    # 高权重 (high) 的 2.2.2.2 应该在前面
    assert result == ["2.2.2.2", "1.1.1.1"]


def test_doh_resolver_skips_failed_servers(mocker):
    """一个端点失败（status != 200）→ 用其他端点的结果。"""
    cfg = ResolverConfig(
        name="doh", upstream_dns=[],
        extra={"dns_servers": [
            {"name": "a", "url": "https://a.dns/q", "country": "cn", "weight": 1.0, "proxy": False},
            {"name": "b", "url": "https://b.dns/q", "country": "us", "weight": 2.0, "proxy": True},
        ]},
    )
    def dispatch(url, *a, **kw):
        if "a.dns" in url:
            return mocker.Mock(status_code=500, content=b"")
        return mocker.Mock(status_code=200, content=_build_doh_response("github.com", ["1.1.1.1"]))

    mocker.patch("dnsprobe.providers.doh.requests.get", side_effect=dispatch)

    r = DoHResolver(cfg)
    assert r.resolve("github.com", cfg) == ["1.1.1.1"]


def test_doh_resolver_raises_when_all_servers_fail(mocker):
    """所有端点都失败 → 抛 ResolverError。"""
    cfg = ResolverConfig(
        name="doh", upstream_dns=[],
        extra={"dns_servers": [
            {"name": "a", "url": "https://a.dns/q", "country": "cn", "weight": 1.0, "proxy": False},
        ]},
    )
    mocker.patch(
        "dnsprobe.providers.doh.requests.get",
        side_effect=requests.exceptions.ConnectionError(),
    )

    r = DoHResolver(cfg)
    with pytest.raises(ResolverError):
        r.resolve("github.com", cfg)


def test_doh_resolver_uses_default_servers_when_dns_servers_empty(mocker):
    """cfg.extra.dns_servers 空时，fallback 到内置默认列表（不抛错）。"""
    cfg = ResolverConfig(name="doh", upstream_dns=[], extra={})  # dns_servers 缺省
    response_wire = _build_doh_response("github.com", ["1.1.1.1"])
    mocker.patch(
        "dnsprobe.providers.doh.requests.get",
        return_value=mocker.Mock(status_code=200, content=response_wire),
    )

    r = DoHResolver(cfg)
    result = r.resolve("github.com", cfg)
    assert result == ["1.1.1.1"]


def test_doh_resolver_is_registered():
    from dnsprobe.providers.doh import DoHResolver  # fixture pop 后本地重绑
    assert get("doh") is DoHResolver


def test_register_builtin_providers_adds_doh_to_registry():
    _REGISTRY.pop("doh", None)
    register_builtin_providers()
    assert "doh" in _REGISTRY
    assert _REGISTRY["doh"].__name__ == "DoHResolver"


def test_register_builtin_providers_is_idempotent():
    register_builtin_providers()
    register_builtin_providers()
    assert _REGISTRY["doh"].__name__ == "DoHResolver"


# ── IPv6 / AAAA 支持 ──────────────────────────────────────────────

def _build_doh_aaaa_response(domain: str, ips: list[str]) -> bytes:
    """构造 AAAA 记录的 DoH 响应 wire bytes。"""
    fqdn = domain if domain.endswith(".") else domain + "."
    q = dns.message.make_query(fqdn, dns.rdatatype.AAAA)
    msg = dns.message.make_response(q)
    for ip in ips:
        rrset = dns.rrset.from_text(fqdn, 300, dns.rdataclass.IN, dns.rdatatype.AAAA, ip)
        msg.answer.append(rrset)
    return msg.to_wire()


def test_doh_resolver_aaaa_returns_ipv6_addresses(mocker):
    """record_types=["AAAA"] 时返回 IPv6 地址。"""
    cfg = ResolverConfig(
        name="doh", upstream_dns=[],
        extra={
            "dns_servers": [
                {"name": "mock", "url": "https://mock.dns/dns-query", "country": "us", "weight": 1.0, "proxy": False},
            ],
            "record_types": ["AAAA"],
        },
    )
    response_wire = _build_doh_aaaa_response("github.com", ["2001:db8::1", "2001:db8::2"])
    mocker.patch(
        "dnsprobe.providers.doh.requests.get",
        return_value=mocker.Mock(status_code=200, content=response_wire),
    )

    r = DoHResolver(cfg)
    result = r.resolve("github.com", cfg)
    assert result == ["2001:db8::1", "2001:db8::2"]


def test_doh_resolver_dual_stack_returns_both_a_and_aaaa(mocker):
    """record_types=["A", "AAAA"] 时同时返回 IPv4 和 IPv6。"""
    cfg = ResolverConfig(
        name="doh", upstream_dns=[],
        extra={
            "dns_servers": [
                {"name": "mock", "url": "https://mock.dns/dns-query", "country": "us", "weight": 1.0, "proxy": False},
            ],
            "record_types": ["A", "AAAA"],
        },
    )

    def dispatch(url, *a, **kw):
        # 从 URL 中的 dns 参数判断查询类型
        if "dns=" in url:
            import base64
            from urllib.parse import parse_qs, urlparse
            qs = parse_qs(urlparse(url).query)
            wire_b64 = qs["dns"][0]
            # 补回 padding
            wire_b64 += "=" * (-len(wire_b64) % 4)
            query_wire = base64.urlsafe_b64decode(wire_b64)
            query_msg = dns.message.from_wire(query_wire)
            qtype = query_msg.question[0].rdtype
            if qtype == dns.rdatatype.A:
                return mocker.Mock(
                    status_code=200,
                    content=_build_doh_response("github.com", ["1.2.3.4"]),
                )
            elif qtype == dns.rdatatype.AAAA:
                return mocker.Mock(
                    status_code=200,
                    content=_build_doh_aaaa_response("github.com", ["2001:db8::1"]),
                )
        return mocker.Mock(status_code=500, content=b"")

    mocker.patch("dnsprobe.providers.doh.requests.get", side_effect=dispatch)

    r = DoHResolver(cfg)
    result = r.resolve("github.com", cfg)
    # A 在前（先查），AAAA 在后
    assert "1.2.3.4" in result
    assert "2001:db8::1" in result
    assert result.index("1.2.3.4") < result.index("2001:db8::1")


def test_doh_resolver_default_record_types_is_a_only(mocker):
    """不配置 record_types 时默认只查 A 记录。"""
    from dnsprobe.providers.doh import _collect_record_types
    cfg = ResolverConfig(name="doh", upstream_dns=[], extra={})
    rdtypes = _collect_record_types(cfg)
    assert rdtypes == [dns.rdatatype.A]


def test_doh_resolver_unsupported_record_types_fallback_to_a(mocker):
    """配置不支持的记录类型时回落到 A。"""
    from dnsprobe.providers.doh import _collect_record_types
    cfg = ResolverConfig(
        name="doh", upstream_dns=[],
        extra={"record_types": ["MX", "TXT"]},
    )
    rdtypes = _collect_record_types(cfg)
    assert rdtypes == [dns.rdatatype.A]
