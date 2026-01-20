"""Comprehensive tests for browser_manager.py module.

Tests the Playwright browser manager, initialization, page management,
profile handling, and cleanup functionality.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "code_puppy"))

from tools.browser.browser_manager import (
    BrowserManager,
    _sync_cleanup_browsers,
    cleanup_all_browsers,
    get_browser_manager,
)


class TestBrowserManagerBase:
    """Base test class with common mocking for browser manager."""

    @pytest.fixture
    def temp_profile_dir(self):
        """Create a temporary directory for browser profiles."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def mock_playwright(self):
        """Mock Playwright components."""
        mock_pw = MagicMock()
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()

        mock_browser.new_page.return_value = mock_page
        mock_context.new_page.return_value = mock_page
        mock_context.pages = [mock_page]
        mock_context.browser = mock_browser

        mock_pw_chromium = AsyncMock()
        mock_pw_chromium.launch_persistent_context.return_value = mock_context
        mock_pw.chromium = mock_pw_chromium

        return mock_pw, mock_browser, mock_context, mock_page


class TestBrowserManagerMultiInstance(TestBrowserManagerBase):
    """Test BrowserManager multi-instance behavior."""

    def test_different_sessions_create_different_instances(self):
        """Test that different session IDs create different instances."""
        manager1 = get_browser_manager("session-1")
        manager2 = get_browser_manager("session-2")

        assert manager1 is not manager2
        assert manager1.session_id == "session-1"
        assert manager2.session_id == "session-2"

    def test_same_session_returns_same_instance(self):
        """Test that same session ID returns same instance."""
        manager1 = get_browser_manager("test-session")
        manager2 = get_browser_manager("test-session")

        assert manager1 is manager2

    def test_default_session_id(self):
        """Test that default session ID is 'default'."""
        manager = get_browser_manager()

        assert manager.session_id == "default"
        assert isinstance(manager, BrowserManager)
        assert hasattr(manager, "headless")
        assert hasattr(manager, "homepage")
        assert hasattr(manager, "profile_dir")


class TestBrowserManagerInitialization(TestBrowserManagerBase):
    """Test BrowserManager initialization and configuration."""

    def test_default_settings(self):
        """Test default browser settings."""
        manager = BrowserManager()

        assert manager.headless is True
        assert manager.homepage == "https://www.google.com"

    def test_profile_directory_creation_per_session(self):
        """Test that each session gets its own profile directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            from code_puppy.tools.browser import browser_manager

            original_cache_dir = browser_manager.config.CACHE_DIR
            try:
                browser_manager.config.CACHE_DIR = temp_dir

                manager1 = BrowserManager("session-a")
                manager2 = BrowserManager("session-b")

                expected_path1 = Path(temp_dir) / "browser_profiles" / "session-a"
                expected_path2 = Path(temp_dir) / "browser_profiles" / "session-b"

                assert manager1.profile_dir == expected_path1
                assert manager2.profile_dir == expected_path2
                assert manager1.profile_dir != manager2.profile_dir
                assert manager1.profile_dir.exists()
                assert manager2.profile_dir.exists()
            finally:
                browser_manager.config.CACHE_DIR = original_cache_dir

    def test_session_id_attribute_set(self):
        """Test that session_id attribute is set during initialization."""
        manager = BrowserManager("my-session")
        assert manager.session_id == "my-session"

    def test_profile_dir_attribute_set(self):
        """Test that profile_dir attribute is set during initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            from code_puppy.tools.browser import browser_manager

            original_cache_dir = browser_manager.config.CACHE_DIR
            try:
                browser_manager.config.CACHE_DIR = temp_dir

                manager = BrowserManager("test-session")

                assert hasattr(manager, "profile_dir")
                assert (
                    manager.profile_dir
                    == Path(temp_dir) / "browser_profiles" / "test-session"
                )
            finally:
                browser_manager.config.CACHE_DIR = original_cache_dir


class TestBrowserManagerAsyncInit(TestBrowserManagerBase):
    """Test async initialization of browser manager."""

    @pytest.mark.asyncio
    async def test_async_initialize_already_initialized(self):
        """Test that async_initialize doesn't re-initialize if already done."""
        manager = BrowserManager()
        manager._initialized = True
        manager._context = AsyncMock()
        manager._browser = AsyncMock()

        with patch("tools.browser.browser_manager.emit_info") as mock_emit:
            await manager.async_initialize()

            mock_emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_initialize_exception_cleanup(self):
        """Test cleanup on initialization exception."""
        manager = BrowserManager("test-cleanup")

        with patch.object(
            manager, "_initialize_browser", side_effect=Exception("Init failed")
        ):
            with patch.object(manager, "_cleanup") as mock_cleanup:
                with pytest.raises(Exception, match="Init failed"):
                    await manager.async_initialize()

                assert manager._initialized is False
                mock_cleanup.assert_called_once()


class TestGetBrowserManagerFunction(TestBrowserManagerBase):
    """Test the get_browser_manager convenience function."""

    def test_get_browser_manager_returns_instance(self):
        """Test that get_browser_manager returns a BrowserManager instance."""
        manager = get_browser_manager("func-test")

        assert isinstance(manager, BrowserManager)

    def test_get_browser_manager_same_session_same_instance(self):
        """Test that get_browser_manager returns the same instance for same session."""
        manager1 = get_browser_manager("same-session")
        manager2 = get_browser_manager("same-session")

        assert manager1 is manager2

    def test_get_browser_manager_different_sessions(self):
        """Test that get_browser_manager returns different instances for different sessions."""
        manager1 = get_browser_manager("session-x")
        manager2 = get_browser_manager("session-y")

        assert manager1 is not manager2


class TestPageManagement(TestBrowserManagerBase):
    """Test page management functionality."""

    @pytest.mark.asyncio
    async def test_get_current_page_with_existing_pages(self, mock_playwright):
        """Test getting current page when pages exist."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = BrowserManager()
        manager._initialized = True
        manager._context = mock_context

        page = await manager.get_current_page()

        assert page is mock_page
        assert mock_context.pages[0] is mock_page

    @pytest.mark.asyncio
    async def test_get_current_page_creates_new_page(self, mock_playwright):
        """Test getting current page creates new page when none exist."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright
        mock_context.pages = []

        manager = BrowserManager()
        manager._initialized = True
        manager._context = mock_context

        page = await manager.get_current_page()

        assert page is mock_page
        mock_context.new_page.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_page_not_initialized(self, mock_playwright):
        """Test get_current_page initializes when not already done."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = BrowserManager("page-test")
        manager._initialized = False

        with patch.object(manager, "async_initialize") as mock_init:

            async def mock_async_init():
                manager._initialized = True
                manager._context = mock_context

            mock_init.side_effect = mock_async_init
            mock_context.pages = [mock_page]

            page = await manager.get_current_page()

            mock_init.assert_called_once()
            assert page is mock_page

    @pytest.mark.asyncio
    async def test_get_current_page_no_context(self):
        """Test get_current_page when no context exists."""
        manager = BrowserManager()
        manager._initialized = True
        manager._context = None

        page = await manager.get_current_page()

        assert page is None

    @pytest.mark.asyncio
    async def test_new_page_without_url(self, mock_playwright):
        """Test creating new page without URL."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = BrowserManager()
        manager._initialized = True
        manager._context = mock_context

        page = await manager.new_page()

        assert page is mock_page
        mock_context.new_page.assert_called_once()
        mock_page.goto.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_page_with_url(self, mock_playwright):
        """Test creating new page with URL navigation."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = BrowserManager()
        manager._initialized = True
        manager._context = mock_context

        page = await manager.new_page(url="https://example.com")

        assert page is mock_page
        mock_context.new_page.assert_called_once()
        mock_page.goto.assert_called_once_with("https://example.com")

    @pytest.mark.asyncio
    async def test_new_page_not_initialized(self, mock_playwright):
        """Test new_page initializes when not already done."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = BrowserManager("new-page-test")
        manager._initialized = False

        with patch.object(manager, "async_initialize") as mock_init:

            async def mock_async_init():
                manager._initialized = True
                manager._context = mock_context

            mock_init.side_effect = mock_async_init

            page = await manager.new_page("https://example.com")

            mock_init.assert_called_once()
            assert page is mock_page
            mock_page.goto.assert_called_once_with("https://example.com")

    @pytest.mark.asyncio
    async def test_close_page(self):
        """Test closing a specific page."""
        page = AsyncMock()
        manager = BrowserManager()

        await manager.close_page(page)

        page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_pages(self, mock_playwright):
        """Test getting all open pages."""
        mock_pw, mock_browser, mock_context, mock_page1 = mock_playwright

        mock_page2 = AsyncMock()
        mock_context.pages = [mock_page1, mock_page2]

        manager = BrowserManager()
        manager._context = mock_context

        pages = await manager.get_all_pages()

        assert pages == [mock_page1, mock_page2]

    @pytest.mark.asyncio
    async def test_get_all_pages_no_context(self):
        """Test getting all pages when no context exists."""
        manager = BrowserManager()
        manager._context = None

        pages = await manager.get_all_pages()

        assert pages == []


class TestCleanupFunctionality(TestBrowserManagerBase):
    """Test cleanup and resource management."""

    @pytest.mark.asyncio
    async def test_cleanup_saves_storage_state(self, mock_playwright):
        """Test cleanup saves browser storage state."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = BrowserManager()
        manager._context = mock_context
        manager._browser = mock_browser
        manager._initialized = True
        manager.profile_dir = Path("/tmp/test_profile")

        with patch("tools.browser.browser_manager.emit_info"):
            mock_context.storage_state = AsyncMock()

            await manager._cleanup()

            expected_path = manager.profile_dir / "storage_state.json"
            mock_context.storage_state.assert_called_once_with(path=str(expected_path))
            mock_context.close.assert_called_once()
            mock_browser.close.assert_called_once()
            assert manager._initialized is False

    @pytest.mark.asyncio
    async def test_cleanup_storage_state_exception(self, mock_playwright):
        """Test cleanup handles storage state save failure gracefully."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = BrowserManager()
        manager._context = mock_context
        manager._browser = mock_browser
        manager._initialized = True

        mock_context.storage_state.side_effect = Exception("Storage save failed")

        await manager._cleanup()

        mock_context.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_no_browser(self):
        """Test cleanup when browser and context are None."""
        manager = BrowserManager()
        manager._context = None
        manager._browser = None
        manager._initialized = True

        with patch("tools.browser.browser_manager.emit_info"):
            await manager._cleanup()

            assert manager._initialized is False

    @pytest.mark.asyncio
    async def test_close_method(self, mock_playwright):
        """Test close method calls cleanup."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = BrowserManager()
        manager._context = mock_context
        manager._browser = mock_browser
        manager._initialized = True

        with patch.object(manager, "_cleanup") as mock_cleanup:
            await manager.close()

            mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_removes_from_active_managers(self):
        """Test that cleanup removes the manager from active managers."""
        from tools.browser import browser_manager

        manager = get_browser_manager("cleanup-test-2")
        manager._initialized = True
        manager._context = AsyncMock()
        manager._browser = AsyncMock()

        assert "cleanup-test-2" in browser_manager._active_managers

        await manager._cleanup()

        assert "cleanup-test-2" not in browser_manager._active_managers


class TestCleanupAllBrowsers(TestBrowserManagerBase):
    """Tests for the cleanup_all_browsers and _sync_cleanup_browsers functions."""

    @pytest.fixture(autouse=True)
    def reset_cleanup_state(self):
        """Reset the cleanup state before each test."""
        from tools.browser import browser_manager

        browser_manager._cleanup_done = False
        yield
        browser_manager._cleanup_done = False

    @pytest.mark.asyncio
    async def test_cleanup_all_browsers_closes_all_initialized_managers(self):
        """Test that cleanup_all_browsers closes all initialized browser managers."""
        from tools.browser import browser_manager

        manager1 = get_browser_manager("cleanup-test-a")
        manager2 = get_browser_manager("cleanup-test-b")

        manager1._initialized = True
        manager1._context = AsyncMock()
        manager1._browser = AsyncMock()

        manager2._initialized = True
        manager2._context = AsyncMock()
        manager2._browser = AsyncMock()

        await cleanup_all_browsers()

        assert not manager1._initialized
        assert not manager2._initialized
        assert browser_manager._cleanup_done is True

    @pytest.mark.asyncio
    async def test_cleanup_all_browsers_skips_if_already_done(self):
        """Test that cleanup_all_browsers doesn't run twice."""
        from tools.browser import browser_manager

        browser_manager._cleanup_done = True

        manager = get_browser_manager("no-cleanup-test")
        manager._initialized = True
        manager._context = AsyncMock()
        manager._browser = AsyncMock()

        await cleanup_all_browsers()

        assert manager._initialized is True

    @pytest.mark.asyncio
    async def test_cleanup_all_browsers_ignores_uninitialized_managers(self):
        """Test that cleanup_all_browsers skips managers that aren't initialized."""
        from tools.browser import browser_manager

        manager = get_browser_manager("uninitialized-test")
        manager._initialized = False

        await cleanup_all_browsers()

        assert browser_manager._cleanup_done is True

    @pytest.mark.asyncio
    async def test_cleanup_all_browsers_handles_exceptions_silently(self):
        """Test that cleanup_all_browsers silently ignores cleanup errors."""
        from tools.browser import browser_manager

        manager = get_browser_manager("error-test")
        manager._initialized = True
        manager._context = AsyncMock()
        manager._browser = AsyncMock()

        with patch.object(manager, "_cleanup", side_effect=Exception("Boom!")):
            await cleanup_all_browsers()

        assert browser_manager._cleanup_done is True

    def test_sync_cleanup_browsers_runs_when_no_managers(self):
        """Test that _sync_cleanup_browsers handles empty managers dict."""
        from tools.browser import browser_manager

        browser_manager._active_managers.clear()
        browser_manager._cleanup_done = False

        _sync_cleanup_browsers()

    def test_sync_cleanup_browsers_skips_if_already_done(self):
        """Test that _sync_cleanup_browsers doesn't run twice."""
        from tools.browser import browser_manager

        browser_manager._cleanup_done = True

        manager = get_browser_manager("sync-no-cleanup")
        manager._initialized = True
        manager._context = MagicMock()
        manager._browser = MagicMock()

        _sync_cleanup_browsers()

        assert manager._initialized is True

    def test_sync_cleanup_browsers_catches_all_exceptions(self):
        """Test that _sync_cleanup_browsers catches all exceptions silently."""
        from tools.browser import browser_manager

        browser_manager._cleanup_done = False

        manager = get_browser_manager("sync-error-test")
        manager._initialized = True

        with patch("asyncio.new_event_loop", side_effect=RuntimeError("No loop!")):
            _sync_cleanup_browsers()
