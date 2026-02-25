"""Full coverage tests for browser_interactions.py - exception branches."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser.browser_interactions import (
    check_element,
    click_element,
    double_click_element,
    get_element_text,
    get_element_value,
    hover_element,
    register_browser_check,
    register_browser_uncheck,
    register_click_element,
    register_double_click_element,
    register_get_element_text,
    register_get_element_value,
    register_hover_element,
    register_select_option,
    register_set_element_text,
    select_option,
    set_element_text,
    uncheck_element,
)

MOD = "code_puppy.tools.browser.browser_interactions"


@pytest.fixture(autouse=True)
def _suppress():
    with (
        patch(f"{MOD}.emit_info"),
        patch(f"{MOD}.emit_error"),
        patch(f"{MOD}.emit_success"),
    ):
        yield


def _mgr_with_page(page):
    mgr = AsyncMock()
    mgr.get_current_page.return_value = page
    return mgr


def _patch_mgr(mgr):
    return patch(f"{MOD}.get_session_browser_manager", return_value=mgr)


def _page_with_element(element):
    page = AsyncMock()
    locator = MagicMock()
    locator.first = element
    page.locator.return_value = locator
    return page


class TestExceptionBranches:
    """Test exception handling in each interaction function."""

    @pytest.mark.asyncio
    async def test_click_no_page(self):
        with _patch_mgr(_mgr_with_page(None)):
            r = await click_element("#x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_click_exception(self):
        elem = AsyncMock()
        elem.wait_for.side_effect = RuntimeError("timeout")
        page = _page_with_element(elem)
        with _patch_mgr(_mgr_with_page(page)):
            r = await click_element("#x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_double_click_no_page(self):
        with _patch_mgr(_mgr_with_page(None)):
            r = await double_click_element("#x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_double_click_exception(self):
        elem = AsyncMock()
        elem.wait_for.side_effect = RuntimeError("err")
        with _patch_mgr(_mgr_with_page(_page_with_element(elem))):
            r = await double_click_element("#x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_hover_no_page(self):
        with _patch_mgr(_mgr_with_page(None)):
            r = await hover_element("#x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_hover_exception(self):
        elem = AsyncMock()
        elem.wait_for.side_effect = RuntimeError("err")
        with _patch_mgr(_mgr_with_page(_page_with_element(elem))):
            r = await hover_element("#x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_set_text_no_page(self):
        with _patch_mgr(_mgr_with_page(None)):
            r = await set_element_text("#x", "hello")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_set_text_exception(self):
        elem = AsyncMock()
        elem.wait_for.side_effect = RuntimeError("err")
        with _patch_mgr(_mgr_with_page(_page_with_element(elem))):
            r = await set_element_text("#x", "hello")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_get_text_no_page(self):
        with _patch_mgr(_mgr_with_page(None)):
            r = await get_element_text("#x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_get_text_exception(self):
        elem = AsyncMock()
        elem.wait_for.side_effect = RuntimeError("err")
        with _patch_mgr(_mgr_with_page(_page_with_element(elem))):
            r = await get_element_text("#x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_get_value_no_page(self):
        with _patch_mgr(_mgr_with_page(None)):
            r = await get_element_value("#x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_get_value_exception(self):
        elem = AsyncMock()
        elem.wait_for.side_effect = RuntimeError("err")
        with _patch_mgr(_mgr_with_page(_page_with_element(elem))):
            r = await get_element_value("#x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_select_no_page(self):
        with _patch_mgr(_mgr_with_page(None)):
            r = await select_option("#x", value="a")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_select_exception(self):
        elem = AsyncMock()
        elem.wait_for.side_effect = RuntimeError("err")
        with _patch_mgr(_mgr_with_page(_page_with_element(elem))):
            r = await select_option("#x", value="a")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_check_no_page(self):
        with _patch_mgr(_mgr_with_page(None)):
            r = await check_element("#x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_check_exception(self):
        elem = AsyncMock()
        elem.wait_for.side_effect = RuntimeError("err")
        with _patch_mgr(_mgr_with_page(_page_with_element(elem))):
            r = await check_element("#x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_uncheck_no_page(self):
        with _patch_mgr(_mgr_with_page(None)):
            r = await uncheck_element("#x")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_uncheck_exception(self):
        elem = AsyncMock()
        elem.wait_for.side_effect = RuntimeError("err")
        with _patch_mgr(_mgr_with_page(_page_with_element(elem))):
            r = await uncheck_element("#x")
            assert r["success"] is False


class TestRegisterFunctions:
    def test_all(self):
        for fn in [
            register_click_element,
            register_double_click_element,
            register_hover_element,
            register_set_element_text,
            register_get_element_text,
            register_get_element_value,
            register_select_option,
            register_browser_check,
            register_browser_uncheck,
        ]:
            agent = MagicMock()
            fn(agent)
            agent.tool.assert_called_once()
