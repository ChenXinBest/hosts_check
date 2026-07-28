# dnsprobe Plugin Development Skill

> **For AI agents:** This file describes how to create a new DNS resolver plugin for the `dnsprobe` project. Follow this guide when the user asks to "add a resolver", "create a plugin", "add a new DNS provider", or similar requests.

## Project Overview

`dnsprobe` resolves DNS for GitHub/TMDB domains and generates `hosts.txt` files to bypass DNS pollution. It uses a pluggable resolver architecture where each provider implements a common interface.

**Key paths:**

| Path | Purpose |
|---|---|
| `src/dnsprobe/` | Core package |
| `src/dnsprobe/resolver.py` | `BaseResolver` abstract class |
| `src/dnsprobe/registry.py` | `@register()` decorator + plugin discovery |
| `src/dnsprobe/providers/doh.py` | Built-in DoH resolver (reference implementation) |
| `src/dnsprobe/pipeline.py` | Main flow: resolve → dedup → reachability → write |
| `src/dnsprobe/reachability.py` | IP reachability check (HTTP HEAD or skip) |
| `src/dnsprobe/config.py` | YAML config loading |
| `plugins/` | User plugin directory (auto-scanned) |
| `tests/` | pytest test suite |
| `config.yml` | Runtime config |
| `domains.yml` | Domain list to resolve |

## Architecture

```
config.yml ──→ load_config() ──→ AppConfig
                                      │
                                      ▼
                              pipeline.run()
                                      │
                    ┌─────────────────┼──────────────────┐
                    ▼                 ▼                   ▼
            _build_resolver()   ThreadPoolExecutor   write_hosts_file()
                    │           (N domains parallel)
                    ▼
            resolver.resolve(domain, cfg)
                    │
                    ▼
            list[str] (IP addresses — IPv4 and/or IPv6)
```

Each resolver is called per-domain. Multiple resolvers run serially per domain; their results are merged and deduplicated by the pipeline.

## Creating a New Resolver Plugin

### Step 1: Create the plugin file

Create `plugins/<your_resolver_name>.py`. Files starting with `_` are ignored.

### Step 2: Implement the resolver

```python
"""<Your resolver description>."""
from __future__ import annotations

from dnsprobe.registry import register
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError


@register("my_resolver")
class MyResolver(BaseResolver):
    """Describe what this resolver does.

    Configuration via extra:
      - extra.some_key: description of what it controls
    """

    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        """Resolve a domain to a list of IP addresses.

        Args:
            domain: The domain name to resolve (e.g. "github.com")
            cfg: ResolverConfig with:
                - cfg.name: str — provider name from config.yml
                - cfg.upstream_dns: list[str] — upstream DNS servers (if applicable)
                - cfg.extra: dict — provider-specific config from config.yml extra: section

        Returns:
            list[str]: IP addresses (IPv4 and/or IPv6 strings).
                       Return empty list or raise ResolverError on failure.

        Raises:
            ResolverError: When resolution fails and no IPs can be returned.
        """
        # Your DNS resolution logic here
        ips: list[str] = []

        # Example: call an HTTP API
        # import requests
        # resp = requests.get(f"https://api.example.com/dns?domain={domain}")
        # ips = resp.json().get("addresses", [])

        if not ips:
            raise ResolverError(f"my_resolver: no results for {domain}")
        return ips
```

### Step 3: Register in config.yml

Add your resolver to `config.yml`:

```yaml
providers:
  - name: my_resolver        # Must match @register("my_resolver") name
    enabled: true
    upstream_dns: []          # Optional: upstream DNS servers
    extra:                    # Provider-specific config (passed as cfg.extra)
      some_key: some_value
```

### Step 4: Write tests

Create `tests/test_my_resolver.py` (or add to `tests/test_resolver.py`):

```python
from __future__ import annotations

import pytest
from unittest.mock import Mock

from dnsprobe.registry import _REGISTRY
from dnsprobe.resolver import ResolverConfig, ResolverError
from plugins.my_resolver import MyResolver


@pytest.fixture(autouse=True)
def _clean_registry():
    _REGISTRY.clear()
    yield
    _REGISTRY.clear()


def test_my_resolver_returns_ips_on_success(mocker):
    """Single successful resolution returns IP list."""
    cfg = ResolverConfig(name="my_resolver", upstream_dns=[], extra={})
    mocker.patch(
        "plugins.my_resolver.requests.get",
        return_value=Mock(status_code=200, json=lambda: {"addresses": ["1.2.3.4"]}),
    )
    r = MyResolver(cfg)
    assert r.resolve("github.com", cfg) == ["1.2.3.4"]


def test_my_resolver_raises_when_all_fail(mocker):
    """All failures → ResolverError."""
    cfg = ResolverConfig(name="my_resolver", upstream_dns=[], extra={})
    mocker.patch(
        "plugins.my_resolver.requests.get",
        side_effect=Exception("network error"),
    )
    r = MyResolver(cfg)
    with pytest.raises(ResolverError):
        r.resolve("github.com", cfg)


def test_my_resolver_is_registered():
    """@register decorator puts class in registry."""
    assert _REGISTRY.get("my_resolver") is MyResolver
```

### Step 5: Run tests

```bash
python -m pytest tests/ -v
```

## Interface Contract

### BaseResolver

```python
class BaseResolver(ABC):
    name: ClassVar[str] = ""   # Set by @register decorator

    def __init__(self, cfg: ResolverConfig) -> None:
        self.cfg = cfg

    @abstractmethod
    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        """Return A/AAAA record IPs. Raise ResolverError or return [] on failure."""
        ...
```

### ResolverConfig

```python
@dataclass
class ResolverConfig:
    name: str            # Provider name from config.yml
    upstream_dns: list[str]  # Upstream DNS servers (provider decides how to use)
    extra: dict          # All provider-specific config from config.yml extra:
```

### Key rules

1. **Return `list[str]`** — plain IP address strings (e.g. `"1.2.3.4"`, `"2001:db8::1"`)
2. **Support both IPv4 and IPv6** — return A records as IPv4 strings, AAAA records as IPv6 strings
3. **Raise `ResolverError`** when all resolution attempts fail (not generic `Exception`)
4. **Handle errors gracefully** — catch network errors, timeouts, etc. inside `resolve()`
5. **Use `cfg.extra`** for all provider-specific configuration
6. **Use `cfg.upstream_dns`** if your resolver supports configurable upstream DNS servers

## IPv6 Support

The project supports both IPv4 (A records) and IPv6 (AAAA records).

### In your resolver

- Return IPv6 addresses as standard strings: `"2001:db8::1"`, `"fe80::1"`
- If using dnspython, query AAAA with `dns.rdatatype.AAAA`
- The pipeline handles deduplication of mixed IPv4/IPv6 results

### In reachability checks

The `_format_host_for_url()` helper in `reachability.py` automatically wraps IPv6 in brackets for HTTP requests: `http://[2001:db8::1]`.

### Built-in DoH provider

The built-in DoH provider supports `record_types` config:

```yaml
extra:
  record_types: ["A"]          # IPv4 only (default)
  # record_types: ["AAAA"]     # IPv6 only
  # record_types: ["A", "AAAA"] # Dual-stack
```

## HTTP Proxy Support

The top-level `http_proxy` in config.yml is automatically injected into `cfg.extra["http_proxy"]`. Use it for HTTP requests:

```python
def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
    http_proxy = cfg.extra.get("http_proxy", "")
    proxies = {"http": http_proxy, "https": http_proxy} if http_proxy else None
    resp = requests.get(url, proxies=proxies, timeout=10)
```

For per-server proxy control (like the DoH provider), add a `proxy: bool` field to each server config and only apply proxy when `server["proxy"]` is True.

## Reference: Built-in DoH Provider

The DoH provider (`src/dnsprobe/providers/doh.py`) is the reference implementation. Key patterns:

- **Parallel queries**: Uses `ThreadPoolExecutor` to query all DNS servers concurrently
- **Weight-based ordering**: Servers sorted by weight (high first); results merged in order
- **Per-server proxy**: Each server has `proxy: true/false` to control proxy usage
- **Graceful failure**: Individual server failures don't block others
- **Error logging**: Failed servers print `[!] server_name: error` to stdout

## Complete Plugin Example: HTTP API Resolver

```python
"""Resolve domains via example.com DNS API."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import requests

from dnsprobe.registry import register
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError

_API = "https://api.example.com/resolve"
_TIMEOUT = 10


def _query_one(dns_server: str, domain: str, http_proxy: str = "") -> list[str]:
    """Query a single upstream DNS via the API."""
    proxies = {"http": http_proxy, "https": http_proxy} if http_proxy else None
    try:
        resp = requests.get(
            _API,
            params={"domain": domain, "dns": dns_server},
            timeout=_TIMEOUT,
            proxies=proxies,
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("addresses", [])
    except Exception:
        return []


@register("example_api")
class ExampleApiResolver(BaseResolver):
    """Resolve via api.example.com. Supports multiple upstream DNS in parallel.

    extra:
      dns_servers: list of upstream DNS IPs (default: ["8.8.8.8", "1.1.1.1"])
    """

    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        dns_list = cfg.extra.get("dns_servers") or ["8.8.8.8", "1.1.1.1"]
        http_proxy = cfg.extra.get("http_proxy", "")

        with ThreadPoolExecutor(max_workers=len(dns_list)) as pool:
            futures = [
                pool.submit(_query_one, dns, domain, http_proxy)
                for dns in dns_list
            ]
            per_dns = [f.result() for f in futures]

        seen: set[str] = set()
        out: list[str] = []
        for ips in per_dns:
            for ip in ips:
                if ip not in seen:
                    seen.add(ip)
                    out.append(ip)

        if not out:
            raise ResolverError(
                f"example_api: all {len(dns_list)} DNS returned no results for {domain}"
            )
        return out
```

Corresponding `config.yml`:

```yaml
providers:
  - name: example_api
    enabled: true
    upstream_dns: []
    extra:
      dns_servers:
        - "8.8.8.8"
        - "1.1.1.1"
```

## Complete Plugin Example: DoH (DNS-over-HTTPS)

```python
"""Resolve domains via DNS-over-HTTPS (DoH)."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

import dns.message
import dns.rdatatype
import requests

from dnsprobe.registry import register
from dnsprobe.resolver import BaseResolver, ResolverConfig, ResolverError

_TIMEOUT = 10


def _doh_query(url: str, domain: str, rdtype: int, http_proxy: str = "") -> list[str]:
    """Send a DoH GET request and parse the response."""
    query = dns.message.make_query(domain, rdtype).to_wire()
    qdata = base64.urlsafe_b64encode(query).rstrip(b"=").decode()
    full_url = f"{url.rstrip('/')}?{urlencode({'dns': qdata})}"
    proxies = {"http": http_proxy, "https": http_proxy} if http_proxy else None
    try:
        resp = requests.get(
            full_url,
            headers={"Accept": "application/dns-message"},
            timeout=_TIMEOUT,
            proxies=proxies,
        )
        if resp.status_code != 200:
            return []
        msg = dns.message.from_wire(resp.content)
        return [
            rdata.address
            for rrset in msg.answer
            if rrset.rdtype == rdtype
            for rdata in rrset
        ]
    except Exception:
        return []


@register("my_doh")
class MyDoHResolver(BaseResolver):
    """DNS-over-HTTPS resolver.

    extra:
      endpoint: DoH URL (default: "https://dns.google/dns-query")
      record_types: ["A"] | ["AAAA"] | ["A", "AAAA"] (default: ["A"])
    """

    def resolve(self, domain: str, cfg: ResolverConfig) -> list[str]:
        endpoint = cfg.extra.get("endpoint", "https://dns.google/dns-query")
        record_types = cfg.extra.get("record_types", ["A"])
        http_proxy = cfg.extra.get("http_proxy", "")

        rdtype_map = {"A": dns.rdatatype.A, "AAAA": dns.rdatatype.AAAA}
        rdtypes = [rdtype_map[r.upper()] for r in record_types if r.upper() in rdtype_map]
        if not rdtypes:
            rdtypes = [dns.rdatatype.A]

        with ThreadPoolExecutor(max_workers=len(rdtypes)) as pool:
            futures = [
                pool.submit(_doh_query, endpoint, domain, rt, http_proxy)
                for rt in rdtypes
            ]
            per_type = [f.result() for f in futures]

        seen: set[str] = set()
        out: list[str] = []
        for ips in per_type:
            for ip in ips:
                if ip not in seen:
                    seen.add(ip)
                    out.append(ip)

        if not out:
            raise ResolverError(f"my_doh: no results for {domain}")
        return out
```

## Testing Checklist

When creating a new resolver, ensure tests cover:

- [ ] **Success case**: resolver returns expected IPs on successful resolution
- [ ] **Failure case**: resolver raises `ResolverError` when all attempts fail
- [ ] **Partial failure**: resolver handles some servers failing gracefully
- [ ] **Registration**: `@register` decorator correctly registers the class
- [ ] **Config parsing**: resolver reads `cfg.extra` fields correctly
- [ ] **IPv6**: if supporting AAAA, test with IPv6 addresses
- [ ] **Proxy**: if using HTTP proxy, test proxy parameter passing

## Common Patterns

### Deduplication

The pipeline handles cross-resolver deduplication. Within your resolver, deduplicate if querying multiple servers:

```python
seen: set[str] = set()
out: list[str] = []
for ips in all_results:
    for ip in ips:
        if ip not in seen:
            seen.add(ip)
            out.append(ip)
```

### Parallel Queries

Use `ThreadPoolExecutor` for parallel HTTP/DNS queries:

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=len(targets)) as pool:
    futures = [pool.submit(query_fn, target) for target in targets]
    results = [f.result() for f in futures]
```

### Error Handling

Always catch exceptions inside `resolve()` — don't let them leak to the pipeline:

```python
try:
    resp = requests.get(url, timeout=10)
except requests.exceptions.Timeout:
    return []
except requests.exceptions.ConnectionError:
    return []
except Exception:
    return []
```

## Running the Project

```bash
# Install dependencies
pip install -r requirements.txt
pip install -e .

# Run
python -m dnsprobe

# Run tests
python -m pytest tests/ -v

# Run with custom config
python -m dnsprobe --config path/to/config.yml --domains path/to/domains.yml
```

## Project Conventions

- **Python**: 3.10+ (CI uses 3.12)
- **Package layout**: `src/dnsprobe/` (src layout)
- **Test framework**: pytest + pytest-mock
- **Commit style**: Conventional Commits, single commit per change
- **Config**: YAML, all secrets/proxies in local-only config (never commit credentials)
- **Logging**: `print()` to stdout for operational messages, `print(..., file=sys.stderr)` for errors
