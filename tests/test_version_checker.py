from unittest.mock import Mock, patch
import subprocess
import sys

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


def test_auto_update_functionality():
    """Test the auto-update functionality integration."""
    # This test simulates the main.py auto-update logic
    current_version = "0.0.77"
    latest_version = "0.0.78"

    # Mock subprocess calls for the update process
    mock_curl_result = Mock()
    mock_curl_result.returncode = 0
    mock_curl_result.stdout = "#!/bin/bash\necho 'Update script executed'"

    mock_bash_result = Mock()
    mock_bash_result.returncode = 0

    with patch("subprocess.run") as mock_subprocess:
        # Configure subprocess.run to return different mocks for curl vs bash
        def subprocess_side_effect(*args, **kwargs):
            if args[0][0] == "curl":
                return mock_curl_result
            elif args[0][0] == "bash":
                return mock_bash_result
            return Mock(returncode=1)

        mock_subprocess.side_effect = subprocess_side_effect

        # Test that auto-update would be triggered
        assert not versions_are_equal(current_version, latest_version)

        # Simulate the update process from main.py
        try:
            result = subprocess.run(
                ["curl", "-sSL", "https://puppy-dev.walmart.com/api/releases/setup"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                bash_result = subprocess.run(
                    ["bash"], input=result.stdout, text=True, timeout=120
                )

                # Verify the update would succeed
                assert bash_result.returncode == 0
                update_success = True
            else:
                update_success = False

        except subprocess.TimeoutExpired:
            update_success = False
        except Exception:
            update_success = False

        assert update_success is True

        # Verify subprocess was called with correct arguments
        calls = mock_subprocess.call_args_list
        assert len(calls) == 2

        # First call should be curl
        curl_call = calls[0]
        assert curl_call[0][0] == [
            "curl",
            "-sSL",
            "https://puppy-dev.walmart.com/api/releases/setup",
        ]
        assert curl_call[1]["capture_output"] is True
        assert curl_call[1]["text"] is True
        assert curl_call[1]["timeout"] == 60

        # Second call should be bash
        bash_call = calls[1]
        assert bash_call[0][0] == ["bash"]
        assert bash_call[1]["input"] == "#!/bin/bash\necho 'Update script executed'"
        assert bash_call[1]["text"] is True
        assert bash_call[1]["timeout"] == 120


def test_auto_update_curl_failure():
    """Test auto-update handling when curl fails."""
    mock_curl_result = Mock()
    mock_curl_result.returncode = 1
    mock_curl_result.stderr = "Connection failed"

    with patch("subprocess.run", return_value=mock_curl_result):
        # Simulate curl failure
        result = subprocess.run(
            ["curl", "-sSL", "https://puppy-dev.walmart.com/api/releases/setup"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        # Should fail gracefully
        assert result.returncode != 0
        update_success = result.returncode == 0
        assert update_success is False


def test_auto_update_bash_failure():
    """Test auto-update handling when bash execution fails."""
    mock_curl_result = Mock()
    mock_curl_result.returncode = 0
    mock_curl_result.stdout = "#!/bin/bash\nexit 1"  # Script that fails

    mock_bash_result = Mock()
    mock_bash_result.returncode = 1  # Bash execution fails

    with patch("subprocess.run") as mock_subprocess:

        def subprocess_side_effect(*args, **kwargs):
            if args[0][0] == "curl":
                return mock_curl_result
            elif args[0][0] == "bash":
                return mock_bash_result
            return Mock(returncode=1)

        mock_subprocess.side_effect = subprocess_side_effect

        # Simulate the update process
        result = subprocess.run(
            ["curl", "-sSL", "https://puppy-dev.walmart.com/api/releases/setup"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        update_success = False
        if result.returncode == 0:
            bash_result = subprocess.run(
                ["bash"], input=result.stdout, text=True, timeout=120
            )
            update_success = bash_result.returncode == 0

        # Should fail gracefully when bash script fails
        assert update_success is False


def test_auto_update_timeout():
    """Test auto-update handling when subprocess times out."""
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["curl"], 60)):
        # Simulate timeout during curl
        update_success = True
        try:
            subprocess.run(
                ["curl", "-sSL", "https://puppy-dev.walmart.com/api/releases/setup"],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            update_success = False

        # Should fail gracefully on timeout
        assert update_success is False
