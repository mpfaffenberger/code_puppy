"""Comprehensive tests for browser_scripts.py module.

Tests JavaScript execution, page manipulation, scrolling (page- and
element-level in every direction), viewport management, element highlighting,
and waiting strategies — plus every exception and no-active-page branch. The
repetitive per-operation bodies are table-driven with the distinct assertions
preserved.
"""

from contextlib import contextmanager
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


@contextmanager
def _mgr(manager):
    with patch(f"{MOD}.get_session_browser_manager", return_value=manager):
        yield


class BrowserScriptsBaseTest:
    """Base fixtures for mocking the browser manager, page and locator."""

    @pytest.fixture
    def mock_browser_manager(self):
        manager = AsyncMock()
        page = AsyncMock()
        page.locator = MagicMock()
        manager.get_current_page.return_value = page
        return manager, page

    @pytest.fixture
    def mock_locator(self):
        locator = AsyncMock()
        locator.wait_for = AsyncMock()
        locator.scroll_into_view_if_needed = AsyncMock()
        locator.is_visible = AsyncMock(return_value=True)
        locator.evaluate = AsyncMock()
        locator.first = locator  # support .first strict-mode chaining
        return locator

    @pytest.fixture
    def mock_context(self):
        return MagicMock()


class TestExecuteJavaScript(BrowserScriptsBaseTest):
    """JavaScript execution result shapes and failure handling."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "return_value,expected",
        [
            (
                {"success": True, "data": "result"},
                {
                    "success": True,
                    "script": "return document.title;",
                    "result": {"success": True, "data": "result"},
                },
            ),
            (
                None,
                {"success": True, "script": "console.log('hello');", "result": None},
            ),
            (
                "Hello World",
                {
                    "success": True,
                    "script": "return 'Hello World';",
                    "result": "Hello World",
                },
            ),
        ],
        ids=["dict", "void", "string"],
    )
    async def test_execute_javascript_results(
        self, mock_browser_manager, return_value, expected
    ):
        manager, page = mock_browser_manager
        page.evaluate.return_value = return_value
        with _mgr(manager):
            result = await execute_javascript(expected["script"], timeout=5000)
        assert result["success"] is expected["success"]
        assert result["script"] == expected["script"]
        assert result["result"] == expected["result"]
        # page.evaluate() does not accept a timeout param in Playwright
        page.evaluate.assert_called_once_with(expected["script"])

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "error_message",
        ["Syntax Error", "Timeout"],
        ids=["syntax-error", "timeout"],
    )
    async def test_execute_javascript_exception(
        self, mock_browser_manager, error_message
    ):
        manager, page = mock_browser_manager
        page.evaluate.side_effect = Exception(error_message)
        script = (
            "invalid javaScript code" if "yntax" in error_message else "while(true) { }"
        )
        with _mgr(manager):
            result = await execute_javascript(script, timeout=1000)
        assert result["success"] is False
        assert error_message in result["error"] or "exceeded" in result["error"]
        assert result["script"] == script


class TestScrollPage(BrowserScriptsBaseTest):
    """Page- and element-level scrolling in every direction."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "direction,amount,position,scroll_by",
        [
            ("down", 3, {"x": 0, "y": 200}, "window.scrollBy(0, 600.0)"),
            ("up", 2, {"x": 0, "y": -100}, "window.scrollBy(0, -400.0)"),
            ("left", 3, {"x": -150, "y": 0}, "window.scrollBy(-600.0, 0)"),
            ("right", 3, {"x": 150, "y": 0}, "window.scrollBy(600.0, 0)"),
        ],
        ids=["down", "up", "left", "right"],
    )
    async def test_scroll_page_directions(
        self, mock_browser_manager, direction, amount, position, scroll_by
    ):
        manager, page = mock_browser_manager
        page.evaluate.side_effect = [600, None, position]
        with _mgr(manager):
            result = await scroll_page(direction=direction, amount=amount)

        assert result["success"]
        assert result["direction"] == direction
        assert result["amount"] == amount
        assert result["target"] == "page"
        assert result["scroll_position"] == position
        page.evaluate.assert_any_call(scroll_by)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "direction", ["down", "up", "left", "right"], ids=lambda x: x
    )
    async def test_scroll_page_element_directions(
        self, mock_browser_manager, mock_locator, direction
    ):
        manager, page = mock_browser_manager
        locator = mock_locator
        scroll_info = {
            "scrollTop": 0,
            "scrollLeft": 0,
            "scrollHeight": 1000,
            "scrollWidth": 800,
            "clientHeight": 200,
            "clientWidth": 400,
        }
        locator.evaluate.side_effect = [scroll_info, None]
        page.evaluate.return_value = {"x": 0, "y": 0}

        with _mgr(manager):
            page.locator.return_value = locator
            result = await scroll_page(
                direction=direction, amount=3, element_selector="#scrollable-div"
            )

        assert result["success"]
        assert result["target"] == "element '#scrollable-div'"
        locator.scroll_into_view_if_needed.assert_called_once()
        locator.evaluate.assert_called()

    @pytest.mark.asyncio
    async def test_scroll_page_exception(self, mock_browser_manager):
        manager, page = mock_browser_manager
        page.evaluate.side_effect = Exception("Scroll failed")
        with _mgr(manager):
            result = await scroll_page("down", 3)
        assert result["success"] is False
        assert "Scroll failed" in result["error"]


class TestScrollToElement(BrowserScriptsBaseTest):
    """scroll_to_element success, invisible, and failure branches."""

    @pytest.mark.asyncio
    async def test_scroll_to_element_success(self, mock_browser_manager, mock_locator):
        manager, page = mock_browser_manager
        locator = mock_locator
        with _mgr(manager):
            page.locator.return_value = locator
            result = await scroll_to_element("#target-element", timeout=5000)

        assert result["success"]
        assert result["selector"] == "#target-element"
        assert result["visible"] is True
        locator.wait_for.assert_called_once_with(state="attached", timeout=5000)
        locator.scroll_into_view_if_needed.assert_called_once()
        locator.is_visible.assert_called_once()

    @pytest.mark.asyncio
    async def test_scroll_to_element_not_visible(
        self, mock_browser_manager, mock_locator
    ):
        manager, page = mock_browser_manager
        locator = mock_locator
        locator.is_visible.return_value = False
        with _mgr(manager):
            page.locator.return_value = locator
            result = await scroll_to_element("#hidden-element")
        assert result["success"]
        assert result["visible"] is False

    @pytest.mark.asyncio
    async def test_scroll_to_element_exception(self, mock_browser_manager):
        manager, page = mock_browser_manager
        page.locator.side_effect = Exception("Element not found")
        with _mgr(manager):
            result = await scroll_to_element("#nonexistent")
        assert result["success"] is False
        assert "Element not found" in result["error"]


class TestSetViewportSize(BrowserScriptsBaseTest):
    """set_viewport_size success (desktop + mobile) and failure."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "width,height",
        [(1200, 800), (375, 667)],
        ids=["desktop", "mobile"],
    )
    async def test_set_viewport_size_success(self, mock_browser_manager, width, height):
        manager, page = mock_browser_manager
        with _mgr(manager):
            result = await set_viewport_size(width=width, height=height)
        assert result["success"]
        assert result["width"] == width
        assert result["height"] == height
        page.set_viewport_size.assert_called_once_with(
            {"width": width, "height": height}
        )

    @pytest.mark.asyncio
    async def test_set_viewport_size_exception(self, mock_browser_manager):
        manager, page = mock_browser_manager
        page.set_viewport_size.side_effect = Exception("Invalid viewport size")
        with _mgr(manager):
            result = await set_viewport_size(-100, -100)
        assert result["success"] is False
        assert "Invalid viewport size" in result["error"]
        assert result["width"] == -100
        assert result["height"] == -100


class TestWaitForElement(BrowserScriptsBaseTest):
    """wait_for_element for every state plus timeout failure."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "state,timeout",
        [
            ("visible", 5000),
            ("hidden", 30000),
            ("attached", 30000),
            ("detached", 30000),
        ],
        ids=["visible", "hidden", "attached", "detached"],
    )
    async def test_wait_for_element_states(
        self, mock_browser_manager, mock_locator, state, timeout
    ):
        manager, page = mock_browser_manager
        locator = mock_locator
        selector = f"#element-{state}"
        with _mgr(manager):
            page.locator.return_value = locator
            result = await wait_for_element(selector, state=state, timeout=timeout)
        assert result["success"]
        assert result["selector"] == selector
        assert result["state"] == state
        locator.wait_for.assert_called_once_with(state=state, timeout=timeout)

    @pytest.mark.asyncio
    async def test_wait_for_element_timeout(self, mock_browser_manager, mock_locator):
        manager, page = mock_browser_manager
        locator = mock_locator
        locator.wait_for.side_effect = Exception("Timeout exceeded")
        with _mgr(manager):
            page.locator.return_value = locator
            result = await wait_for_element("#slow-element", timeout=1000)
        assert result["success"] is False
        assert "Timeout exceeded" in result["error"]
        assert result["selector"] == "#slow-element"


class TestHighlightElement(BrowserScriptsBaseTest):
    """highlight_element in different colors plus failure."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("color", ["red", "blue"], ids=lambda c: c)
    async def test_highlight_element_success(
        self, mock_browser_manager, mock_locator, color
    ):
        manager, page = mock_browser_manager
        locator = mock_locator
        with _mgr(manager):
            page.locator.return_value = locator
            result = await highlight_element("#target", color=color, timeout=5000)

        assert result["success"]
        assert result["selector"] == "#target"
        assert result["color"] == color
        locator.wait_for.assert_called_once_with(state="visible", timeout=5000)
        locator.evaluate.assert_called_once()
        highlight_script = locator.evaluate.call_args[0][0]
        assert color in highlight_script
        assert "data-highlighted" in highlight_script

    @pytest.mark.asyncio
    async def test_highlight_element_exception(self, mock_browser_manager):
        manager, page = mock_browser_manager
        page.locator.side_effect = Exception("Element not found")
        with _mgr(manager):
            result = await highlight_element("#missing")
        assert result["success"] is False
        assert "Element not found" in result["error"]


class TestClearHighlights(BrowserScriptsBaseTest):
    """clear_highlights success (with/without highlights) and failure."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("count", [3, 0], ids=["some", "none"])
    async def test_clear_highlights_success(self, mock_browser_manager, count):
        manager, page = mock_browser_manager
        page.evaluate.return_value = count
        with _mgr(manager):
            result = await clear_highlights()
        assert result["success"]
        assert result["cleared_count"] == count
        page.evaluate.assert_called_once()
        clear_script = page.evaluate.call_args[0][0]
        assert "data-highlighted" in clear_script
        assert "removeAttribute" in clear_script

    @pytest.mark.asyncio
    async def test_clear_highlights_exception(self, mock_browser_manager):
        manager, page = mock_browser_manager
        page.evaluate.side_effect = Exception("JavaScript error")
        with _mgr(manager):
            result = await clear_highlights()
        assert result["success"] is False
        assert "JavaScript error" in result["error"]


class TestIntegrationScenarios(BrowserScriptsBaseTest):
    """Integration scenarios combining multiple script functions."""

    @pytest.mark.asyncio
    async def test_page_manipulation_workflow(self, mock_browser_manager, mock_locator):
        manager, page = mock_browser_manager
        locator = mock_locator
        page.evaluate.side_effect = [
            {"success": True},  # execute_javascript
            600,  # scroll_page viewport height
            None,  # scrollBy
            {"x": 0, "y": 300},  # scroll position
        ]
        with _mgr(manager):
            page.locator.return_value = locator
            viewport_result = await set_viewport_size(1200, 800)
            js_result = await execute_javascript("document.title = 'Test'")
            scroll_result = await scroll_page("down", 3)
            highlight_result = await highlight_element("#main")

        assert all(
            r["success"]
            for r in [viewport_result, js_result, scroll_result, highlight_result]
        )
        page.set_viewport_size.assert_called_once()
        page.evaluate.assert_called()
        locator.evaluate.assert_called()

    @pytest.mark.asyncio
    async def test_highlight_and_clear_sequence(
        self, mock_browser_manager, mock_locator
    ):
        manager, page = mock_browser_manager
        locator = mock_locator
        with _mgr(manager):
            page.locator.return_value = locator
            page.evaluate.return_value = 2
            result1 = await highlight_element("#element1", "red")
            result2 = await highlight_element("#element2", "blue")
            clear_result = await clear_highlights()

        assert result1["success"] and result2["success"] and clear_result["success"]
        assert clear_result["cleared_count"] == 2
        assert locator.evaluate.call_count == 2
        page.evaluate.assert_called()


@pytest.mark.parametrize(
    "register_func,expected_tool",
    [
        (register_execute_javascript, "browser_execute_js"),
        (register_scroll_page, "browser_scroll"),
        (register_scroll_to_element, "browser_scroll_to_element"),
        (register_set_viewport_size, "browser_set_viewport"),
        (register_wait_for_element, "browser_wait_for_element"),
        (register_browser_highlight_element, "browser_highlight_element"),
        (register_browser_clear_highlights, "browser_clear_highlights"),
    ],
    ids=[
        "execute_javascript",
        "scroll_page",
        "scroll_to_element",
        "set_viewport_size",
        "wait_for_element",
        "highlight_element",
        "clear_highlights",
    ],
)
class TestToolRegistration:
    """Parametrized registration checks for every tool in this module."""

    def test_register_tool(self, register_func, expected_tool):
        agent = MagicMock()
        register_func(agent)
        agent.tool.assert_called_once()
        tool_name = agent.tool.call_args[0][0]
        assert tool_name.__name__ == expected_tool


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("func", "args"),
    [
        (execute_javascript, ("return true;",)),
        (scroll_page, ("down", 3)),
        (scroll_to_element, ("#element",)),
        (set_viewport_size, (800, 600)),
        (wait_for_element, ("#element",)),
        (highlight_element, ("#element",)),
        (clear_highlights, ()),
    ],
    ids=[
        "execute_javascript",
        "scroll_page",
        "scroll_to_element",
        "set_viewport_size",
        "wait_for_element",
        "highlight_element",
        "clear_highlights",
    ],
)
class TestNoActivePage(BrowserScriptsBaseTest):
    """Every script tool degrades gracefully when no page is active."""

    async def test_no_active_page(self, mock_browser_manager, func, args):
        manager, page = mock_browser_manager
        manager.get_current_page.return_value = None
        with _mgr(manager):
            result = await func(*args)
        assert result["success"] is False
        assert "No active browser page available" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__])
