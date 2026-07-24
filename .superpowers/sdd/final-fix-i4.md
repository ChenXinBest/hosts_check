# Status

PASS

# Diff summary

- `check_ip_reachable()` now accepts `method`, rejects unsupported values with `ValueError`, and preserves backward compatibility with the default `http_head` method.
- Restored per-IP `[OK]`/`[×]` logs for HTTP results, timeouts, connection errors, and unexpected exceptions.
- `filter_reachable()` now passes both `cfg.timeout` and `cfg.method` to the reachability check.
- Added regression tests for unknown methods, success logging, and timeout logging.

# Tests

- `python -m pytest tests/ -v`
- Result: `45 passed in 0.16s`
- `python -m compileall -q hosts_check tests`
- Result: PASS
- `python -m ruff check hosts_check tests`
- Result: unavailable; `ruff` is not installed.
- `python -m mypy hosts_check tests`
- Result: unavailable; `mypy` is not installed.
