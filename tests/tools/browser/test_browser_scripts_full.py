"""Full coverage tests for browser_scripts.py - exception branches + register fns."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser.browser_scripts import (
    clear_highlights,
    execute_javascript,
    highlight_element,
    register_browser_clear_highlights,
    register_browser_highlight_element,
    register_execute_javascript,
    register_scroll_page,
    register_scroll_to_element,
    register_set_viewport_size,
    register_wait_for_element,
    scroll_page,
    scroll_to_element,
    set_viewport_size,
    wait_for_element,
)

MOD = "code_puppy.tools.browser.browser_scripts"


@pytest.fixture(autouse=True)
def _suppress():
    with (
        patch(f"{MOD}.emit_info"),
        patch(f"{MOD}.emit_error"),
        patch(f"{MOD}.emit_success"),
    ):
        yield


def _mgr(page):
    mgr = AsyncMock()
    mgr.get_current_page.return_value = page
    return mgr


def _pm(mgr):
    return patch(f"{MOD}.get_session_browser_manager", return_value=mgr)


class TestExceptionBranches:
    @pytest.mark.asyncio
    async def test_execute_js_exception(self):
        page = AsyncMock()
        page.evaluate.side_effect = RuntimeError("err")
        with _pm(_mgr(page)):
            r = await execute_javascript("alert(1)")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_scroll_page_exception(self):
        page = AsyncMock()
        page.evaluate.side_effect = RuntimeError("err")
        with _pm(_mgr(page)):
            r = await scroll_page()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_scroll_to_element_exception(self):
        page = AsyncMock()
        loc = MagicMock()
        loc.first = AsyncMock()
        loc.first.wait_for.side_effect = RuntimeError("err")
        page.locator.return_value = loc
        with _pm(_mgr(page)):
            r = await scroll_to_element("#x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_set_viewport_exception(self):
        page = AsyncMock()
        page.set_viewport_size.side_effect = RuntimeError("err")
        with _pm(_mgr(page)):
            r = await set_viewport_size(800, 600)
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_wait_for_element_exception(self):
        page = AsyncMock()
        loc = MagicMock()
        loc.first = AsyncMock()
        loc.first.wait_for.side_effect = RuntimeError("timeout")
        page.locator.return_value = loc
        with _pm(_mgr(page)):
            r = await wait_for_element("#x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_highlight_element_exception(self):
        page = AsyncMock()
        loc = MagicMock()
        loc.first = AsyncMock()
        loc.first.wait_for.side_effect = RuntimeError("err")
        page.locator.return_value = loc
        with _pm(_mgr(page)):
            r = await highlight_element("#x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_clear_highlights_exception(self):
        page = AsyncMock()
        page.evaluate.side_effect = RuntimeError("err")
        with _pm(_mgr(page)):
            r = await clear_highlights()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_scroll_page_element_selector(self):
        """Test scroll_page with element_selector for left/right/up directions."""
        for direction in ["up", "left", "right"]:
            page = MagicMock()  # sync locator call
            elem = AsyncMock()
            elem.evaluate.return_value = {
                "scrollTop": 0,
                "scrollLeft": 0,
                "scrollHeight": 1000,
                "scrollWidth": 1000,
                "clientHeight": 500,
                "clientWidth": 500,
            }
            loc = MagicMock()
            loc.first = elem
            page.locator.return_value = loc

            async def mock_evaluate(script):
                if "pageXOffset" in script or "pageYOffset" in script:
                    return {"x": 0, "y": 0}
                return 800

            page.evaluate = mock_evaluate

            with _pm(_mgr(page)):
                r = await scroll_page(
                    direction=direction, element_selector=".container"
                )
                assert r["success"] is True

    @pytest.mark.asyncio
    async def test_scroll_page_directions(self):
        """Test page-level scroll in all directions."""
        for direction in ["up", "left", "right"]:
            page = MagicMock()

            async def mock_evaluate(script):
                if "innerHeight" in script:
                    return 800
                return {"x": 0, "y": 0}

            page.evaluate = mock_evaluate

            with _pm(_mgr(page)):
                r = await scroll_page(direction=direction)
                assert r["success"] is True


class TestRegisterFunctions:
    def test_all(self):
        for fn in [
            register_execute_javascript,
            register_scroll_page,
            register_scroll_to_element,
            register_set_viewport_size,
            register_wait_for_element,
            register_browser_highlight_element,
            register_browser_clear_highlights,
        ]:
            agent = MagicMock()
            fn(agent)
            agent.tool.assert_called_once()
