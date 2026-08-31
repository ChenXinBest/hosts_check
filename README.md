

# hosts_check

解析 TMDB / GitHub 系列域名的可用 IP，生成 `hosts.txt`，绕过 DNS 污染。支持 IPv4（A）和 IPv6（AAAA）记录。

## 使用

- **直接用 hosts**：复制 [HOST每日更新](https://raw.githubusercontent.com/ChenXinBest/hosts_check/master/hosts.txt) 到你的 hosts 文件
- **手动运行**：
  ```bash
  pip install -r requirements.txt
  pip install -e .
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

### IPv6 支持

在 `config.yml` 的 provider `extra` 中配置 `record_types`：

```yaml
providers:
  - name: doh
    extra:
      record_types: ["A"]          # 仅 IPv4（默认）
      # record_types: ["AAAA"]     # 仅 IPv6
      # record_types: ["A", "AAAA"] # 双栈
```

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

> **AI 工具用户**：项目根目录有 `SKILL.md`，是给 AI 编程助手（Cursor、Copilot、Mavis 等）看的插件开发指南，包含完整的接口说明、代码模板和测试要求。

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
