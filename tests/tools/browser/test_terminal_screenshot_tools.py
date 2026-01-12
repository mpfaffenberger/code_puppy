"""Comprehensive tests for terminal_screenshot_tools.py.

Tests terminal screenshot analysis, output reading, mockup comparison,
and image analysis with extensive mocking to avoid actual browser
and VQA model operations.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import BinaryContent, ToolReturn

from code_puppy.tools.browser.terminal_screenshot_tools import (
    XTERM_TEXT_EXTRACTION_JS,
    _build_screenshot_path,
    _capture_terminal_screenshot,
    load_image,
    register_load_image,
    register_terminal_compare_mockup,
    register_terminal_read_output,
    register_terminal_screenshot,
    terminal_read_output,
    terminal_screenshot,
)


class TestBuildScreenshotPath:
    """Tests for _build_screenshot_path helper function."""

    def test_build_screenshot_path_format(self):
        """Test that screenshot path has correct format."""
        path = _build_screenshot_path("terminal")

        assert "terminal" in path.name
        assert path.suffix == ".png"
        # Verify it has timestamp format (YYYYMMDD_HHMMSS_FFFFFF)
        assert len(path.name) > len("terminal.png")

    def test_build_screenshot_path_different_prefixes(self):
        """Test path generation with different prefixes."""
        terminal_path = _build_screenshot_path("terminal")
        comparison_path = _build_screenshot_path("comparison")

        assert "terminal" in terminal_path.name
        assert "comparison" in comparison_path.name
        assert terminal_path != comparison_path


class TestCaptureTerminalScreenshot:
    """Tests for _capture_terminal_screenshot internal function."""

    @pytest.mark.asyncio
    async def test_capture_screenshot_success(self):
        """Test successful screenshot capture."""
        mock_page = AsyncMock()
        mock_page.screenshot.return_value = b"fake_screenshot_data"
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools.get_session_manager",
            return_value=mock_manager,
        ):
            result = await _capture_terminal_screenshot(
                full_page=False,
                save_to_disk=False,
            )

            assert result["success"] is True
            assert result["screenshot_bytes"] == b"fake_screenshot_data"

    @pytest.mark.asyncio
    async def test_capture_screenshot_no_page(self):
        """Test screenshot capture when no page is available."""
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = None

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools.get_session_manager",
            return_value=mock_manager,
        ):
            result = await _capture_terminal_screenshot()

            assert result["success"] is False
            assert "No active terminal page" in result["error"]

    @pytest.mark.asyncio
    async def test_capture_screenshot_full_page(self):
        """Test full page screenshot capture."""
        mock_page = AsyncMock()
        mock_page.screenshot.return_value = b"full_page_data"
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools.get_session_manager",
            return_value=mock_manager,
        ):
            result = await _capture_terminal_screenshot(
                full_page=True,
                save_to_disk=False,
            )

            assert result["success"] is True
            mock_page.screenshot.assert_called_once_with(full_page=True, type="png")

    @pytest.mark.asyncio
    async def test_capture_screenshot_saves_file(self):
        """Test that screenshot is saved when save_to_disk=True."""
        mock_page = AsyncMock()
        mock_page.screenshot.return_value = b"screenshot_bytes"
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools.get_session_manager",
            return_value=mock_manager,
        ):
            result = await _capture_terminal_screenshot(
                save_to_disk=True,
            )

            assert result["success"] is True
            assert "screenshot_path" in result
            # Verify the file was created
            screenshot_path = Path(result["screenshot_path"])
            assert screenshot_path.exists()
            # Cleanup
            screenshot_path.unlink()

    @pytest.mark.asyncio
    async def test_capture_screenshot_handles_error(self):
        """Test error handling during screenshot capture."""
        mock_page = AsyncMock()
        mock_page.screenshot.side_effect = RuntimeError("Screenshot failed")
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools.get_session_manager",
            return_value=mock_manager,
        ):
            result = await _capture_terminal_screenshot()

            assert result["success"] is False
            assert "Screenshot failed" in result["error"]


class TestTerminalScreenshot:
    """Tests for terminal_screenshot function."""

    @pytest.mark.asyncio
    async def test_screenshot_success(self):
        """Test successful terminal screenshot returns ToolReturn with BinaryContent."""
        mock_page = AsyncMock()
        mock_page.screenshot.return_value = b"screenshot"
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools.get_session_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                ):
                    result = await terminal_screenshot(full_page=False)

                    # Should be ToolReturn with BinaryContent
                    assert isinstance(result, ToolReturn)
                    assert "screenshot" in result.return_value.lower()

                    # Content should include BinaryContent image
                    binary_contents = [
                        c for c in result.content if isinstance(c, BinaryContent)
                    ]
                    assert len(binary_contents) == 1
                    assert binary_contents[0].media_type == "image/png"

                    # Metadata should have success info
                    assert result.metadata["success"] is True


class TestTerminalReadOutput:
    """Tests for terminal_read_output function."""

    @pytest.mark.asyncio
    async def test_read_output_success(self):
        """Test successful terminal output reading."""
        mock_page = AsyncMock()
        mock_page.evaluate.return_value = {
            "success": True,
            "lines": ["$ ls", "file1.txt", "file2.txt", "$ _"],
            "method": "dom_scraping",
        }
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools.get_session_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                ):
                    result = await terminal_read_output(lines=50)

                    assert result["success"] is True
                    assert "$ ls" in result["output"]
                    assert result["line_count"] == 4

    @pytest.mark.asyncio
    async def test_read_output_limited_lines(self):
        """Test reading limited number of lines."""
        mock_page = AsyncMock()
        mock_page.evaluate.return_value = {
            "success": True,
            "lines": ["line1", "line2", "line3", "line4", "line5"],
            "method": "dom_scraping",
        }
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools.get_session_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                ):
                    result = await terminal_read_output(lines=2)

                    assert result["success"] is True
                    assert result["line_count"] == 2
                    # Should get last 2 lines
                    assert "line4" in result["output"]
                    assert "line5" in result["output"]

    @pytest.mark.asyncio
    async def test_read_output_no_page(self):
        """Test reading when no terminal page is available."""
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = None

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools.get_session_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_error"
                ):
                    result = await terminal_read_output()

                    assert result["success"] is False
                    assert "No active terminal page" in result["error"]

    @pytest.mark.asyncio
    async def test_read_output_extraction_failure(self):
        """Test handling when DOM extraction fails."""
        mock_page = AsyncMock()
        mock_page.evaluate.return_value = {
            "success": False,
            "error": "Could not find xterm.js terminal container",
        }
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools.get_session_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_error"
                ):
                    result = await terminal_read_output()

                    assert result["success"] is False
                    assert "xterm.js" in result["error"]

    @pytest.mark.asyncio
    async def test_read_output_javascript_error(self):
        """Test handling when page.evaluate throws error."""
        mock_page = AsyncMock()
        mock_page.evaluate.side_effect = RuntimeError("JavaScript error")
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools.get_session_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_error"
                ):
                    result = await terminal_read_output()

                    assert result["success"] is False
                    assert "JavaScript error" in result["error"]


class TestLoadImage:
    """Tests for load_image function."""

    @pytest.mark.asyncio
    async def test_load_image_success(self):
        """Test successful image loading returns ToolReturn with BinaryContent."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"fake_image_data")
            image_path = f.name

        try:
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                ):
                    result = await load_image(image_path=image_path)

                    # Should be ToolReturn with BinaryContent
                    assert isinstance(result, ToolReturn)
                    assert image_path in result.return_value

                    # Content should include BinaryContent image
                    binary_contents = [
                        c for c in result.content if isinstance(c, BinaryContent)
                    ]
                    assert len(binary_contents) == 1
                    assert binary_contents[0].media_type == "image/png"

                    # Metadata should have path info
                    assert result.metadata["success"] is True
                    assert result.metadata["image_path"] == image_path
        finally:
            Path(image_path).unlink()

    @pytest.mark.asyncio
    async def test_load_image_not_found(self):
        """Test handling when image file doesn't exist."""
        with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_error"):
                result = await load_image(image_path="/nonexistent/image.png")

                assert result["success"] is False
                assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_load_image_is_directory(self):
        """Test handling when image path is a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_error"
                ):
                    result = await load_image(image_path=tmpdir)

                    assert result["success"] is False
                    assert "not a file" in result["error"]

    @pytest.mark.asyncio
    async def test_load_image_different_formats(self):
        """Test loading different image formats returns ToolReturn."""
        formats = [
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".webp",
        ]

        for suffix in formats:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(b"image_data")
                image_path = f.name

            try:
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_info"
                ):
                    with patch(
                        "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                    ):
                        result = await load_image(image_path=image_path)

                        assert isinstance(result, ToolReturn)
                        # All images are converted to PNG after resizing
                        binary_contents = [
                            c for c in result.content if isinstance(c, BinaryContent)
                        ]
                        assert len(binary_contents) == 1
                        assert binary_contents[0].media_type == "image/png"
            finally:
                Path(image_path).unlink()

    @pytest.mark.asyncio
    async def test_load_image_read_error(self):
        """Test handling when image read fails."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"data")
            image_path = f.name

        try:
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_error"
                ):
                    # Mock Path.read_bytes to fail
                    with patch(
                        "code_puppy.tools.browser.terminal_screenshot_tools.Path.read_bytes",
                        side_effect=RuntimeError("Read failed"),
                    ):
                        result = await load_image(image_path=image_path)

                        assert result["success"] is False
                        assert "Failed to load image" in result["error"]
        finally:
            Path(image_path).unlink()


class TestToolRegistration:
    """Tests for tool registration functions."""

    def test_register_terminal_screenshot(self):
        """Test terminal_screenshot registration."""
        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(return_value=lambda f: f)

        register_terminal_screenshot(mock_agent)

        assert mock_agent.tool.called

    def test_register_terminal_read_output(self):
        """Test terminal_read_output registration."""
        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(return_value=lambda f: f)

        register_terminal_read_output(mock_agent)

        assert mock_agent.tool.called

    def test_register_terminal_compare_mockup(self):
        """Test terminal_compare_mockup registration."""
        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(return_value=lambda f: f)

        register_terminal_compare_mockup(mock_agent)

        assert mock_agent.tool.called

    def test_register_load_image(self):
        """Test load_image registration."""
        mock_agent = MagicMock()
        mock_agent.tool = MagicMock(return_value=lambda f: f)

        register_load_image(mock_agent)

        assert mock_agent.tool.called


class TestXtermExtractionJavaScript:
    """Tests for the xterm.js text extraction JavaScript."""

    def test_javascript_is_valid_string(self):
        """Test that the JS extraction code is a valid string."""
        assert isinstance(XTERM_TEXT_EXTRACTION_JS, str)
        assert len(XTERM_TEXT_EXTRACTION_JS) > 0

    def test_javascript_contains_selectors(self):
        """Test that JS code contains expected xterm selectors."""
        assert ".xterm-rows" in XTERM_TEXT_EXTRACTION_JS
        assert ".xterm" in XTERM_TEXT_EXTRACTION_JS

    def test_javascript_returns_structure(self):
        """Test that JS code returns expected structure."""
        assert "success" in XTERM_TEXT_EXTRACTION_JS
        assert "lines" in XTERM_TEXT_EXTRACTION_JS
        assert "error" in XTERM_TEXT_EXTRACTION_JS


class TestIntegrationScenarios:
    """Integration-like tests for full workflows."""

    @pytest.mark.asyncio
    async def test_screenshot_then_load_image_workflow(self):
        """Test taking screenshot then loading an image - both return ToolReturn."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"image_data")
            image_path = f.name

        try:
            mock_page = AsyncMock()
            mock_page.screenshot.return_value = b"screenshot"
            mock_manager = AsyncMock()
            mock_manager.get_current_page.return_value = mock_page

            with patch(
                "code_puppy.tools.browser.terminal_screenshot_tools.get_session_manager",
                return_value=mock_manager,
            ):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_info"
                ):
                    with patch(
                        "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                    ):
                        # First take screenshot
                        screenshot_result = await terminal_screenshot(full_page=False)
                        assert isinstance(screenshot_result, ToolReturn)
                        assert screenshot_result.metadata["success"] is True

                        # Then load image
                        load_result = await load_image(image_path=image_path)
                        assert isinstance(load_result, ToolReturn)
                        assert load_result.metadata["success"] is True
        finally:
            Path(image_path).unlink()

    @pytest.mark.asyncio
    async def test_read_output_then_screenshot_workflow(self):
        """Test reading output then taking screenshot - screenshot returns ToolReturn."""
        mock_page = AsyncMock()
        mock_page.evaluate.return_value = {
            "success": True,
            "lines": ["$ echo hello", "hello"],
            "method": "dom_scraping",
        }
        mock_page.screenshot.return_value = b"screenshot"
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.terminal_screenshot_tools.get_session_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.terminal_screenshot_tools.emit_info"):
                with patch(
                    "code_puppy.tools.browser.terminal_screenshot_tools.emit_success"
                ):
                    # First read output (still returns dict)
                    read_result = await terminal_read_output(lines=10)
                    assert read_result["success"] is True
                    assert "hello" in read_result["output"]

                    # Then take screenshot (returns ToolReturn now!)
                    screenshot_result = await terminal_screenshot(full_page=False)
                    assert isinstance(screenshot_result, ToolReturn)
                    assert screenshot_result.metadata["success"] is True
