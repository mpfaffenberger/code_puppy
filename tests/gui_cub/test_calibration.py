"""Tests for GUI-Cub calibration."""

from unittest.mock import patch
from code_puppy.tools.gui_cub.calibration import (
    detect_platform,
    detect_displays,
    _is_admin,
    _update_system_path_registry,
)


class TestDetectPlatform:
    """Test platform detection."""

    @patch("sys.platform", "darwin")
    @patch("platform.release", return_value="22.1.0")
    @patch("platform.machine", return_value="arm64")
    def test_detect_platform_macos(self, mock_machine, mock_release):
        """Should detect macOS correctly."""
        result = detect_platform()
        assert result["os"] == "darwin"
        assert result["os_display"] == "macOS"
        assert result["version"] == "22.1.0"
        assert result["machine"] == "arm64"

    @patch("sys.platform", "win32")
    @patch("platform.release", return_value="11")
    @patch("platform.machine", return_value="AMD64")
    def test_detect_platform_windows(self, mock_machine, mock_release):
        """Should detect Windows correctly."""
        result = detect_platform()
        assert result["os"] == "win32"
        assert result["os_display"] == "Windows"
        assert result["version"] == "11"
        assert result["machine"] == "AMD64"

    @patch("sys.platform", "linux")
    @patch("platform.release", return_value="5.15.0")
    @patch("platform.machine", return_value="x86_64")
    def test_detect_platform_linux(self, mock_machine, mock_release):
        """Should detect Linux - currently unsupported."""
        result = detect_platform()
        assert result["os"] == "linux"
        assert result["os_display"] == "Unsupported"  # Linux is not currently supported
        assert result["version"] == "5.15.0"
        assert result["machine"] == "x86_64"


class TestDetectDisplays:
    """Test display detection."""

    @patch("code_puppy.tools.gui_cub.calibration.detection._detect_macos_monitors")
    @patch("code_puppy.tools.gui_cub.calibration.detection._detect_windows_monitors")
    @patch("pyautogui.size", return_value=(1920, 1080))
    def test_detect_displays_basic(
        self, mock_size, mock_win_monitors, mock_mac_monitors
    ):
        """Should detect basic display info."""
        # Mock both platform-specific functions to return a single monitor
        mock_monitor = [
            {
                "id": 0,
                "resolution": [1920, 1080],
                "scale": 1.0,
                "primary": True,
                "bounds": {"x": 0, "y": 0, "width": 1920, "height": 1080},
            }
        ]
        mock_mac_monitors.return_value = mock_monitor
        mock_win_monitors.return_value = mock_monitor

        result = detect_displays()
        assert result["monitor_count"] == 1
        assert result["primary_resolution"] == [1920, 1080]

    @patch("pyautogui.size", return_value=(2560, 1440))
    def test_detect_displays_different_resolution(self, mock_size):
        """Should handle different resolutions."""
        result = detect_displays()
        assert result["primary_resolution"] == [2560, 1440]


class TestIsAdmin:
    """Test admin detection."""

    @patch("sys.platform", "darwin")
    def test_is_admin_returns_true_on_macos(self):
        """Should return True on macOS (doesn't check admin)."""
        result = _is_admin()
        assert result is True

    @patch("sys.platform", "linux")
    def test_is_admin_returns_true_on_linux(self):
        """Should return True on Linux (doesn't check admin)."""
        result = _is_admin()
        assert result is True


class TestUpdateSystemPathRegistry:
    """Test Windows PATH update via registry."""

    @patch("sys.platform", "darwin")
    def test_update_path_returns_false_on_non_windows(self):
        """Should return False on non-Windows platforms."""
        success, message = _update_system_path_registry("C:\\\\Test")
        assert success is False
        assert "Not Windows" in message
