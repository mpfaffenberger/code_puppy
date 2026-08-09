"""Exception-branch coverage for browser interactions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser import browser_interactions as interactions

MOD = interactions.__name__
OPERATIONS = [
    ("click", interactions.click_element, ("#x",)),
    ("double_click", interactions.double_click_element, ("#x",)),
    ("hover", interactions.hover_element, ("#x",)),
    ("set_text", interactions.set_element_text, ("#x", "hello")),
    ("get_text", interactions.get_element_text, ("#x",)),
    ("get_value", interactions.get_element_value, ("#x",)),
    ("select", interactions.select_option, ("#x",), {"value": "a"}),
    ("check", interactions.check_element, ("#x",)),
    ("uncheck", interactions.uncheck_element, ("#x",)),
]
REGISTRARS = [
    interactions.register_click_element,
    interactions.register_double_click_element,
    interactions.register_hover_element,
    interactions.register_set_element_text,
    interactions.register_get_element_text,
    interactions.register_get_element_value,
    interactions.register_select_option,
    interactions.register_browser_check,
    interactions.register_browser_uncheck,
]


@pytest.fixture(autouse=True)
def _suppress():
    with (
        patch(f"{MOD}.emit_info"),
        patch(f"{MOD}.emit_error"),
        patch(f"{MOD}.emit_success"),
    ):
        yield


def _manager(page):
    manager = AsyncMock()
    manager.get_current_page.return_value = page
    return manager


def _page_raising_on_wait():
    element = AsyncMock()
    element.wait_for.side_effect = RuntimeError("interaction failed")
    page = MagicMock()
    locator = MagicMock()
    locator.first = element
    page.locator.return_value = locator
    return page


@pytest.mark.asyncio
@pytest.mark.parametrize("case", OPERATIONS, ids=lambda case: case[0])
@pytest.mark.parametrize("page", [None, "raising"], ids=["no-page", "exception"])
async def test_interaction_failure_branches(case, page):
    _, operation, args, *optional_kwargs = case
    kwargs = optional_kwargs[0] if optional_kwargs else {}
    page = _page_raising_on_wait() if page == "raising" else None
    with patch(f"{MOD}.get_session_browser_manager", return_value=_manager(page)):
        result = await operation(*args, **kwargs)
    assert result["success"] is False


@pytest.mark.parametrize("register", REGISTRARS)
def test_register_interaction(register):
    agent = MagicMock()
    register(agent)
    agent.tool.assert_called_once()
