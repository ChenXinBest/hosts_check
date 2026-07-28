from __future__ import annotations

import sys

import pytest
import requests

from dnsprobe._bootstrap import register_builtin_providers
from dnsprobe.providers.toolhelper import ToolhelperResolver
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
    cfg = ResolverConfig(name="toolhelper", upstream_dns=["1.1.1.1"], extra={"k": "v"})
    assert cfg.name == "toolhelper"
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
    """每个测试前清空注册表与 toolhelper 模块缓存，避免污染。"""
    _REGISTRY.clear()
    sys.modules.pop("dnsprobe.providers.toolhelper", None)
    providers_pkg = sys.modules.get("dnsprobe.providers")
    if providers_pkg is not None:
        providers_pkg.__dict__.pop("toolhelper", None)
    yield
    _REGISTRY.clear()
    sys.modules.pop("dnsprobe.providers.toolhelper", None)
    providers_pkg = sys.modules.get("dnsprobe.providers")
    if providers_pkg is not None:
        providers_pkg.__dict__.pop("toolhelper", None)


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


def test_toolhelper_resolver_returns_ips_on_success(mocker):
    """Tag=1 响应应返回 Data.A 中 <br> 分隔的 IP 列表（去空）。"""
    cfg = ResolverConfig(name="toolhelper", upstream_dns=[], extra={})
    mocker.patch(
        "dnsprobe.providers.toolhelper.requests.post",
        return_value=mocker.Mock(
            status_code=200,
            json=lambda: {
                "Total": 0,
                "Data": {
                    "A": "1.1.1.1<br>2.2.2.2<br>3.3.3.3",
                    "AAAA": "",
                    "NS": "",
                    "MX": "",
                    "TXT": "",
                    "SOA": "",
                },
                "Tag": 1,
                "Message": None,
                "Description": None,
            },
            raise_for_status=lambda: None,
        ),
    )
    r = ToolhelperResolver(cfg)
    assert r.resolve("github.com", cfg) == ["1.1.1.1", "2.2.2.2", "3.3.3.3"]


def test_toolhelper_resolver_posts_host_param_and_headers(mocker):
    """POST data={host: domain} + headers 含 Origin/Referer/X-Requested-With + URL 含 query。"""
    cfg = ResolverConfig(name="toolhelper", upstream_dns=[], extra={})
    mock_post = mocker.patch(
        "dnsprobe.providers.toolhelper.requests.post",
        return_value=mocker.Mock(
            status_code=200,
            json=lambda: {"Total": 0, "Data": {"A": "1.1.1.1"}, "Tag": 1, "Message": None, "Description": None},
            raise_for_status=lambda: None,
        ),
    )
    r = ToolhelperResolver(cfg)
    r.resolve("avatars.githubusercontent.com", cfg)

    call = mock_post.call_args
    # data 是 form-encoded body
    assert call.kwargs["data"] == {"host": "avatars.githubusercontent.com"}
    # URL 走 keyword args，应是空字符串（参数走 data）
    assert "url" not in call.kwargs or call.kwargs.get("url") is None
    # headers 验证
    headers = call.kwargs["headers"]
    assert headers["Origin"] == "https://www.toolhelper.cn"
    assert headers["Referer"] == "https://www.toolhelper.cn/Http/DNSCheck"
    assert headers["X-Requested-With"] == "XMLHttpRequest"
    # URL query string 验证：call.args[0] 是 URL
    url = call.args[0]
    assert url.startswith("https://www.toolhelper.cn/Http/DNSCheck?")
    assert "gts=" in url
    assert "gv=334" in url
    assert "r_=" in url


def test_toolhelper_resolver_raises_on_tag_0_no_records(mocker):
    """Tag=0 响应（无 DNS 记录）应抛 ResolverError。"""
    cfg = ResolverConfig(name="toolhelper", upstream_dns=[], extra={})
    mocker.patch(
        "dnsprobe.providers.toolhelper.requests.post",
        return_value=mocker.Mock(
            status_code=200,
            json=lambda: {"Total": 0, "Data": None, "Tag": 0, "Message": "未发现对应的 DNS 记录", "Description": None},
            raise_for_status=lambda: None,
        ),
    )
    r = ToolhelperResolver(cfg)
    with pytest.raises(ResolverError):
        r.resolve("nonexistent.example.invalid", cfg)


def test_toolhelper_resolver_raises_on_tag_minus_one_invalid_request(mocker):
    """Tag=-1 响应（非法访问）应抛 ResolverError。"""
    cfg = ResolverConfig(name="toolhelper", upstream_dns=[], extra={})
    mocker.patch(
        "dnsprobe.providers.toolhelper.requests.post",
        return_value=mocker.Mock(
            status_code=200,
            json=lambda: {"Total": 0, "Data": None, "Tag": -1, "Message": "非法访问", "Description": None},
            raise_for_status=lambda: None,
        ),
    )
    r = ToolhelperResolver(cfg)
    with pytest.raises(ResolverError):
        r.resolve("example.com", cfg)


def test_toolhelper_resolver_raises_on_http_failure(mocker):
    """HTTP 请求异常应抛 ResolverError。"""
    cfg = ResolverConfig(name="toolhelper", upstream_dns=[], extra={})
    mocker.patch(
        "dnsprobe.providers.toolhelper.requests.post",
        side_effect=requests.exceptions.ConnectionError(),
    )
    r = ToolhelperResolver(cfg)
    with pytest.raises(ResolverError):
        r.resolve("example.com", cfg)


def test_toolhelper_resolver_is_registered():
    from dnsprobe.providers.toolhelper import ToolhelperResolver  # fixture pop sys.modules 后本地重绑，保证 is 同一对象
    assert get("toolhelper") is ToolhelperResolver


def test_register_builtin_providers_adds_toolhelper_to_registry():
    """显式调用 register_builtin_providers() 后 _REGISTRY 含 toolhelper。"""
    _REGISTRY.pop("toolhelper", None)  # 先清理（防 fixture 残留）
    register_builtin_providers()
    assert "toolhelper" in _REGISTRY
    assert _REGISTRY["toolhelper"].__name__ == "ToolhelperResolver"


def test_register_builtin_providers_is_idempotent():
    """重复调用不抛错、不重复注册。"""
    register_builtin_providers()
    register_builtin_providers()
    # 同一 class object 仍在 _REGISTRY
    assert _REGISTRY["toolhelper"].__name__ == "ToolhelperResolver"
