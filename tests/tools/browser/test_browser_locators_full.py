"""Full coverage tests for browser_locators.py - exception branches."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser.browser_locators import (
    find_buttons,
    find_by_label,
    find_by_placeholder,
    find_by_role,
    find_by_test_id,
    find_by_text,
    find_links,
    register_find_buttons,
    register_find_by_label,
    register_find_by_placeholder,
    register_find_by_role,
    register_find_by_test_id,
    register_find_by_text,
    register_find_links,
    register_run_xpath_query,
    run_xpath_query,
)

MOD = "code_puppy.tools.browser.browser_locators"


@pytest.fixture(autouse=True)
def _suppress():
    with patch(f"{MOD}.emit_info"), patch(f"{MOD}.emit_success"):
        yield


def _mgr(page):
    mgr = AsyncMock()
    mgr.get_current_page.return_value = page
    return mgr


def _pm(mgr):
    return patch(f"{MOD}.get_session_browser_manager", return_value=mgr)


class TestExceptionBranches:
    @pytest.mark.asyncio
    async def test_find_by_role_no_page(self):
        with _pm(_mgr(None)):
            r = await find_by_role("button")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_find_by_role_exception(self):
        page = AsyncMock()
        page.get_by_role.side_effect = RuntimeError("err")
        with _pm(_mgr(page)):
            r = await find_by_role("button")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_find_by_text_no_page(self):
        with _pm(_mgr(None)):
            r = await find_by_text("hello")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_find_by_text_exception(self):
        page = AsyncMock()
        page.get_by_text.side_effect = RuntimeError("err")
        with _pm(_mgr(page)):
            r = await find_by_text("hello")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_find_by_label_no_page(self):
        with _pm(_mgr(None)):
            r = await find_by_label("email")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_find_by_label_exception(self):
        page = AsyncMock()
        page.get_by_label.side_effect = RuntimeError("err")
        with _pm(_mgr(page)):
            r = await find_by_label("email")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_find_by_placeholder_no_page(self):
        with _pm(_mgr(None)):
            r = await find_by_placeholder("search")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_find_by_placeholder_exception(self):
        page = AsyncMock()
        page.get_by_placeholder.side_effect = RuntimeError("err")
        with _pm(_mgr(page)):
            r = await find_by_placeholder("search")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_find_by_test_id_no_page(self):
        with _pm(_mgr(None)):
            r = await find_by_test_id("btn")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_find_by_test_id_exception(self):
        page = AsyncMock()
        page.get_by_test_id.side_effect = RuntimeError("err")
        with _pm(_mgr(page)):
            r = await find_by_test_id("btn")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_run_xpath_no_page(self):
        with _pm(_mgr(None)):
            r = await run_xpath_query("//div")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_run_xpath_exception(self):
        page = AsyncMock()
        page.locator.side_effect = RuntimeError("err")
        with _pm(_mgr(page)):
            r = await run_xpath_query("//div")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_find_buttons_no_page(self):
        with _pm(_mgr(None)):
            r = await find_buttons()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_find_buttons_exception(self):
        page = AsyncMock()
        page.get_by_role.side_effect = RuntimeError("err")
        with _pm(_mgr(page)):
            r = await find_buttons()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_find_links_no_page(self):
        with _pm(_mgr(None)):
            r = await find_links()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_find_links_exception(self):
        page = AsyncMock()
        page.get_by_role.side_effect = RuntimeError("err")
        with _pm(_mgr(page)):
            r = await find_links()
            assert r["success"] is False


class TestRegisterFunctions:
    def test_all(self):
        for fn in [
            register_find_by_role,
            register_find_by_text,
            register_find_by_label,
            register_find_by_placeholder,
            register_find_by_test_id,
            register_run_xpath_query,
            register_find_buttons,
            register_find_links,
        ]:
            agent = MagicMock()
            fn(agent)
            agent.tool.assert_called_once()
