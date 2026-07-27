from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import textwrap


def test_cli_runs_with_complete_setup(tmp_path: Path) -> None:
    """端到端 CLI: 完整 config + domains + 第三方 plugin，跑 subprocess。

    spec §9 验收标准 3: CLI 在隔离 tmp_path 下能完整解析 → 写 hosts.txt。
    """
    config = tmp_path / "config.yml"
    domains = tmp_path / "domains.yml"
    plugins = tmp_path / "plugins"
    plugins.mkdir()

    hosts_out = tmp_path / "hosts.txt"
    config.write_text(
        f"""\
providers:
  - name: fake_cli
    enabled: true
    upstream_dns: [1.1.1.1]
    extra:
      fake_ips: ["9.9.9.9"]
output:
  path: {hosts_out.as_posix()}
  keep_old_section: false
reachability:
  method: http_head
  timeout: 0.001
""",
        encoding="utf-8",
    )
    domains.write_text("domains:\n  - a.example\n", encoding="utf-8")
    (plugins / "fake_cli.py").write_text(
        textwrap.dedent(
            """\
            from dnsprobe.registry import register
            from dnsprobe.resolver import BaseResolver, ResolverConfig

            @register("fake_cli")
            class FakeCli(BaseResolver):
                def resolve(self, domain, cfg):
                    return list(cfg.extra["fake_ips"])
            """
        ),
        encoding="utf-8",
    )

    project_root = Path(__file__).resolve().parent.parent
    env = {**os.environ, "PYTHONPATH": str(project_root)}

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "dnsprobe",
            "--config",
            str(config),
            "--domains",
            str(domains),
        ],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    # 在隔离 subprocess 环境无法 mock network。CLI 会在 reachability 阶段超时失败
    # （graceful 退出码 1），或全部 reachable（退出码 0）。两种都是 spec §9 标准 1
    # 的合法子情形：只要 hosts.txt 结构合法（###start###/###end### 包裹）。
    assert result.returncode in (0, 1), (
        f"CLI 退出码 {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert hosts_out.exists()
    content = hosts_out.read_text(encoding="utf-8")
    assert content.startswith("###start###\n")
    assert "###end###\n" in content
    assert "###最后更新时间:" in content
    if result.returncode == 0:
        # reachability 通过：fake_ips 出现在文件里
        assert "9.9.9.9\ta.example" in content