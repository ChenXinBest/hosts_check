# hosts_check 重构设计

- **日期**：2026-07-23
- **状态**：待用户审阅
- **范围**：单一实现计划可覆盖

## 背景

`hosts_check` 通过上游 DNS 解析一组受 DNS 污染影响的域名（TMDB、GitHub 等），筛选可用 IP 后生成 `hosts.txt`，由 GitHub Action 每日更新。当前所有逻辑耦合在 `DailyJob.py` / `DnsParse.py` 中，HOSTS 列表、DNS 上游、解析方式全部硬编码，扩展困难。

本次重构在**不改变对外契约**（`hosts.txt` 输出格式、README 链接、GitHub Action 调度）的前提下，引入以下结构：

1. 待解析域名列表外置到 YAML 文件
2. DNS 解析方法抽象为接口（`BaseResolver`），通过插件目录支持第三方扩展
3. 配置文件选择启用哪些 provider
4. GitHub Action 与手动运行共用同一入口

## 方案选型

经过 brainstorming 三个方案对比（A 最简 / B 标准迁移+可扩展 / C 完整拓展），**采用方案 B**。

理由：
- 方案 A 单独无法验证"扩展性好不好用"——你既然要支持别人加 Provider，至少给一个模板和默认实现
- 方案 C 的本地 DNS 兜底在 GitHub Action 场景下无价值（Runner 出口 DNS 同样污染）

方案对比中已确认的细节决策：
- 配置格式：YAML
- 抽象边界：只抽象 DNS 解析这一环（拿到 IP 列表即可），可达性检测留在主流程
- 域名列表：YAML 纯列表
- 抽象主体：Provider = 解析方式，上游 DNS 服务器作为 Provider 的参数
- 扩展方式：本地 `plugins/` 目录扫描 `.py` 文件
- 旧脚本：`DnsParse.py` 直接删除
- 主代码组织：Python 包 `hosts_check/`

## 1. 项目结构

```
hosts_check/
├── hosts_check/                      # Python 包
│   ├── __init__.py
│   ├── __main__.py                   # python -m hosts_check 入口
│   ├── config.py                     # 加载 YAML 配置 + domains
│   ├── resolver.py                   # BaseResolver 抽象 + ResolverConfig
│   ├── registry.py                   # 插件扫描 + 名称 → Provider 类映射
│   ├── providers/
│   │   └── ip33.py                   # 内置 Ip33Resolver（迁移原 ip33.com 逻辑）
│   ├── pipeline.py                   # 串联：解析 → 可达性检测 → 写文件
│   ├── reachability.py               # HTTP HEAD 测连通（迁移现逻辑）
│   └── writer.py                     # 生成 hosts.txt（迁移现逻辑）
├── plugins/                          # 第三方扩展（被扫描）
│   ├── README.md                     # 如何写一个 plugin
│   └── example_resolver.py           # 模板示例
├── tests/
│   ├── test_config.py
│   ├── test_registry.py
│   ├── test_resolver.py
│   ├── test_writer.py
│   └── test_pipeline.py
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-07-23-hosts_check-refactor-design.md
├── config.yml                        # 启用哪些 provider + 上游 DNS
├── domains.yml                       # 待解析域名
├── .github/workflows/run.yml         # 改：python -m hosts_check
├── requirements.txt                  # 新增：pyyaml
├── requirements-dev.txt              # 新增：pytest + pytest-mock
├── README.md                         # 重写：加 "如何加 Provider" 一节
├── .gitignore                        # 保留：hosts.txt 忽略
└── DnsParse.py                       # 删除
```

要点：
- 内置 `Ip33Resolver` 放 `hosts_check/providers/`，跟外部 plugins 走**同一个注册通道**（不特殊化），代码逻辑只有一条路径
- `plugins/` 在仓库内是空的（只放 README + 模板），用户/扩展者 fork 后往里加文件即可
- `hosts.txt` 仍由 GitHub Action 生成推到 master 分支，README 链接不变

## 2. 核心抽象

### 2.1 `BaseResolver`（`hosts_check/resolver.py`）

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

@dataclass
class ResolverConfig:
    """单个 provider 实例的运行配置（来自 YAML 的 providers.<name> 节点）"""
    name: str
    upstream_dns: list[str]   # 该 provider 用哪些上游 DNS 服务器
    extra: dict              # provider 自己的自定义参数

class BaseResolver(ABC):
    """所有 DNS resolver 必须继承这个"""
    name: ClassVar[str] = ""  # 由 @register 装饰器填入

    def __init__(self, cfg: ResolverConfig) -> None:
        self.cfg = cfg  # 默认实现：保存配置。子类若无特殊需要可不重写 __init__

    @abstractmethod
    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        """输入域名，返回 A 记录 IP 列表。失败抛 ResolverError 或返回 []"""
        ...

class ResolverError(Exception): ...
```

### 2.2 注册机制（`hosts_check/registry.py`）

```python
_REGISTRY: dict[str, type[BaseResolver]] = {}

def register(name: str):
    """装饰器：把 Resolver 子类挂到全局注册表"""
    def deco(cls: type[BaseResolver]) -> type[BaseResolver]:
        cls.name = name
        _REGISTRY[name] = cls
        return cls
    return deco

def discover_plugins(plugins_dir: Path) -> None:
    """扫描 plugins_dir 下所有 .py，import 触发 @register 副作用"""
    for py in plugins_dir.glob("*.py"):
        if py.name.startswith("_"):
            continue
        importlib.import_module(f"plugins.{py.stem}")

# 说明：__main__.py 在调用 discover_plugins 之前必须 `sys.path.insert(0, ".")`，
# 以确保 `plugins.xxx` 包可被 import。GitHub Action 在仓库根目录跑 `python -m hosts_check` 时默认即如此。

def get(name: str) -> type[BaseResolver]:
    if name not in _REGISTRY:
        raise KeyError(f"resolver '{name}' not registered")
    return _REGISTRY[name]
```

### 2.3 一个 plugin 的完整形态（`plugins/example_resolver.py`）

```python
from hosts_check.resolver import BaseResolver, ResolverConfig, ResolverError, register

@register("example")
class ExampleResolver(BaseResolver):
    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        # cfg.upstream_dns 里取一个用
        # ... 自定义协议 ...
        if error:
            raise ResolverError("...")
        return ["1.2.3.4", "5.6.7.8"]
```

特点：
- 扩展者只需写一个文件：继承 `BaseResolver`、写 `resolve()`、加 `@register("xxx")` —— 行数 < 30
- 协议细节（HTTP/DoH/本地 socket/dig 子进程）完全由 resolver 内部决定，对主流程透明
- 配置参数（`ResolverConfig`）从 YAML 透传到 `resolve()`，扩展者按需读取 `cfg.extra`

## 3. 配置文件 & 域名文件

### 3.1 `config.yml`

```yaml
# 启用的 provider 列表（按顺序使用；name 必须是被 @register 注册过的）
providers:
  - name: ip33                  # 对应 @register("ip33")
    enabled: true
    upstream_dns:               # 这个 provider 用哪些上游 DNS
      - 156.154.70.1
      - 208.67.222.222
    extra:                      # provider 私有参数（透传到 ResolverConfig.extra）
      timeout: 10

  # 第三方加的 provider（前提：plugins/ 下有对应文件）
  - name: example
    enabled: false              # 默认关，注册了但不用
    upstream_dns:
      - 8.8.8.8
    extra: {}

# 写入目标
output:
  path: hosts.txt
  keep_old_section: true        # 是否保留 hosts.txt 中 ###start### 外的内容

# 可达性检测
reachability:
  method: http_head             # 现阶段只支持 http_head，留扩展位
  timeout: 5.0
```

### 3.2 `domains.yml`

```yaml
domains:
  - api.themoviedb.org
  - image.tmdb.org
  - www.themoviedb.org
  - alive.github.com
  - api.github.com
  # ...（从 DailyJob.py 现有 HOSTS 列表完整迁移）
```

要点：
- `providers` 是列表而非字典 —— 故意保留顺序，方便未来按顺序做"主备"语义
- `enabled: false` 表示"注册了但这次不使用"
- `enabled` 缺省时 = `true`（不写就启用）
- `domains.yml` 与 `config.yml` 拆开 —— 域名列表人工编辑频率高，单独一个文件 git diff 更清爽
- `reachability.method` 字段现阶段只支持 `http_head`，但**保留接口位**，以后想加 `tcp_connect`/`ping` 都能配

## 4. 主流程

`hosts_check/pipeline.py` 伪代码：

```python
def run(config: AppConfig) -> None:
    # 1. 加载 provider 类
    discover_plugins(Path("plugins"))
    resolvers = []
    for p in config.providers:
        if not p.enabled: continue
        cls = get(p.name)             # 找不到就 KeyError，由 __main__ 兜成友好提示
        # p 在循环里已是 ResolverConfig；通过 cls(p) 注入，是约定：BaseResolver
        # 子类 __init__ 必须接受 ResolverConfig 并保存（不需要重写时使用默认基类实现）
        resolvers.append((cls(p), p)) # 实例 + 它的配置

    # 2. 对每个域名 × 每个 resolver 取 IP
    raw: dict[str, list[str]] = defaultdict(list)
    for domain in config.domains:
        for resolver, rcfg in resolvers:
            try:
                ips = resolver.resolve(domain, rcfg)
            except ResolverError as e:
                log(f"[!] {resolver.name} on {domain}: {e}")
                continue
            raw[domain].extend(ips)

    # 3. 去重 + 可达性检测（保留原顺序）
    filtered: dict[str, list[str]] = {}
    for domain, ips in raw.items():
        unique = list(dict.fromkeys(ips))           # 保序去重
        reachable = filter_reachable(unique, domain, config.reachability)
        if reachable:
            filtered[domain] = reachable

    # 4. 写 hosts.txt
    write_hosts_file(filtered, config.output)
    log(f"完成: {len(filtered)}/{len(config.domains)} 个域名有可用 IP")
```

`__main__.py` 负责：参数解析（`--config`、`--domains` 覆盖默认路径）、异常兜底（友好错误信息 + 非零退出码）。

### 与现状的差异

- 现有 `DailyJob.py:101` 是嵌套循环 `for host for dns`，每个 host × 每个 dns 独立解析。**新设计改成一个 domain × 一个 resolver**（resolver 内部用 `cfg.upstream_dns` 列表），把"上游 DNS"封装进 resolver 自己的逻辑里 —— 这是最关键的语义变化：原来 `DNS_PROVIDERS = ["156.154.70.1", ...]` 是 ip33 专属的（它的 API 要求传 `dns` 参数），新设计里这层关系由 `Ip33Resolver` 自己处理
- `Ip33Resolver` 处理多 upstream DNS 的策略：**逐个上游 DNS 解析 + 合并 IP 列表**（不去重、不抛错），由主流程第 3 步统一去重 + 可达性检测。这样与现有行为完全一致，迁移后输出结果与重构前等价
- 异常隔离：单个 provider 失败不影响其他 provider；单个 domain 失败不影响其他 domain
- 退出码：0=至少一个有结果，1=全部失败（GitHub Action 可据此决定是否提交）

## 5. 错误处理

按"不掩盖、不崩溃、能恢复就恢复"的原则，分三层：

### 5.1 配置层错误（启动即失败）

- `config.yml` / `domains.yml` 不存在 → 友好提示 + 退出码 1
- YAML 解析失败 → 打印行号 + 退出码 1
- `providers[].name` 未注册 → 列出已注册的 provider 供对照 + 退出码 1
- `domains` 为空 → 警告但继续跑（生成空 hosts.txt）

### 5.2 Provider 层错误（单个域名内部失败）

- `ResolverError`（自定义异常）→ 记录到 stdout（GitHub Action 日志可见），跳过该 domain×provider 组合
- 网络超时 / HTTP 5xx → 在 `Ip33Resolver` 内部包成 `ResolverError` 抛出，不直接污染主流程
- 上游 DNS 全部失败 → resolver 返回 `[]`（不抛异常），由主流程的"是否非空"判断

### 5.3 写入层错误（接近尾声）

- `hosts.txt` 写失败（权限、磁盘）→ 抛原始异常 + 退出码 1（**不**静默吞，因为这是产物）
- 如果 `output.keep_old_section=true` 且原 `hosts.txt` 含 `###start###`，写之前先剥离再追加，**任何异常都不能让用户丢失原有 host 配置**。"原有 host 配置"特指 `###start###` 与 `###end###` 标记之外的所有用户自定义 hosts 行。

### 5.4 可达性检测层

- HTTP HEAD 超时 → 跳过该 IP（不影响其他 IP）
- HTTP HEAD 抛异常 → 同上

### 5.5 日志格式

统一 stdout，便于 GitHub Action 抓取：
- `[OK]` 成功
- `[!]` 警告/可恢复错误
- `[×]` 失败（单个 IP / 单个 domain）
- 退出码仅在"整体失败"时非零

## 6. 测试

`tests/` 目录下，单测为主（不依赖网络）：

| 文件 | 覆盖 |
|---|---|
| `test_config.py` | YAML 加载、缺字段默认值、`enabled` 缺省为 `true`、空 domains 不报错 |
| `test_registry.py` | `@register` 装饰器、`discover_plugins` 扫描 `plugins/`、未注册 name 抛 KeyError、`get` 返回正确类 |
| `test_resolver.py` | `BaseResolver` 抽象类不能直接实例化；自定义 Resolver 通过 `resolve()` 返回正确类型；解析失败抛 `ResolverError` |
| `test_writer.py` | `write_hosts_file` 输出格式与现有 `hosts.txt` 字节级一致；`keep_old_section` 行为；空结果生成合法文件（含 `###start###` 与 `###end###`） |
| `test_pipeline.py` | mock 一个 resolver，跑全流程，验证调用顺序与 host 字典组装 |

关键策略：
- **不测 `Ip33Resolver` 真实网络行为** —— 那是 ip33 接口稳定性，不是我们的代码。它通过 `test_resolver.py` 的"协议行为"间接覆盖（mock 它）
- **不测 GitHub Action workflow** —— 那是 YAML 调度，跑 CI 才是它的测试
- `pytest` + `pytest-mock` 即可，`requirements-dev.txt` 单独列

### 依赖文件

`requirements.txt`：
```
requests>=2.28
pyyaml>=6.0
```

`requirements-dev.txt`：
```
pytest>=7.0
pytest-mock>=3.10
```

## 7. 迁移与删除

- `DnsParse.py` 直接删除
- `DailyJob.py` 内容迁移到 `hosts_check/` 包各模块后删除
- `HOSTS` 列表（当前在 `DailyJob.py:14-34`）逐字迁移到 `domains.yml`
- `DNS_PROVIDERS` 列表（当前在 `DailyJob.py:36`）迁移到 `config.yml` 的 `providers[ip33].upstream_dns`
- `.github/workflows/run.yml` 改 `python DailyJob.py` → `python -m hosts_check`
- `README.md` 重写：保留原"HOST 每日更新"链接、新增"如何加 Provider"章节

## 8. 不在本次范围

- CI（GitHub Action 跑 pytest）—— 留给后续
- DoH / 本地 DNS 兜底 Provider —— 见方案 C 说明
- 多种输出格式（JSON / CSV）—— 现阶段 `hosts.txt` 足够
- 国际化 / 多 README 翻译
- `resolver.py` 之外的 `Checker` 抽象（可达性检测沿用 HTTP HEAD，写在 `reachability.py` 即可）

## 9. 验收标准

1. `python -m hosts_check` 在仓库根目录能跑通，输出 `hosts.txt` 的**结构与重构前一致**：`###start###` 与 `###end###` 标记、域名与 IP 顺序相同；时间戳按当前时刻生成（旧实现亦如此），不要求逐字节相同
2. `python -m pytest tests/` 全部通过
3. 复制 `plugins/example_resolver.py` 改名为 `plugins/my_doh.py`、把 `@register("example")` 改成 `@register("mydoh")`、在 `config.yml` 加一个 `mydoh` provider 后，`python -m hosts_check` 能正常加载并使用它
4. 在 `config.yml` 中把 `ip33.enabled` 设为 `false` 后，`python -m hosts_check` 仍能跑（如果有其他启用 provider）或优雅退出
5. GitHub Action 每日 16:00 UTC 自动跑 + 手动 `workflow_dispatch` 都能正常生成并提交 `hosts.txt`
