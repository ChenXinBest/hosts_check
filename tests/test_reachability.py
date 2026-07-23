from __future__ import annotations

import requests

from hosts_check.config import ReachabilityConfig
from hosts_check.reachability import check_ip_reachable, filter_reachable


def test_check_ip_reachable_true_on_2xx(mocker):
    mocker.patch(
        "hosts_check.reachability.requests.head",
        return_value=mocker.Mock(status_code=200),
    )
    assert check_ip_reachable("1.2.3.4", "example.com", timeout=5.0) is True


def test_check_ip_reachable_true_on_3xx(mocker):
    mocker.patch(
        "hosts_check.reachability.requests.head",
        return_value=mocker.Mock(status_code=301),
    )
    assert check_ip_reachable("1.2.3.4", "example.com", timeout=5.0) is True


def test_check_ip_reachable_false_on_4xx(mocker):
    mocker.patch(
        "hosts_check.reachability.requests.head",
        return_value=mocker.Mock(status_code=404),
    )
    assert check_ip_reachable("1.2.3.4", "example.com", timeout=5.0) is False


def test_check_ip_reachable_false_on_timeout(mocker):
    mocker.patch(
        "hosts_check.reachability.requests.head",
        side_effect=requests.exceptions.Timeout(),
    )
    assert check_ip_reachable("1.2.3.4", "example.com", timeout=5.0) is False


def test_check_ip_reachable_false_on_connection_error(mocker):
    mocker.patch(
        "hosts_check.reachability.requests.head",
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
        "hosts_check.reachability.requests.head",
        side_effect=responses,
    )
    cfg = ReachabilityConfig(method="http_head", timeout=5.0)
    result = filter_reachable(["1.1.1.1", "2.2.2.2", "3.3.3.3"], "example.com", cfg)
    assert result == ["1.1.1.1", "3.3.3.3"]