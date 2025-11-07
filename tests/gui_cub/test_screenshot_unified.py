"""Unit tests for unified screenshot functions.

Tests for the consolidated screenshot() and screenshot_analyze() functions
that replaced the previous fragmented screenshot implementation.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from code_puppy.tools.gui_cub.result_types import ScreenshotResult, WindowBoundsResult


class TestUnifiedScreenshotFunction:
    """Test unified screenshot() function."""

    @patch("code_puppy.tools.gui_cub.screen_capture.capture_screen")
    def test_screenshot_full_screen_mode(self, mock_capture):
        """Test full screen mode."""
        from code_puppy.tools.gui_cub.screen_capture import screenshot

        # Mock the capture_screen result
        mock_capture.return_value = ScreenshotResult(
            success=True,
            screenshot_path="/tmp/screenshot.png",
            width=1920,
            height=1080,
        )

        result = screenshot(mode="full_screen")

        assert result.success is True
        mock_capture.assert_called_once()
        # Full screen should pass region=None
        call_kwargs = mock_capture.call_args[1]
        assert call_kwargs["region"] is None

    @patch("code_puppy.tools.gui_cub.screen_capture.capture_screen")
    def test_screenshot_region_coordinates(self, mock_capture):
        """Test region capture with individual coordinates."""
        from code_puppy.tools.gui_cub.screen_capture import screenshot

        mock_capture.return_value = ScreenshotResult(
            success=True, screenshot_path="/tmp/region.png", width=800, height=600
        )

        result = screenshot(x=100, y=100, width=800, height=600)

        assert result.success is True
        # Should pass region tuple to capture_screen
        call_kwargs = mock_capture.call_args[1]
        assert call_kwargs["region"] == (100, 100, 800, 600)

    @patch("code_puppy.tools.gui_cub.screen_capture.capture_screen")
    @patch("code_puppy.tools.gui_cub.window_control._get_active_window_bounds_impl")
    def test_screenshot_partial_region_ignored(self, mock_get_bounds, mock_capture):
        """Test that partial region params fallback to active window."""
        from code_puppy.tools.gui_cub.screen_capture import screenshot

        # Mock window bounds (active_window is default mode)
        mock_get_bounds.return_value = WindowBoundsResult(
            success=True, x=77, y=128, width=837, height=872, window_title="Test"
        )

        mock_capture.return_value = ScreenshotResult(
            success=True, screenshot_path="/tmp/screenshot.png"
        )

        # Only provide x and y, not width/height
        result = screenshot(x=100, y=100)

        assert result.success is True
        # Should fallback to active window (default mode)
        call_kwargs = mock_capture.call_args[1]
        # Region should be window bounds since partial coords are ignored
        assert call_kwargs.get("region") is not None

    @patch("code_puppy.tools.gui_cub.screen_capture.capture_screen")
    @patch("code_puppy.tools.gui_cub.window_control._get_active_window_bounds_impl")
    def test_screenshot_active_window_mode(self, mock_get_bounds, mock_capture):
        """Test active window mode with bounds detection."""
        from code_puppy.tools.gui_cub.screen_capture import screenshot

        # Mock window bounds
        mock_get_bounds.return_value = WindowBoundsResult(
            success=True,
            x=100,
            y=50,
            width=1200,
            height=800,
            window_title="Test Window",
        )

        mock_capture.return_value = ScreenshotResult(
            success=True, screenshot_path="/tmp/window.png", width=1200, height=800
        )

        result = screenshot(mode="active_window")

        assert result.success is True
        # Should have called window bounds detection
        mock_get_bounds.assert_called_once()
        # Should pass window bounds as region
        call_kwargs = mock_capture.call_args[1]
        assert call_kwargs["region"] == (100, 50, 1200, 800)

    @patch("code_puppy.tools.gui_cub.screen_capture.capture_screen")
    def test_screenshot_with_grid(self, mock_capture):
        """Test grid overlay parameter."""
        from code_puppy.tools.gui_cub.screen_capture import screenshot

        mock_capture.return_value = ScreenshotResult(
            success=True, screenshot_path="/tmp/grid.png"
        )

        result = screenshot(add_grid=True, grid_spacing=50)

        assert result.success is True
        call_kwargs = mock_capture.call_args[1]
        assert call_kwargs["add_grid"] is True
        assert call_kwargs["grid_spacing"] == 50

    @patch("code_puppy.tools.gui_cub.screen_capture.capture_screen")
    def test_screenshot_custom_save_path(self, mock_capture):
        """Test custom save path functionality."""
        import tempfile
        from pathlib import Path
        from code_puppy.tools.gui_cub.screen_capture import screenshot

        temp_path = Path(tempfile.gettempdir()) / "test_screenshot.png"

        # Mock capture_screen to return a temp file
        mock_capture.return_value = ScreenshotResult(
            success=True,
            screenshot_path=str(Path(tempfile.gettempdir()) / "original.png"),
        )

        # Create a fake file to move
        original_file = Path(tempfile.gettempdir()) / "original.png"
        original_file.write_bytes(b"fake_png_data")

        result = screenshot(save_path=str(temp_path))

        assert result.success is True
        # Path may be normalized (e.g., /private/var on macOS)
        assert temp_path.exists()
        assert str(
            temp_path
        ) in result.screenshot_path or result.screenshot_path.endswith(temp_path.name)
        # Original file should have been moved
        assert temp_path.exists()

        # Cleanup
        if temp_path.exists():
            temp_path.unlink()


class TestUnifiedScreenshotAnalyzeFunction:
    """Test unified screenshot_analyze() function."""

    @pytest.mark.asyncio
    @patch("code_puppy.tools.gui_cub.screen_capture.screenshot")
    @patch("PIL.Image.open")
    @patch("code_puppy.tools.gui_cub.ocr_tools.extract_text_from_image")
    async def test_screenshot_analyze_ocr_mode(
        self, mock_ocr, mock_pil_open, mock_screenshot
    ):
        """Test OCR mode (question=None)."""
        import tempfile
        from pathlib import Path
        from code_puppy.tools.gui_cub.screen_capture import screenshot_analyze
        from code_puppy.tools.gui_cub.ocr_tools import OCRExtractResult

        # Create a real temp file for the screenshot
        temp_path = Path(tempfile.gettempdir()) / "test_ocr.png"
        temp_path.write_bytes(b"fake_png_data")

        # Mock screenshot
        mock_screenshot.return_value = ScreenshotResult(
            success=True, screenshot_path=str(temp_path)
        )

        # Mock PIL Image.open to return a mock image
        mock_image_instance = Mock()
        mock_pil_open.return_value = mock_image_instance

        # Mock OCR result
        mock_ocr.return_value = OCRExtractResult(
            success=True,
            full_text="Login\nUsername\nPassword\nSubmit",
            text_elements=[],
        )

        result = await screenshot_analyze(question=None)

        assert result["success"] is True
        assert result["analysis_type"] == "ocr"
        assert "full_text" in result
        assert result["word_count"] == 4
        assert "Login" in result["full_text"]

        # Cleanup
        if temp_path.exists():
            temp_path.unlink()

    @pytest.mark.asyncio
    @patch("code_puppy.tools.gui_cub.screen_capture.screenshot")
    @patch("code_puppy.tools.gui_cub.vqa_desktop.run_desktop_vqa_analysis")
    async def test_screenshot_analyze_vqa_mode(self, mock_vqa, mock_screenshot):
        """Test VQA mode (question provided)."""
        from code_puppy.tools.gui_cub.screen_capture import screenshot_analyze
        from code_puppy.tools.gui_cub.result_types import VQAResult
        import tempfile
        from pathlib import Path

        # Create a fake screenshot file
        temp_path = Path(tempfile.gettempdir()) / "vqa_test.png"
        temp_path.write_bytes(b"fake_png_data")

        # Mock screenshot
        mock_screenshot.return_value = ScreenshotResult(
            success=True, screenshot_path=str(temp_path)
        )

        # Mock VQA result
        mock_vqa.return_value = VQAResult(
            success=True,
            question="Where is the Submit button?",
            answer="Bottom-right corner at coordinates (450, 380)",
            confidence=0.92,
            observations="Login form with username, password fields and submit button",
        )

        result = await screenshot_analyze(question="Where is the Submit button?")

        assert result["success"] is True
        assert result["analysis_type"] == "vqa"
        assert "answer" in result
        assert result["confidence"] == 0.92
        assert "Bottom-right corner" in result["answer"]

        # Cleanup
        if temp_path.exists():
            temp_path.unlink()

    @pytest.mark.asyncio
    @patch("code_puppy.tools.gui_cub.screen_capture.screenshot")
    @patch("code_puppy.tools.gui_cub.vqa_desktop.run_desktop_vqa_analysis")
    async def test_screenshot_analyze_auto_refine(self, mock_vqa, mock_screenshot):
        """Test auto-refine with low confidence."""
        from code_puppy.tools.gui_cub.screen_capture import screenshot_analyze
        from code_puppy.tools.gui_cub.result_types import VQAResult
        import tempfile
        from pathlib import Path

        # Create fake screenshot files
        temp_path1 = Path(tempfile.gettempdir()) / "vqa_low_conf.png"
        temp_path2 = Path(tempfile.gettempdir()) / "vqa_high_conf.png"
        temp_path1.write_bytes(b"fake_png_data_1")
        temp_path2.write_bytes(b"fake_png_data_2")

        # Mock screenshot to return different files on each call
        mock_screenshot.side_effect = [
            ScreenshotResult(success=True, screenshot_path=str(temp_path1)),
            ScreenshotResult(success=True, screenshot_path=str(temp_path2)),
        ]

        # Mock VQA to return low confidence first, then high
        mock_vqa.side_effect = [
            VQAResult(
                success=True,
                question="Find button",
                answer="Unsure of location",
                confidence=0.65,  # Below threshold
            ),
            VQAResult(
                success=True,
                question="Find button",
                answer="Button at (400, 300) according to grid",
                confidence=0.95,  # Above threshold
            ),
        ]

        result = await screenshot_analyze(
            question="Find button",
            auto_refine=True,
            confidence_threshold=0.9,
        )

        assert result["success"] is True
        assert result["confidence"] == 0.95
        assert "grid" in result["answer"].lower()
        assert result.get("grid_refined") is True

        # Cleanup
        for path in [temp_path1, temp_path2]:
            if path.exists():
                path.unlink()

    @pytest.mark.asyncio
    @patch("code_puppy.tools.gui_cub.screen_capture.screenshot")
    @patch("PIL.Image.open")
    @patch("code_puppy.tools.gui_cub.ocr_tools.extract_text_from_image")
    async def test_screenshot_analyze_region_params(
        self, mock_ocr, mock_pil_open, mock_screenshot
    ):
        """Test region parameters passed through."""
        import tempfile
        from pathlib import Path
        from code_puppy.tools.gui_cub.screen_capture import screenshot_analyze
        from code_puppy.tools.gui_cub.ocr_tools import OCRExtractResult

        # Create a real temp file
        temp_path = Path(tempfile.gettempdir()) / "region_ocr.png"
        temp_path.write_bytes(b"fake_png_data")

        mock_screenshot.return_value = ScreenshotResult(
            success=True, screenshot_path=str(temp_path)
        )

        # Mock PIL Image.open to return a mock image
        mock_image_instance = Mock()
        mock_pil_open.return_value = mock_image_instance

        mock_ocr.return_value = OCRExtractResult(
            success=True, full_text="Status: OK", text_elements=[]
        )

        result = await screenshot_analyze(
            question=None,  # OCR mode
            x=1200,
            y=0,
            width=300,
            height=100,
        )

        assert result["success"] is True
        # Verify screenshot was called with region params
        mock_screenshot.assert_called_once()
        call_kwargs = mock_screenshot.call_args[1]
        assert call_kwargs["x"] == 1200
        assert call_kwargs["y"] == 0
        assert call_kwargs["width"] == 300
        assert call_kwargs["height"] == 100

        # Cleanup
        if temp_path.exists():
            temp_path.unlink()


class TestBackwardsCompatibility:
    """Test backwards compatibility with old functions."""

    def test_capture_screen_still_exists(self):
        """Verify capture_screen() still exists for compatibility."""
        from code_puppy.tools.gui_cub.screen_capture import capture_screen

        assert callable(capture_screen)

    def test_take_desktop_screenshot_and_analyze_still_exists(self):
        """Verify take_desktop_screenshot_and_analyze() still exists."""
        from code_puppy.tools.gui_cub.screen_capture import (
            take_desktop_screenshot_and_analyze,
        )

        assert callable(take_desktop_screenshot_and_analyze)

    def test_coordinate_conversion_functions_exist(self):
        """Verify coordinate conversion functions still exist."""
        from code_puppy.tools.gui_cub.coordinates import (
            window_to_screen_coords,
            screen_to_window_coords,
        )

        # These should be available
        assert callable(window_to_screen_coords)
        assert callable(screen_to_window_coords)
