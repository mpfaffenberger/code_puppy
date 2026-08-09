"""Exception-branch coverage for browser locator helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser import browser_locators as locators

MOD = locators.__name__
OPERATIONS = [
    ("role", locators.find_by_role, ("button",), "get_by_role"),
    ("text", locators.find_by_text, ("hello",), "get_by_text"),
    ("label", locators.find_by_label, ("email",), "get_by_label"),
    ("placeholder", locators.find_by_placeholder, ("search",), "get_by_placeholder"),
    ("test-id", locators.find_by_test_id, ("btn",), "get_by_test_id"),
    ("xpath", locators.run_xpath_query, ("//div",), "locator"),
    ("buttons", locators.find_buttons, (), "get_by_role"),
    ("links", locators.find_links, (), "get_by_role"),
]
REGISTRARS = [
    locators.register_find_by_role,
    locators.register_find_by_text,
    locators.register_find_by_label,
    locators.register_find_by_placeholder,
    locators.register_find_by_test_id,
    locators.register_run_xpath_query,
    locators.register_find_buttons,
    locators.register_find_links,
]


@pytest.fixture(autouse=True)
def _suppress():
    with patch(f"{MOD}.emit_info"), patch(f"{MOD}.emit_success"):
        yield


def _manager(page):
    manager = AsyncMock()
    manager.get_current_page.return_value = page
    return manager


@pytest.mark.asyncio
@pytest.mark.parametrize("case", OPERATIONS, ids=lambda case: case[0])
@pytest.mark.parametrize("page_kind", ["none", "raising"], ids=["no-page", "exception"])
async def test_locator_failure_branches(case, page_kind):
    _, operation, args, failing_method = case
    page = None
    if page_kind == "raising":
        page = MagicMock()
        getattr(page, failing_method).side_effect = RuntimeError("locator failed")
    with patch(f"{MOD}.get_session_browser_manager", return_value=_manager(page)):
        result = await operation(*args)
    assert result["success"] is False


@pytest.mark.parametrize("register", REGISTRARS)
def test_register_locator(register):
    agent = MagicMock()
    register(agent)
    agent.tool.assert_called_once()
