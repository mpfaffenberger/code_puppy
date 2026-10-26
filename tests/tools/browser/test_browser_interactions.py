"""Comprehensive tests for browser_interactions.py module.

Tests browser element interactions — clicking, typing, form manipulation,
hovering, and other user actions. A single operation table drives the shared
success / no-active-page / exception branches across every operation; the
per-operation option variants and integration scenarios keep their distinct
assertions so no branch is lost.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser import browser_interactions as interactions

MOD = interactions.__name__

# Operation table legend: fn/args/kwargs to invoke, wait_timeout, expected locator
# method+args, pre-invocations, mocked ret, and expected result keys/dict.
OPS = [
    {
        "name": "click",
        "fn": interactions.click_element,
        "args": ("#submit-button",),
        "method": "click",
        "method_kwargs": {"force": False, "button": "left", "timeout": 10000},
        "result": {"action": "left_click", "selector": "#submit-button"},
    },
    {
        "name": "double_click",
        "fn": interactions.double_click_element,
        "args": ("#double-click-area",),
        "method": "dblclick",
        "method_kwargs": {"force": False, "timeout": 10000},
        "result": {"action": "double_click", "selector": "#double-click-area"},
    },
    {
        "name": "hover",
        "fn": interactions.hover_element,
        "args": ("#hover-menu",),
        "method": "hover",
        "method_kwargs": {"force": False, "timeout": 10000},
        "result": {"action": "hover", "selector": "#hover-menu"},
    },
    {
        "name": "set_text",
        "fn": interactions.set_element_text,
        "args": ("#input-field", "new text"),
        "method": "fill",
        "method_args": ("new text",),
        "method_kwargs": {"timeout": 10000},
        "pre": [("clear", (), {"timeout": 10000})],
        "result": {"action": "set_text", "text": "new text"},
    },
    {
        "name": "get_text",
        "fn": interactions.get_element_text,
        "args": ("#content",),
        "kwargs": {"timeout": 5000},
        "method": "text_content",
        "ret": "Element content",
        "wait_timeout": 5000,
        "result": {"text": "Element content", "selector": "#content"},
    },
    {
        "name": "get_value",
        "fn": interactions.get_element_value,
        "args": ("#input-field",),
        "method": "input_value",
        "ret": "current value",
        "result": {"value": "current value", "selector": "#input-field"},
    },
    {
        "name": "select",
        "fn": interactions.select_option,
        "args": ("#dropdown",),
        "kwargs": {"value": "option1"},
        "method": "select_option",
        "method_kwargs": {"value": "option1", "timeout": 10000},
        "result": {"selection": "option1", "selector": "#dropdown"},
    },
    {
        "name": "check",
        "fn": interactions.check_element,
        "args": ("#checkbox",),
        "method": "check",
        "method_kwargs": {"timeout": 10000},
        "result": {"action": "check", "selector": "#checkbox"},
    },
    {
        "name": "uncheck",
        "fn": interactions.uncheck_element,
        "args": ("#checkbox",),
        "method": "uncheck",
        "method_kwargs": {"timeout": 10000},
        "result": {"action": "uncheck", "selector": "#checkbox"},
    },
]


@pytest.fixture
def browser_page():
    """Manager + page + ready interaction locator, all mocked."""
    manager = MagicMock()
    page = MagicMock()
    manager.get_current_page = AsyncMock(return_value=page)
    locator = AsyncMock()
    locator.first = locator  # support .first strict-mode chaining
    page.locator.return_value = locator
    return manager, page, locator


async def _call(op, manager, **overrides):
    with patch(f"{MOD}.get_session_browser_manager", return_value=manager):
        return await op["fn"](*op["args"], **{**op.get("kwargs", {}), **overrides})


class TestSuccessBranches:
    """Shared success-path assertions for every operation."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("op", OPS, ids=lambda op: op["name"])
    async def test_operation_success(self, browser_page, op):
        manager, page, locator = browser_page
        if "ret" in op:
            getattr(locator, op["method"]).return_value = op["ret"]

        result = await _call(op, manager)

        assert result["success"] is True
        for key, value in op["result"].items():
            assert result[key] == value

        page.locator.assert_called_once_with(op["args"][0])
        locator.wait_for.assert_called_once_with(
            state="visible", timeout=op.get("wait_timeout", 10000)
        )
        getattr(locator, op["method"]).assert_called_once_with(
            *op.get("method_args", ()), **op.get("method_kwargs", {})
        )
        for pre_method, pre_args, pre_kwargs in op.get("pre", []):
            getattr(locator, pre_method).assert_called_once_with(
                *pre_args, **pre_kwargs
            )


class TestFailureBranches:
    """No-active-page and exception branches for every operation."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("op", OPS, ids=lambda op: op["name"])
    async def test_no_active_page(self, browser_page, op):
        manager, _, _ = browser_page
        manager.get_current_page.return_value = None

        result = await _call(op, manager)

        assert result["success"] is False
        assert "No active browser page available" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("op", OPS, ids=lambda op: op["name"])
    async def test_operation_exception(self, op):
        manager = MagicMock()
        page = MagicMock()
        manager.get_current_page = AsyncMock(return_value=page)
        element = AsyncMock()
        element.wait_for.side_effect = RuntimeError("interaction failed")
        locator = MagicMock()
        locator.first = element
        page.locator.return_value = locator

        result = await _call(op, manager)

        assert result["success"] is False


class TestOptionsAndEdges:
    """Distinct per-operation option/edge variants."""

    @pytest.mark.asyncio
    async def test_click_with_options(self, browser_page):
        manager, _, locator = browser_page
        with patch(f"{MOD}.get_session_browser_manager", return_value=manager):
            result = await interactions.click_element(
                "#custom-button",
                timeout=5000,
                force=True,
                button="right",
                modifiers=["Control", "Shift"],
            )

        assert result["success"] is True
        assert result["action"] == "right_click"
        locator.wait_for.assert_called_once_with(state="visible", timeout=5000)
        locator.click.assert_called_once_with(
            force=True, button="right", timeout=5000, modifiers=["Control", "Shift"]
        )

    @pytest.mark.asyncio
    async def test_double_click_force(self, browser_page):
        manager, _, locator = browser_page
        with patch(f"{MOD}.get_session_browser_manager", return_value=manager):
            result = await interactions.double_click_element(
                "#selector", timeout=3000, force=True
            )

        assert result["success"] is True
        locator.dblclick.assert_called_once_with(force=True, timeout=3000)

    @pytest.mark.asyncio
    async def test_hover_force(self, browser_page):
        manager, _, locator = browser_page
        with patch(f"{MOD}.get_session_browser_manager", return_value=manager):
            result = await interactions.hover_element("#menu", timeout=2000, force=True)

        assert result["success"] is True
        locator.hover.assert_called_once_with(force=True, timeout=2000)

    @pytest.mark.asyncio
    async def test_set_text_no_clear(self, browser_page):
        manager, _, locator = browser_page
        with patch(f"{MOD}.get_session_browser_manager", return_value=manager):
            result = await interactions.set_element_text(
                "#input", "append text", clear_first=False
            )

        assert result["success"] is True
        locator.clear.assert_not_called()
        locator.fill.assert_called_once_with("append text", timeout=10000)
        assert result["text"] == "append text"

    @pytest.mark.asyncio
    async def test_set_text_long_text(self, browser_page):
        manager, _, locator = browser_page
        long_text = "a" * 1000
        with patch(f"{MOD}.get_session_browser_manager", return_value=manager):
            result = await interactions.set_element_text("#textarea", long_text)

        assert result["success"] is True
        assert result["text"] == long_text
        locator.fill.assert_called_once_with(long_text, timeout=10000)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", ["", None], ids=["empty", "none"])
    async def test_get_text_empty_or_none(self, browser_page, value):
        manager, _, locator = browser_page
        locator.text_content.return_value = value
        with patch(f"{MOD}.get_session_browser_manager", return_value=manager):
            result = await interactions.get_element_text("#content")

        assert result["success"] is True
        assert result["text"] == value

    @pytest.mark.asyncio
    async def test_get_value_empty(self, browser_page):
        manager, _, locator = browser_page
        locator.input_value.return_value = ""
        with patch(f"{MOD}.get_session_browser_manager", return_value=manager):
            result = await interactions.get_element_value("#empty-input")

        assert result["success"] is True
        assert result["value"] == ""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kwargs,expected",
        [
            ({"label": "Option Label"}, {"label": "Option Label", "timeout": 10000}),
            ({"index": 2}, {"index": 2, "timeout": 10000}),
        ],
        ids=["by-label", "by-index"],
    )
    async def test_select_by_label_or_index(self, browser_page, kwargs, expected):
        manager, _, locator = browser_page
        with patch(f"{MOD}.get_session_browser_manager", return_value=manager):
            result = await interactions.select_option("#dropdown", **kwargs)

        assert result["success"] is True
        locator.select_option.assert_called_once_with(**expected)

    @pytest.mark.asyncio
    async def test_select_no_params(self, browser_page):
        manager, _, locator = browser_page
        with patch(f"{MOD}.get_session_browser_manager", return_value=manager):
            result = await interactions.select_option("#dropdown")

        assert result["success"] is False
        assert "Must specify value, label, or index" in result["error"]
        assert result["selector"] == "#dropdown"
        locator.select_option.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_custom_timeout(self, browser_page):
        manager, _, locator = browser_page
        with patch(f"{MOD}.get_session_browser_manager", return_value=manager):
            result = await interactions.check_element("#checkbox", timeout=5000)

        assert result["success"] is True
        locator.wait_for.assert_called_once_with(state="visible", timeout=5000)
        locator.check.assert_called_once_with(timeout=5000)


class TestIntegrationScenarios:
    """Integration scenarios combining multiple interaction functions."""

    @pytest.mark.asyncio
    async def test_form_interaction_workflow(self, browser_page):
        manager, page, locator = browser_page
        with patch(f"{MOD}.get_session_browser_manager", return_value=manager):
            text_result = await interactions.set_element_text("#username", "testuser")
            value_result = await interactions.get_element_value("#username")
            check_result = await interactions.check_element("#agree-terms")
            click_result = await interactions.click_element("#submit")

        assert text_result["success"] is True
        assert value_result["success"] is True
        assert check_result["success"] is True
        assert click_result["success"] is True

        assert page.locator.call_count == 4
        locator.fill.assert_called_once_with("testuser", timeout=10000)
        locator.input_value.assert_called_once()
        locator.check.assert_called_once()
        locator.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_dropdown_interaction_sequence(self, browser_page):
        manager, page, _ = browser_page

        dropdown_locator1 = AsyncMock()
        dropdown_locator1.wait_for = AsyncMock()
        dropdown_locator1.select_option = AsyncMock()
        dropdown_locator1.first = dropdown_locator1

        dropdown_locator2 = AsyncMock()
        dropdown_locator2.wait_for = AsyncMock()
        dropdown_locator2.select_option = AsyncMock()
        dropdown_locator2.first = dropdown_locator2

        hover_locator = AsyncMock()
        hover_locator.wait_for = AsyncMock()
        hover_locator.hover = AsyncMock()
        hover_locator.first = hover_locator

        page.locator.side_effect = [
            dropdown_locator1,
            dropdown_locator2,
            hover_locator,
        ]

        with patch(f"{MOD}.get_session_browser_manager", return_value=manager):
            select_result1 = await interactions.select_option(
                "#dropdown", value="option1"
            )
            select_result2 = await interactions.select_option(
                "#dropdown", label="Another option"
            )
            hover_result = await interactions.hover_element("#dropdown-menu")

        assert select_result1["success"] is True
        assert select_result2["success"] is True
        assert hover_result["success"] is True

        dropdown_locator1.wait_for.assert_called_once_with(
            state="visible", timeout=10000
        )
        dropdown_locator1.select_option.assert_called_once_with(
            value="option1", timeout=10000
        )
        dropdown_locator2.wait_for.assert_called_once_with(
            state="visible", timeout=10000
        )
        dropdown_locator2.select_option.assert_called_once_with(
            label="Another option", timeout=10000
        )
        hover_locator.wait_for.assert_called_once_with(state="visible", timeout=10000)
        hover_locator.hover.assert_called_once_with(force=False, timeout=10000)


@pytest.mark.parametrize(
    "register_func,expected_tool",
    [
        (interactions.register_click_element, "browser_click"),
        (interactions.register_double_click_element, "browser_double_click"),
        (interactions.register_hover_element, "browser_hover"),
        (interactions.register_set_element_text, "browser_set_text"),
        (interactions.register_get_element_text, "browser_get_text"),
        (interactions.register_get_element_value, "browser_get_value"),
        (interactions.register_select_option, "browser_select_option"),
        (interactions.register_browser_check, "browser_check"),
        (interactions.register_browser_uncheck, "browser_uncheck"),
    ],
    ids=[
        "click_element",
        "double_click_element",
        "hover_element",
        "set_element_text",
        "get_element_text",
        "get_element_value",
        "select_option",
        "browser_check",
        "browser_uncheck",
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


if __name__ == "__main__":
    pytest.main([__file__])
