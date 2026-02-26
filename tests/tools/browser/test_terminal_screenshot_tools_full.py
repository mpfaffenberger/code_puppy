"""Full coverage tests for terminal_screenshot_tools.py."""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image
from pydantic_ai import ToolReturn

from code_puppy.tools.browser.terminal_screenshot_tools import (
    _capture_terminal_screenshot,
    _resize_image,
    load_image,
    register_load_image,
    register_terminal_compare_mockup,
    register_terminal_read_output,
    register_terminal_screenshot,
    terminal_read_output,
    terminal_screenshot,
)

MOD = "code_puppy.tools.browser.terminal_screenshot_tools"


@pytest.fixture(autouse=True)
def _suppress():
    with (
        patch(f"{MOD}.emit_info"),
        patch(f"{MOD}.emit_error"),
        patch(f"{MOD}.emit_success"),
    ):
        yield


def _make_png(width=100, height=100):
    img = Image.new("RGB", (width, height), "red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestResizeImage:
    def test_no_resize_needed(self):
        small = _make_png(50, 50)
        result = _resize_image(small, max_height=100)
        assert result == small

    def test_resize_needed(self):
        big = _make_png(200, 1000)
        result = _resize_image(big, max_height=100)
        img = Image.open(io.BytesIO(result))
        assert img.height == 100

    def test_resize_exception(self):
        result = _resize_image(b"not-an-image", max_height=100)
        assert result == b"not-an-image"


class TestCaptureTerminalScreenshot:
    @pytest.mark.asyncio
    async def test_no_page(self):
        mgr = AsyncMock()
        mgr.get_current_page.return_value = None
        with patch(f"{MOD}.get_session_manager", return_value=mgr):
            r = await _capture_terminal_screenshot()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_success_save(self):
        page = AsyncMock()
        page.screenshot.return_value = _make_png(50, 50)
        mgr = AsyncMock()
        mgr.get_current_page.return_value = page
        with patch(f"{MOD}.get_session_manager", return_value=mgr):
            r = await _capture_terminal_screenshot(save_to_disk=True, group_id="g")
            assert r["success"] is True
            assert "screenshot_path" in r

    @pytest.mark.asyncio
    async def test_success_no_save(self):
        page = AsyncMock()
        page.screenshot.return_value = _make_png(50, 50)
        mgr = AsyncMock()
        mgr.get_current_page.return_value = page
        with patch(f"{MOD}.get_session_manager", return_value=mgr):
            r = await _capture_terminal_screenshot(save_to_disk=False)
            assert r["success"] is True
            assert "screenshot_path" not in r

    @pytest.mark.asyncio
    async def test_exception(self):
        mgr = AsyncMock()
        mgr.get_current_page.side_effect = RuntimeError("err")
        with patch(f"{MOD}.get_session_manager", return_value=mgr):
            r = await _capture_terminal_screenshot()
            assert r["success"] is False


class TestTerminalScreenshot:
    @pytest.mark.asyncio
    async def test_success(self):
        with patch(
            f"{MOD}._capture_terminal_screenshot",
            return_value={
                "success": True,
                "screenshot_bytes": b"png",
                "screenshot_path": "/tmp/s.png",
            },
        ):
            r = await terminal_screenshot()
            assert isinstance(r, ToolReturn)

    @pytest.mark.asyncio
    async def test_failure(self):
        with patch(
            f"{MOD}._capture_terminal_screenshot",
            return_value={"success": False, "error": "no page"},
        ):
            r = await terminal_screenshot()
            assert isinstance(r, dict)
            assert r["success"] is False


class TestTerminalReadOutput:
    @pytest.mark.asyncio
    async def test_no_page(self):
        mgr = AsyncMock()
        mgr.get_current_page.return_value = None
        with patch(f"{MOD}.get_session_manager", return_value=mgr):
            r = await terminal_read_output()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_js_fails(self):
        page = AsyncMock()
        page.evaluate.return_value = {"success": False, "error": "no container"}
        mgr = AsyncMock()
        mgr.get_current_page.return_value = page
        with patch(f"{MOD}.get_session_manager", return_value=mgr):
            r = await terminal_read_output()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_truncates_lines(self):
        page = AsyncMock()
        page.evaluate.return_value = {
            "success": True,
            "lines": [f"line{i}" for i in range(100)],
            "method": "row_extraction",
        }
        mgr = AsyncMock()
        mgr.get_current_page.return_value = page
        with patch(f"{MOD}.get_session_manager", return_value=mgr):
            r = await terminal_read_output(lines=10)
            assert r["line_count"] == 10

    @pytest.mark.asyncio
    async def test_exception(self):
        mgr = AsyncMock()
        mgr.get_current_page.side_effect = RuntimeError("boom")
        with patch(f"{MOD}.get_session_manager", return_value=mgr):
            r = await terminal_read_output()
            assert r["success"] is False


class TestLoadImage:
    @pytest.mark.asyncio
    async def test_file_not_found(self):
        r = await load_image("/nonexistent/path.png")
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_path_is_directory(self, tmp_path):
        r = await load_image(str(tmp_path))
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_success(self, tmp_path):
        img_path = tmp_path / "test.png"
        img_path.write_bytes(_make_png(50, 50))
        r = await load_image(str(img_path))
        assert isinstance(r, ToolReturn)

    @pytest.mark.asyncio
    async def test_exception(self, tmp_path):
        img_path = tmp_path / "test.png"
        img_path.write_bytes(b"not-png")
        with patch(f"{MOD}._resize_image", side_effect=RuntimeError("fail")):
            r = await load_image(str(img_path))
            assert r["success"] is False


class TestRegisterFunctions:
    def test_all(self):
        for fn in [
            register_terminal_screenshot,
            register_terminal_read_output,
            register_load_image,
            register_terminal_compare_mockup,
        ]:
            agent = MagicMock()
            fn(agent)
            agent.tool.assert_called_once()
