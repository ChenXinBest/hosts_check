from __future__ import annotations

import datetime

from hosts_check.config import OutputConfig
from hosts_check.writer import write_hosts_file


def test_write_hosts_file_basic_format(tmp_path):
    cfg = OutputConfig(path=str(tmp_path / "hosts.txt"), keep_old_section=False)
    host_dict = {"a.example": ["1.1.1.1", "2.2.2.2"], "b.example": ["3.3.3.3"]}
    fixed = datetime.datetime(2026, 7, 23, 12, 0, 0)

    write_hosts_file(host_dict, cfg, now=fixed)

    content = (tmp_path / "hosts.txt").read_text(encoding="utf-8")
    expected = (
        "###start###\n"
        "1.1.1.1\ta.example\n"
        "2.2.2.2\ta.example\n"
        "3.3.3.3\tb.example\n"
        "###最后更新时间:2026-07-23 12:00:00###\n"
        "###end###\n"
    )
    assert content == expected


def test_write_hosts_file_empty_dict(tmp_path):
    cfg = OutputConfig(path=str(tmp_path / "hosts.txt"), keep_old_section=False)
    fixed = datetime.datetime(2026, 1, 1, 0, 0, 0)

    write_hosts_file({}, cfg, now=fixed)

    content = (tmp_path / "hosts.txt").read_text(encoding="utf-8")
    expected = (
        "###start###\n"
        "###最后更新时间:2026-01-01 00:00:00###\n"
        "###end###\n"
    )
    assert content == expected


def test_write_hosts_file_keep_old_section_strips_existing(tmp_path):
    hosts_file = tmp_path / "hosts.txt"
    hosts_file.write_text(
        "# user custom line 1\n"
        "# user custom line 2\n"
        "###start###\n"
        "9.9.9.9\told.example\n"
        "###最后更新时间:2020-01-01 00:00:00###\n"
        "###end###\n",
        encoding="utf-8",
    )

    cfg = OutputConfig(path=str(hosts_file), keep_old_section=True)
    host_dict = {"fresh.example": ["5.5.5.5"]}
    fixed = datetime.datetime(2026, 7, 23, 12, 0, 0)

    write_hosts_file(host_dict, cfg, now=fixed)

    content = hosts_file.read_text(encoding="utf-8")
    assert content.startswith("# user custom line 1\n# user custom line 2\n")
    assert "9.9.9.9" not in content
    assert "5.5.5.5\tfresh.example\n" in content
    assert "###最后更新时间:2026-07-23 12:00:00###" in content


def test_write_hosts_file_no_keep_old_section_writes_only_new(tmp_path):
    hosts_file = tmp_path / "hosts.txt"
    hosts_file.write_text(
        "###start###\n"
        "9.9.9.9\told.example\n"
        "###last###\n"
    )

    cfg = OutputConfig(path=str(hosts_file), keep_old_section=False)
    host_dict = {"fresh.example": ["5.5.5.5"]}
    fixed = datetime.datetime(2026, 7, 23, 12, 0, 0)

    write_hosts_file(host_dict, cfg, now=fixed)

    content = hosts_file.read_text(encoding="utf-8")
    assert "9.9.9.9" not in content
    assert content.startswith("###start###\n")
