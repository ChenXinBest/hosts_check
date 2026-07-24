from __future__ import annotations


def test_main_returns_one_on_pipeline_crash(tmp_path, monkeypatch, mocker, capsys):
    from hosts_check import __main__

    monkeypatch.chdir(tmp_path)
    mocker.patch("hosts_check.__main__.load_config", return_value=object())
    mocker.patch(
        "hosts_check.__main__.run",
        side_effect=RuntimeError("boom"),
    )

    rc = __main__.main(["--config", "config.yml"])

    assert rc == 1
    assert "[×] pipeline crashed: boom" in capsys.readouterr().err
