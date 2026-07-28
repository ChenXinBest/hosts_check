# dnschecked provider 替换 toolhelper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把内置 provider 从 `toolhelper.cn DNSCheck`（单 endpoint、Tag=1/0/-1 协议）替换为 `dnschecked.com query_dns`（JSON API + 可指定上游 DNS），按**大洲/国家**批量配置上游 DNS（默认北美洲），所有 DNS 并行查询取结果并集，移除 toolhelper 相关代码与测试。

**Architecture:** 新建 `src/dnsprobe/providers/dnschecked.py`，内置两个硬编码常量 `CONTINENT_DNS: dict[str, list[str]]`（大洲 → IP 列表）和 `COUNTRY_DNS: dict[str, list[str]]`（国家代码 → IP 列表），数据从 `https://dnschecked.com/_next/static/chunks/913-5c5215ba2da48371.js` 的 `n.Z` 数组提取。`resolve(domain)` 流程：(1) 读 `cfg.extra.continents` + `cfg.extra.countries` 合并出本次要用的 DNS 列表；(2) `requests.post(API, json=...)` 并行查所有 DNS（用 `concurrent.futures.ThreadPoolExecutor`）；(3) 收集所有 200 响应的 `results[*]` 取并集 + 去重；(4) 全部失败抛 `ResolverError`。

**Tech Stack:** Python 3.10+（GitHub Action 3.12），`requests>=2.28`、`pyyaml>=6.0`、`pytest>=7.0`、`pytest-mock>=3.10`。新增 `concurrent.futures`（stdlib，无需新依赖）。

## Global Constraints

- 仓库名 `hosts_check`，包名 `dnsprobe`（沿用现有约定）
- provider 名 `dnschecked`（跟 API 域名一致）
- 内置常量 `CONTINENT_DNS` / `COUNTRY_DNS` 数据来源注释指明 JS 源
- 默认 `extra.continents: [north-america]`（8.8.8.8 / Cloudflare / OpenDNS / Quad9 / VeriSign 等美区权威 DNS，对 GitHub/TMDB 等主要服务解析稳定）
- 并行查所有 DNS，max_workers = DNS 数量（无需节流，API 没有 rate limit 文档说明）
- 单个 DNS 失败不影响其他：异常/4xx 都吞掉，OK 响应的 `results` 才计入
- 全量收集 OK 结果并集 + 保序去重（跟主流程 `pipeline.py` 已有去重逻辑对齐）
- 全部 5x 个测试在迁移后仍需 PASS

---

## API 协议（实测）

| 维度 | 值 |
|---|---|
| URL | `https://api.dnschecked.com/query_dns` |
| Method | POST |
| Content-Type | `application/json` |
| Body | `{"domain": "<domain>", "record_type": "A", "dns_server": "<ip>"}` |
| Headers | `Origin: https://dnschecked.com`, `Referer: https://dnschecked.com/`, `User-Agent: Mozilla/... Chrome/150.0.0.0` |
| 成功响应 | HTTP 200 + `{"status_code": 200, "domain": "...", "record_type": "A", "dns_server": "...", "results": ["1.2.3.4", ...]}` |
| 失败响应（域名不存在） | HTTP 4xx + `{"detail": "The DNS query name does not exist: <domain>."}` |
| 失败响应（其他） | HTTP 4xx + `{"detail": "..."}` |

---

## DNS 列表（内置常量，数据源：dnschecked.com）

### 大洲到 DNS 的映射

```python
CONTINENT_DNS: dict[str, list[str]] = {
    "global": [   # "global" 不是真大洲，是前端"全部"页的聚合
        "8.8.8.8", "208.67.222.220", "9.9.9.9", "204.117.214.10",
        "64.6.64.6", "185.228.169.9", "156.154.70.64",
        "208.91.112.53", "65.39.166.132",
        "223.5.5.5", "202.46.34.75",
        "1.1.1.1", "61.8.0.113",
        "195.46.39.39", "77.88.8.8",
        "212.98.231.69",
        "115.178.96.2",
        "148.235.82.66",
        "5.11.11.5",
        "38.54.96.87",
        "38.54.57.69",
        "38.54.8.230", "38.54.13.84",
        "80.196.100.209",
        "194.145.241.6",
        "80.80.81.81", "80.80.80.80",
        "212.230.255.1",
        "80.67.169.40",
        "38.54.23.99",
        "38.54.88.61",
        "38.54.119.67",
        "209.150.154.1",
        "202.46.34.75",   # KR（与 cn 重复但前端也列）
        "83.137.41.9",
        "185.228.168.9",
        "122.56.107.86",
        "185.83.212.30",
    ],
    "asia": [
        "223.5.5.5", "202.46.34.75",   # CN: 阿里云 + 深圳
        "115.178.96.2", "103.194.240.35", "103.99.150.10",  # IN
        "112.133.219.34", "164.100.138.248", "112.133.192.89",
        "38.54.96.87", "211.25.206.147",  # MY
        "38.54.8.230",                      # AE
        "38.54.23.99",                      # HK
        "38.54.88.61", "202.248.37.74", "202.248.20.133", "210.227.116.101",  # JP
        "38.54.119.67", "139.59.219.245", "103.86.99.100",  # SG
        "209.150.154.1", "125.209.116.22",  # PK
        "202.46.34.75", "168.126.63.1",     # KR
        "114.130.5.6", "103.157.237.34",   # BD
        "212.98.231.69",                    # TR
    ],
    "africa": ["5.11.11.5", "196.15.170.131"],
    "antarctica": [],   # 极地无 DNS
    "europe": [
        "80.67.169.40", "83.145.86.7", "46.105.55.84", "80.67.169.12",  # FR
        "82.96.64.2", "81.27.162.100", "195.243.214.4", "194.172.160.4",  # DE
        "139.18.25.33", "82.193.241.125",                                # DE
        "194.145.241.6", "194.145.240.6",                                # GB
        "80.80.81.81", "193.58.204.59", "185.107.80.84", "80.80.80.80",  # NL
        "87.213.100.113", "213.125.105.234",
        "194.209.157.109",                                                # CH
        "212.230.255.1", "89.29.128.250", "62.81.238.230", "195.235.225.10",  # ES
        "84.236.142.130",                                                  # ES
        "83.137.41.9",                                                     # AT
        "185.228.168.9",                                                   # IE
        "185.83.212.30",                                                   # PT
        "195.46.39.39", "176.103.130.130", "213.135.113.250", "212.122.4.2",  # RU
        "77.88.8.8", "212.96.218.97", "213.248.45.60", "83.149.17.52", "176.114.200.193",
        "80.196.100.209",                                                  # DK
    ],
    "north-america": [
        "8.8.8.8", "38.60.205.207", "38.54.6.178",                         # US
        "208.67.222.220", "9.9.9.9", "204.117.214.10",
        "64.6.64.6", "185.228.169.9", "205.171.202.66", "156.154.70.64",
        "208.91.112.53", "65.39.166.132",                                  # CA
        "148.235.82.66", "200.56.224.11",                                  # MX
    ],
    "oceania": [
        "1.1.1.1", "61.8.0.113", "139.130.4.4",                            # AU
        "223.165.64.97", "122.56.107.86",                                  # NZ
    ],
    "south-america": [
        "38.54.57.69", "187.6.84.178", "200.221.11.101", "189.125.18.5",   # BR
        "189.126.192.4",
    ],
}
```

### 国家代码到 DNS 的映射（从 JS 提取，覆盖页面"国家"列表）

```python
COUNTRY_DNS: dict[str, list[str]] = {
    "us": ["8.8.8.8", "38.60.205.207", "38.54.6.178", "208.67.222.220", "9.9.9.9",
           "204.117.214.10", "64.6.64.6", "185.228.169.9", "205.171.202.66", "156.154.70.64"],
    "cn": ["223.5.5.5", "202.46.34.75"],
    "ru": ["195.46.39.39", "176.103.130.130", "213.135.113.250", "212.122.4.2",
           "77.88.8.8", "212.96.218.97", "213.248.45.60", "83.149.17.52", "176.114.200.193"],
    "tr": ["212.98.231.69"],
    "in": ["115.178.96.2", "103.194.240.35", "103.99.150.10", "112.133.219.34",
           "164.100.138.248", "112.133.192.89"],
    "mx": ["148.235.82.66", "200.56.224.11"],
    "za": ["5.11.11.5", "196.15.170.131"],
    "my": ["38.54.96.87", "211.25.206.147"],
    "br": ["38.54.57.69", "187.6.84.178", "200.221.11.101", "189.125.18.5", "189.126.192.4"],
    "ae": ["38.54.8.230"],
    "de": ["38.54.13.84", "82.96.64.2", "81.27.162.100", "195.243.214.4",
           "194.172.160.4", "139.18.25.33", "82.193.241.125"],
    "hk": ["38.54.23.99"],
    "jp": ["38.54.88.61", "202.248.37.74", "202.248.20.133", "210.227.116.101"],
    "sg": ["38.54.119.67", "139.59.219.245", "103.86.99.100"],
    "ca": ["208.91.112.53", "65.39.166.132"],
    "pk": ["209.150.154.1", "125.209.116.22"],
    "kr": ["202.46.34.75", "168.126.63.1"],
    "bd": ["114.130.5.6", "103.157.237.34"],
    "dk": ["80.196.100.209"],
    "gb": ["194.145.241.6", "194.145.240.6"],
    "nl": ["80.80.81.81", "193.58.204.59", "185.107.80.84", "80.80.80.80",
           "87.213.100.113", "213.125.105.234"],
    "fr": ["80.67.169.40", "83.145.86.7", "46.105.55.84", "80.67.169.12"],
    "at": ["83.137.41.9"],
    "ie": ["185.228.168.9"],
    "nz": ["223.165.64.97", "122.56.107.86"],
    "pt": ["185.83.212.30"],
    "es": ["212.230.255.1", "89.29.128.250", "62.81.238.230", "195.235.225.10", "84.236.142.130"],
    "ch": ["194.209.157.109"],
}
```

> 数据源注释：`https://dnschecked.com/_next/static/chunks/913-5c5215ba2da48371.js` 的 `n.Z` 数组（90+ 条记录），按 `countryCode` + `continent` 分组得到。

---

## Task 1: 替换 provider 实现

**Files:**
- Create: `src/dnsprobe/providers/dnschecked.py`（含内置 `CONTINENT_DNS` / `COUNTRY_DNS` 常量 + `DnscheckedResolver` 类）
- Remove: `src/dnsprobe/providers/toolhelper.py`
- Modify: `src/dnsprobe/_bootstrap.py`（import 指向 dnschecked）
- Modify: `config.yml`（`name: toolhelper` → `name: dnschecked`，`extra:` 加 `continents: [north-america]` + `countries: []`）

**Interfaces:**
- Consumes: `BaseResolver`, `ResolverConfig`, `ResolverError`
- Produces:
  - `dnschecked.providers.dnschecked.DnscheckedResolver.resolve(domain, cfg) -> list[str]`
  - `cfg.extra.continents: list[str]`（可选，默认 `[north-america]`）
  - `cfg.extra.countries: list[str]`（可选，默认 `[]`）
  - 行为：合并 continents + countries 列表中的 DNS 去重，并行查所有 DNS，取所有 OK 响应的 `results[*]` 并集 + 去重

**Step 1: 写失败测试（替换 toolhelper 测试）**

完整替换 `tests/test_resolver.py` 中所有 `test_toolhelper_*` 函数 + `test_register_builtin_providers_*` 函数为以下 5 个测试 + 1 个注册测试：

```python
def test_dnschecked_resolver_returns_ips_on_success(mocker):
    """单个 DNS 200 + results 非空 → 返回 IP 列表。"""
    cfg = ResolverConfig(name="dnschecked", upstream_dns=[], extra={"continents": ["cn"]})
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
    cfg = ResolverConfig(name="dnschecked", upstream_dns=[], extra={"continents": ["cn"]})
    mock_post = mocker.patch(
        "dnsprobe.providers.dnschecked.requests.post",
        return_value=mocker.Mock(status_code=200, json=lambda: {"status_code": 200, "results": []}),
    )
    r = DnscheckedResolver(cfg)
    r.resolve("avatars.githubusercontent.com", cfg)

    # 所有 DNS 调用都验证 body + headers（这里只取第一个 call）
    call = mock_post.call_args_list[0]
    assert call.kwargs["json"] == {
        "domain": "avatars.githubusercontent.com",
        "record_type": "A",
        "dns_server": "223.5.5.5",
    }
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
    from dnsprobe.providers.dnschecked import DnscheckedResolver
    assert get("dnschecked") is DnscheckedResolver


def test_register_builtin_providers_adds_dnschecked_to_registry():
    _REGISTRY.pop("dnschecked", None)
    register_builtin_providers()
    assert "dnschecked" in _REGISTRY
    assert _REGISTRY["dnschecked"].__name__ == "DnscheckedResolver"
```

顶部 import 区：
```python
from dnsprobe._bootstrap import register_builtin_providers
from dnsprobe.providers.dnschecked import DnscheckedResolver
from dnsprobe.registry import register, get, discover_plugins, _REGISTRY
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError
```

并删除：
- `from dnsprobe.providers.toolhelper import ToolhelperResolver`
- 所有 `test_toolhelper_*` 函数

fixture 改：
```python
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
```

**Step 2: 跑测试确认失败（dnschecked 模块不存在）**

```bash
python -m pytest tests/test_resolver.py -v
```

Expected: 7 个 dnschecked 测试 FAIL（`ModuleNotFoundError: No module named 'dnsprobe.providers.dnschecked'`）。

**Step 3: 实现 `src/dnsprobe/providers/dnschecked.py`**

完整内容：

```python
"""调用 https://api.dnschecked.com/query_dns 解析域名。

支持按大洲/国家批量配置上游 DNS，并行查所有 DNS 后合并 results 取并集。
DNS 列表内置，数据源：https://dnschecked.com/_next/static/chunks/913-5c5215ba2da48371.js
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import requests

from dnsprobe.registry import register
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError

_API = "https://api.dnschecked.com/query_dns"
_TIMEOUT = 10
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://dnschecked.com",
    "Referer": "https://dnschecked.com/",
}


# 大洲 → DNS 列表（"global" 不是真大洲，是前端"全部"页的聚合）
CONTINENT_DNS: dict[str, list[str]] = {
    "global": [
        "8.8.8.8", "208.67.222.220", "9.9.9.9", "204.117.214.10",
        "64.6.64.6", "185.228.169.9", "156.154.70.64",
        "208.91.112.53", "65.39.166.132",
        "223.5.5.5", "202.46.34.75",
        "1.1.1.1", "61.8.0.113",
        "195.46.39.39", "77.88.8.8",
        "212.98.231.69",
        "115.178.96.2",
        "148.235.82.66",
        "5.11.11.5",
        "38.54.96.87",
        "38.54.57.69",
        "38.54.8.230", "38.54.13.84",
        "80.196.100.209",
        "194.145.241.6",
        "80.80.81.81", "80.80.80.80",
        "212.230.255.1",
        "80.67.169.40",
        "38.54.23.99",
        "38.54.88.61",
        "38.54.119.67",
        "209.150.154.1",
        "83.137.41.9",
        "185.228.168.9",
        "122.56.107.86",
        "185.83.212.30",
    ],
    "asia": [
        "223.5.5.5", "202.46.34.75",
        "115.178.96.2", "103.194.240.35", "103.99.150.10",
        "112.133.219.34", "164.100.138.248", "112.133.192.89",
        "38.54.96.87", "211.25.206.147",
        "38.54.8.230",
        "38.54.23.99",
        "38.54.88.61", "202.248.37.74", "202.248.20.133", "210.227.116.101",
        "38.54.119.67", "139.59.219.245", "103.86.99.100",
        "209.150.154.1", "125.209.116.22",
        "202.46.34.75", "168.126.63.1",
        "114.130.5.6", "103.157.237.34",
        "212.98.231.69",
    ],
    "africa": ["5.11.11.5", "196.15.170.131"],
    "antarctica": [],
    "europe": [
        "80.67.169.40", "83.145.86.7", "46.105.55.84", "80.67.169.12",
        "82.96.64.2", "81.27.162.100", "195.243.214.4", "194.172.160.4",
        "139.18.25.33", "82.193.241.125",
        "194.145.241.6", "194.145.240.6",
        "80.80.81.81", "193.58.204.59", "185.107.80.84", "80.80.80.80",
        "87.213.100.113", "213.125.105.234",
        "194.209.157.109",
        "212.230.255.1", "89.29.128.250", "62.81.238.230", "195.235.225.10",
        "84.236.142.130",
        "83.137.41.9",
        "185.228.168.9",
        "185.83.212.30",
        "195.46.39.39", "176.103.130.130", "213.135.113.250", "212.122.4.2",
        "77.88.8.8", "212.96.218.97", "213.248.45.60", "83.149.17.52", "176.114.200.193",
        "80.196.100.209",
    ],
    "north-america": [
        "8.8.8.8", "38.60.205.207", "38.54.6.178",
        "208.67.222.220", "9.9.9.9", "204.117.214.10",
        "64.6.64.6", "185.228.169.9", "205.171.202.66", "156.154.70.64",
        "208.91.112.53", "65.39.166.132",
        "148.235.82.66", "200.56.224.11",
    ],
    "oceania": [
        "1.1.1.1", "61.8.0.113", "139.130.4.4",
        "223.165.64.97", "122.56.107.86",
    ],
    "south-america": [
        "38.54.57.69", "187.6.84.178", "200.221.11.101", "189.125.18.5",
        "189.126.192.4",
    ],
}


# 国家代码 → DNS 列表
COUNTRY_DNS: dict[str, list[str]] = {
    "us": ["8.8.8.8", "38.60.205.207", "38.54.6.178", "208.67.222.220", "9.9.9.9",
           "204.117.214.10", "64.6.64.6", "185.228.169.9", "205.171.202.66", "156.154.70.64"],
    "cn": ["223.5.5.5", "202.46.34.75"],
    "ru": ["195.46.39.39", "176.103.130.130", "213.135.113.250", "212.122.4.2",
           "77.88.8.8", "212.96.218.97", "213.248.45.60", "83.149.17.52", "176.114.200.193"],
    "tr": ["212.98.231.69"],
    "in": ["115.178.96.2", "103.194.240.35", "103.99.150.10", "112.133.219.34",
           "164.100.138.248", "112.133.192.89"],
    "mx": ["148.235.82.66", "200.56.224.11"],
    "za": ["5.11.11.5", "196.15.170.131"],
    "my": ["38.54.96.87", "211.25.206.147"],
    "br": ["38.54.57.69", "187.6.84.178", "200.221.11.101", "189.125.18.5", "189.126.192.4"],
    "ae": ["38.54.8.230"],
    "de": ["38.54.13.84", "82.96.64.2", "81.27.162.100", "195.243.214.4",
           "194.172.160.4", "139.18.25.33", "82.193.241.125"],
    "hk": ["38.54.23.99"],
    "jp": ["38.54.88.61", "202.248.37.74", "202.248.20.133", "210.227.116.101"],
    "sg": ["38.54.119.67", "139.59.219.245", "103.86.99.100"],
    "ca": ["208.91.112.53", "65.39.166.132"],
    "pk": ["209.150.154.1", "125.209.116.22"],
    "kr": ["202.46.34.75", "168.126.63.1"],
    "bd": ["114.130.5.6", "103.157.237.34"],
    "dk": ["80.196.100.209"],
    "gb": ["194.145.241.6", "194.145.240.6"],
    "nl": ["80.80.81.81", "193.58.204.59", "185.107.80.84", "80.80.80.80",
           "87.213.100.113", "213.125.105.234"],
    "fr": ["80.67.169.40", "83.145.86.7", "46.105.55.84", "80.67.169.12"],
    "at": ["83.137.41.9"],
    "ie": ["185.228.168.9"],
    "nz": ["223.165.64.97", "122.56.107.86"],
    "pt": ["185.83.212.30"],
    "es": ["212.230.255.1", "89.29.128.250", "62.81.238.230", "195.235.225.10", "84.236.142.130"],
    "ch": ["194.209.157.109"],
}


def _collect_dns(cfg: ResolverConfig) -> list[str]:
    """从 cfg.extra.continents + cfg.extra.countries 收集 DNS 列表（去重保序）。"""
    continents = cfg.extra.get("continents", ["north-america"])
    countries = cfg.extra.get("countries", [])
    if not isinstance(continents, list) or not isinstance(countries, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for ip in (CONTINENT_DNS.get(c, []) for c in continents):
        for x in ip:
            if x not in seen:
                seen.add(x)
                out.append(x)
    for ip in (COUNTRY_DNS.get(c, []) for c in countries):
        for x in ip:
            if x not in seen:
                seen.add(x)
                out.append(x)
    return out


def _query_one(dns_server: str, domain: str) -> list[str]:
    """调用 API 查询一个 DNS，返回 results IP 列表（失败返回空）。"""
    try:
        resp = requests.post(
            _API,
            json={"domain": domain, "record_type": "A", "dns_server": dns_server},
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        payload: dict[str, Any] = resp.json()
        return list(payload.get("results") or [])
    except Exception:
        return []


@register("dnschecked")
class DnscheckedResolver(BaseResolver):
    """通过 dnschecked.com query_dns API 解析 A 记录。

    配置 `extra.continents` 和 `extra.countries` 选择要并行查询的 DNS。
    默认 `continents=["north-america"]`（8.8.8.8 / Cloudflare / OpenDNS / Quad9 / VeriSign 等美区权威 DNS）。
    所有 DNS 并行查，结果取并集 + 去重。
    """

    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        dns_list = _collect_dns(cfg)
        if not dns_list:
            raise ResolverError(
                f"dnschecked: no DNS configured (continents={cfg.extra.get('continents')!r}, "
                f"countries={cfg.extra.get('countries')!r})"
            )

        with ThreadPoolExecutor(max_workers=len(dns_list)) as pool:
            futures = [pool.submit(_query_one, dns, domain) for dns in dns_list]
            per_dns_ips = [f.result() for f in futures]

        seen: set[str] = set()
        out: list[str] = []
        for ips in per_dns_ips:
            for ip in ips:
                if ip not in seen:
                    seen.add(ip)
                    out.append(ip)

        if not out:
            raise ResolverError(
                f"dnschecked resolve failed for {domain}: all {len(dns_list)} DNS returned no results"
            )
        return out
```

**Step 4: 改 `src/dnsprobe/_bootstrap.py`**

```python
def register_builtin_providers() -> None:
    """触发内置 provider 的 @register 副作用。幂等。"""
    from dnsprobe.providers import dnschecked  # noqa: F401  # 触发 @register("dnschecked")
```

**Step 5: 改 `config.yml`**

```yaml
# 启用的 provider 列表（按顺序使用；name 必须是被 @register 注册过的）
providers:
  # dnschecked.com query_dns API 不接 dns 参数；upstream_dns 字段对本 provider 无意义
  # （schema 保留以兼容其他可能支持多上游 DNS 的 provider）
  - name: dnschecked
    enabled: true
    upstream_dns: []
    extra:                      # provider 私有参数（透传到 ResolverConfig.extra）
      # 按大洲/国家批量配置上游 DNS（数据源：dnschecked.com JS 数组）
      # 默认北美洲（8.8.8.8 / 1.1.1.1 / OpenDNS / Quad9 等）；可加 countries 补充特定国家
      continents: [north-america]
      countries: []
```

**Step 6: 跑 dnschecked 相关测试确认通过**

```bash
python -m pytest tests/test_resolver.py -v -k "dnschecked"
```

Expected: 7 个 dnschecked 测试全部 PASS。

---

## Task 2: 修 `tests/test_config.py` 字面

**Files:**
- Modify: `tests/test_config.py`（3 处 `name: toolhelper` → `name: dnschecked`）

**Step 1: 改 3 处字面**

```python
# test_load_config_minimal
"providers:\n  - name: dnschecked\n",

# test_load_config_enabled_defaults_true
"providers:\n  - name: dnschecked\n    upstream_dns: [1.1.1.1]\n",

# test_load_config_explicit_enabled_false
"providers:\n  - name: dnschecked\n    enabled: false\n",
```

并把期望的 `ProviderConfig(name="toolhelper")` 改为 `ProviderConfig(name="dnschecked")`。

**Step 2: 跑 test_config 确认通过**

```bash
python -m pytest tests/test_config.py -v
```

Expected: 7 个 config 测试全 PASS。

---

## Task 3: 删除 toolhelper.py + 跑全套测试

**Files:**
- Remove: `src/dnsprobe/providers/toolhelper.py`

**Step 1: git rm toolhelper.py**

```bash
git rm src/dnsprobe/providers/toolhelper.py
```

**Step 2: 跑全套测试**

```bash
python -m pytest tests/ -q
```

Expected: **54 passed**（53 既有 - 1 toolhelper 旧测试 + 7 新 dnschecked 测试 = 59，等等让我重算：旧 53 含 6 个 toolhelper 测试 + 2 个 bootstrap 测试 = 53；删 6 + 加 7 = +1；其他不变。应该是 54 passed。）

> 等等要更准：现有测试 54 个（含 toolhelper 5+1 + bootstrap 1+1 = 8 个 dnschecked 相关测试）。Task 1 删 6 + 加 7 = +1；54 + 1 = 55 passed。

**Step 3: 跑 dnsprobe 烟测**

```bash
python -m dnsprobe --help
```

Expected: argparse help 文本输出 `usage: dnsprobe`。

```bash
python -m dnsprobe
```

Expected: exit code 0 或 1（视 dnschecked API 可达性）；stdout 含 `[OK] 完成: .../43`。

**Step 4: 提交**

```bash
git add -A
git commit -m "feat: replace ToolhelperResolver with DnscheckedResolver using api.dnschecked.com"
```

---

## Task 4: 更新 hosts.txt + force push

**Files:**
- Modify: `hosts.txt`（由 `python -m dnsprobe` 重写）

**Step 1: 跑 dnsprobe 拿新 hosts.txt**

```bash
python -m dnsprobe
```

**Step 2: 提交 hosts.txt**

```bash
git add hosts.txt
git commit -m "chore: update hosts 2026-07-28"
```

**Step 3: force push**

```bash
git push --force-with-lease origin master
```

Expected: `+ <old>...<new> master -> master (forced update)`。

---

## 自查报告

### 1. Spec 覆盖

| Spec 章节 | 覆盖任务 |
|---|---|
| provider 替换（toolhelper → dnschecked） | Task 1 |
| 大洲/国家配置默认北美洲 | Task 1（config.yml `continents: [north-america]`） |
| 并行查 + 结果并集 | Task 1（ThreadPoolExecutor + 集合保序去重） |
| 测试覆盖 5 个成功/失败 + 1 个 bootstrap | Task 1 |

### 2. 占位符扫描

无 TBD / TODO / "implement later" / "类似 Task N" 占位符。

### 3. 类型一致性复核

- `dnschecked.providers.dnschecked.DnscheckedResolver.resolve(domain, cfg) -> list[str]`
- `dnschecked._collect_dns(cfg) -> list[str]`（内部）
- `dnschecked._query_one(dns_server, domain) -> list[str]`（内部）

### 4. 风险

- 远端 dnschecked.com API 没有 rate limit 文档，每次查 30+ DNS 触发 30+ HTTP 请求，GitHub Action 上限 60 次/小时，无风险。
- 极地大洲 `antarctica` 是空列表，配置 `continents: [antarctica]` 会抛 `ResolverError`——这是预期（提示用户无 DNS 可查）。
- 多个 DNS 返回相同 IP，逻辑已保序去重。
