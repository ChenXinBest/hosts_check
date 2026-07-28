"""生成 hosts.txt（迁移自 DailyJob.py:85-94 与 DnsParse.py:66-105）。"""
from __future__ import annotations

import datetime
import os
from pathlib import Path

from dnsprobe.config import OutputConfig

_START = "###start###"
_END = "###end###"
_TIME_PREFIX = "###最后更新时间:"
_TIME_SUFFIX = "###"


def _format_now(now: datetime.datetime) -> str:
    return now.strftime("%Y-%m-%d %H:%M:%S")


def _strip_old_section(content: str) -> str:
    """剥离 ###start### 与 ###end### 之间的全部内容，保留其外的所有行。

    行结束符统一标准化为 LF，避免跨平台差异污染字节级输出。
    未配对的 marker 也走 normalize 路径，保证字节级输出稳定。
    """
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines(keepends=True)
    out: list[str] = []
    in_section = False
    for line in lines:
        if _START in line:
            if in_section:
                return normalized
            in_section = True
            continue
        if _END in line:
            if not in_section:
                return normalized
            in_section = False
            continue
        if not in_section:
            out.append(line)
    if in_section:
        return normalized
    return "".join(out)


def _render_body(host_dict: dict[str, list[str]], now: datetime.datetime) -> str:
    lines = [_START + "\n"]
    for host, ips in host_dict.items():
        for ip in ips:
            lines.append(f"{ip}\t{host}\n")
    lines.append(f"{_TIME_PREFIX}{_format_now(now)}{_TIME_SUFFIX}\n")
    lines.append(_END + "\n")
    return "".join(lines)


def write_hosts_file(
    host_dict: dict[str, list[str]],
    cfg: OutputConfig,
    now: datetime.datetime | None = None,
) -> None:
    """把 host_dict 写入 cfg.path。

    若 cfg.keep_old_section=True 且文件已存在，先剥离旧 ###start###/###end### 段。
    """
    if now is None:
        now = datetime.datetime.now()

    path = Path(cfg.path)
    prefix = ""
    if cfg.keep_old_section and path.exists():
        prefix = _strip_old_section(path.read_text(encoding="utf-8"))

    body = _render_body(host_dict, now)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".{path.name}.tmp"
    try:
        tmp_path.write_text(prefix + body, encoding="utf-8", newline="")
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)
