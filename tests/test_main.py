"""dnsprobe.__main__ 的单元测试：argparse + main() 函数 + 错误分支。"""
from __future__ import annotations

from pathlib import Path

import pytest

from dnsprobe.__main__ import _parse_args, main


def test_parse_args_defaults():
    args = _parse_args([])
    assert args.config == "config.yml"
    assert args.domains is None


def test_parse_args_custom_paths():
    args = _parse_args(["--config", "c.yml", "--domains", "d.yml"])
    assert args.config == "c.yml"
    assert args.domains == "d.yml"


def test_main_returns_one_on_missing_config(tmp_path: Path, capsys: pytest.CaptureFixture):
    rc = main(["--config", str(tmp_path / "nope.yml")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "[×]" in err
    assert "config file not found" in err


def test_main_returns_one_on_pipeline_crash(tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture):
    (tmp_path / "config.yml").write_text("providers: []\n", encoding="utf-8")
    (tmp_path / "domains.yml").write_text("domains: []\n", encoding="utf-8")

    def boom(*args, **kwargs):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr("dnsprobe.__main__.run", boom)

    rc = main(["--config", str(tmp_path / "config.yml")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "[×] pipeline crashed" in err
    assert "simulated crash" in err


def test_main_passes_domains_path_through(tmp_path: Path, monkeypatch):
    captured: dict = {}

    def fake_run(config, plugins_dir):
        captured["domains"] = list(config.domains)
        return 0

    monkeypatch.setattr("dnsprobe.__main__.run", fake_run)

    (tmp_path / "config.yml").write_text("providers: []\n", encoding="utf-8")
    (tmp_path / "custom.yml").write_text(
        "domains:\n  - a.example\n", encoding="utf-8"
    )

    rc = main(
        [
            "--config",
            str(tmp_path / "config.yml"),
            "--domains",
            str(tmp_path / "custom.yml"),
        ]
    )
    assert rc == 0
    assert captured["domains"] == ["a.example"]
