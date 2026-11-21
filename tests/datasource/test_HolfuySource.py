import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from source.datasource.HolfuySource import HolfuySource


@pytest.fixture
def holfuy_source():
    source = HolfuySource("testpw")
    source.logger = MagicMock()
    return source


@patch("requests.Session.post")
def test_fetch_realtime_sends_key_in_post_body(mock_post, holfuy_source):
    resp = MagicMock()
    resp.json.return_value = {}
    resp.raise_for_status.return_value = None
    mock_post.return_value = resp
    holfuy_source.transform_realtime_data = MagicMock(return_value={"ok": True})

    holfuy_source.fetch_realtime_data("101")

    args, kwargs = mock_post.call_args
    assert "pw=" not in args[0]  # key must not be in the URL
    assert kwargs["data"] == {"pw": "testpw"}  # key travels in the POST body


@patch("requests.Session.post")
def test_is_station_online_sends_key_in_post_body(mock_post, holfuy_source):
    resp = MagicMock()
    resp.json.return_value = {}  # no error keys => considered online
    resp.raise_for_status.return_value = None
    mock_post.return_value = resp

    assert holfuy_source.is_station_online("101") is True
    args, kwargs = mock_post.call_args
    assert "pw=" not in args[0]
    assert kwargs["data"] == {"pw": "testpw"}


@patch("requests.Session.post")
def test_is_station_online_handles_request_error(mock_post, holfuy_source):
    mock_post.side_effect = requests.exceptions.ConnectionError("boom")
    # must not raise; returns False and routes through _handle_error
    assert holfuy_source.is_station_online("101") is False


def test_handle_error_redacts_secret_in_url(holfuy_source):
    err = requests.exceptions.HTTPError(
        "500 Server Error for url: https://api.holfuy.com/live/?s=101&pw=SECRET123&utc"
    )
    holfuy_source._handle_error(err)
    logged = holfuy_source.logger.error.call_args[0][0]
    assert "SECRET123" not in logged
    assert "pw=<redacted>" in logged
