"""Branch coverage for browser navigation helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser import browser_navigation as navigation

MOD = navigation.__name__
SIMPLE_OPERATIONS = [
    ("back", navigation.go_back, "go_back", True),
    ("forward", navigation.go_forward, "go_forward", True),
    ("reload", navigation.reload_page, "reload", True),
    ("wait", navigation.wait_for_load_state, "wait_for_load_state", False),
]
REGISTRARS = [
    navigation.register_navigate_to_url,
    navigation.register_get_page_info,
    navigation.register_browser_go_back,
    navigation.register_browser_go_forward,
    navigation.register_reload_page,
    navigation.register_wait_for_load_state,
]


@pytest.fixture(autouse=True)
def _suppress():
    with (
        patch(f"{MOD}.emit_info"),
        patch(f"{MOD}.emit_error"),
        patch(f"{MOD}.emit_success"),
    ):
        yield


def _manager(page=None):
    manager = AsyncMock()
    manager.get_current_page.return_value = page
    return manager


@pytest.mark.asyncio
@pytest.mark.parametrize("page_kind", ["none", "raising"], ids=["no-page", "exception"])
async def test_navigate_failure_branches(page_kind):
    page = None
    if page_kind == "raising":
        page = AsyncMock()
        page.goto.side_effect = RuntimeError("network failed")
    with patch(f"{MOD}.get_session_browser_manager", return_value=_manager(page)):
        result = await navigation.navigate_to_url("http://x")
    assert result["success"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "manager", [_manager(None), None], ids=["no-page", "exception"]
)
async def test_get_page_info_failure_branches(manager):
    if manager is None:
        manager = AsyncMock()
        manager.get_current_page.side_effect = RuntimeError("failed")
    with patch(f"{MOD}.get_session_browser_manager", return_value=manager):
        result = await navigation.get_page_info()
    assert result["success"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("case", SIMPLE_OPERATIONS, ids=lambda case: case[0])
@pytest.mark.parametrize("state", ["no-page", "success", "exception"])
async def test_navigation_operation_branches(case, state):
    _, operation, page_method, needs_title = case
    page = None
    if state != "no-page":
        page = AsyncMock()
        page.url = "http://result"
        if needs_title:
            page.title.return_value = "Result"
        if state == "exception":
            getattr(page, page_method).side_effect = RuntimeError("failed")
    with patch(f"{MOD}.get_session_browser_manager", return_value=_manager(page)):
        result = await operation()
    assert result["success"] is (state == "success")


@pytest.mark.parametrize("register", REGISTRARS)
def test_register_navigation(register):
    agent = MagicMock()
    register(agent)
    agent.tool.assert_called_once()
