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
