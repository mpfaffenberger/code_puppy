"""Unit tests for debug screenshot management.

Tests the centralized temporary screenshot storage system without
actually taking screenshots of the user's desktop.
"""

import tempfile
from pathlib import Path

from PIL import Image

from code_puppy.tools.gui_cub.debug_screenshot_manager import (
    cleanup_old_temp_screenshots,
    copy_last_screenshot_to_pwd,
    get_temp_screenshot_dir,
    save_temp_debug_screenshot,
)


class TestGetTempScreenshotDir:
    """Test temporary directory creation and management."""

    def test_creates_temp_directory(self):
        """Test that temp directory is created in system temp."""
        # Reset global state
        import code_puppy.tools.gui_cub.debug_screenshot_manager as mgr

        mgr._TEMP_SCREENSHOT_DIR = None

        temp_dir = get_temp_screenshot_dir()

        assert temp_dir.exists()
        assert temp_dir.is_dir()
        assert "code_puppy_debug_screenshots" in str(temp_dir)
        assert str(tempfile.gettempdir()) in str(temp_dir)

    def test_returns_same_directory_on_multiple_calls(self):
        """Test that directory is cached and reused."""
        dir1 = get_temp_screenshot_dir()
        dir2 = get_temp_screenshot_dir()

        assert dir1 == dir2


class TestSaveTempDebugScreenshot:
    """Test saving screenshots to temp directory."""

    def test_saves_screenshot_with_timestamp(self):
        """Test that screenshot is saved with timestamp in filename."""
        # Create a simple test image
        img = Image.new("RGB", (100, 100), color="red")

        # Save to temp
        path = save_temp_debug_screenshot(img, "test_image", None)

        assert path.exists()
        assert path.suffix == ".png"
        assert "test_image" in path.name
        assert path.parent == get_temp_screenshot_dir()

        # Cleanup
        path.unlink()

    def test_includes_group_id_in_filename(self):
        """Test that group_id is included in filename."""
        img = Image.new("RGB", (100, 100), color="blue")

        path = save_temp_debug_screenshot(img, "test", "my_group")

        assert "my_group" in path.name
        assert "test" in path.name

        # Cleanup
        path.unlink()

    def test_updates_last_screenshot_global(self):
        """Test that global _LAST_SCREENSHOT_PATH is updated."""
        import code_puppy.tools.gui_cub.debug_screenshot_manager as mgr

        img = Image.new("RGB", (100, 100), color="green")

        path = save_temp_debug_screenshot(img, "test", None)

        assert mgr._LAST_SCREENSHOT_PATH == path

        # Cleanup
        path.unlink()


class TestCopyLastScreenshotToPwd:
    """Test copying last screenshot to working directory."""

    def test_copies_last_screenshot_with_custom_filename(self, tmp_path, monkeypatch):
        """Test copying with custom filename."""
        # Mock pwd to be our temp directory
        monkeypatch.chdir(tmp_path)

        # Create and save a test image
        img = Image.new("RGB", (100, 100), color="yellow")
        temp_path = save_temp_debug_screenshot(img, "test", None)

        # Copy to pwd with custom name
        result = copy_last_screenshot_to_pwd("my_custom_name.png")

        assert result is not None
        assert result.name == "my_custom_name.png"
        assert result.parent == tmp_path
        assert result.exists()

        # Cleanup
        temp_path.unlink()
        result.unlink()

    def test_copies_with_auto_generated_filename(self, tmp_path, monkeypatch):
        """Test copying with auto-generated timestamp filename."""
        monkeypatch.chdir(tmp_path)

        img = Image.new("RGB", (100, 100), color="purple")
        temp_path = save_temp_debug_screenshot(img, "test", None)

        result = copy_last_screenshot_to_pwd(None)

        assert result is not None
        assert result.name.startswith("debug_screenshot_")
        assert result.suffix == ".png"
        assert result.exists()

        # Cleanup
        temp_path.unlink()
        result.unlink()

    def test_returns_none_when_no_screenshot_available(self):
        """Test that None is returned when no screenshot exists."""
        import code_puppy.tools.gui_cub.debug_screenshot_manager as mgr

        # Clear global state
        mgr._LAST_SCREENSHOT_PATH = None

        result = copy_last_screenshot_to_pwd("test.png")

        assert result is None

    def test_returns_none_when_screenshot_file_missing(self):
        """Test that None is returned when screenshot file is deleted."""
        import code_puppy.tools.gui_cub.debug_screenshot_manager as mgr

        # Set global to non-existent path
        mgr._LAST_SCREENSHOT_PATH = Path("/nonexistent/path/test.png")

        result = copy_last_screenshot_to_pwd("test.png")

        assert result is None


class TestCleanupOldTempScreenshots:
    """Test cleanup of old temporary screenshots."""

    def test_deletes_old_screenshots(self, tmp_path, monkeypatch):
        """Test that old screenshots are deleted."""
        import time

        import code_puppy.tools.gui_cub.debug_screenshot_manager as mgr

        # Mock temp directory to use tmp_path
        mgr._TEMP_SCREENSHOT_DIR = tmp_path

        # Create some old files
        old_file = tmp_path / "old_screenshot.png"
        old_file.write_text("old")

        # Make it look old by mocking mtime
        old_time = time.time() - (25 * 3600)  # 25 hours ago
        import os

        os.utime(old_file, (old_time, old_time))

        # Create a recent file
        recent_file = tmp_path / "recent_screenshot.png"
        recent_file.write_text("recent")

        # Cleanup old files (older than 24 hours)
        deleted = cleanup_old_temp_screenshots(max_age_hours=24)

        assert deleted == 1
        assert not old_file.exists()
        assert recent_file.exists()

        # Cleanup
        recent_file.unlink()

    def test_returns_zero_when_no_old_files(self, tmp_path, monkeypatch):
        """Test that zero is returned when no old files exist."""
        import code_puppy.tools.gui_cub.debug_screenshot_manager as mgr

        mgr._TEMP_SCREENSHOT_DIR = tmp_path

        # Create only recent files
        recent_file = tmp_path / "recent.png"
        recent_file.write_text("recent")

        deleted = cleanup_old_temp_screenshots(max_age_hours=24)

        assert deleted == 0
        assert recent_file.exists()

        # Cleanup
        recent_file.unlink()

    def test_returns_zero_when_directory_not_exists(self):
        """Test that zero is returned when temp dir doesn't exist."""
        import code_puppy.tools.gui_cub.debug_screenshot_manager as mgr

        # Set to non-existent path
        mgr._TEMP_SCREENSHOT_DIR = Path("/nonexistent/temp/dir")

        deleted = cleanup_old_temp_screenshots()

        assert deleted == 0


class TestIntegration:
    """Integration tests for the full workflow."""

    def test_full_workflow_save_and_copy(self, tmp_path, monkeypatch):
        """Test the complete save -> copy workflow."""
        import code_puppy.tools.gui_cub.debug_screenshot_manager as mgr

        monkeypatch.chdir(tmp_path)
        # Use a separate temp directory for screenshots
        screenshot_dir = tmp_path / "screenshots"
        screenshot_dir.mkdir()
        mgr._TEMP_SCREENSHOT_DIR = screenshot_dir

        # Create test image
        img = Image.new("RGB", (200, 200), color="orange")

        # Save to temp
        temp_path = save_temp_debug_screenshot(img, "workflow_test", "test_group")
        assert temp_path.exists()

        # Copy to pwd
        pwd_path = copy_last_screenshot_to_pwd("workflow_output.png")
        assert pwd_path is not None
        assert pwd_path.exists()

        # Verify it's the same image
        temp_img = Image.open(temp_path)
        pwd_img = Image.open(pwd_path)
        assert temp_img.size == pwd_img.size
        assert temp_img.mode == pwd_img.mode

        # Cleanup
        temp_path.unlink()
        pwd_path.unlink()

    def test_multiple_screenshots_tracks_last(self, tmp_path):
        """Test that multiple saves track the last one correctly."""
        import code_puppy.tools.gui_cub.debug_screenshot_manager as mgr

        # Use tmp_path to ensure directory exists
        mgr._TEMP_SCREENSHOT_DIR = tmp_path

        img1 = Image.new("RGB", (100, 100), color="red")
        img2 = Image.new("RGB", (100, 100), color="blue")

        path1 = save_temp_debug_screenshot(img1, "first", None)
        path2 = save_temp_debug_screenshot(img2, "second", None)

        # Last screenshot should be path2
        assert mgr._LAST_SCREENSHOT_PATH == path2

        # Cleanup
        path1.unlink()
        path2.unlink()
