from __future__ import annotations

import pytest
import requests

from dnsprobe.config import ReachabilityConfig
from dnsprobe.reachability import check_ip_reachable, filter_reachable


def test_check_ip_reachable_true_on_2xx(mocker):
    mocker.patch(
        "dnsprobe.reachability.requests.head",
        return_value=mocker.Mock(status_code=200),
    )
    assert check_ip_reachable("1.2.3.4", "example.com", timeout=5.0) is True


def test_check_ip_reachable_true_on_3xx(mocker):
    mocker.patch(
        "dnsprobe.reachability.requests.head",
        return_value=mocker.Mock(status_code=301),
    )
    assert check_ip_reachable("1.2.3.4", "example.com", timeout=5.0) is True


def test_check_ip_reachable_false_on_4xx(mocker):
    mocker.patch(
        "dnsprobe.reachability.requests.head",
        return_value=mocker.Mock(status_code=404),
    )
    assert check_ip_reachable("1.2.3.4", "example.com", timeout=5.0) is False


def test_check_ip_reachable_false_on_timeout(mocker):
    mocker.patch(
        "dnsprobe.reachability.requests.head",
        side_effect=requests.exceptions.Timeout(),
    )
    assert check_ip_reachable("1.2.3.4", "example.com", timeout=5.0) is False


def test_check_ip_reachable_false_on_connection_error(mocker):
    mocker.patch(
        "dnsprobe.reachability.requests.head",
        side_effect=requests.exceptions.ConnectionError(),
    )
    assert check_ip_reachable("1.2.3.4", "example.com", timeout=5.0) is False


def test_filter_reachable_keeps_only_responding_ips(mocker):
    responses = [
        mocker.Mock(status_code=200),  # reachable
        mocker.Mock(status_code=500),  # not reachable
        mocker.Mock(status_code=302),  # reachable
    ]
    mocker.patch(
        "dnsprobe.reachability.requests.head",
        side_effect=responses,
    )
    cfg = ReachabilityConfig(method="http_head", timeout=5.0)
    result = filter_reachable(["1.1.1.1", "2.2.2.2", "3.3.3.3"], "example.com", cfg)
    assert result == ["1.1.1.1", "3.3.3.3"]


def test_check_ip_reachable_rejects_unknown_method():
    with pytest.raises(ValueError, match="unsupported reachability method"):
        check_ip_reachable("1.2.3.4", "example.com", method="ping")


def test_check_ip_reachable_method_none_skips_check():
    """method='none' 直接返回 True，不发请求。"""
    assert check_ip_reachable("1.2.3.4", "example.com", method="none") is True


def test_check_ip_reachable_logs_success_to_stdout(mocker, capsys):
    mocker.patch(
        "dnsprobe.reachability.requests.head",
        return_value=mocker.Mock(status_code=200),
    )

    assert check_ip_reachable("1.2.3.4", "example.com") is True
    assert "[OK]" in capsys.readouterr().out


def test_check_ip_reachable_logs_timeout_to_stderr_or_stdout(mocker, capsys):
    mocker.patch(
        "dnsprobe.reachability.requests.head",
        side_effect=requests.exceptions.Timeout(),
    )

    assert check_ip_reachable("1.2.3.4", "example.com") is False
    captured = capsys.readouterr()
    assert "连接超时" in captured.out or "连接超时" in captured.err
