# Plugins

本目录用于放置第三方 DNS resolver 扩展。

> **完整开发指南**：项目根目录 `SKILL.md` 是面向 AI 编程助手的详细插件开发文档，包含接口定义、完整代码模板、IPv6 支持、HTTP 代理、测试要求等。推荐配合使用。

## 编写一个 plugin

1. 在本目录下创建 `my_resolver.py`（文件名以下划线开头会被忽略）
2. 继承 `dnsprobe.resolver.BaseResolver`
3. 用 `@register("name")` 装饰你的类
4. 实现 `resolve(domain, cfg) -> list[str]`
5. 在 `config.yml` 的 `providers` 列表中添加这个 name

最小模板：

```python
from dnsprobe.registry import register
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError


@register("my_resolver")
class MyResolver(BaseResolver):
    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        # cfg.upstream_dns: list[str] —— 上游 DNS 服务器列表
        # cfg.extra: dict —— 你的私有参数
        # 失败抛 ResolverError，成功返回 IP 列表
        ...
```

启动时 `python -m dnsprobe` 会自动扫描本目录下所有 `.py` 文件并 import，触发 `@register` 副作用。