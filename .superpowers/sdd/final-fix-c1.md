# Final Fix C1 报告

## Status

PASS

## Diff summary

- `hosts_check/writer.py`
  - 新增 `os` 导入。
  - `_strip_old_section` 仅在 marker 成对且结构有效时剥离旧段；未配对或嵌套 marker 时原样保留旧内容。
  - `write_hosts_file` 在同目录写入隐藏临时文件 `.hosts.txt.tmp`，通过 `os.replace` 原子替换目标文件，并在异常或成功后清理临时文件。
- `tests/test_writer.py`
  - 新增原子替换路径验证。
  - 新增写入失败后的临时文件清理验证。
  - 新增未配对 start marker 的 graceful fallback 验证。

## Tests

- TDD RED：新增测试在旧实现上按预期失败（3 failed）。
- TDD GREEN：`python -m pytest tests/test_writer.py -k "atomic_write_uses_replace or cleans_up_tmp_on_failure or strips_unmatched_marker_safely" -v` → `3 passed`。
- 完整测试：`python -m pytest tests/ -v` → `35 passed in 0.15s`。
- 语法检查：`python -m compileall -q hosts_check tests` → PASS。
- `ruff` 与 `mypy` 未安装，无法执行项目 lint/typecheck 命令。

## 工作区说明

- `hosts.txt` 原有修改未纳入本 fix commit。
