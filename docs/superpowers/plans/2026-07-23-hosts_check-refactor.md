# hosts_check 重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 `hosts_check` 项目，将域名列表外置到 YAML、把 DNS 解析抽象为接口（`BaseResolver`）并通过 `plugins/` 目录支持第三方扩展，让用户在 `config.yml` 中选择启用哪些 provider，最后删除旧的 `DnsParse.py` / `DailyJob.py` 并改用 `python -m hosts_check` 作为统一入口。

**Architecture:** 单一 Python 包 `hosts_check/`。核心抽象是 `BaseResolver`，通过 `@register("name")` 装饰器 + `discover_plugins()` 扫描统一的注册机制覆盖内置 Provider（`Ip33Resolver`）与外部插件。YAML 配置驱动 provider 启用、上游 DNS 列表、可达性检测参数与输出路径。主流程 (`pipeline.py`) 串联：解析 → 保序去重 → 可达性检测 → 写 hosts.txt。

**Tech Stack:** Python 3.12+（GitHub Action 目标版本 3.12），`requests>=2.28`，`pyyaml>=6.0`（运行时）；`pytest>=7.0`，`pytest-mock>=3.10`（测试）。

## Global Constraints

- **Python 目标版本**：3.12（GitHub Action 用 `python-version: "3.12"`），但本地开发兼容 3.10+
- **配置文件**：`config.yml` + `domains.yml` 拆分；YAML 格式
- **日志格式**：stdout，三级标签：`[OK]` 成功 / `[!]` 警告 / `[×]` 失败
- **退出码**：0 = 至少一个域名有可用 IP；1 = 全部失败或配置错误
- **输出文件**：`hosts.txt`，结构以 `###start###` 与 `###end###` 包围，时间戳用 `datetime.datetime.now()` 格式 `%Y-%m-%d %H:%M:%S`
- **Provider 抽象**：`BaseResolver` 抽象类，`__init__(cfg: ResolverConfig)` 默认保存配置；`resolve(domain, cfg) -> list[str]` 抽象方法；`ResolverError` 自定义异常
- **注册机制**：`_REGISTRY` 字典 + `@register(name)` 装饰器 + `discover_plugins(dir)` 扫描 `.py` + `get(name)` 查表
- **依赖**：`requirements.txt` 列运行时；`requirements-dev.txt` 列测试
- **旧脚本**：`DnsParse.py` 与 `DailyJob.py` 在 Task 14 删除
- **GitHub Action**：`.github/workflows/run.yml` 改用 `python -m hosts_check`
- **Git 提交约定**：每完成一个 Task 立即 `git commit`，标题用 `feat:` / `test:` / `chore:` / `docs:` 前缀
- **单一 spec 来源**：所有任务必须可追溯到 `docs/superpowers/specs/2026-07-23-hosts_check-refactor-design.md`

---

## Task 1: 项目骨架与依赖

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `tests/__init__.py`
- Create: `hosts_check/__init__.py`
- Create: `hosts_check/__main__.py`（最简占位）

**Interfaces:**
- Consumes: 无
- Produces: `hosts_check` 包可被 `python -m hosts_check` 调用（即使空实现）；测试目录可通过 `pytest` 收集

- [ ] **Step 1: 创建 `tests/__init__.py`**

```python
# 让 tests/ 成为 package，便于 pytest 收集
```

- [ ] **Step 2: 创建 `hosts_check/__init__.py`**

```python
"""hosts_check: 通过 DNS 解析生成可用 hosts 文件。"""

__version__ = "0.1.0"
```

- [ ] **Step 3: 创建 `hosts_check/__main__.py`（占位）**

```python
"""python -m hosts_check 入口（占位，Task 9 替换为完整实现）。"""
import sys

if __name__ == "__main__":
    print("hosts_check package bootstrap OK")
    sys.exit(0)
```

- [ ] **Step 4: 创建 `requirements.txt`**

```
requests>=2.28
pyyaml>=6.0
```

- [ ] **Step 5: 创建 `requirements-dev.txt`**

```
-r requirements.txt
pytest>=7.0
pytest-mock>=3.10
```

- [ ] **Step 6: 安装依赖**

Run: `pip install -r requirements-dev.txt`
Expected: `Successfully installed ... requests ... pyyaml ... pytest ... pytest-mock ...`

- [ ] **Step 7: 验证 `python -m hosts_check`**

Run: `python -m hosts_check`
Expected: stdout 打印 `hosts_check package bootstrap OK`，退出码 0

- [ ] **Step 8: 验证 pytest 可发现 tests**

Run: `python -m pytest tests/ --collect-only -q`
Expected: `no tests ran` 或 `0 tests collected`（说明收集机制 OK），退出码 0 或 5

- [ ] **Step 9: 提交**

```bash
git add requirements.txt requirements-dev.txt hosts_check/__init__.py hosts_check/__main__.py tests/__init__.py
git commit -m "chore: scaffold hosts_check package skeleton"
```

---

## Task 2: `BaseResolver` 抽象 + `ResolverError`

**Files:**
- Create: `hosts_check/resolver.py`
- Create: `tests/test_resolver.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `class ResolverConfig`（dataclass，字段 `name: str`, `upstream_dns: list[str]`, `extra: dict`）
  - `class ResolverError(Exception)`
  - `class BaseResolver(ABC)`：`name: ClassVar[str]`，`__init__(cfg: ResolverConfig) -> None`（保存 `self.cfg = cfg`），`resolve(domain: str, cfg: ResolverConfig) -> list[str]` 抽象方法

- [ ] **Step 1: 写失败的测试 `tests/test_resolver.py`**

```python
from __future__ import annotations

import pytest

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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_resolver.py -v`
Expected: 全部 FAIL（`ModuleNotFoundError: No module named 'hosts_check.resolver'`）

- [ ] **Step 3: 实现 `hosts_check/resolver.py`**

```python
"""DNS resolver 抽象层。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar


@dataclass
class ResolverConfig:
    """单个 provider 实例的运行配置（来自 YAML 的 providers.<name> 节点）。"""

    name: str
    upstream_dns: list[str]
    extra: dict


class ResolverError(Exception):
    """解析失败时由具体 resolver 抛出。"""


class BaseResolver(ABC):
    """所有 DNS resolver 必须继承这个。"""

    name: ClassVar[str] = ""

    def __init__(self, cfg: ResolverConfig) -> None:
        self.cfg = cfg

    @abstractmethod
    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        """返回 A 记录 IP 列表。失败抛 ResolverError 或返回 []。"""
        ...
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `python -m pytest tests/test_resolver.py -v`
Expected: 5 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add hosts_check/resolver.py tests/test_resolver.py
git commit -m "feat: add BaseResolver abstraction and ResolverConfig"
```

---

## Task 3: 注册机制（`registry.py`）

**Files:**
- Create: `hosts_check/registry.py`
- Modify: `tests/test_resolver.py`（追加 `register` 相关测试）

**Interfaces:**
- Consumes: `BaseResolver`（Task 2）
- Produces:
  - `register(name: str) -> Callable` 装饰器
  - `discover_plugins(plugins_dir: Path) -> None` 扫描 `plugins_dir` 下所有非 `_` 开头的 `.py`，通过 `importlib.import_module("plugins." + stem)` 触发 `@register` 副作用
  - `get(name: str) -> type[BaseResolver]` 查表，未注册抛 `KeyError`
  - 全局变量 `_REGISTRY: dict[str, type[BaseResolver]]`

- [ ] **Step 1: 写失败的测试（追加到 `tests/test_resolver.py` 末尾）**

```python
from hosts_check.registry import register, get, discover_plugins, _REGISTRY


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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_resolver.py -v`
Expected: 新增 4 个测试 FAIL（`ModuleNotFoundError: No module named 'hosts_check.registry'`）

- [ ] **Step 3: 实现 `hosts_check/registry.py`**

```python
"""Resolver 注册表：装饰器 + 插件目录扫描。"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Callable

from hosts_check.resolver import BaseResolver

_REGISTRY: dict[str, type[BaseResolver]] = {}


def register(name: str) -> Callable[[type[BaseResolver]], type[BaseResolver]]:
    """把 Resolver 子类挂到全局注册表。"""

    def deco(cls: type[BaseResolver]) -> type[BaseResolver]:
        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return deco


def discover_plugins(plugins_dir: Path) -> None:
    """扫描 plugins_dir 下所有 .py，import 触发 @register 副作用。

    调用者需确保 `plugins_dir` 的父目录在 sys.path 上（通常通过 __main__.py
    在启动时 sys.path.insert(0, "."))。
    """
    for py in plugins_dir.glob("*.py"):
        if py.name.startswith("_"):
            continue
        importlib.import_module(f"plugins.{py.stem}")


def get(name: str) -> type[BaseResolver]:
    """按 name 查 Provider 类。未注册抛 KeyError。"""
    if name not in _REGISTRY:
        raise KeyError(f"resolver '{name}' not registered")
    return _REGISTRY[name]
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `python -m pytest tests/test_resolver.py -v`
Expected: 9 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add hosts_check/registry.py tests/test_resolver.py
git commit -m "feat: add resolver registry with @register and plugin discovery"
```

---

## Task 4: 配置加载（`config.py`）

**Files:**
- Create: `hosts_check/config.py`
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `class ProviderConfig`（dataclass）：`name: str`, `enabled: bool = True`, `upstream_dns: list[str] = []`, `extra: dict`（注：`extra` 缺省 `{}`）
  - `class OutputConfig`（dataclass）：`path: str = "hosts.txt"`, `keep_old_section: bool = True`
  - `class ReachabilityConfig`（dataclass）：`method: str = "http_head"`, `timeout: float = 5.0`
  - `class AppConfig`（dataclass）：`providers: list[ProviderConfig]`, `output: OutputConfig`, `reachability: ReachabilityConfig`, `domains: list[str]`
  - `load_config(config_path: Path) -> AppConfig`：加载 `config.yml` + `domains.yml`（默认 `config_path` 同目录下的 `domains.yml`），合并成一个 `AppConfig`

- [ ] **Step 1: 写失败的测试 `tests/test_config.py`**

```python
from __future__ import annotations

from pathlib import Path

import pytest

from hosts_check.config import (
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
        "providers:\n  - name: ip33\n",
    )
    _write(
        tmp_path / "domains.yml",
        "domains:\n  - a.example\n  - b.example\n",
    )

    cfg = load_config(tmp_path / "config.yml")

    assert isinstance(cfg, AppConfig)
    assert cfg.providers == [ProviderConfig(name="ip33")]
    assert cfg.domains == ["a.example", "b.example"]
    assert cfg.output == OutputConfig()
    assert cfg.reachability == ReachabilityConfig()


def test_load_config_enabled_defaults_true(tmp_path: Path):
    _write(
        tmp_path / "config.yml",
        "providers:\n  - name: ip33\n    upstream_dns: [1.1.1.1]\n",
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
        "providers:\n  - name: ip33\n    enabled: false\n",
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_config.py -v`
Expected: 6 个测试全部 FAIL（`ModuleNotFoundError: No module named 'hosts_check.config'`）

- [ ] **Step 3: 实现 `hosts_check/config.py`**

```python
"""加载 YAML 配置 + domains，统一为 AppConfig。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ProviderConfig:
    name: str
    enabled: bool = True
    upstream_dns: list[str] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class OutputConfig:
    path: str = "hosts.txt"
    keep_old_section: bool = True


@dataclass
class ReachabilityConfig:
    method: str = "http_head"
    timeout: float = 5.0


@dataclass
class AppConfig:
    providers: list[ProviderConfig]
    output: OutputConfig
    reachability: ReachabilityConfig
    domains: list[str]


def _load_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}


def _parse_providers(raw: list[dict[str, Any]] | None) -> list[ProviderConfig]:
    out: list[ProviderConfig] = []
    for item in raw or []:
        out.append(
            ProviderConfig(
                name=item["name"],
                enabled=item.get("enabled", True),
                upstream_dns=list(item.get("upstream_dns", []) or []),
                extra=dict(item.get("extra", {}) or {}),
            )
        )
    return out


def load_config(config_path: Path) -> AppConfig:
    """加载 config.yml + 同目录的 domains.yml，合并成 AppConfig。"""
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"config file not found: {config_path}")

    domains_path = config_path.parent / "domains.yml"
    if not domains_path.exists():
        raise FileNotFoundError(f"domains file not found: {domains_path}")

    cfg_raw = _load_yaml(config_path)
    dom_raw = _load_yaml(domains_path)

    return AppConfig(
        providers=_parse_providers(cfg_raw.get("providers")),
        output=OutputConfig(**(cfg_raw.get("output") or {})),
        reachability=ReachabilityConfig(**(cfg_raw.get("reachability") or {})),
        domains=list(dom_raw.get("domains", []) or []),
    )
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `python -m pytest tests/test_config.py -v`
Expected: 6 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add hosts_check/config.py tests/test_config.py
git commit -m "feat: add YAML config loader with AppConfig dataclass"
```

---

## Task 5: `Ip33Resolver`（内置 Provider）

**Files:**
- Create: `hosts_check/providers/__init__.py`
- Create: `hosts_check/providers/ip33.py`
- Modify: `tests/test_resolver.py`（追加 `Ip33Resolver` 测试）

**Interfaces:**
- Consumes: `BaseResolver`, `ResolverConfig`, `register`, `ResolverError`（Task 2-3）
- Produces:
  - `class Ip33Resolver(BaseResolver)`：`@register("ip33")` 装饰
  - `resolve(domain, cfg)` 策略：对 `cfg.upstream_dns` 逐个 POST `http://api.ip33.com/dns/resolver`（form: `domain`, `type=A`, `dns=<server>`），合并所有 IP 列表返回；任意一次失败抛 `ResolverError`

- [ ] **Step 1: 写失败的测试（追加到 `tests/test_resolver.py` 末尾）**

```python
from hosts_check.providers.ip33 import Ip33Resolver


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
    mocker.patch("hosts_check.providers.ip33.requests.post", side_effect=fake_responses)

    r = Ip33Resolver(cfg)
    assert r.resolve("example.com", cfg) == ["9.9.9.9", "8.8.8.8", "7.7.7.7"]


def test_ip33_resolver_raises_resolvererror_on_http_failure(mocker):
    cfg = ResolverConfig(name="ip33", upstream_dns=["1.1.1.1"], extra={})

    mocker.patch(
        "hosts_check.providers.ip33.requests.post",
        side_effect=RuntimeError("net down"),
    )

    r = Ip33Resolver(cfg)
    with pytest.raises(ResolverError):
        r.resolve("example.com", cfg)


def test_ip33_resolver_is_registered():
    assert get("ip33") is Ip33Resolver
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_resolver.py -v`
Expected: 新增 3 个测试 FAIL（`ModuleNotFoundError: No module named 'hosts_check.providers.ip33'`）

- [ ] **Step 3: 创建 `hosts_check/providers/__init__.py`**

```python
"""内置 resolver 实现。"""
```

- [ ] **Step 4: 实现 `hosts_check/providers/ip33.py`**

```python
"""调用 http://www.ip33.com/ 的接口解析域名。"""
from __future__ import annotations

import json
from typing import Any

import requests

from hosts_check.registry import register
from hosts_check.resolver import BaseResolver, ResolverConfig, ResolverError

_API = "http://api.ip33.com/dns/resolver"
_TIMEOUT = 10
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


@register("ip33")
class Ip33Resolver(BaseResolver):
    """通过 ip33.com HTTP 接口解析 A 记录。

    策略：对 cfg.upstream_dns 逐个查询并合并所有 IP 列表，
    不去重（去重由主流程统一处理）。
    """

    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        ips: list[str] = []
        for dns in cfg.upstream_dns:
            try:
                resp = requests.post(
                    _API,
                    data={"domain": domain, "type": "A", "dns": dns},
                    headers=_HEADERS,
                    timeout=_TIMEOUT,
                )
                payload: dict[str, Any] = json.loads(resp.text)
                ips.extend(record["ip"] for record in payload.get("record", []))
            except Exception as e:
                raise ResolverError(
                    f"ip33 resolve failed for {domain} via {dns}: {e}"
                ) from e
        return ips
```

- [ ] **Step 5: 跑测试，确认通过**

Run: `python -m pytest tests/test_resolver.py -v`
Expected: 12 个测试全部 PASS

- [ ] **Step 6: 提交**

```bash
git add hosts_check/providers/ tests/test_resolver.py
git commit -m "feat: add Ip33Resolver built-in provider"
```

---

## Task 6: `reachability.py` —— HTTP HEAD 测连通

**Files:**
- Create: `hosts_check/reachability.py`
- Create: `tests/test_reachability.py`

**Interfaces:**
- Consumes: `ReachabilityConfig`（Task 4）
- Produces:
  - `def check_ip_reachable(ip: str, domain: str, timeout: float) -> bool`：HTTP HEAD `http://<ip>`，Host header 设为 `domain`，2xx/3xx 视为可达
  - `def filter_reachable(ips: list[str], domain: str, cfg: ReachabilityConfig) -> list[str]`：批量过滤

- [ ] **Step 1: 写失败的测试 `tests/test_reachability.py`**

```python
from __future__ import annotations

import requests

from hosts_check.config import ReachabilityConfig
from hosts_check.reachability import check_ip_reachable, filter_reachable


def test_check_ip_reachable_true_on_2xx(mocker):
    mocker.patch(
        "hosts_check.reachability.requests.head",
        return_value=mocker.Mock(status_code=200),
    )
    assert check_ip_reachable("1.2.3.4", "example.com", timeout=5.0) is True


def test_check_ip_reachable_true_on_3xx(mocker):
    mocker.patch(
        "hosts_check.reachability.requests.head",
        return_value=mocker.Mock(status_code=301),
    )
    assert check_ip_reachable("1.2.3.4", "example.com", timeout=5.0) is True


def test_check_ip_reachable_false_on_4xx(mocker):
    mocker.patch(
        "hosts_check.reachability.requests.head",
        return_value=mocker.Mock(status_code=404),
    )
    assert check_ip_reachable("1.2.3.4", "example.com", timeout=5.0) is False


def test_check_ip_reachable_false_on_timeout(mocker):
    mocker.patch(
        "hosts_check.reachability.requests.head",
        side_effect=requests.exceptions.Timeout(),
    )
    assert check_ip_reachable("1.2.3.4", "example.com", timeout=5.0) is False


def test_check_ip_reachable_false_on_connection_error(mocker):
    mocker.patch(
        "hosts_check.reachability.requests.head",
        side_effect=requests.exceptions.ConnectionError(),
    )
    assert check_ip_reachable("1.2.3.4", "example.com", timeout=5.0) is False


def test_filter_reachable_keeps_only_responding_ips(mocker):
    responses = [
        mocker.Mock(status_code=200),  # reachable
        mocker.Mock(status_code=500),  # not reachable
        mocker.Mock(status_code=302),  # reachable
    ]
    mocker.patch(
        "hosts_check.reachability.requests.head",
        side_effect=responses,
    )
    cfg = ReachabilityConfig(method="http_head", timeout=5.0)
    result = filter_reachable(["1.1.1.1", "2.2.2.2", "3.3.3.3"], "example.com", cfg)
    assert result == ["1.1.1.1", "3.3.3.3"]
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_reachability.py -v`
Expected: 6 个测试全部 FAIL（`ModuleNotFoundError: No module named 'hosts_check.reachability'`）

- [ ] **Step 3: 实现 `hosts_check/reachability.py`**

```python
"""HTTP HEAD 测连通（迁移自 DailyJob.py:43-67）。"""
from __future__ import annotations

import requests

from hosts_check.config import ReachabilityConfig


def check_ip_reachable(ip: str, domain: str, timeout: float = 5.0) -> bool:
    """通过 HTTP HEAD 检查 IP 是否可达。

    使用 IP 直连，Host header 指明域名（用于虚拟主机场景）。
    2xx/3xx 视为可达。
    """
    try:
        response = requests.head(
            f"http://{ip}",
            headers={"Host": domain},
            timeout=timeout,
            allow_redirects=True,
        )
        return 200 <= response.status_code < 400
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        return False
    except Exception:
        return False


def filter_reachable(
    ips: list[str], domain: str, cfg: ReachabilityConfig
) -> list[str]:
    """过滤出可达的 IP，按原顺序保留。"""
    return [ip for ip in ips if check_ip_reachable(ip, domain, cfg.timeout)]
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `python -m pytest tests/test_reachability.py -v`
Expected: 6 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add hosts_check/reachability.py tests/test_reachability.py
git commit -m "feat: add reachability check via HTTP HEAD"
```

---

## Task 7: `writer.py` —— 生成 `hosts.txt`

**Files:**
- Create: `hosts_check/writer.py`
- Create: `tests/test_writer.py`

**Interfaces:**
- Consumes: `OutputConfig`（Task 4）
- Produces:
  - `def write_hosts_file(host_dict: dict[str, list[str]], cfg: OutputConfig, now: datetime | None = None) -> None`：把 `host_dict` 写入 `cfg.path`；格式与 `DailyJob.py:85-94` 一致；以 `###start###` 开头、以 `###最后更新时间:<time>###` + `###end###` 结尾（`now` 缺省=`datetime.now()`，用于测试固定时间戳）

- [ ] **Step 1: 写失败的测试 `tests/test_writer.py`**

```python
from __future__ import annotations

import datetime

from hosts_check.config import OutputConfig
from hosts_check.writer import write_hosts_file


def test_write_hosts_file_basic_format(tmp_path):
    cfg = OutputConfig(path=str(tmp_path / "hosts.txt"), keep_old_section=False)
    host_dict = {"a.example": ["1.1.1.1", "2.2.2.2"], "b.example": ["3.3.3.3"]}
    fixed = datetime.datetime(2026, 7, 23, 12, 0, 0)

    write_hosts_file(host_dict, cfg, now=fixed)

    content = (tmp_path / "hosts.txt").read_text(encoding="utf-8")
    expected = (
        "###start###\n"
        "1.1.1.1\ta.example\n"
        "2.2.2.2\ta.example\n"
        "3.3.3.3\tb.example\n"
        "###最后更新时间:2026-07-23 12:00:00###\n"
        "###end###\n"
    )
    assert content == expected


def test_write_hosts_file_empty_dict(tmp_path):
    cfg = OutputConfig(path=str(tmp_path / "hosts.txt"), keep_old_section=False)
    fixed = datetime.datetime(2026, 1, 1, 0, 0, 0)

    write_hosts_file({}, cfg, now=fixed)

    content = (tmp_path / "hosts.txt").read_text(encoding="utf-8")
    expected = (
        "###start###\n"
        "###最后更新时间:2026-01-01 00:00:00###\n"
        "###end###\n"
    )
    assert content == expected


def test_write_hosts_file_keep_old_section_strips_existing(tmp_path):
    hosts_file = tmp_path / "hosts.txt"
    hosts_file.write_text(
        "# user custom line 1\n"
        "# user custom line 2\n"
        "###start###\n"
        "9.9.9.9\told.example\n"
        "###最后更新时间:2020-01-01 00:00:00###\n"
        "###end###\n",
        encoding="utf-8",
    )

    cfg = OutputConfig(path=str(hosts_file), keep_old_section=True)
    host_dict = {"fresh.example": ["5.5.5.5"]}
    fixed = datetime.datetime(2026, 7, 23, 12, 0, 0)

    write_hosts_file(host_dict, cfg, now=fixed)

    content = hosts_file.read_text(encoding="utf-8")
    assert content.startswith("# user custom line 1\n# user custom line 2\n")
    assert "9.9.9.9" not in content
    assert "5.5.5.5\tfresh.example\n" in content
    assert "###最后更新时间:2026-07-23 12:00:00###" in content


def test_write_hosts_file_no_keep_old_section_writes_only_new(tmp_path):
    hosts_file = tmp_path / "hosts.txt"
    hosts_file.write_text(
        "###start###\n"
        "9.9.9.9\told.example\n"
        "###last###\n"
    )

    cfg = OutputConfig(path=str(hosts_file), keep_old_section=False)
    host_dict = {"fresh.example": ["5.5.5.5"]}
    fixed = datetime.datetime(2026, 7, 23, 12, 0, 0)

    write_hosts_file(host_dict, cfg, now=fixed)

    content = hosts_file.read_text(encoding="utf-8")
    assert "9.9.9.9" not in content
    assert content.startswith("###start###\n")
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_writer.py -v`
Expected: 4 个测试全部 FAIL（`ModuleNotFoundError: No module named 'hosts_check.writer'`）

- [ ] **Step 3: 实现 `hosts_check/writer.py`**

```python
"""生成 hosts.txt（迁移自 DailyJob.py:85-94 与 DnsParse.py:66-105）。"""
from __future__ import annotations

import datetime
from pathlib import Path

from hosts_check.config import OutputConfig

_START = "###start###"
_END = "###end###"
_TIME_PREFIX = "###最后更新时间:"
_TIME_SUFFIX = "###"


def _format_now(now: datetime.datetime) -> str:
    return now.strftime("%Y-%m-%d %H:%M:%S")


def _strip_old_section(content: str) -> str:
    """剥离 ###start### 与 ###end### 之间的全部内容，保留其外的所有行。"""
    lines = content.splitlines(keepends=True)
    out: list[str] = []
    in_section = False
    for line in lines:
        if _START in line:
            in_section = True
            continue
        if _END in line:
            in_section = False
            continue
        if not in_section:
            out.append(line)
    return "".join(out)


def _render_body(host_dict: dict[str, list[str]], now: datetime.datetime) -> str:
    lines = [_START + "\n"]
    for host, ips in host_dict.items():
        for ip in ips:
            lines.append(f"{ip}\t{host}\n")
    lines.append(f"{_TIME_PREFIX}{_format_now(now)}{_TIME_SUFFIX}\n")
    lines.append(_END + "\n")
    return "".join(lines)


def write_hosts_file(
    host_dict: dict[str, list[str]],
    cfg: OutputConfig,
    now: datetime.datetime | None = None,
) -> None:
    """把 host_dict 写入 cfg.path。

    若 cfg.keep_old_section=True 且文件已存在，先剥离旧 ###start###/###end### 段。
    """
    if now is None:
        now = datetime.datetime.now()

    path = Path(cfg.path)
    prefix = ""
    if cfg.keep_old_section and path.exists():
        prefix = _strip_old_section(path.read_text(encoding="utf-8"))

    body = _render_body(host_dict, now)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prefix + body, encoding="utf-8")
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `python -m pytest tests/test_writer.py -v`
Expected: 4 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add hosts_check/writer.py tests/test_writer.py
git commit -m "feat: add hosts.txt writer with keep_old_section support"
```

---

## Task 8: `pipeline.py` —— 主流程

**Files:**
- Create: `hosts_check/pipeline.py`
- Create: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `AppConfig`（Task 4）、`BaseResolver`/`get()`/`discover_plugins()`（Task 2-3）、`filter_reachable`（Task 6）、`write_hosts_file`（Task 7）
- Produces:
  - `def run(config: AppConfig, plugins_dir: Path | None = None) -> int`：完整流程；返回退出码（0=至少一个有结果，1=全部失败）

- [ ] **Step 1: 写失败的测试 `tests/test_pipeline.py`**

```python
from __future__ import annotations

import datetime
from pathlib import Path

from hosts_check.config import (
    AppConfig,
    OutputConfig,
    ProviderConfig,
    ReachabilityConfig,
)
from hosts_check.pipeline import run


def _make_cfg(tmp_path: Path, domains: list[str]) -> AppConfig:
    return AppConfig(
        providers=[ProviderConfig(name="fake", upstream_dns=["1.1.1.1"])],
        output=OutputConfig(path=str(tmp_path / "hosts.txt"), keep_old_section=False),
        reachability=ReachabilityConfig(method="http_head", timeout=5.0),
        domains=domains,
    )


def test_pipeline_returns_zero_when_at_least_one_domain_works(tmp_path, mocker):
    from hosts_check import registry

    class FakeResolver:
        name = "fake"

        def __init__(self, cfg):
            self.cfg = cfg

        def resolve(self, domain, cfg):
            return ["1.1.1.1"]

    registry._REGISTRY["fake"] = FakeResolver
    mocker.patch(
        "hosts_check.pipeline.filter_reachable",
        return_value=["1.1.1.1"],
    )

    cfg = _make_cfg(tmp_path, ["a.example", "b.example"])
    rc = run(cfg, plugins_dir=None)

    assert rc == 0
    content = (tmp_path / "hosts.txt").read_text(encoding="utf-8")
    assert "1.1.1.1\ta.example" in content
    assert "1.1.1.1\tb.example" in content


def test_pipeline_returns_one_when_all_domains_fail(tmp_path, mocker):
    from hosts_check import registry

    class FakeResolver:
        name = "fake"

        def __init__(self, cfg):
            self.cfg = cfg

        def resolve(self, domain, cfg):
            return []

    registry._REGISTRY["fake"] = FakeResolver
    mocker.patch("hosts_check.pipeline.filter_reachable", return_value=[])

    cfg = _make_cfg(tmp_path, ["a.example"])
    rc = run(cfg, plugins_dir=None)

    assert rc == 1


def test_pipeline_skips_disabled_providers(tmp_path, mocker):
    from hosts_check import registry

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
        "hosts_check.pipeline.filter_reachable",
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
    from hosts_check import registry
    from hosts_check.resolver import ResolverError

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
        "hosts_check.pipeline.filter_reachable",
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: 4 个测试全部 FAIL（`ModuleNotFoundError: No module named 'hosts_check.pipeline'`）

- [ ] **Step 3: 实现 `hosts_check/pipeline.py`**

```python
"""主流程：解析 → 去重 → 可达性检测 → 写 hosts.txt。"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from hosts_check.config import AppConfig
from hosts_check.reachability import filter_reachable
from hosts_check.registry import discover_plugins, get
from hosts_check.resolver import BaseResolver, ResolverConfig, ResolverError
from hosts_check.writer import write_hosts_file


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


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run_from_config())
```

- [ ] **Step 4: 跑测试，确认通过**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: 4 个测试全部 PASS

- [ ] **Step 5: 提交**

```bash
git add hosts_check/pipeline.py tests/test_pipeline.py
git commit -m "feat: add pipeline orchestrating resolve-dedupe-check-write"
```

---

## Task 9: `__main__.py` —— 入口

**Files:**
- Modify: `hosts_check/__main__.py`（替换为完整实现）

**Interfaces:**
- Consumes: `load_config`（Task 4）、`run`（Task 8）
- Produces: CLI 入口，`--config` / `--domains` 参数，sys.path 注入项目根（让 `plugins.xxx` 可 import），异常兜底 + 友好错误 + 非零退出码

- [ ] **Step 1: 替换 `hosts_check/__main__.py`**

完整内容：

```python
"""python -m hosts_check 入口。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hosts_check.config import load_config
from hosts_check.pipeline import run


_DEFAULT_CONFIG = "config.yml"
_DEFAULT_DOMAINS = "domains.yml"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="hosts_check")
    p.add_argument(
        "--config",
        default=_DEFAULT_CONFIG,
        help="配置文件路径（默认 config.yml）",
    )
    p.add_argument(
        "--domains",
        default=None,
        help="域名文件路径（默认与 config 同目录下的 domains.yml）",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    # 让 plugins.<stem> 可被 import
    cwd = Path.cwd()
    if str(cwd) not in sys.path:
        sys.path.insert(0, str(cwd))

    try:
        config = load_config(Path(args.config))
    except FileNotFoundError as e:
        print(f"[×] {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[×] 配置解析失败: {e}", file=sys.stderr)
        return 1

    plugins_dir = cwd / "plugins"
    if not plugins_dir.exists():
        plugins_dir = None

    try:
        return run(config, plugins_dir=plugins_dir)
    except KeyError as e:
        print(f"[×] {e}", file=sys.stderr)
        print(
            "[!] 已注册的 provider: "
            + ", ".join(sorted(_registered_names()))
            or "(无)",
            file=sys.stderr,
        )
        return 1


def _registered_names() -> list[str]:
    from hosts_check.registry import _REGISTRY

    return list(_REGISTRY.keys())


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: 跑全部测试，确保不破坏**

Run: `python -m pytest tests/ -v`
Expected: 全部测试 PASS（约 27 个）

- [ ] **Step 3: 烟测 CLI（暂时无 config.yml，应 FileNotFoundError 但退出码 1）**

Run: `python -m hosts_check`
Expected: 退出码 1，stderr 含 `[×] config file not found:`（或 `domains file not found:`）

- [ ] **Step 4: 提交**

```bash
git add hosts_check/__main__.py
git commit -m "feat: add CLI entrypoint with --config and --domains options"
```

---

## Task 10: 配置文件与域名文件

**Files:**
- Create: `config.yml`
- Create: `domains.yml`

**Interfaces:**
- Consumes: `load_config`（Task 4）
- Produces: 默认配置文件，启用 `ip33` provider，上游 DNS 列表与原 `DailyJob.py:36` 一致；域名列表与原 `DailyJob.py:14-34` 逐字一致

- [ ] **Step 1: 创建 `config.yml`**

```yaml
# 启用的 provider 列表（按顺序使用；name 必须是被 @register 注册过的）
providers:
  - name: ip33
    enabled: true
    upstream_dns:
      - 156.154.70.1
      - 208.67.222.222
    extra:
      timeout: 10

# 写入目标
output:
  path: hosts.txt
  keep_old_section: true

# 可达性检测
reachability:
  method: http_head
  timeout: 5.0
```

- [ ] **Step 2: 创建 `domains.yml`**

```yaml
domains:
  - api.themoviedb.org
  - image.tmdb.org
  - www.themoviedb.org
  - alive.github.com
  - api.github.com
  - assets-cdn.github.com
  - avatars.githubusercontent.com
  - avatars0.githubusercontent.com
  - avatars1.githubusercontent.com
  - avatars2.githubusercontent.com
  - avatars3.githubusercontent.com
  - avatars4.githubusercontent.com
  - avatars5.githubusercontent.com
  - camo.githubusercontent.com
  - central.github.com
  - cloud.githubusercontent.com
  - codeload.githubusercontent.com
  - collector.github.com
  - desktop.githubusercontent.com
  - favicons.githubusercontent.com
  - gist.github.com
  - github-cloud.s3.amazonaws.com
  - github-com.s3.amazonaws.com
  - github-production-release-asset-2e65be.s3.amazonaws.com
  - github-production-repository-file-5c1aeb.s3.amazonaws.com
  - github-production-user-asset-6210df.s3.amazonaws.com
  - github.blog
  - github.com
  - github.community
  - github.githubassets.com
  - github.global.ssl.fastly.net
  - github.io
  - github.map.fastly.net
  - githubstatus.com
  - live.github.com
  - media.githubusercontent.com
  - objects.githubusercontent.com
  - pipelines.actions.githubusercontent.com
  - raw.githubusercontent.com
  - user-images.githubusercontent.com
  - vscode.dev
  - education.github.com
  - private-user-images.githubusercontent.com
```

- [ ] **Step 3: 验证 `load_config` 能跑通**

Run: `python -c "from hosts_check.config import load_config; from pathlib import Path; c = load_config(Path('config.yml')); print('providers:', [p.name for p in c.providers], 'domains:', len(c.domains))"`
Expected: `providers: ['ip33'] domains: 43`

- [ ] **Step 4: 跑全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add config.yml domains.yml
git commit -m "feat: add default config.yml and domains.yml migrated from DailyJob"
```

---

## Task 11: `plugins/` 模板

**Files:**
- Create: `plugins/example_resolver.py`
- Create: `plugins/README.md`

**Interfaces:**
- Consumes: `BaseResolver`, `ResolverConfig`, `register`, `ResolverError`（Task 2-3）
- Produces: 一个**可工作**的示例 plugin（不用真实网络，docstring 写明如何替换）和 `plugins/README.md` 教程

- [ ] **Step 1: 创建 `plugins/example_resolver.py`**

```python
"""Example resolver plugin.

演示如何写一个 DNS resolver plugin。要切换到真实协议，把
``resolve()` 里的循环换成 HTTP/DoH/socket/dig 子进程调用即可。

启用方式：在 config.yml 的 providers 列表中添加：

    - name: example
      enabled: true
      upstream_dns:
        - 8.8.8.8
      extra: {}
"""
from __future__ import annotations

from hosts_check.registry import register
from hosts_check.resolver import BaseResolver, ResolverConfig, ResolverError


@register("example")
class ExampleResolver(BaseResolver):
    """示例 resolver：直接返回 cfg.extra 里的固定 IP 列表（仅用于演示）。"""

    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        ips = cfg.extra.get("fake_ips")
        if not ips:
            raise ResolverError(
                "example resolver requires cfg.extra['fake_ips'] to be set"
            )
        return list(ips)
```

- [ ] **Step 2: 创建 `plugins/README.md`**

```markdown
# Plugins

本目录用于放置第三方 DNS resolver 扩展。

## 编写一个 plugin

1. 在本目录下创建 `my_resolver.py`（文件名以下划线开头会被忽略）
2. 继承 `hosts_check.resolver.BaseResolver`
3. 用 `@register("name")` 装饰你的类
4. 实现 `resolve(domain, cfg) -> list[str]`
5. 在 `config.yml` 的 `providers` 列表中添加这个 name

最小模板：

```python
from hosts_check.registry import register
from hosts_check.resolver import BaseResolver, ResolverConfig, ResolverError


@register("my_resolver")
class MyResolver(BaseResolver):
    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        # cfg.upstream_dns: list[str] —— 上游 DNS 服务器列表
        # cfg.extra: dict —— 你的私有参数
        # 失败抛 ResolverError，成功返回 IP 列表
        ...
```

启动时 `python -m hosts_check` 会自动扫描本目录下所有 `.py` 文件并 import，触发 `@register` 副作用。
```

- [ ] **Step 3: 验证 plugin 可被扫描（用 mock plugins_dir 测试已在 Task 3 覆盖）**

Run: `python -c "import sys; from pathlib import Path; sys.path.insert(0, '.'); from hosts_check.registry import discover_plugins, get; discover_plugins(Path('plugins')); print('registered:', sorted(__import__('hosts_check.registry', fromlist=['_REGISTRY'])._REGISTRY.keys()))"`
Expected: 包含 `ip33` 和 `example`

- [ ] **Step 4: 跑全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add plugins/example_resolver.py plugins/README.md
git commit -m "feat: add plugins/ template and example resolver"
```

---

## Task 12: 修改 GitHub Action workflow

**Files:**
- Modify: `.github/workflows/run.yml`

**Interfaces:**
- Consumes: `python -m hosts_check`（Task 9）
- Produces: workflow 文件仍然每天 16:00 UTC + 手动 `workflow_dispatch` 触发，但执行命令改为 `python -m hosts_check`，并安装新依赖 `pyyaml`

- [ ] **Step 1: 替换 `.github/workflows/run.yml`**

完整内容：

```yaml
name: Daily Ping

on:
  schedule:
    - cron: "0 16 * * *"
  workflow_dispatch:

jobs:
  ping:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run daily job
        run: python -m hosts_check

      - name: Configure SSH and push
        env:
          SSH_PRIVATE_KEY: ${{ secrets.SSH_PRIVATE_KEY }}
        run: |
          mkdir -p ~/.ssh
          echo "$SSH_PRIVATE_KEY" > ~/.ssh/id_rsa
          chmod 600 ~/.ssh/id_rsa
          ssh-keyscan github.com >> ~/.ssh/known_hosts
          git config user.name "Daily Job"
          git config user.email "git@daily.com"
          git remote set-url origin git@github.com:ChenXinBest/hosts_check.git
          git add hosts.txt
          git diff --staged --quiet || git commit -m "chore: update hosts $(date +%Y-%m-%d)"
          git push
```

- [ ] **Step 2: 验证 YAML 语法**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/run.yml')); print('OK')"`
Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add .github/workflows/run.yml
git commit -m "chore: switch GitHub Action to python -m hosts_check"
```

---

## Task 13: 重写 README

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: 无
- Produces: 保留原 `HOST每日更新` 链接（用户获取 hosts 的契约不变），新增项目说明 + "如何加 Provider"章节

- [ ] **Step 1: 替换 `README.md`**

完整内容：

```markdown
# hosts_check

解析 TMDB / GitHub 系列域名的可用 IP，生成 `hosts.txt`，绕过 DNS 污染。

## 使用

- 直接使用 hosts： 复制 [HOST每日更新](https://raw.githubusercontent.com/ChenXinBest/hosts_check/master/hosts.txt) 到你的 hosts 文件
- 手动运行： 在仓库根目录执行 `python -m hosts_check`（需先 `pip install -r requirements.txt`）

## 配置文件

- `config.yml` —— 启用哪些 provider、每个 provider 的上游 DNS、输出与可达性参数
- `domains.yml` —— 待解析的域名列表

修改 `domains.yml` 即可定制自己的域名清单。

## 添加自定义 Provider

在 `plugins/` 目录下新建 `.py` 文件，继承 `BaseResolver` 并用 `@register("name")` 装饰：

```python
from hosts_check.registry import register
from hosts_check.resolver import BaseResolver, ResolverConfig, ResolverError


@register("my_resolver")
class MyResolver(BaseResolver):
    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        # cfg.upstream_dns: list[str] —— 上游 DNS 服务器列表
        # cfg.extra: dict —— 你的私有参数
        # ...
        return ["1.2.3.4"]
```

然后在 `config.yml` 中启用：

```yaml
providers:
  - name: my_resolver
    enabled: true
    upstream_dns:
      - 8.8.8.8
    extra: {}
```

详见 `plugins/README.md`。
```

- [ ] **Step 2: 提交**

```bash
git add README.md
git commit -m "docs: rewrite README with provider extension guide"
```

---

## Task 14: 删除旧脚本

**Files:**
- Delete: `DnsParse.py`
- Delete: `DailyJob.py`

**Interfaces:**
- Consumes: 无
- Produces: 仓库仅保留新结构

- [ ] **Step 1: 删除 `DnsParse.py`**

Run: `git rm DnsParse.py`
Expected: `rm 'DnsParse.py'`

- [ ] **Step 2: 删除 `DailyJob.py`**

Run: `git rm DailyJob.py`
Expected: `rm 'DailyJob.py'`

- [ ] **Step 3: 验证目录结构**

Run: `Get-ChildItem -Force` (Windows) 或 `ls -la` (Linux)
Expected: 不再含 `DnsParse.py` 与 `DailyJob.py`；含 `hosts_check/`、`plugins/`、`tests/`、`config.yml`、`domains.yml`、`requirements.txt`、`requirements-dev.txt`

- [ ] **Step 4: 跑全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git commit -m "chore: remove obsolete DnsParse.py and DailyJob.py"
```

---

## Task 15: 端到端验证

**Files:**
- 无新文件

**Interfaces:**
- Consumes: 全部前述任务
- Produces: 验收标准 1-5 全部通过

- [ ] **Step 1: 跑全部测试**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS（约 27 个）

- [ ] **Step 2: 验证 CLI 启动正常**

Run: `python -c "import sys; sys.path.insert(0, '.'); from hosts_check.config import load_config; from hosts_check.pipeline import run; from pathlib import Path; cfg = load_config(Path('config.yml')); print('config OK, providers:', [p.name for p in cfg.providers], 'domains:', len(cfg.domains))"`
Expected: `config OK, providers: ['ip33'] domains: 43`

- [ ] **Step 3: 验证 plugin 加载机制**

Run: `python -c "import sys; sys.path.insert(0, '.'); from pathlib import Path; from hosts_check.registry import discover_plugins, _REGISTRY; discover_plugins(Path('plugins')); print('registered:', sorted(_REGISTRY.keys()))"`
Expected: 包含 `ip33` 与 `example`

- [ ] **Step 4: 验证 import 路径干净**

Run: `python -c "from hosts_check import resolver, registry, config, pipeline, reachability, writer; from hosts_check.providers import ip33; print('all imports OK')"`
Expected: `all imports OK`

- [ ] **Step 5: 验证 GitHub Action workflow YAML 合法**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/run.yml')); print('OK')"`
Expected: `OK`

- [ ] **Step 6: 手动运行 `python -m hosts_check`（可选；需网络）**

Run: `python -m hosts_check`
Expected: 退出码 0 或 1（网络环境而定）；输出 `hosts.txt` 结构合法（`###start###` + `###end###` 包裹）

- [ ] **Step 7: 提交（如有未提交变更）**

```bash
git status
# 若有变更：
git add -A
git commit -m "chore: end-to-end verification cleanup"
```

---

## 自查报告

### 1. Spec 覆盖

| Spec 章节 | 覆盖任务 |
|---|---|
| §1 项目结构 | Task 1（骨架）、Task 10（配置）、Task 11（plugins 模板） |
| §2 核心抽象 | Task 2（BaseResolver）、Task 3（registry）、Task 5（Ip33Resolver） |
| §3 配置文件 & 域名文件 | Task 4（config.py）、Task 10（config.yml + domains.yml） |
| §4 主流程 | Task 8（pipeline.py）、Task 9（__main__.py） |
| §5 错误处理 | Task 4（FileNotFoundError）、Task 5（ResolverError）、Task 8（异常隔离）、Task 9（友好错误 + 退出码） |
| §6 测试 | Task 2-8 各自单测 |
| §7 迁移与删除 | Task 13（README）、Task 14（删除旧脚本）、Task 12（workflow） |
| §9 验收标准 | Task 15 端到端验证 |

无遗漏。

### 2. 占位符扫描

无 TBD / TODO / "implement later" / "类似 Task N" 类占位符。

### 3. 类型一致性复核

- `BaseResolver.__init__(cfg: ResolverConfig)` —— Task 2 定义，Task 5（Ip33Resolver 不重写）、Task 8（pipeline 用 `cls(cfg)`）一致使用
- `ResolverConfig{name, upstream_dns, extra}` —— Task 2 定义，Task 4（解析用）、Task 5（Ip33Resolver 读）、Task 8（pipeline 构造）一致
- `AppConfig{providers, output, reachability, domains}` —— Task 4 定义，Task 8 接收，Task 9 通过 `load_config` 传入
- `ProviderConfig{name, enabled, upstream_dns, extra}` —— Task 4 定义，Task 8 使用 `p.enabled` / `p.upstream_dns` / `p.extra` / `p.name`
- `OutputConfig{path, keep_old_section}` —— Task 4 定义，Task 7 接收 `cfg.path` / `cfg.keep_old_section`
- `ReachabilityConfig{method, timeout}` —— Task 4 定义，Task 6 接收 `cfg.timeout`
- `register(name)` / `discover_plugins(dir)` / `get(name)` —— Task 3 定义，Task 5（Ip33Resolver 用 `@register`）、Task 8（pipeline 用 `discover_plugins` + `get`）、Task 11（example plugin 用 `@register`）一致
- `resolver.resolve(domain, cfg) -> list[str]` —— Task 2 定义，Task 5/8/11 一致
- `writers.py` 的 `write_hosts_file(host_dict, cfg, now=None)` 签名 —— Task 7 定义，Task 8 调用一致

无类型不一致。
