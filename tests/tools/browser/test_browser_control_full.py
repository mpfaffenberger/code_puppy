"""Full coverage tests for browser_control.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser.browser_control import (
    create_new_page,
    get_browser_status,
    list_pages,
    register_close_browser,
    register_create_new_page,
    register_get_browser_status,
    register_initialize_browser,
    register_list_pages,
)


def _mock_manager(**kwargs):
    m = AsyncMock()
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


def _patch_control(target, **kwargs):
    return patch(f"code_puppy.tools.browser.browser_control.{target}", **kwargs)


@pytest.fixture(autouse=True)
def _suppress_emit():
    with (
        patch("code_puppy.tools.browser.browser_control.emit_info"),
        patch("code_puppy.tools.browser.browser_control.emit_error"),
        patch("code_puppy.tools.browser.browser_control.emit_success"),
        patch("code_puppy.tools.browser.browser_control.emit_warning"),
    ):
        yield


class TestGetBrowserStatusNoPage:
    @pytest.mark.asyncio
    async def test_initialized_no_page(self):
        """Cover lines 116-118: initialized but page is None."""
        mgr = _mock_manager(_initialized=True, browser_type="chromium", headless=False)
        mgr.get_current_page.return_value = None
        with _patch_control("get_session_browser_manager", return_value=mgr):
            result = await get_browser_status()
            assert result["success"] is True
            assert result["current_url"] is None
            assert result["page_count"] == 0


class TestCreateNewPage:
    @pytest.mark.asyncio
    async def test_success(self):
        page = AsyncMock()
        page.url = "https://example.com"
        page.title.return_value = "Example"
        mgr = _mock_manager(_initialized=True)
        mgr.new_page.return_value = page
        with _patch_control("get_session_browser_manager", return_value=mgr):
            result = await create_new_page("https://example.com")
            assert result["success"] is True
            assert result["url"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_not_initialized(self):
        mgr = _mock_manager(_initialized=False)
        with _patch_control("get_session_browser_manager", return_value=mgr):
            result = await create_new_page()
            assert result["success"] is False
            assert "not initialized" in result["error"]

    @pytest.mark.asyncio
    async def test_exception(self):
        mgr = _mock_manager(_initialized=True)
        mgr.new_page.side_effect = RuntimeError("fail")
        with _patch_control("get_session_browser_manager", return_value=mgr):
            result = await create_new_page("http://x")
            assert result["success"] is False


class TestListPages:
    @pytest.mark.asyncio
    async def test_success(self):
        page = AsyncMock()
        page.url = "https://a.com"
        page.title.return_value = "A"
        page.is_closed.return_value = False
        mgr = _mock_manager(_initialized=True)
        mgr.get_all_pages.return_value = [page]
        with _patch_control("get_session_browser_manager", return_value=mgr):
            result = await list_pages()
            assert result["success"] is True
            assert result["page_count"] == 1

    @pytest.mark.asyncio
    async def test_not_initialized(self):
        mgr = _mock_manager(_initialized=False)
        with _patch_control("get_session_browser_manager", return_value=mgr):
            result = await list_pages()
            assert result["success"] is False

    @pytest.mark.asyncio
    async def test_page_error(self):
        page = AsyncMock()
        page.url = property(lambda s: (_ for _ in ()).throw(RuntimeError("dead")))
        # Simpler: make title raise
        page2 = MagicMock()
        page2.url = "http://x"
        page2.title = AsyncMock(side_effect=RuntimeError("dead"))
        page2.is_closed = MagicMock(return_value=False)
        mgr = _mock_manager(_initialized=True)
        mgr.get_all_pages.return_value = [page2]
        with _patch_control("get_session_browser_manager", return_value=mgr):
            result = await list_pages()
            assert result["success"] is True
            assert result["pages"][0]["closed"] is True

    @pytest.mark.asyncio
    async def test_exception(self):
        mgr = _mock_manager(_initialized=True)
        mgr.get_all_pages.side_effect = RuntimeError("boom")
        with _patch_control("get_session_browser_manager", return_value=mgr):
            result = await list_pages()
            assert result["success"] is False


class TestRegisterFunctions:
    def test_register_initialize_browser(self):
        agent = MagicMock()
        register_initialize_browser(agent)
        agent.tool.assert_called_once()

    def test_register_close_browser(self):
        agent = MagicMock()
        register_close_browser(agent)
        agent.tool.assert_called_once()

    def test_register_get_browser_status(self):
        agent = MagicMock()
        register_get_browser_status(agent)
        agent.tool.assert_called_once()

    def test_register_create_new_page(self):
        agent = MagicMock()
        register_create_new_page(agent)
        agent.tool.assert_called_once()

    def test_register_list_pages(self):
        agent = MagicMock()
        register_list_pages(agent)
        agent.tool.assert_called_once()
