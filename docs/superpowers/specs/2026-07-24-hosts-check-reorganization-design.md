# hosts_check 整理设计（src 布局 + 包名解耦 + ip33 新接口）

- **日期**：2026-07-24
- **状态**：待用户审阅
- **范围**：单一实现计划可覆盖
- **前序**：2026-07-23 重构已完成（28 commits，48/48 测试 PASS）

## 背景

2026-07-23 的重构把 `hosts_check` 从 `DailyJob.py` / `DnsParse.py` 拆为 `hosts_check/` Python 包 + 插件体系 + YAML 配置 + 48 个测试。

审视当前状态发现两个**结构问题**：

1. **仓库名 = 包名**：GitHub 仓库叫 `hosts_check`，根目录下又有 `hosts_check/` Python 包。两者名字完全相同，让外部读者困惑（看起来像是"项目里有个同名子文件夹"）。Python 社区标准做法是 `src/<package_name>/`，把包放进 `src/` 目录，并让包名与仓库名解耦。
2. **side-effect import**：当前为了让内置 `ip33` 注册进 `_REGISTRY`，在 `pipeline.py:13` 和 `providers/__init__.py` 都用了 `import ... # noqa: F401` 触发 `@register` 副作用。这种"import 链隐藏逻辑"不优雅，未来新增内置 provider 时容易遗漏。

本次还在实测中发现 ip33 **升级了 API**：从 `http://api.ip33.com/dns/resolver` 改为 `https://www.ip33.com/api/ip/search`，新协议不再接受 `dns` 参数，`cfg.upstream_dns` 对 ip33 resolver 不再有 failover 意义。

本次整理在**不破坏 48/48 测试、不改对外契约（`hosts.txt` 输出格式 / README 链接 / GitHub Action 调度）** 的前提下：

- 迁移到 `src/` 布局
- 包改名为 `dnsprobe`（与仓库名 `hosts_check` 解耦）
- side-effect import 重构为显式 `register_builtin_providers()`
- 内置 ip33 升级到新 API
- 拆分 `test_main.py` / `test_cli.py` 职责
- README 重写（补 dev 安装 / 测试 / 项目结构 / GitHub Action 说明）

## 方案选型

经过 brainstorming 决策：

| 决策 | 选择 | 理由 |
|---|---|---|
| 工作范围 | B 类（A 清理 + 重构代码 + README） | 用户选 |
| `docs/superpowers/` | 保留原状 | 历史可追溯 |
| `.superpowers/sdd/` final-fix reports | 保留 commit | 用户选 |
| `hosts.txt` | 保留 tracked | GitHub Action 推它供外部访问 |
| `__pycache__/` | 已 gitignore，无需 action | — |
| 包结构 | `src/dnsprobe/` | 与仓库名 `hosts_check` 解耦 |
| side-effect import | 显式 `register_builtin_providers()` | 优雅、可测试 |
| `test_main.py` / `test_cli.py` | 按功能名划分 | unit vs subprocess integration |
| README | 补齐使用与配置 | 用户选 |
| ip33 endpoint | `https://www.ip33.com/api/ip/search` | 用户指定 + 实测验证 |

## 1. 项目结构

```
hosts_check/                              ← GitHub 仓库根（项目名 hosts_check）
├── pyproject.toml                        ← 新增：src 布局 + console_script
├── src/
│   └── dnsprobe/                         ← Python 包（import 路径 = dnsprobe）
│       ├── __init__.py                   ← __version__ = "0.1.0"
│       ├── __main__.py                   ← python -m dnsprobe 入口
│       ├── _bootstrap.py                 ← 新增：register_builtin_providers()
│       ├── config.py                     ← AppConfig + load_config()
│       ├── resolver.py                   ← BaseResolver + ResolverConfig
│       ├── registry.py                   ← @register + discover_plugins + get
│       ├── providers/
│       │   ├── __init__.py               ← 故意为空（_bootstrap 显式 import）
│       │   └── ip33.py                   ← 升级到新 API endpoint
│       ├── pipeline.py                   ← run() + 调用 _bootstrap
│       ├── reachability.py
│       └── writer.py
├── plugins/                              ← 不变（用户/扩展者 plugin）
│   ├── README.md
│   └── example_resolver.py
├── tests/                                ← 全部 import: hosts_check.X → dnsprobe.X
│   ├── __init__.py
│   ├── test_main.py                      ← 重写：argparse + main() 单元测试
│   ├── test_cli.py                       ← 保留：subprocess 集成测试
│   ├── test_config.py
│   ├── test_integration.py
│   ├── test_pipeline.py
│   ├── test_reachability.py
│   ├── test_resolver.py
│   └── test_writer.py
├── docs/
│   └── superpowers/
│       ├── specs/2026-07-23-hosts_check-refactor-design.md
│       ├── specs/2026-07-24-hosts-check-reorganization-design.md
│       └── plans/2026-07-23-hosts_check-refactor.md
├── config.yml
├── domains.yml
├── requirements.txt
├── requirements-dev.txt
├── README.md                             ← 重写
├── .github/workflows/run.yml             ← 改：python -m dnsprobe
├── .gitignore
└── .superpowers/                         ← skill scratch（已 gitignore）
```

**关键变化**：
- 仓库根 = `hosts_check/`
- 包 = `src/dnsprobe/`
- `import dnsprobe` 通过 `pyproject.toml` 的 `[tool.setuptools.packages.find]` `where = ["src"]` 指向 `src/`
- CLI 入口：`python -m dnsprobe` 或 `dnsprobe`（pyproject console script）

## 2. side-effect import 重构

### 2.1 `_bootstrap.py`（新增）

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

### 2.2 `providers/__init__.py`（改）

```python
"""内置 resolver 实现。"""
# 故意为空：内置 provider 通过 dnsprobe._bootstrap.register_builtin_providers() 显式 import
```

### 2.3 `pipeline.py`（改）

删除：`import hosts_check.providers  # noqa: F401`

新增调用：

```python
from dnsprobe._bootstrap import register_builtin_providers


def _build_resolver_instances(providers, plugins_dir):
    register_builtin_providers()  # ← 在此显式调用
    ...
```

### 2.4 `__main__.py`（改）

新增调用（在 load_config 之后、run 之前）：

```python
from dnsprobe._bootstrap import register_builtin_providers


def main(argv=None):
    ...
    register_builtin_providers()  # ← 双保险
    ...
```

## 3. 内置 ip33 API 升级

### 3.1 新协议（实测）

| 字段 | 旧协议 | 新协议 |
|---|---|---|
| URL | `http://api.ip33.com/dns/resolver` | `https://www.ip33.com/api/ip/search` |
| 协议 | HTTP | HTTPS |
| Form 参数 | `domain`, `type=A`, `dns=<server>` | 仅 `s=<domain>`（不再接 `dns`） |
| 必带 Headers | — | `Origin`、`Referer`、`X-Requested-With: XMLHttpRequest`、User-Agent |
| 响应（成功） | `{"record": [{"ip": "..."}]}` | `{"type": 3, "ips": [{"ip": "...", "area": "..."}]}` |
| 响应（失败） | — | `{"type": 4}` |
| 响应（本机 IP） | — | `{"type": 1, "ip": "...", "area": "..."}` |

### 3.2 `Ip33Resolver` 新实现（`src/dnsprobe/providers/ip33.py`）

```python
"""调用 https://www.ip33.com/api/ip/search 解析域名。"""
from __future__ import annotations

import json
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
    """通过 ip33 新 API 解析 A 记录。"""

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

### 3.3 默认 `config.yml`（改）

```yaml
providers:
  - name: ip33
    enabled: true
    # 注：ip33 新 API 不再接受 dns 参数；upstream_dns 字段对本 provider 无意义
    # （schema 保留以兼容其他可能支持多上游 DNS 的 provider）
    upstream_dns: []
    extra:
      timeout: 10

output:
  path: hosts.txt
  keep_old_section: true

reachability:
  method: http_head
  timeout: 5.0
```

### 3.4 测试

`tests/test_resolver.py` 当前 6 个 `test_ip33_*` 测试需要按新协议**重写**（不是简单更新）：

- **删除**：原 Task 5 的 multi-upstream 行为测试（`merges_results_from_multiple_upstream`、`continues_when_first_upstream_fails`、`returns_partial_results`、`raises_when_all_upstreams_fail`）—— 新 API 不支持 multi-upstream
- **新增**：4 个测试
  1. `test_ip33_resolver_returns_ips_on_success`：mock 返回 `{"type": 3, "ips": [{"ip": "1.1.1.1"}]}`，验证返回 `["1.1.1.1"]`
  2. `test_ip33_resolver_posts_with_s_param_and_headers`：mock 后 `mocker.call_args` 验证 `data={"s": domain}` + headers 含 `Origin`、`Referer`、`X-Requested-With`
  3. `test_ip33_resolver_raises_on_type_4_failure`：mock 返回 `{"type": 4}`，验证抛 `ResolverError`
  4. `test_ip33_resolver_raises_on_http_failure`：mock `requests.post` 抛异常，验证抛 `ResolverError`
- **保留**：`test_ip33_resolver_is_registered`（仅验证类名，跨版本不变）

## 4. 测试文件划分

### 4.1 `tests/test_main.py`（重写）

**单元测试**（不启 subprocess），覆盖：

```python
from dnsprobe.__main__ import main, _parse_args


def test_parse_args_defaults():
    args = _parse_args([])
    assert args.config == "config.yml"
    assert args.domains is None


def test_parse_args_custom_paths():
    args = _parse_args(["--config", "c.yml", "--domains", "d.yml"])
    assert args.config == "c.yml"
    assert args.domains == "d.yml"


def test_main_returns_one_on_missing_config(tmp_path, capsys):
    rc = main(["--config", str(tmp_path / "nope.yml")])
    assert rc == 1
    assert "config file not found" in capsys.readouterr().err


def test_main_returns_one_on_pipeline_crash(tmp_path, monkeypatch, capsys):
    (tmp_path / "config.yml").write_text("providers: []\n")
    (tmp_path / "domains.yml").write_text("domains: []\n")
    monkeypatch.setattr("dnsprobe.__main__.run",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    rc = main(["--config", str(tmp_path / "config.yml")])
    assert rc == 1
    assert "pipeline crashed" in capsys.readouterr().err


def test_main_passes_domains_path_through(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "dnsprobe.__main__.run",
        lambda cfg, plugins_dir: (captured.setdefault("d", list(cfg.domains)) or 0),
    )
    (tmp_path / "config.yml").write_text("providers: []\n")
    (tmp_path / "custom.yml").write_text("domains:\n  - a.example\n")
    rc = main(["--config", str(tmp_path / "config.yml"),
               "--domains", str(tmp_path / "custom.yml")])
    assert rc == 0
    assert captured["d"] == ["a.example"]
```

### 4.2 `tests/test_cli.py`（保留）

subprocess 端到端集成测试，从前次重构继承：

```python
"""dnsprobe CLI 端到端 subprocess 集成测试。"""
def test_cli_runs_with_complete_setup(tmp_path):
    # 写 config.yml / domains.yml / plugins/fake_cli.py
    # subprocess.run([sys.executable, "-m", "dnsprobe", ...])
    # 验证 exit code in (0, 1) + hosts.txt 结构合法
```

### 4.3 `tests/test_resolver.py` 的 `_clean_registry` fixture

继续保留（autouse）；新 `register_builtin_providers()` 测试需显式调用，不依赖 fixture 副作用。

## 5. pyproject.toml（新增）

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

## 6. README 重写

完整内容（章节顺序）：

```markdown
# hosts_check

解析 TMDB / GitHub 系列域名的可用 IP，生成 `hosts.txt`，绕过 DNS 污染。

## 使用

- 直接用 hosts：复制 [HOST每日更新](https://raw.githubusercontent.com/ChenXinBest/hosts_check/master/hosts.txt)
- 手动运行：
  ```bash
  pip install -r requirements.txt
  python -m dnsprobe
  ```
  或装包后：
  ```bash
  pip install -e .
  dnsprobe
  ```

## 配置

- `config.yml` —— 启用哪些 provider、每个 provider 的上游 DNS、输出与可达性参数
- `domains.yml` —— 待解析的域名列表

修改 `domains.yml` 即可定制自己的域名清单。

## 添加自定义 Provider

在 `plugins/` 目录下新建 `.py` 文件，继承 `BaseResolver` 并用 `@register("name")` 装饰（详见 `plugins/README.md`）。

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

`.github/workflows/run.yml` 每天 16:00 UTC 自动跑 `python -m dnsprobe` 并推送 `hosts.txt` 回 master。也可手动触发。

### 设计文档

`docs/superpowers/specs/` 与 `docs/superpowers/plans/` 记录项目设计与实现计划。
```

## 7. GitHub Action workflow 改动

`.github/workflows/run.yml`：

```yaml
# 改：python -m hosts_check → python -m dnsprobe
- name: Run daily job
  run: python -m dnsprobe
```

其余 cron / workflow_dispatch / Python 版本 / SSH push 块保留。

## 8. 不在本次范围

- CI（GitHub Action 跑 pytest）
- 新 ip33 API 之外的 DoH / 本地 DNS provider
- ruff / mypy lint 配置
- 国际化 README
- 控制台 script 在 Windows 下的 PATH 配置细节（pyproject `dnsprobe = "dnsprobe.__main__:main"` 在 Linux/macOS 正常；Windows 通过 `python -m dnsprobe` 走）

## 9. 验收标准

1. `python -m dnsprobe` 在仓库根目录能跑通，`hosts.txt` 结构合法
2. `python -m pytest tests/ -v` 全部通过（目标 ≥ 48 个）
3. `pip install -e .` 后 `dnsprobe` 命令可用
4. `import dnsprobe` / `from dnsprobe.providers.ip33 import Ip33Resolver` 可工作
5. `register_builtin_providers()` 调用后 `_REGISTRY` 含 `ip33`
6. 复制 `plugins/example_resolver.py` 改名后启用能正常加载
7. GitHub Action 每日 16:00 UTC 自动跑 + 手动 `workflow_dispatch` 都能正常生成并提交 `hosts.txt`
8. 仓库根目录无 `dnsprobe/` 子文件夹；包在 `src/dnsprobe/`