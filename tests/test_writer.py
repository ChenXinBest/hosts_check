from __future__ import annotations

import datetime
from pathlib import Path

from dnsprobe import writer
from dnsprobe.config import OutputConfig
from dnsprobe.writer import write_hosts_file


def test_write_hosts_file_basic_format(tmp_path):
    cfg = OutputConfig(path=str(tmp_path / "hosts.txt"), keep_old_section=False)
    host_dict = {"a.example": ["1.1.1.1", "2.2.2.2"], "b.example": ["3.3.3.3"]}
    fixed = datetime.datetime(2026, 7, 23, 12, 0, 0)

    write_hosts_file(host_dict, cfg, now=fixed)

    content_bytes = (tmp_path / "hosts.txt").read_bytes()
    expected_bytes = (
        "###start###\n"
        "1.1.1.1\ta.example\n"
        "2.2.2.2\ta.example\n"
        "3.3.3.3\tb.example\n"
        "###最后更新时间:2026-07-23 12:00:00###\n"
        "###end###\n"
    ).encode("utf-8")
    assert content_bytes == expected_bytes


def test_write_hosts_file_empty_dict(tmp_path):
    cfg = OutputConfig(path=str(tmp_path / "hosts.txt"), keep_old_section=False)
    fixed = datetime.datetime(2026, 1, 1, 0, 0, 0)

    write_hosts_file({}, cfg, now=fixed)

    content_bytes = (tmp_path / "hosts.txt").read_bytes()
    expected_bytes = (
        "###start###\n"
        "###最后更新时间:2026-01-01 00:00:00###\n"
        "###end###\n"
    ).encode("utf-8")
    assert content_bytes == expected_bytes


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

    content_bytes = hosts_file.read_bytes()
    assert content_bytes.startswith(b"# user custom line 1\n# user custom line 2\n")
    assert b"9.9.9.9" not in content_bytes
    assert b"5.5.5.5\tfresh.example\n" in content_bytes
    assert "###最后更新时间:2026-07-23 12:00:00###".encode("utf-8") in content_bytes


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

    content_bytes = hosts_file.read_bytes()
    assert b"9.9.9.9" not in content_bytes
    assert content_bytes.startswith(b"###start###\n")


def test_write_hosts_file_atomic_write_uses_replace(tmp_path, monkeypatch):
    hosts_file = tmp_path / "hosts.txt"
    cfg = OutputConfig(path=str(hosts_file), keep_old_section=False)
    replace_calls = []
    real_replace = writer.os.replace

    def record_replace(source, destination):
        replace_calls.append((source, destination))
        real_replace(source, destination)

    monkeypatch.setattr(writer.os, "replace", record_replace)

    write_hosts_file({"fresh.example": ["5.5.5.5"]}, cfg)

    assert replace_calls == [(tmp_path / ".hosts.txt.tmp", hosts_file)]
    assert hosts_file.exists()
    assert not (tmp_path / ".hosts.txt.tmp").exists()


def test_write_hosts_file_cleans_up_tmp_on_failure(tmp_path, monkeypatch):
    hosts_file = tmp_path / "hosts.txt"
    cfg = OutputConfig(path=str(hosts_file), keep_old_section=False)
    tmp_file = tmp_path / ".hosts.txt.tmp"
    unlinked = []

    def fail_write_text(self, *args, **kwargs):
        raise OSError("disk full")

    def record_unlink(self, *args, **kwargs):
        unlinked.append((self, args, kwargs))

    monkeypatch.setattr(Path, "write_text", fail_write_text)
    monkeypatch.setattr(Path, "unlink", record_unlink)

    try:
        write_hosts_file({"fresh.example": ["5.5.5.5"]}, cfg)
    except OSError as exc:
        assert str(exc) == "disk full"
    else:
        raise AssertionError("write_hosts_file should raise the write error")

    assert unlinked == [(tmp_file, (), {"missing_ok": True})]


def test_write_hosts_file_strips_unmatched_marker_safely(tmp_path):
    hosts_file = tmp_path / "hosts.txt"
    old_content = "# user custom line\n###start###\n9.9.9.9\told.example\n"
    hosts_file.write_text(old_content, encoding="utf-8")
    cfg = OutputConfig(path=str(hosts_file), keep_old_section=True)
    fixed = datetime.datetime(2026, 7, 23, 12, 0, 0)

    write_hosts_file({"fresh.example": ["5.5.5.5"]}, cfg, now=fixed)

    content_bytes = hosts_file.read_bytes()
    expected_bytes = (
        old_content
        + "###start###\n"
        + "5.5.5.5\tfresh.example\n"
        + "###最后更新时间:2026-07-23 12:00:00###\n"
        + "###end###\n"
    ).encode("utf-8")
    assert content_bytes == expected_bytes