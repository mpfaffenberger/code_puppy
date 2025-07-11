from unittest.mock import Mock, patch

import requests

from code_puppy.version_checker import (
    fetch_latest_version,
    normalize_version,
    versions_are_equal,
)


def test_fetch_latest_version_success():
    """Test successful version fetch from staging API."""
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "success": True,
        "data": {
            "version": "v0.0.78",
            "name": "Release v0.0.78",
            "published_at": "2025-07-10T15:58:33Z",
            "prerelease": False,
            "draft": False,
        },
        "message": "Latest release info fetched successfully! 🐶",
        "cached": False,
    }
    with patch("requests.get", return_value=mock_response) as mock_get:
        version = fetch_latest_version("some-pkg")
        assert (
            version == "0.0.78"
        )  # fetch_latest_version normalizes by stripping 'v' prefix
        # Verify we're calling the right endpoint with SSL verification
        mock_get.assert_called_once_with(
            "https://puppy.stg.walmart.com/api/releases/latest", timeout=5, verify=True
        )


def test_fetch_latest_version_request_error():
    """Test handling of network/request errors."""
    with patch("requests.get", side_effect=requests.RequestException("Network error")):
        version = fetch_latest_version("does-not-matter")
        assert version is None


def test_fetch_latest_version_timeout():
    """Test handling of request timeout."""
    with patch(
        "requests.get", side_effect=requests.exceptions.Timeout("Request timed out")
    ):
        version = fetch_latest_version()
        assert version is None


def test_fetch_latest_version_api_failure():
    """Test handling when API returns success=False."""
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "success": False,
        "message": "API is down for maintenance",
        "data": None,
    }
    with patch("requests.get", return_value=mock_response):
        version = fetch_latest_version()
        assert version is None


def test_fetch_latest_version_missing_version():
    """Test handling when version is missing from response."""
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "success": True,
        "data": {
            "name": "Some release",
            # version field is missing!
        },
        "message": "Success but no version",
    }
    with patch("requests.get", return_value=mock_response):
        version = fetch_latest_version()
        assert version is None


def test_fetch_latest_version_malformed_json():
    """Test handling of malformed JSON response."""
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.side_effect = ValueError("Invalid JSON")
    with patch("requests.get", return_value=mock_response):
        version = fetch_latest_version()
        assert version is None


def test_normalize_version():
    """Test version string normalization."""
    assert normalize_version("v1.2.3") == "1.2.3"
    assert normalize_version("1.2.3") == "1.2.3"
    assert normalize_version("v0.0.78") == "0.0.78"
    assert normalize_version("0.0.78") == "0.0.78"
    assert normalize_version("") == ""
    assert normalize_version(None) is None
    assert normalize_version("vvv1.2.3") == "1.2.3"  # Multiple v's


def test_versions_are_equal():
    """Test version equality comparison."""
    # Same versions with and without v prefix
    assert versions_are_equal("1.2.3", "v1.2.3") is True
    assert versions_are_equal("v1.2.3", "1.2.3") is True
    assert versions_are_equal("v1.2.3", "v1.2.3") is True
    assert versions_are_equal("1.2.3", "1.2.3") is True

    # The specific case from our API
    assert versions_are_equal("0.0.78", "v0.0.78") is True
    assert versions_are_equal("v0.0.78", "0.0.78") is True

    # Different versions
    assert versions_are_equal("1.2.3", "1.2.4") is False
    assert versions_are_equal("v1.2.3", "v1.2.4") is False
    assert versions_are_equal("1.2.3", "v1.2.4") is False

    # Edge cases
    assert versions_are_equal("", "") is True
    assert versions_are_equal(None, None) is True
    assert versions_are_equal("1.2.3", "") is False
    assert versions_are_equal("", "1.2.3") is False
