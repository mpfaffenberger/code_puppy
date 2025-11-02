from unittest.mock import MagicMock, patch

import httpx

from code_puppy.version_checker import (
    default_version_mismatch_behavior,
    fetch_latest_version,
    normalize_version,
    versions_are_equal,
)


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


class TestFetchLatestVersion:
    """Test fetch_latest_version function."""

    @patch("code_puppy.version_checker.httpx.get")
    def test_fetch_latest_version_success(self, mock_get):
        """Test successful version fetch from PyPI."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"info": {"version": "1.2.3"}}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        version = fetch_latest_version("test-package")

        assert version == "1.2.3"
        mock_get.assert_called_once_with("https://pypi.org/pypi/test-package/json")

    @patch("code_puppy.version_checker.httpx.get")
    def test_fetch_latest_version_http_error(self, mock_get):
        """Test version fetch with HTTP error."""
        mock_get.side_effect = httpx.HTTPError("Connection failed")

        version = fetch_latest_version("test-package")

        assert version is None

    @patch("code_puppy.version_checker.httpx.get")
    def test_fetch_latest_version_invalid_json(self, mock_get):
        """Test version fetch with invalid JSON response."""
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        version = fetch_latest_version("test-package")

        assert version is None

    @patch("code_puppy.version_checker.httpx.get")
    def test_fetch_latest_version_missing_info_key(self, mock_get):
        """Test version fetch with missing 'info' key."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"releases": {}}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        version = fetch_latest_version("test-package")

        assert version is None

    @patch("code_puppy.version_checker.httpx.get")
    def test_fetch_latest_version_status_error(self, mock_get):
        """Test version fetch with HTTP status error."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=MagicMock()
        )
        mock_get.return_value = mock_response

        version = fetch_latest_version("nonexistent-package")

        assert version is None


class TestDefaultVersionMismatchBehavior:
    """Test default_version_mismatch_behavior function."""

    @patch("code_puppy.version_checker.console")
    @patch("code_puppy.version_checker.fetch_latest_version")
    def test_version_mismatch_shows_update_message(self, mock_fetch, mock_console):
        """Test that update message is shown when versions differ."""
        mock_fetch.return_value = "2.0.0"

        default_version_mismatch_behavior("1.0.0")

        # Should print current version
        mock_console.print.assert_any_call("Current version: 1.0.0")
        # Should print latest version
        mock_console.print.assert_any_call("Latest version: 2.0.0")
        # Should show update available message
        assert mock_console.print.call_count >= 4

    @patch("code_puppy.version_checker.console")
    @patch("code_puppy.version_checker.fetch_latest_version")
    def test_version_match_still_shows_current_version(self, mock_fetch, mock_console):
        """Test that current version is still shown when versions match."""
        mock_fetch.return_value = "1.0.0"

        default_version_mismatch_behavior("1.0.0")

        # Should print current version even when versions match
        mock_console.print.assert_called_once_with("Current version: 1.0.0")

    @patch("code_puppy.version_checker.console")
    @patch("code_puppy.version_checker.fetch_latest_version")
    def test_version_fetch_failure_still_shows_current(self, mock_fetch, mock_console):
        """Test behavior when fetch_latest_version returns None."""
        mock_fetch.return_value = None

        default_version_mismatch_behavior("1.0.0")

        # Should still print current version even when version fetch fails
        mock_console.print.assert_called_once_with("Current version: 1.0.0")

    @patch("code_puppy.version_checker.console")
    @patch("code_puppy.version_checker.fetch_latest_version")
    def test_update_message_content(self, mock_fetch, mock_console):
        """Test the exact content of update messages."""
        mock_fetch.return_value = "2.5.0"

        default_version_mismatch_behavior("2.0.0")

        # Check for specific messages
        calls = [str(call) for call in mock_console.print.call_args_list]
        assert any("new version" in str(call).lower() for call in calls)
        assert any("2.5.0" in str(call) for call in calls)
        assert any(
            "updating" in str(call).lower() or "update" in str(call).lower()
            for call in calls
        )
