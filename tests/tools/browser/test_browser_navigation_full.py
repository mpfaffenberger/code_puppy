"""Full coverage tests for browser_navigation.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser.browser_navigation import (
    get_page_info,
    go_back,
    go_forward,
    navigate_to_url,
    register_browser_go_back,
    register_browser_go_forward,
    register_get_page_info,
    register_navigate_to_url,
    register_reload_page,
    register_wait_for_load_state,
    reload_page,
    wait_for_load_state,
)

MOD = "code_puppy.tools.browser.browser_navigation"


@pytest.fixture(autouse=True)
def _suppress():
    with (
        patch(f"{MOD}.emit_info"),
        patch(f"{MOD}.emit_error"),
        patch(f"{MOD}.emit_success"),
    ):
        yield


def _mgr_with_page(page=None):
    mgr = AsyncMock()
    mgr.get_current_page.return_value = page
    return mgr


def _patch_mgr(mgr):
    return patch(f"{MOD}.get_session_browser_manager", return_value=mgr)


class TestNavigateToUrl:
    @pytest.mark.asyncio
    async def test_no_page(self):
        with _patch_mgr(_mgr_with_page(None)):
            r = await navigate_to_url("http://x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_exception(self):
        page = AsyncMock()
        page.goto.side_effect = RuntimeError("net")
        with _patch_mgr(_mgr_with_page(page)):
            r = await navigate_to_url("http://x")
            assert r["success"] is False


class TestGetPageInfo:
    @pytest.mark.asyncio
    async def test_no_page(self):
        with _patch_mgr(_mgr_with_page(None)):
            r = await get_page_info()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_exception(self):
        mgr = AsyncMock()
        mgr.get_current_page.side_effect = RuntimeError("err")
        with _patch_mgr(mgr):
            r = await get_page_info()
            assert r["success"] is False


class TestGoBack:
    @pytest.mark.asyncio
    async def test_no_page(self):
        with _patch_mgr(_mgr_with_page(None)):
            r = await go_back()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_success(self):
        page = AsyncMock()
        page.url = "http://prev"
        page.title.return_value = "Prev"
        with _patch_mgr(_mgr_with_page(page)):
            r = await go_back()
            assert r["success"] is True

    @pytest.mark.asyncio
    async def test_exception(self):
        page = AsyncMock()
        page.go_back.side_effect = RuntimeError("err")
        with _patch_mgr(_mgr_with_page(page)):
            r = await go_back()
            assert r["success"] is False


class TestGoForward:
    @pytest.mark.asyncio
    async def test_no_page(self):
        with _patch_mgr(_mgr_with_page(None)):
            r = await go_forward()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_success(self):
        page = AsyncMock()
        page.url = "http://next"
        page.title.return_value = "Next"
        with _patch_mgr(_mgr_with_page(page)):
            r = await go_forward()
            assert r["success"] is True

    @pytest.mark.asyncio
    async def test_exception(self):
        page = AsyncMock()
        page.go_forward.side_effect = RuntimeError("err")
        with _patch_mgr(_mgr_with_page(page)):
            r = await go_forward()
            assert r["success"] is False


class TestReloadPage:
    @pytest.mark.asyncio
    async def test_no_page(self):
        with _patch_mgr(_mgr_with_page(None)):
            r = await reload_page()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_success(self):
        page = AsyncMock()
        page.url = "http://r"
        page.title.return_value = "R"
        with _patch_mgr(_mgr_with_page(page)):
            r = await reload_page()
            assert r["success"] is True

    @pytest.mark.asyncio
    async def test_exception(self):
        page = AsyncMock()
        page.reload.side_effect = RuntimeError("err")
        with _patch_mgr(_mgr_with_page(page)):
            r = await reload_page()
            assert r["success"] is False


class TestWaitForLoadState:
    @pytest.mark.asyncio
    async def test_no_page(self):
        with _patch_mgr(_mgr_with_page(None)):
            r = await wait_for_load_state()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_success(self):
        page = AsyncMock()
        page.url = "http://w"
        with _patch_mgr(_mgr_with_page(page)):
            r = await wait_for_load_state()
            assert r["success"] is True

    @pytest.mark.asyncio
    async def test_exception(self):
        page = AsyncMock()
        page.wait_for_load_state.side_effect = RuntimeError("timeout")
        with _patch_mgr(_mgr_with_page(page)):
            r = await wait_for_load_state()
            assert r["success"] is False


class TestRegisterFunctions:
    def test_all_register_functions(self):
        for fn in [
            register_navigate_to_url,
            register_get_page_info,
            register_browser_go_back,
            register_browser_go_forward,
            register_reload_page,
            register_wait_for_load_state,
        ]:
            agent = MagicMock()
            fn(agent)
            agent.tool.assert_called_once()
