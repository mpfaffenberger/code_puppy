"""Comprehensive tests for browser_control.py with extensive mocking.

Tests browser initialization, lifecycle, and cleanup without actual browser execution.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser.browser_control import (
    close_browser,
    create_new_page,
    get_browser_status,
    initialize_browser,
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


class TestBrowserInitialization:
    """Test browser initialization functionality."""

    @pytest.mark.asyncio
    async def test_initialize_browser_default_settings(self):
        """Test browser initialization with default settings."""
        # Mock the browser manager
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.url = "https://www.google.com"
        mock_page.title.return_value = "Google"
        mock_manager.get_current_page.return_value = mock_page
        mock_manager.async_initialize.return_value = None
        mock_manager._initialized = True

        with patch(
            "code_puppy.tools.browser.browser_control.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch(
                "code_puppy.tools.browser.browser_control.emit_info"
            ) as mock_emit_info:
                with patch("code_puppy.tools.browser.browser_control.emit_error"):
                    result = await initialize_browser()

                    # Verify result
                    assert result["success"] is True
                    assert result["browser_type"] == "chromium"
                    assert result["headless"] is False
                    assert result["homepage"] == "https://www.google.com"
                    assert result["current_url"] == "https://www.google.com"
                    assert result["current_title"] == "Google"

                    # Verify emit_info was called
                    assert mock_emit_info.called

    @pytest.mark.asyncio
    async def test_initialize_browser_headless_mode(self):
        """Test browser initialization in headless mode."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.title.return_value = "Example Domain"
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_control.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_control.emit_info"):
                result = await initialize_browser(headless=True)

                assert result["success"] is True
                assert result["headless"] is True

                # Verify settings were applied
                assert mock_manager.headless is True

    @pytest.mark.asyncio
    async def test_initialize_browser_custom_settings(self):
        """Test browser initialization with custom settings."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.url = "https://github.com"
        mock_page.title.return_value = "GitHub"
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_control.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_control.emit_info"):
                result = await initialize_browser(
                    headless=True,
                    browser_type="firefox",
                    homepage="https://github.com",
                )

                assert result["success"] is True
                assert result["browser_type"] == "firefox"
                assert result["homepage"] == "https://github.com"
                assert mock_manager.browser_type == "firefox"
                assert mock_manager.homepage == "https://github.com"

    @pytest.mark.asyncio
    async def test_initialize_browser_no_page_available(self):
        """Test initialization when no page is available."""
        mock_manager = AsyncMock()
        mock_manager.get_current_page.return_value = None

        with patch(
            "code_puppy.tools.browser.browser_control.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_control.emit_info"):
                result = await initialize_browser()

                assert result["success"] is True
                assert result["current_url"] == "Unknown"
                assert result["current_title"] == "Unknown"

    @pytest.mark.asyncio
    async def test_initialize_browser_initialization_error(self):
        """Test initialization failure handling."""
        mock_manager = AsyncMock()
        mock_manager.async_initialize.side_effect = RuntimeError(
            "Browser initialization failed"
        )

        with patch(
            "code_puppy.tools.browser.browser_control.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_control.emit_info"):
                with patch(
                    "code_puppy.tools.browser.browser_control.emit_error"
                ) as mock_emit_error:
                    result = await initialize_browser()

                    assert result["success"] is False
                    assert "error" in result
                    assert "Browser initialization failed" in result["error"]
                    assert mock_emit_error.called


class TestBrowserClosing:
    """Test browser closing and cleanup."""

    @pytest.mark.asyncio
    async def test_close_browser_success(self):
        """Test successful browser closing."""
        mock_manager = AsyncMock()
        mock_manager.close.return_value = None

        with patch(
            "code_puppy.tools.browser.browser_control.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_control.emit_info"):
                with patch(
                    "code_puppy.tools.browser.browser_control.emit_warning"
                ) as mock_emit_warning:
                    result = await close_browser()

                    assert result["success"] is True
                    assert "message" in result
                    assert mock_manager.close.called
                    assert mock_emit_warning.called

    @pytest.mark.asyncio
    async def test_close_browser_already_closed(self):
        """Test closing an already-closed browser."""
        mock_manager = AsyncMock()
        mock_manager.close.side_effect = RuntimeError("Browser already closed")

        with patch(
            "code_puppy.tools.browser.browser_control.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_control.emit_info"):
                result = await close_browser()

                assert result["success"] is False
                assert "error" in result

    @pytest.mark.asyncio
    async def test_close_browser_cleanup_called(self):
        """Test that cleanup is called during close."""
        mock_manager = AsyncMock()
        mock_manager.close.return_value = None

        with patch(
            "code_puppy.tools.browser.browser_control.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_control.emit_info"):
                with patch("code_puppy.tools.browser.browser_control.emit_warning"):
                    await close_browser()

                    # Verify close was called on the manager
                    mock_manager.close.assert_called_once()


class TestBrowserStatus:
    """Test browser status checking."""

    @pytest.mark.asyncio
    async def test_get_browser_status_initialized(self):
        """Test getting status of initialized browser."""
        mock_manager = AsyncMock()
        mock_manager._initialized = True
        mock_manager.browser_type = "chromium"
        mock_manager.headless = False
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.title.return_value = "Example"
        mock_manager.get_current_page.return_value = mock_page
        mock_manager.get_all_pages.return_value = [mock_page]

        with patch(
            "code_puppy.tools.browser.browser_control.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_control.emit_info"):
                result = await get_browser_status()

                assert result["success"] is True
                assert result["status"] == "initialized"
                assert result["current_url"] == "https://example.com"
                assert result["current_title"] == "Example"

    @pytest.mark.asyncio
    async def test_get_browser_status_not_initialized(self):
        """Test getting status of uninitialized browser."""
        mock_manager = AsyncMock()
        mock_manager._initialized = False
        mock_manager.browser_type = "chromium"
        mock_manager.headless = False

        with patch(
            "code_puppy.tools.browser.browser_control.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_control.emit_info"):
                result = await get_browser_status()

                # Should return not initialized status
                assert result["success"] is True
                assert result["status"] == "not_initialized"

    @pytest.mark.asyncio
    async def test_get_browser_status_error(self):
        """Test error handling in status check."""
        mock_manager = AsyncMock()
        mock_manager._initialized = True
        mock_manager.get_current_page.side_effect = RuntimeError("Cannot get page")

        with patch(
            "code_puppy.tools.browser.browser_control.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_control.emit_info"):
                result = await get_browser_status()

                # Should handle error gracefully
                assert result is not None


class TestBrowserIntegration:
    """Integration tests for browser control operations."""

    @pytest.mark.asyncio
    async def test_init_then_close_workflow(self):
        """Test typical init → check status → close workflow."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.title.return_value = "Example"
        mock_manager.get_current_page.return_value = mock_page
        mock_manager._initialized = True

        with patch(
            "code_puppy.tools.browser.browser_control.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_control.emit_info"):
                with patch("code_puppy.tools.browser.browser_control.emit_warning"):
                    # Initialize
                    init_result = await initialize_browser()
                    assert init_result["success"] is True

                    # Check status
                    status_result = await get_browser_status()
                    assert status_result["success"] is True

                    # Close
                    close_result = await close_browser()
                    assert close_result["success"] is True

    @pytest.mark.asyncio
    async def test_multiple_browsers_different_types(self):
        """Test initializing different browser types."""
        mock_manager = AsyncMock()
        mock_page = AsyncMock()
        mock_page.url = "https://example.com"
        mock_page.title.return_value = "Example"
        mock_manager.get_current_page.return_value = mock_page

        with patch(
            "code_puppy.tools.browser.browser_control.get_session_browser_manager",
            return_value=mock_manager,
        ):
            with patch("code_puppy.tools.browser.browser_control.emit_info"):
                # Test different browser types
                for browser_type in ["chromium", "firefox", "webkit"]:
                    result = await initialize_browser(browser_type=browser_type)
                    assert result["success"] is True
                    assert result["browser_type"] == browser_type


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
        """Cover initialized-but-no-page branch (current_url is None)."""
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
    @pytest.mark.parametrize(
        "register",
        [
            register_initialize_browser,
            register_close_browser,
            register_get_browser_status,
            register_create_new_page,
            register_list_pages,
        ],
    )
    def test_register_registers_tool(self, register):
        agent = MagicMock()
        register(agent)
        agent.tool.assert_called_once()
