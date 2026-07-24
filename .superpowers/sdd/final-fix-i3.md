# Status

PASS

# Diff summary

- `_build_resolver_instances()` now logs and skips providers whose registry lookup, config creation, or resolver construction raises an exception.
- `run()` now logs and skips unexpected resolver exceptions while preserving the existing `ResolverError` log format.
- `main()` now converts unexpected pipeline crashes into exit code 1 with a concise stderr message.
- Added regression tests for unexpected resolve errors, unavailable providers, and CLI crash isolation.

# Tests

- `python -m pytest tests/ -v`
- Result: `42 passed in 0.19s` (the suite contained 39 tests before the 3 requested additions, so the actual total is 42 rather than the anticipated 41).
- `python -m compileall -q hosts_check tests`
- Result: PASS
