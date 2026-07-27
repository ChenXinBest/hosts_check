# hosts_check 整理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `hosts_check` 项目从 `hosts_check/`（仓库根下的包，与项目名同名）迁移到 `src/dnsprobe/`（src 布局，包名与项目名解耦），同时把内置 ip33 升级到新 API、消除 side-effect import、拆分 test_main/test_cli、重写 README。

**Architecture:** 通过 `git mv` 整体重命名包目录到 `src/dnsprobe/`，批量替换所有 `from hosts_check` 为 `from dnsprobe`，新增 `pyproject.toml` 让 `pip install -e .` 后 `dnsprobe` 命令可用。新增 `_bootstrap.register_builtin_providers()` 显式替代散落的 side-effect import。重写内置 ip33 用新 API endpoint `https://www.ip33.com/api/ip/search`（HTTPS + `s=<domain>` 参数 + `type=3/4` 响应协议）。所有改动保持 48+ 测试 PASS。

**Tech Stack:** Python 3.10+（GitHub Action 3.12），`requests>=2.28`、`pyyaml>=6.0`、`pytest>=7.0`、`pytest-mock>=3.10`。新增 `pyproject.toml` 用 setuptools 后端。

## Global Constraints

- 仓库名 `hosts_check`，包名 `dnsprobe`，二者**严格解耦**（spec §1）
- src 布局：`src/dnsprobe/` 作为 Python 包；`pyproject.toml` 用 `[tool.setuptools.packages.find]` `where=["src"]`（spec §5）
- 提交 prefix 严格用 `feat:` / `test:` / `chore:` / `docs:` / `fix:`（沿用现有约定）
- 所有 import 字符串 `from hosts_check` / `import hosts_check` 改为 `from dnsprobe` / `import dnsprobe`
- 内置 ip33 endpoint `https://www.ip33.com/api/ip/search`（spec §3.1）
- ip33 新协议 Form 参数仅 `s=<domain>`（spec §3.1）—— 不再传 `dns=`
- ip33 必带 Headers：`User-Agent`、`Origin: https://www.ip33.com`、`Referer: https://www.ip33.com/`、`X-Requested-With: XMLHttpRequest`（spec §3.2）
- ip33 响应 `type=3` 为成功（含 `ips[*].ip`），`type=4` 为失败（spec §3.1）
- `register_builtin_providers()` 必须在 `pipeline._build_resolver_instances()` 与 `__main__.main()` 中显式调用（spec §2.3 / §2.4）
- `tests/test_main.py` 是 argparse + main() 单元测试；`tests/test_cli.py` 是 subprocess 集成测试（spec §4.1 / §4.2）
- 全部既有 48 个测试在迁移后仍需 PASS，Task 3 / Task 4 按 spec §3.4 重写 6 个 ip33 测试为 4 新 + 1 保留

---

## Task 1: 包结构迁移到 src/dnsprobe + pyproject.toml

**Files:**
- Move: `hosts_check/` → `src/dnsprobe/`（含 `__init__.py`、`__main__.py`、`config.py`、`resolver.py`、`registry.py`、`providers/__init__.py`、`providers/ip33.py`、`pipeline.py`、`reachability.py`、`writer.py`）
- Move: `plugins/example_resolver.py`（保持 plugins/ 顶层；只改 import 字符串）
- Modify: 所有 `tests/*.py`（替换 import 字符串）
- Create: `pyproject.toml`
- Create: `src/dnsprobe/__init__.py`（重置 `__version__ = "0.1.0"`）

**Interfaces:**
- Consumes: 无
- Produces: `import dnsprobe` / `from dnsprobe.providers.ip33 import Ip33Resolver` / `python -m dnsprobe` 工作

- [ ] **Step 1: 创建 src 目录并 git mv hosts_check → src/dnsprobe**

```bash
mkdir src
git mv hosts_check src/dnsprobe
git status --short
```
Expected: 看到 `R` 状态的重命名（git 自动检测），例如 `hosts_check/__init__.py` → `src/dnsprobe/__init__.py`。

- [ ] **Step 2: 批量替换所有 import 字符串**

PowerShell 命令（在仓库根）：
```powershell
$files = Get-ChildItem -Recurse -Include *.py -Exclude "*__pycache__*" -Path . 
foreach ($f in $files) {
    $content = Get-Content $f.FullName -Raw
    $new = $content -replace 'from hosts_check', 'from dnsprobe' -replace 'import hosts_check', 'import dnsprobe'
    if ($new -ne $content) {
        Set-Content -LiteralPath $f.FullName -Value $new -NoNewline
        Write-Host "Updated: $($f.FullName)"
    }
}
```
Expected: 列出 `src/dnsprobe/__init__.py`、`src/dnsprobe/__main__.py` 等所有 .py；以及 `tests/test_*.py`、`plugins/example_resolver.py`。

- [ ] **Step 3: 验证替换结果**

```bash
grep -rn "hosts_check" --include="*.py" --exclude-dir=__pycache__ --exclude-dir=.git .
```
Expected: **无输出**（所有 `hosts_check` 字面都已替换）。

- [ ] **Step 4: 创建 `pyproject.toml`**

完整内容：

```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "dnsprobe"
version = "0.1.0"
description = "Resolve DNS and generate hosts.txt, pluggable via plugins"
requires-python = ">=3.10"
dependencies = [
    "requests>=2.28",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.0", "pytest-mock>=3.10"]

[project.scripts]
dnsprobe = "dnsprobe.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 5: 验证 import 与 CLI 启动**

```bash
python -c "import dnsprobe; print('version:', dnsprobe.__version__)"
python -m dnsprobe --help
```
Expected: 第一行输出 `version: 0.1.0`；第二行 argparse help 文本。

- [ ] **Step 6: 跑全部既有测试**

```bash
python -m pytest tests/ -q
```
Expected: **48 passed**（重构未改逻辑，测试不应破）。

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "refactor: rename package hosts_check to dnsprobe under src/ layout"
```

---

## Task 2: side-effect import 重构为 `_bootstrap.register_builtin_providers()`

**Files:**
- Create: `src/dnsprobe/_bootstrap.py`
- Modify: `src/dnsprobe/providers/__init__.py`（清空）
- Modify: `src/dnsprobe/pipeline.py`（删 side-effect import + 加 bootstrap 调用）
- Modify: `src/dnsprobe/__main__.py`（加 bootstrap 调用）
- Modify: `tests/test_resolver.py`（加 1 个测试覆盖 register_builtin_providers）

**Interfaces:**
- Consumes: `dnsprobe.registry._REGISTRY`（已有）
- Produces: `dnsprobe._bootstrap.register_builtin_providers() -> None`（幂等）

- [ ] **Step 1: 写失败测试（追加 `tests/test_resolver.py` 末尾）**

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

```bash
python -m pytest tests/test_resolver.py::test_register_builtin_providers_adds_ip33_to_registry tests/test_resolver.py::test_register_builtin_providers_is_idempotent -v
```
Expected: 2 FAILED（`ModuleNotFoundError: No module named 'dnsprobe._bootstrap'`）。

- [ ] **Step 3: 创建 `src/dnsprobe/_bootstrap.py`**

完整内容：

```python
"""显式注册内置 provider。

避免散落的 side-effect import：在 pipeline.run() / __main__.main() 入口显式调用
register_builtin_providers()，让内置 ip33 注册进 _REGISTRY。幂等。
"""
from __future__ import annotations


def register_builtin_providers() -> None:
    """触发内置 provider 的 @register 副作用。幂等。"""
    from dnsprobe.providers import ip33  # noqa: F401  # 触发 @register("ip33")
```

- [ ] **Step 4: 清空 `src/dnsprobe/providers/__init__.py`**

完整内容：

```python
"""内置 resolver 实现。"""
# 故意为空：内置 provider 通过 dnsprobe._bootstrap.register_builtin_providers() 显式 import
```

- [ ] **Step 5: 改 `src/dnsprobe/pipeline.py` —— 删除 side-effect import + 加 bootstrap 调用**

在 `src/dnsprobe/pipeline.py` 顶部 import 区，找到现在的：
```python
import hosts_check.providers  # noqa: F401  # 触发 @register("ip33") 副作用
```

（迁移后已变为 `import dnsprobe.providers`）

**删除这一行**。

然后在顶部 import 区加入：
```python
from dnsprobe._bootstrap import register_builtin_providers
```

并在 `_build_resolver_instances()` 函数体**最前面**加入：
```python
    register_builtin_providers()
```

完整修改后 `pipeline.py` 顶部应为：

```python
"""主流程：解析 → 去重 → 可达性检测 → 写 hosts.txt。"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from dnsprobe._bootstrap import register_builtin_providers
from dnsprobe.config import AppConfig
from dnsprobe.reachability import filter_reachable
from dnsprobe.registry import discover_plugins, get
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError
from dnsprobe.writer import write_hosts_file


def _log(msg: str) -> None:
    print(msg)


def _build_resolver_instances(providers, plugins_dir):
    register_builtin_providers()  # ← 显式 bootstrap
    ...
```

- [ ] **Step 6: 改 `src/dnsprobe/__main__.py` —— 加 bootstrap 调用**

在 `src/dnsprobe/__main__.py` 顶部 import 区加入：
```python
from dnsprobe._bootstrap import register_builtin_providers
```

并在 `main()` 函数体内、`run()` 调用**之前**加入：
```python
    register_builtin_providers()  # ← 双保险
```

完整修改后 `main()` 应为：

```python
def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    cwd = Path.cwd()
    if str(cwd) not in sys.path:
        sys.path.insert(0, str(cwd))

    try:
        domains_path = Path(args.domains) if args.domains else None
        config = load_config(Path(args.config), domains_path=domains_path)
    except FileNotFoundError as e:
        print(f"[×] {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[×] 配置解析失败: {e}", file=sys.stderr)
        return 1

    register_builtin_providers()

    plugins_dir = cwd / "plugins"
    if not plugins_dir.exists():
        plugins_dir = None

    try:
        return run(config, plugins_dir=plugins_dir)
    except Exception as e:
        print(f"[×] pipeline crashed: {e}", file=sys.stderr)
        return 1
```

- [ ] **Step 7: 跑测试确认通过**

```bash
python -m pytest tests/ -q
```
Expected: **50 passed**（48 既有 + 2 新 bootstrap 测试）。

- [ ] **Step 8: 提交**

```bash
git add -A
git commit -m "refactor: replace side-effect imports with explicit register_builtin_providers()"
```

---

## Task 3: 内置 ip33 升级到新 API（实测协议）

**Files:**
- Rewrite: `src/dnsprobe/providers/ip33.py`
- Modify: `tests/test_resolver.py`（删 4 个 multi-upstream 测试 + 加 4 个新协议测试 + 保留 1 个）
- Modify: `config.yml`（upstream_dns 注释）

**Interfaces:**
- Consumes: `BaseResolver`, `register`, `ResolverError`
- Produces: `Ip33Resolver` 用新 API endpoint + 响应协议

- [ ] **Step 1: 写 4 个新协议测试（先加，再删旧的）**

替换 `tests/test_resolver.py` 中所有 `test_ip33_*` 函数为以下 5 个（保留 `is_registered`，删其余）：

```python
def test_ip33_resolver_returns_ips_on_success(mocker):
    """type=3 响应应返回 ips[*].ip 列表。"""
    cfg = ResolverConfig(name="ip33", upstream_dns=[], extra={})
    mocker.patch(
        "dnsprobe.providers.ip33.requests.post",
        return_value=mocker.Mock(
            status_code=200,
            json=lambda: {"type": 3, "ips": [{"ip": "1.1.1.1", "area": "X"}, {"ip": "2.2.2.2", "area": "Y"}]},
            raise_for_status=lambda: None,
        ),
    )
    r = Ip33Resolver(cfg)
    assert r.resolve("example.com", cfg) == ["1.1.1.1", "2.2.2.2"]


def test_ip33_resolver_posts_with_s_param_and_headers(mocker):
    """POST data={s: domain} + headers 含 Origin/Referer/X-Requested-With。"""
    cfg = ResolverConfig(name="ip33", upstream_dns=[], extra={})
    mock_post = mocker.patch(
        "dnsprobe.providers.ip33.requests.post",
        return_value=mocker.Mock(
            status_code=200,
            json=lambda: {"type": 3, "ips": []},
            raise_for_status=lambda: None,
        ),
    )
    r = Ip33Resolver(cfg)
    r.resolve("github.com", cfg)

    call = mock_post.call_args
    assert call.kwargs["data"] == {"s": "github.com"}
    headers = call.kwargs["headers"]
    assert headers["Origin"] == "https://www.ip33.com"
    assert headers["Referer"] == "https://www.ip33.com/"
    assert headers["X-Requested-With"] == "XMLHttpRequest"


def test_ip33_resolver_raises_on_type_4_failure(mocker):
    """type=4 响应（解析失败）应抛 ResolverError。"""
    cfg = ResolverConfig(name="ip33", upstream_dns=[], extra={})
    mocker.patch(
        "dnsprobe.providers.ip33.requests.post",
        return_value=mocker.Mock(
            status_code=200,
            json=lambda: {"type": 4},
            raise_for_status=lambda: None,
        ),
    )
    r = Ip33Resolver(cfg)
    with pytest.raises(ResolverError):
        r.resolve("nonexistent.example.invalid", cfg)


def test_ip33_resolver_raises_on_http_failure(mocker):
    """HTTP 请求异常应抛 ResolverError。"""
    cfg = ResolverConfig(name="ip33", upstream_dns=[], extra={})
    mocker.patch(
        "dnsprobe.providers.ip33.requests.post",
        side_effect=requests.exceptions.ConnectionError(),
    )
    r = Ip33Resolver(cfg)
    with pytest.raises(ResolverError):
        r.resolve("example.com", cfg)


def test_ip33_resolver_is_registered():
    assert get("ip33") is Ip33Resolver
```

并在文件顶部 import 区添加：
```python
import requests as _requests_for_tests  # noqa: F401  # 仅测试用，触发 ConnectionError
```

或者更简洁：测试内直接用 `import requests`（已通过 dnsprobe 传递性可用），不需额外 import。如果 lint 报，可改为：
```python
import requests
```

并删除旧的 4 个 multi-upstream 测试函数（`test_ip33_resolver_merges_results_from_multiple_upstream`、`test_ip33_resolver_continues_when_first_upstream_fails`、`test_ip33_resolver_returns_partial_results`、`test_ip33_resolver_raises_when_all_upstreams_fail`）以及 `test_ip33_resolver_raises_resolvererror_on_http_failure`（旧的会被新 4 个替代）。

- [ ] **Step 2: 跑测试确认失败**

```bash
python -m pytest tests/test_resolver.py -v -k "ip33"
```
Expected: 旧测试可能通过（如果保留），新测试 FAIL（`ModuleNotFoundError` 或方法签名不匹配）。

- [ ] **Step 3: 重写 `src/dnsprobe/providers/ip33.py`**

完整内容：

```python
"""调用 https://www.ip33.com/api/ip/search 解析域名。"""
from __future__ import annotations

from typing import Any

import requests

from dnsprobe.registry import register
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError

_API = "https://www.ip33.com/api/ip/search"
_TIMEOUT = 10
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Origin": "https://www.ip33.com",
    "Referer": "https://www.ip33.com/",
    "X-Requested-With": "XMLHttpRequest",
}


@register("ip33")
class Ip33Resolver(BaseResolver):
    """通过 ip33 新 API 解析 A 记录。

    新协议不再接 dns 参数；上游 DNS 由 ip33 内部池化。
    """

    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        ips: list[str] = []
        errors: list[str] = []
        try:
            resp = requests.post(
                _API,
                data={"s": domain},
                headers=_HEADERS,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            payload: dict[str, Any] = resp.json()
            if payload.get("type") == 3:
                ips.extend(record["ip"] for record in payload.get("ips", []))
            else:
                errors.append(f"type={payload.get('type')}")
        except Exception as e:
            errors.append(str(e))

        if not ips:
            raise ResolverError(
                f"ip33 resolve failed for {domain}: {errors}"
            )
        return ips
```

- [ ] **Step 4: 改 `config.yml` 默认配置**

把现在的：
```yaml
  - name: ip33
    enabled: true
    upstream_dns:
      - 156.154.70.1
      - 208.67.222.222
    extra:
      timeout: 10
```

改为：
```yaml
  # 注：ip33 新 API 不再接受 dns 参数；upstream_dns 字段对本 provider 无意义
  # （schema 保留以兼容其他可能支持多上游 DNS 的 provider）
  - name: ip33
    enabled: true
    upstream_dns: []
    extra:
      timeout: 10
```

- [ ] **Step 5: 跑 ip33 相关测试确认通过**

```bash
python -m pytest tests/test_resolver.py -v -k "ip33"
```
Expected: 5 个 ip33 测试全部 PASS。

- [ ] **Step 6: 跑全部测试**

```bash
python -m pytest tests/ -q
```
Expected: **49 passed**（50 既有 - 4 旧 + 4 新 = 50；实际是 50+1 - 4 + 4 = 51... 让我算一下：Task 2 加了 2 个 bootstrap 测试 = 50；Task 3 删 4 旧 + 加 4 新 = -4+4 = 不变；再减 1 旧 ip33（`test_ip33_resolver_raises_resolvererror_on_http_failure` 也被替代），再加 0 = 49）。

预期：49 passed。

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "feat: upgrade Ip33Resolver to new ip33.com/api/ip/search endpoint"
```

---

## Task 4: test_main.py 重写（argparse + main 单元测试）

**Files:**
- Rewrite: `tests/test_main.py`

**Interfaces:**
- Consumes: `dnsprobe.__main__.main`, `_parse_args`
- Produces: 5 个单元测试（不启 subprocess）

- [ ] **Step 1: 写 5 个新单元测试**

完整替换 `tests/test_main.py`：

```python
"""dnsprobe.__main__ 的单元测试：argparse + main() 函数 + 错误分支。"""
from __future__ import annotations

from pathlib import Path

import pytest

from dnsprobe.__main__ import _parse_args, main


def test_parse_args_defaults():
    args = _parse_args([])
    assert args.config == "config.yml"
    assert args.domains is None


def test_parse_args_custom_paths():
    args = _parse_args(["--config", "c.yml", "--domains", "d.yml"])
    assert args.config == "c.yml"
    assert args.domains == "d.yml"


def test_main_returns_one_on_missing_config(tmp_path: Path, capsys: pytest.CaptureFixture):
    rc = main(["--config", str(tmp_path / "nope.yml")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "[×]" in err
    assert "config file not found" in err


def test_main_returns_one_on_pipeline_crash(tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture):
    (tmp_path / "config.yml").write_text("providers: []\n", encoding="utf-8")
    (tmp_path / "domains.yml").write_text("domains: []\n", encoding="utf-8")

    def boom(*args, **kwargs):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr("dnsprobe.__main__.run", boom)

    rc = main(["--config", str(tmp_path / "config.yml")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "[×] pipeline crashed" in err
    assert "simulated crash" in err


def test_main_passes_domains_path_through(tmp_path: Path, monkeypatch):
    captured: dict = {}

    def fake_run(config, plugins_dir):
        captured["domains"] = list(config.domains)
        return 0

    monkeypatch.setattr("dnsprobe.__main__.run", fake_run)

    (tmp_path / "config.yml").write_text("providers: []\n", encoding="utf-8")
    (tmp_path / "custom.yml").write_text(
        "domains:\n  - a.example\n", encoding="utf-8"
    )

    rc = main(
        [
            "--config",
            str(tmp_path / "config.yml"),
            "--domains",
            str(tmp_path / "custom.yml"),
        ]
    )
    assert rc == 0
    assert captured["domains"] == ["a.example"]
```

- [ ] **Step 2: 跑 test_main.py 确认通过**

```bash
python -m pytest tests/test_main.py -v
```
Expected: 5 个测试全部 PASS。

- [ ] **Step 3: 跑全部测试**

```bash
python -m pytest tests/ -q
```
Expected: **54 passed**（Task 3 后 49 + 5 新 = 54）。

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "test: rewrite test_main.py as argparse + main() unit tests"
```

---

## Task 5: README 重写

**Files:**
- Rewrite: `README.md`

**Interfaces:**
- Consumes: 无
- Produces: 完整 README（使用 / 配置 / 添加 Provider / 开发 / 项目结构 / GitHub Action / 设计文档 七节）

- [ ] **Step 1: 完整替换 `README.md`**

完整内容：

```markdown
# hosts_check

解析 TMDB / GitHub 系列域名的可用 IP，生成 `hosts.txt`，绕过 DNS 污染。

## 使用

- **直接用 hosts**：复制 [HOST每日更新](https://raw.githubusercontent.com/ChenXinBest/hosts_check/master/hosts.txt) 到你的 hosts 文件
- **手动运行**：
  ```bash
  pip install -r requirements.txt
  python -m dnsprobe
  ```
  或装包后直接：
  ```bash
  pip install -e .
  dnsprobe
  ```

## 配置

- `config.yml` —— 启用哪些 provider、每个 provider 的上游 DNS、输出与可达性参数
- `domains.yml` —— 待解析的域名列表

修改 `domains.yml` 即可定制自己的域名清单。

## 添加自定义 Provider

在 `plugins/` 目录下新建 `.py` 文件，继承 `BaseResolver` 并用 `@register("name")` 装饰：

```python
from dnsprobe.registry import register
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError


@register("my_resolver")
class MyResolver(BaseResolver):
    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        # cfg.upstream_dns: list[str] —— 上游 DNS 服务器列表（仅对支持多上游 DNS 的 provider 有意义）
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

## 开发

### 环境要求

- Python 3.10+（GitHub Action 用 3.12）

### 开发安装

```bash
pip install -r requirements-dev.txt
pip install -e .
```

### 跑测试

```bash
python -m pytest tests/ -v
```

### 项目结构

```
src/dnsprobe/        Python 包（import 路径 = dnsprobe）
plugins/             第三方/本地扩展（被扫描）
tests/               单元 + 集成测试
docs/                设计文档与历史
```

### GitHub Action 自动更新

`.github/workflows/run.yml` 每天 16:00 UTC 自动跑 `python -m dnsprobe` 并推送 `hosts.txt` 回 master。也可手动触发（Actions → Daily Ping → Run workflow）。

### 设计文档

`docs/superpowers/specs/` 与 `docs/superpowers/plans/` 记录项目设计与实现计划。
```

- [ ] **Step 2: 验证 README 不再提及旧包名**

```bash
grep -n "hosts_check" README.md
```
Expected: 仅在"复制 HOST每日更新"链接里出现 `ChenXinBest/hosts_check`（仓库名）—— 这是正确的（仓库名不变）。其他位置不应有 `hosts_check` 字样。

- [ ] **Step 3: 提交**

```bash
git add README.md
git commit -m "docs: rewrite README with src/dnsprobe layout and dev workflow"
```

---

## Task 6: GitHub Action workflow 改命令

**Files:**
- Modify: `.github/workflows/run.yml`（一行）

**Interfaces:**
- Consumes: `python -m dnsprobe`（Task 1 后可用）
- Produces: workflow 用 `python -m dnsprobe` 替代 `python -m hosts_check`

- [ ] **Step 1: 改 `.github/workflows/run.yml` 第 25 行**

把：
```yaml
      - name: Run daily job
        run: python -m hosts_check
```

改为：
```yaml
      - name: Run daily job
        run: python -m dnsprobe
```

- [ ] **Step 2: 验证 YAML 合法**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/run.yml')); print('OK')"
```
Expected: `OK`。

- [ ] **Step 3: 提交**

```bash
git add .github/workflows/run.yml
git commit -m "chore: switch GitHub Action to python -m dnsprobe"
```

---

## Task 7: 端到端验证

**Files:** 无新文件

**Interfaces:**
- Consumes: 所有前 6 task 产物
- Produces: spec §9 验收标准 1-8 全部通过

- [ ] **Step 1: 跑全部测试**

```bash
python -m pytest tests/ -v
```
Expected: **54 passed**（Task 4 后）。

- [ ] **Step 2: 验证 `python -m dnsprobe` 启动正常**

```bash
python -m dnsprobe --help
```
Expected: argparse help 文本输出 `usage: dnsprobe`。

- [ ] **Step 3: 验证 `dnsprobe` 命令可用（pyproject console_script）**

```bash
pip install -e .
dnsprobe --help
```
Expected: 与 Step 2 相同输出。

- [ ] **Step 4: 验证 `import dnsprobe` 工作 + 包结构**

```bash
python -c "
import dnsprobe
from dnsprobe import resolver, registry, config, pipeline, reachability, writer
from dnsprobe.providers import ip33
print('version:', dnsprobe.__version__)
print('all imports OK')
"
```
Expected: `version: 0.1.0` + `all imports OK`。

- [ ] **Step 5: 验证 `register_builtin_providers()` 后 _REGISTRY 含 ip33**

```bash
python -c "
import dnsprobe
from dnsprobe._bootstrap import register_builtin_providers
from dnsprobe.registry import _REGISTRY
register_builtin_providers()
print('registered:', sorted(_REGISTRY.keys()))
"
```
Expected: `registered: ['ip33']`。

- [ ] **Step 6: 验证 plugins/ 扫描**

```bash
python -c "
import sys; sys.path.insert(0, '.')
from pathlib import Path
from dnsprobe.registry import discover_plugins, _REGISTRY
from dnsprobe._bootstrap import register_builtin_providers
register_builtin_providers()
discover_plugins(Path('plugins'))
print('registered:', sorted(_REGISTRY.keys()))
"
```
Expected: `registered: ['example', 'ip33']`。

- [ ] **Step 7: 验证 load_config 仍能解析 config.yml**

```bash
python -c "
import sys; sys.path.insert(0, '.')
from pathlib import Path
from dnsprobe.config import load_config
c = load_config(Path('config.yml'))
print('providers:', [p.name for p in c.providers], 'domains:', len(c.domains))
"
```
Expected: `providers: ['ip33'] domains: 43`。

- [ ] **Step 8: 验证 GitHub Action workflow YAML 合法**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/run.yml')); print('OK')"
```
Expected: `OK`。

- [ ] **Step 9: 烟测 `python -m dnsprobe`（端到端）**

```bash
python -m dnsprobe
```
Expected: exit code 0 或 1（视 ip33 API 可达性）；stdout 含 `[OK] 完成: .../43` 或 `[×] 所有域名解析失败`；无 `KeyError("ip33")`；`hosts.txt` 结构合法。

- [ ] **Step 10: 验证仓库根无 dnsprobe 子文件夹**

```bash
ls hosts_check 2>/dev/null && echo "FAIL: hosts_check dir still exists" || echo "OK: no hosts_check dir"
ls dnsprobe 2>/dev/null && echo "FAIL: dnsprobe dir at root" || echo "OK: no dnsprobe dir at root"
ls src/dnsprobe/__init__.py && echo "OK: src/dnsprobe exists"
```
Expected: 三行 OK。

- [ ] **Step 11: 提交（如有未提交变更）**

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
| §1 项目结构 | Task 1（迁移 + pyproject）、Task 5（README）、Task 6（workflow） |
| §2 side-effect import 重构 | Task 2 |
| §3 内置 ip33 API 升级 | Task 3 |
| §4 测试文件划分 | Task 4 |
| §5 pyproject.toml | Task 1 |
| §6 README 重写 | Task 5 |
| §7 workflow 改动 | Task 6 |
| §9 验收标准 1-8 | Task 7 |

无遗漏。

### 2. 占位符扫描

无 TBD / TODO / "implement later" / "类似 Task N" 类占位符。每个 task 都有完整代码与命令。

### 3. 类型一致性复核

- `dnsprobe._bootstrap.register_builtin_providers() -> None` —— Task 2 定义，Task 2 测试、Task 3（被 ip33 测试 fixture 触发）、Task 7 验证使用一致
- `dnsprobe.providers.ip33.Ip33Resolver.resolve(domain, cfg) -> list[str]` —— Task 3 定义，Task 3 测试、Task 7 验证一致
- `dnsprobe.__main__.main(argv=None) -> int` / `_parse_args(argv: list[str]) -> argparse.Namespace` —— Task 4 测试使用，与 Task 1 / Task 6 / Task 7 一致
- `dnsprobe.config.load_config(config_path, domains_path=None) -> AppConfig` —— Task 7 验证，与 Task 1 一致

无类型不一致。