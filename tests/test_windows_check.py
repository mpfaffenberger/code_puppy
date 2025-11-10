"""Tests for Windows-specific checks and utilities."""

import platform
import sys
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.utils.windows_check import (
    check_long_paths_enabled,
    get_long_paths_warning,
    is_path_too_long,
    is_windows,
    warn_if_long_paths_disabled,
)


class TestIsWindows:
    """Tests for is_windows() function."""

    def test_returns_true_on_windows(self):
        """Test that is_windows returns True on Windows."""
        with patch("platform.system", return_value="Windows"):
            assert is_windows() is True

    def test_returns_false_on_linux(self):
        """Test that is_windows returns False on Linux."""
        with patch("platform.system", return_value="Linux"):
            assert is_windows() is False

    def test_returns_false_on_darwin(self):
        """Test that is_windows returns False on macOS."""
        with patch("platform.system", return_value="Darwin"):
            assert is_windows() is False


class TestCheckLongPathsEnabled:
    """Tests for check_long_paths_enabled() function."""

    def test_returns_true_on_non_windows(self):
        """Test that check_long_paths_enabled returns True on non-Windows systems."""
        with patch("code_puppy.utils.windows_check.is_windows", return_value=False):
            assert check_long_paths_enabled() is True

    @pytest.mark.skipif(
        platform.system() != "Windows", reason="Windows-specific test"
    )
    def test_checks_registry_on_windows(self):
        """Test that check_long_paths_enabled checks the registry on Windows."""
        # This test will actually check the real registry on Windows
        result = check_long_paths_enabled()
        assert isinstance(result, bool)

    def test_returns_false_on_registry_error(self):
        """Test that check_long_paths_enabled returns False on registry errors."""
        with patch("code_puppy.utils.windows_check.is_windows", return_value=True):
            # Mock winreg to raise an error
            with patch("winreg.OpenKey", side_effect=FileNotFoundError):
                assert check_long_paths_enabled() is False

    def test_returns_true_when_enabled(self):
        """Test that check_long_paths_enabled returns True when registry value is 1."""
        with patch("code_puppy.utils.windows_check.is_windows", return_value=True):
            mock_key = MagicMock()
            with patch("winreg.OpenKey", return_value=mock_key):
                with patch("winreg.QueryValueEx", return_value=(1, None)):
                    with patch("winreg.CloseKey"):
                        assert check_long_paths_enabled() is True

    def test_returns_false_when_disabled(self):
        """Test that check_long_paths_enabled returns False when registry value is 0."""
        with patch("code_puppy.utils.windows_check.is_windows", return_value=True):
            mock_key = MagicMock()
            with patch("winreg.OpenKey", return_value=mock_key):
                with patch("winreg.QueryValueEx", return_value=(0, None)):
                    with patch("winreg.CloseKey"):
                        assert check_long_paths_enabled() is False


class TestGetLongPathsWarning:
    """Tests for get_long_paths_warning() function."""

    def test_returns_none_on_non_windows(self):
        """Test that get_long_paths_warning returns None on non-Windows systems."""
        with patch("code_puppy.utils.windows_check.is_windows", return_value=False):
            assert get_long_paths_warning() is None

    def test_returns_none_when_enabled(self):
        """Test that get_long_paths_warning returns None when long paths are enabled."""
        with patch("code_puppy.utils.windows_check.is_windows", return_value=True):
            with patch(
                "code_puppy.utils.windows_check.check_long_paths_enabled",
                return_value=True,
            ):
                assert get_long_paths_warning() is None

    def test_returns_warning_when_disabled(self):
        """Test that get_long_paths_warning returns a warning when long paths are disabled."""
        with patch("code_puppy.utils.windows_check.is_windows", return_value=True):
            with patch(
                "code_puppy.utils.windows_check.check_long_paths_enabled",
                return_value=False,
            ):
                warning = get_long_paths_warning()
                assert warning is not None
                assert isinstance(warning, str)
                assert "WARNING" in warning
                assert "Long Path" in warning


class TestWarnIfLongPathsDisabled:
    """Tests for warn_if_long_paths_disabled() function."""

    def test_prints_nothing_when_enabled(self, capsys):
        """Test that warn_if_long_paths_disabled prints nothing when long paths are enabled."""
        with patch(
            "code_puppy.utils.windows_check.get_long_paths_warning", return_value=None
        ):
            warn_if_long_paths_disabled()
            captured = capsys.readouterr()
            assert captured.err == ""

    def test_prints_warning_when_disabled(self, capsys):
        """Test that warn_if_long_paths_disabled prints a warning when long paths are disabled."""
        test_warning = "Test warning message"
        with patch(
            "code_puppy.utils.windows_check.get_long_paths_warning",
            return_value=test_warning,
        ):
            warn_if_long_paths_disabled()
            captured = capsys.readouterr()
            assert test_warning in captured.err


class TestIsPathTooLong:
    """Tests for is_path_too_long() function."""

    def test_returns_false_on_non_windows(self):
        """Test that is_path_too_long returns False on non-Windows systems."""
        with patch("code_puppy.utils.windows_check.is_windows", return_value=False):
            long_path = "x" * 300
            assert is_path_too_long(long_path) is False

    def test_returns_false_when_long_paths_enabled(self):
        """Test that is_path_too_long returns False when long paths are enabled."""
        with patch("code_puppy.utils.windows_check.is_windows", return_value=True):
            with patch(
                "code_puppy.utils.windows_check.check_long_paths_enabled",
                return_value=True,
            ):
                long_path = "x" * 300
                assert is_path_too_long(long_path) is False

    def test_returns_true_for_long_path_when_disabled(self):
        """Test that is_path_too_long returns True for paths exceeding limit."""
        with patch("code_puppy.utils.windows_check.is_windows", return_value=True):
            with patch(
                "code_puppy.utils.windows_check.check_long_paths_enabled",
                return_value=False,
            ):
                long_path = "x" * 300
                assert is_path_too_long(long_path) is True

    def test_returns_false_for_short_path_when_disabled(self):
        """Test that is_path_too_long returns False for paths within limit."""
        with patch("code_puppy.utils.windows_check.is_windows", return_value=True):
            with patch(
                "code_puppy.utils.windows_check.check_long_paths_enabled",
                return_value=False,
            ):
                short_path = "x" * 100
                assert is_path_too_long(short_path) is False

    def test_respects_custom_max_length(self):
        """Test that is_path_too_long respects custom max_length parameter."""
        with patch("code_puppy.utils.windows_check.is_windows", return_value=True):
            with patch(
                "code_puppy.utils.windows_check.check_long_paths_enabled",
                return_value=False,
            ):
                path = "x" * 150
                assert is_path_too_long(path, max_length=100) is True
                assert is_path_too_long(path, max_length=200) is False
