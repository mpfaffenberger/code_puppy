from unittest.mock import Mock, patch

import requests

from code_puppy.version_checker import fetch_latest_version


def test_fetch_latest_version_success():
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"info": {"version": "9.8.7"}}
    with patch("requests.get", return_value=mock_response):
        version = fetch_latest_version("some-pkg")
        assert version == "9.8.7"


def test_fetch_latest_version_error():
    with patch("requests.get", side_effect=requests.RequestException):
        version = fetch_latest_version("does-not-matter")
        assert version is None
