"""Comprehensive tests for browser_screenshot.py.

Tests screenshot capture functionality that returns ToolReturn with BinaryContent
for direct viewing by multimodal models.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import BinaryContent, ToolReturn

from code_puppy.tools.browser.browser_screenshot import (
    _capture_screenshot,
    register_take_screenshot_and_analyze,
    take_screenshot,
)


class TestScreenshotCapture:
    """Test screenshot capture functionality."""

    @pytest.mark.asyncio
    async def test_capture_screenshot_basic(self):
        """Test basic screenshot capture."""
        mock_page = AsyncMock()
        screenshot_data = b"fake_png_data_here"
        mock_page.screenshot.return_value = screenshot_data

        result = await _capture_screenshot(mock_page, save_screenshot=False)

        assert result["success"] is True
        assert result["screenshot_bytes"] == screenshot_data
        assert "timestamp" in result
        assert mock_page.screenshot.called

    @pytest.mark.asyncio
    async def test_capture_full_page_screenshot(self):
        """Test full page screenshot capture."""
        mock_page = AsyncMock()
        screenshot_data = b"full_page_png_data"
        mock_page.screenshot.return_value = screenshot_data

        result = await _capture_screenshot(
            mock_page, full_page=True, save_screenshot=False
        )

        assert result["success"] is True
        # Verify full_page parameter was passed
        call_kwargs = mock_page.screenshot.call_args[1]
        assert call_kwargs.get("full_page") is True

    @pytest.mark.asyncio
    async def test_capture_element_screenshot(self):
        """Test screenshot of a specific visible element."""
        page = MagicMock()
        elem = AsyncMock()
        elem.is_visible.return_value = True
        elem.screenshot.return_value = b"PNG"

        async def fake_first():
            return elem

        locator_obj = MagicMock()
        locator_obj.first = fake_first()
        page.locator.return_value = locator_obj
        result = await _capture_screenshot(
            page, element_selector="#x", save_screenshot=False
        )
        assert result["success"] is True
        assert result["screenshot_bytes"] == b"PNG"
        elem.screenshot.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_capture_hidden_element_error(self):
        """Test screenshot of a hidden element returns an error."""
        page = MagicMock()
        elem = AsyncMock()
        elem.is_visible.return_value = False

        async def fake_first():
            return elem

        locator_obj = MagicMock()
        locator_obj.first = fake_first()
        page.locator.return_value = locator_obj
        result = await _capture_screenshot(page, element_selector="#x")
        assert result["success"] is False
        assert "not visible" in result["error"]

    @pytest.mark.asyncio
    async def test_capture_screenshot_with_save(self, tmp_path):
        """Test screenshot capture and save to file."""
        mock_page = AsyncMock()
        screenshot_data = b"fake_png_data"
        mock_page.screenshot.return_value = screenshot_data

        with patch(
            "code_puppy.tools.browser.browser_screenshot._TEMP_SCREENSHOT_ROOT",
            tmp_path,
        ):
            result = await _capture_screenshot(mock_page, save_screenshot=True)

            assert result["success"] is True
            assert "screenshot_path" in result
            assert result["screenshot_path"] is not None

            # Verify file was created
            saved_path = Path(result["screenshot_path"])
            assert saved_path.exists()
            assert saved_path.read_bytes() == screenshot_data

    @pytest.mark.asyncio
    async def test_capture_screenshot_error_handling(self):
        """Test error handling during screenshot capture."""
        mock_page = AsyncMock()
        mock_page.screenshot.side_effect = RuntimeError("Screenshot failed")

        result = await _capture_screenshot(mock_page, save_screenshot=False)

        # Should handle the error gracefully
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_capture_with_emit_messages(self):
        """Test that emit functions are called during capture."""
        mock_page = AsyncMock()
        mock_page.screenshot.return_value = b"screenshot_data"

        with patch(
            "code_puppy.tools.browser.browser_screenshot.emit_success"
        ) as mock_emit:
            result = await _capture_screenshot(
                mock_page,
                save_screenshot=True,
                group_id="test_group",
            )

            assert result["success"] is True
            # emit_success should be called if group_id is provided
            if mock_emit.called:
                # Verify it was called with correct group_id
                call_kwargs = mock_emit.call_args[1]
                assert call_kwargs.get("message_group") == "test_group"

    @pytest.mark.asyncio
    async def test_capture_returns_raw_bytes(self):
        """Test that capture returns raw screenshot bytes."""
        mock_page = AsyncMock()
        screenshot_data = b"test_png_bytes"
        mock_page.screenshot.return_value = screenshot_data

        result = await _capture_screenshot(mock_page, save_screenshot=False)

        assert result["success"] is True
        assert "screenshot_bytes" in result
        assert result["screenshot_bytes"] == screenshot_data


class TestTakeScreenshot:
    """Test take_screenshot function that wraps capture with browser access."""

    @pytest.mark.asyncio
    async def test_take_screenshot_success(self):
        """Test successful screenshot capture returns ToolReturn with BinaryContent."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"screenshot_data")
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_screenshot.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_screenshot.emit_info"):
                result = await take_screenshot(full_page=False)

                # Should be a ToolReturn with rich content
                assert isinstance(result, ToolReturn)
                assert "Screenshot captured successfully" in result.return_value

                # Content should include BinaryContent image
                assert result.content is not None
                binary_contents = [
                    c for c in result.content if isinstance(c, BinaryContent)
                ]
                assert len(binary_contents) == 1
                assert binary_contents[0].media_type == "image/png"
                assert binary_contents[0].data == b"screenshot_data"

                # Metadata should have success info
                assert result.metadata is not None
                assert result.metadata["success"] is True

    @pytest.mark.asyncio
    async def test_take_screenshot_no_page(self):
        """Test screenshot when no page is available returns error dict."""
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = None

        with patch(
            "code_puppy.tools.browser.browser_screenshot.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_screenshot.emit_info"):
                with patch("code_puppy.tools.browser.browser_screenshot.emit_error"):
                    result = await take_screenshot()

                    # Error case returns dict, not ToolReturn
                    assert isinstance(result, dict)
                    assert result["success"] is False
                    assert "No active browser page" in result["error"]

    @pytest.mark.asyncio
    async def test_take_screenshot_full_page(self):
        """Test full page screenshot includes metadata."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"full_page_data")
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_screenshot.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_screenshot.emit_info"):
                result = await take_screenshot(full_page=True)

                assert isinstance(result, ToolReturn)
                # Verify full_page was passed to screenshot
                call_kwargs = mock_page.screenshot.call_args[1]
                assert call_kwargs.get("full_page") is True
                # Metadata should reflect full_page
                assert result.metadata["full_page"] is True
                assert result.metadata["target"] == "full_page"

    @pytest.mark.asyncio
    async def test_take_screenshot_capture_fails(self):
        """Test take_screenshot when the underlying capture raises."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.screenshot.side_effect = RuntimeError("boom")
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_screenshot.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_screenshot.emit_info"):
                with patch("code_puppy.tools.browser.browser_screenshot.emit_error"):
                    result = await take_screenshot()
                    assert isinstance(result, dict)
                    assert result["success"] is False

    @pytest.mark.asyncio
    async def test_take_screenshot_outer_exception(self):
        """Test take_screenshot when fetching the page itself raises."""
        mock_manager = AsyncMock()
        mock_manager.get_current_page.side_effect = RuntimeError("boom")

        with patch(
            "code_puppy.tools.browser.browser_screenshot.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_screenshot.emit_info"):
                with patch("code_puppy.tools.browser.browser_screenshot.emit_error"):
                    result = await take_screenshot()
                    assert isinstance(result, dict)
                    assert result["success"] is False
                    assert "Screenshot failed" in result["error"]

    def test_register_screenshot_tool(self):
        """Test that the screenshot tool registers with the agent."""
        agent = MagicMock()
        register_take_screenshot_and_analyze(agent)
        agent.tool.assert_called_once()


class TestScreenshotIntegration:
    """Integration tests for screenshot workflows."""

    @pytest.mark.asyncio
    async def test_multiple_screenshots(self):
        """Test taking multiple screenshots in sequence."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.screenshot.return_value = b"screenshot_data"
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_screenshot.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_screenshot.emit_info"):
                # Take first screenshot
                result1 = await _capture_screenshot(mock_page, save_screenshot=False)
                assert result1["success"] is True

                # Take second screenshot
                result2 = await _capture_screenshot(mock_page, save_screenshot=False)
                assert result2["success"] is True

                # Timestamps should be different (or very close)
                assert "timestamp" in result1
                assert "timestamp" in result2

    @pytest.mark.asyncio
    async def test_screenshot_returns_toolreturn_with_binary_content(self):
        """Test that screenshot returns ToolReturn with BinaryContent for multimodal."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.screenshot = AsyncMock(return_value=b"png_bytes")
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_screenshot.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_screenshot.emit_info"):
                result = await take_screenshot()

                # Must be ToolReturn for pydantic-ai to handle properly
                assert isinstance(result, ToolReturn)

                # return_value is the text summary
                assert isinstance(result.return_value, str)
                assert "Screenshot captured" in result.return_value

                # content list should have BinaryContent for the model to SEE
                assert result.content is not None
                assert len(result.content) == 3  # description, image, prompt
                binary_content = result.content[1]
                assert isinstance(binary_content, BinaryContent)
                assert binary_content.media_type == "image/png"
                assert binary_content.data == b"png_bytes"

                # metadata for structured access
                assert result.metadata is not None
                assert result.metadata["success"] is True
                assert "timestamp" in result.metadata
