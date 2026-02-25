"""Full coverage tests for browser_screenshot.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser.browser_screenshot import (
    _capture_screenshot,
    register_take_screenshot_and_analyze,
    take_screenshot,
)

MOD = "code_puppy.tools.browser.browser_screenshot"


@pytest.fixture(autouse=True)
def _suppress():
    with (
        patch(f"{MOD}.emit_info"),
        patch(f"{MOD}.emit_error"),
        patch(f"{MOD}.emit_success"),
    ):
        yield


class TestCaptureScreenshot:
    @pytest.mark.asyncio
    async def test_element_not_visible(self):
        # The code does: element = await page.locator(sel).first
        # This is quirky - we need locator().first to be awaitable
        # Use a coroutine-returning property
        page = MagicMock()
        elem = AsyncMock()
        elem.is_visible.return_value = False

        async def fake_first():
            return elem

        locator_obj = MagicMock()
        locator_obj.first = fake_first()
        page.locator.return_value = locator_obj
        r = await _capture_screenshot(page, element_selector="#x")
        assert r["success"] is False
        assert "not visible" in r["error"]

    @pytest.mark.asyncio
    async def test_element_visible(self):
        page = MagicMock()
        elem = AsyncMock()
        elem.is_visible.return_value = True
        elem.screenshot.return_value = b"PNG"

        async def fake_first():
            return elem

        locator_obj = MagicMock()
        locator_obj.first = fake_first()
        page.locator.return_value = locator_obj
        r = await _capture_screenshot(
            page, element_selector="#x", save_screenshot=False
        )
        assert r["success"] is True

    @pytest.mark.asyncio
    async def test_exception(self):
        page = AsyncMock()
        page.screenshot.side_effect = RuntimeError("err")
        r = await _capture_screenshot(page)
        assert r["success"] is False


class TestTakeScreenshot:
    @pytest.mark.asyncio
    async def test_no_page(self):
        mgr = AsyncMock()
        mgr.get_current_page.return_value = None
        with patch(f"{MOD}.get_session_browser_manager", return_value=mgr):
            r = await take_screenshot()
            assert isinstance(r, dict)
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_capture_fails(self):
        mgr = AsyncMock()
        page = AsyncMock()
        page.screenshot.side_effect = RuntimeError("fail")
        mgr.get_current_page.return_value = page
        with patch(f"{MOD}.get_session_browser_manager", return_value=mgr):
            r = await take_screenshot()
            assert isinstance(r, dict)
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_outer_exception(self):
        mgr = AsyncMock()
        mgr.get_current_page.side_effect = RuntimeError("boom")
        with patch(f"{MOD}.get_session_browser_manager", return_value=mgr):
            r = await take_screenshot()
            assert r["success"] is False


class TestRegister:
    def test_register(self):
        agent = MagicMock()
        register_take_screenshot_and_analyze(agent)
        agent.tool.assert_called_once()
