"""Tests for semantic (accessibility-locator) interaction helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser.browser_locator_resolver import (
    SEMANTIC_STRATEGIES,
    describe_target,
    resolve_locator,
)
from code_puppy.tools.browser.browser_semantic_interactions import (
    click_by_role,
    click_by_text,
    register_click_by_role,
    register_click_by_text,
    register_set_text_by_label,
    set_text_by_label,
)


# --- resolver unit tests ---------------------------------------------------


def test_describe_target_role_with_name():
    assert describe_target("role", "button", "Submit") == "role='button' name='Submit'"


def test_describe_target_plain():
    assert describe_target("text", "Log in") == "text='Log in'"


def test_resolve_locator_dispatches_by_strategy():
    page = MagicMock()
    resolve_locator(page, "role", "button", name="Go", exact=True)
    page.get_by_role.assert_called_once_with("button", name="Go", exact=True)

    resolve_locator(page, "text", "hi", exact=False)
    page.get_by_text.assert_called_once_with("hi", exact=False)

    resolve_locator(page, "label", "Email")
    page.get_by_label.assert_called_once_with("Email", exact=False)

    resolve_locator(page, "placeholder", "Search")
    page.get_by_placeholder.assert_called_once_with("Search", exact=False)

    resolve_locator(page, "test_id", "submit-btn")
    page.get_by_test_id.assert_called_once_with("submit-btn")


def test_resolve_locator_unknown_strategy():
    with pytest.raises(ValueError):
        resolve_locator(MagicMock(), "nope", "x")


def test_all_strategies_covered():
    assert set(SEMANTIC_STRATEGIES) == {
        "role",
        "text",
        "label",
        "placeholder",
        "test_id",
    }


# --- interaction tests -----------------------------------------------------


def _mock_page_with_locator(count=1):
    """Return (manager, page, element) mocks wired for a single match."""
    element = MagicMock()
    element.wait_for = AsyncMock()
    element.click = AsyncMock()
    element.fill = AsyncMock()
    element.check = AsyncMock()

    locator = MagicMock()
    locator.count = AsyncMock(return_value=count)
    locator.first = element

    page = MagicMock()
    page.get_by_role = MagicMock(return_value=locator)
    page.get_by_text = MagicMock(return_value=locator)
    page.get_by_label = MagicMock(return_value=locator)

    manager = AsyncMock()
    manager.get_current_page.return_value = page
    return manager, page, element


@pytest.mark.asyncio
async def test_click_by_role_success():
    manager, _page, element = _mock_page_with_locator()
    with patch(
        "code_puppy.tools.browser.browser_semantic_interactions.get_session_browser_manager",
        return_value=manager,
    ):
        with patch("code_puppy.tools.browser.browser_semantic_interactions.emit_info"):
            with patch(
                "code_puppy.tools.browser.browser_semantic_interactions.emit_success"
            ):
                result = await click_by_role("button", name="Submit")

    assert result["success"] is True
    assert result["action"] == "click"
    assert result["strategy"] == "role"
    element.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_click_by_text_no_match_is_deterministic():
    manager, _page, element = _mock_page_with_locator(count=0)
    with patch(
        "code_puppy.tools.browser.browser_semantic_interactions.get_session_browser_manager",
        return_value=manager,
    ):
        with patch("code_puppy.tools.browser.browser_semantic_interactions.emit_info"):
            with patch(
                "code_puppy.tools.browser.browser_semantic_interactions.emit_error"
            ):
                result = await click_by_text("Nope")

    assert result["success"] is False
    assert "No element matched" in result["error"]
    element.click.assert_not_called()


@pytest.mark.asyncio
async def test_set_text_by_label_fills():
    manager, _page, element = _mock_page_with_locator()
    with patch(
        "code_puppy.tools.browser.browser_semantic_interactions.get_session_browser_manager",
        return_value=manager,
    ):
        with patch("code_puppy.tools.browser.browser_semantic_interactions.emit_info"):
            with patch(
                "code_puppy.tools.browser.browser_semantic_interactions.emit_success"
            ):
                result = await set_text_by_label("Email", "a@b.com")

    assert result["success"] is True
    assert result["text"] == "a@b.com"
    element.fill.assert_awaited_once_with("a@b.com", timeout=10000)


@pytest.mark.asyncio
async def test_semantic_no_page():
    manager = AsyncMock()
    manager.get_current_page.return_value = None
    with patch(
        "code_puppy.tools.browser.browser_semantic_interactions.get_session_browser_manager",
        return_value=manager,
    ):
        with patch("code_puppy.tools.browser.browser_semantic_interactions.emit_info"):
            result = await click_by_role("button")

    assert result["success"] is False
    assert "No active browser page" in result["error"]


def test_semantic_registrations():
    for register in (
        register_click_by_role,
        register_click_by_text,
        register_set_text_by_label,
    ):
        agent = MagicMock()
        register(agent)
        agent.tool.assert_called_once()
