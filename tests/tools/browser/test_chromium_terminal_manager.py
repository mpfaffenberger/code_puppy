"""Comprehensive tests for chromium_terminal_manager.py module.

Tests the ChromiumTerminalManager session-based initialization, page management,
and cleanup functionality.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "code_puppy"))

from tools.browser.chromium_terminal_manager import (
    ChromiumTerminalManager,
    _active_managers,
    get_chromium_terminal_manager,
)


class TestChromiumTerminalManagerBase:
    """Base test class with common setup for Chromium terminal manager."""

    @pytest.fixture
    def mock_playwright(self):
        """Mock Playwright components."""
        mock_pw = AsyncMock()
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()

        mock_browser.new_page.return_value = mock_page
        mock_context.new_page.return_value = mock_page
        mock_context.pages = [mock_page]
        mock_context.close = AsyncMock()

        mock_browser.new_context.return_value = mock_context
        mock_browser.close = AsyncMock()

        mock_chromium = AsyncMock()
        mock_chromium.launch.return_value = mock_browser
        mock_pw.chromium = mock_chromium
        mock_pw.stop = AsyncMock()

        return mock_pw, mock_browser, mock_context, mock_page

    @pytest.fixture(autouse=True)
    def reset_managers(self):
        """Reset active managers before each test."""
        # Clear all active managers before each test
        _active_managers.clear()
        yield
        # Clean up after test
        _active_managers.clear()


class TestChromiumTerminalManagerSingleton(TestChromiumTerminalManagerBase):
    """Test ChromiumTerminalManager session-based management."""

    def test_different_sessions_create_different_managers(self):
        """Test that different session IDs create different manager instances."""
        manager1 = ChromiumTerminalManager("session-1")
        manager2 = ChromiumTerminalManager("session-2")

        # Different sessions should be different instances
        assert manager1 is not manager2
        assert manager1.session_id == "session-1"
        assert manager2.session_id == "session-2"

    def test_get_instance_returns_new_instance(self):
        """Test creating a manager with get_chromium_terminal_manager."""
        manager = get_chromium_terminal_manager("test-session")

        assert isinstance(manager, ChromiumTerminalManager)
        assert hasattr(manager, "headless")
        assert hasattr(manager, "session_id")
        assert manager.session_id == "test-session"

    def test_multiple_get_instance_calls(self):
        """Test that calls with same session_id return same instance."""
        manager1 = get_chromium_terminal_manager("test-session")
        manager2 = get_chromium_terminal_manager("test-session")
        manager3 = get_chromium_terminal_manager("test-session")

        assert manager1 is manager2
        assert manager2 is manager3

    def test_default_session_id(self):
        """Test that None session_id uses 'default'."""
        manager1 = get_chromium_terminal_manager()
        manager2 = get_chromium_terminal_manager(None)
        manager3 = get_chromium_terminal_manager("default")

        assert manager1 is manager2
        assert manager2 is manager3
        assert manager1.session_id == "default"


class TestChromiumTerminalManagerInitialization(TestChromiumTerminalManagerBase):
    """Test ChromiumTerminalManager initialization and settings."""

    def test_default_settings(self):
        """Test default configuration values."""
        manager = ChromiumTerminalManager()

        # Default headless should be False (for terminal use)
        assert manager.headless is False
        assert manager.session_id is not None  # Auto-generated UUID

    @patch.dict("os.environ", {"CHROMIUM_HEADLESS": "true"})
    def test_headless_env_override(self):
        """Test that CHROMIUM_HEADLESS env var overrides default."""
        manager = ChromiumTerminalManager("test")

        assert manager.headless is True

    def test_profile_directory_creation(self):
        """Test that session_id is set correctly."""
        manager = ChromiumTerminalManager("custom-session")

        # Session ID should be what we passed
        assert manager.session_id == "custom-session"

    def test_init_only_once(self):
        """Test that each instance is independent."""
        manager1 = ChromiumTerminalManager("session-a")
        manager2 = ChromiumTerminalManager("session-b")

        # Each should have its own session
        assert manager1.session_id != manager2.session_id
        assert manager1 is not manager2


class TestChromiumTerminalManagerAsyncInit(TestChromiumTerminalManagerBase):
    """Test async initialization of ChromiumTerminalManager."""

    @pytest.mark.asyncio
    async def test_async_initialize_success(self, mock_playwright):
        """Test successful browser initialization."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        with patch(
            "tools.browser.chromium_terminal_manager.async_playwright"
        ) as mock_pw_func:
            mock_pw_func.return_value.start = AsyncMock(return_value=mock_pw)

            manager = ChromiumTerminalManager("test")
            await manager.async_initialize()

            assert manager._initialized is True
            assert manager._context is mock_context

    @pytest.mark.asyncio
    async def test_async_initialize_already_initialized(self, mock_playwright):
        """Test that async_initialize skips if already initialized."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = ChromiumTerminalManager("test")
        manager._initialized = True

        # Should not call playwright again
        with patch(
            "tools.browser.chromium_terminal_manager.async_playwright"
        ) as mock_pw_func:
            await manager.async_initialize()
            mock_pw_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_initialize_exception_cleanup(self):
        """Test that exceptions during init trigger cleanup."""
        with patch(
            "tools.browser.chromium_terminal_manager.async_playwright"
        ) as mock_pw_func:
            mock_pw_func.return_value.start = AsyncMock(side_effect=Exception("Failed"))

            manager = ChromiumTerminalManager("test")

            with pytest.raises(Exception, match="Failed"):
                await manager.async_initialize()

            # Should have cleaned up
            assert manager._initialized is False


class TestGetChromiumTerminalManagerFunction(TestChromiumTerminalManagerBase):
    """Test the convenience function get_chromium_terminal_manager."""

    def test_get_chromium_terminal_manager_returns_instance(self):
        """Test that get_chromium_terminal_manager returns valid instance."""
        manager = get_chromium_terminal_manager("test")

        assert isinstance(manager, ChromiumTerminalManager)

    def test_get_chromium_terminal_manager_same_instance(self):
        """Test that repeated calls with same session return same instance."""
        manager1 = get_chromium_terminal_manager("my-session")
        manager2 = get_chromium_terminal_manager("my-session")

        assert manager1 is manager2

    def test_get_chromium_terminal_manager_different_sessions(self):
        """Test that different sessions return different instances."""
        manager1 = get_chromium_terminal_manager("session-x")
        manager2 = get_chromium_terminal_manager("session-y")

        assert manager1 is not manager2


class TestPageManagement(TestChromiumTerminalManagerBase):
    """Test page management functionality."""

    @pytest.mark.asyncio
    async def test_get_current_page_with_existing_pages(self, mock_playwright):
        """Test get_current_page returns first page when pages exist."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = ChromiumTerminalManager("test")
        manager._initialized = True
        manager._context = mock_context

        page = await manager.get_current_page()

        assert page is mock_page

    @pytest.mark.asyncio
    async def test_get_current_page_creates_new_page(self, mock_playwright):
        """Test get_current_page creates new page when none exist."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright
        mock_context.pages = []  # No existing pages

        manager = ChromiumTerminalManager("test")
        manager._initialized = True
        manager._context = mock_context

        page = await manager.get_current_page()

        mock_context.new_page.assert_called_once()
        assert page is mock_page

    @pytest.mark.asyncio
    async def test_get_current_page_no_context(self, mock_playwright):
        """Test get_current_page returns None when no context available."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        with patch(
            "tools.browser.chromium_terminal_manager.async_playwright"
        ) as mock_pw_func:
            mock_pw_func.return_value.start = AsyncMock(return_value=mock_pw)

            manager = ChromiumTerminalManager("test")
            manager._initialized = True
            manager._context = None

            # Force initialize to not set context
            with patch.object(manager, "async_initialize", new=AsyncMock()):
                page = await manager.get_current_page()

            assert page is None

    @pytest.mark.asyncio
    async def test_new_page_without_url(self, mock_playwright):
        """Test new_page creates page without navigation."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = ChromiumTerminalManager("test")
        manager._initialized = True
        manager._context = mock_context

        page = await manager.new_page()

        mock_context.new_page.assert_called_once()
        mock_page.goto.assert_not_called()
        assert page is mock_page

    @pytest.mark.asyncio
    async def test_new_page_with_url(self, mock_playwright):
        """Test new_page navigates to URL when provided."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = ChromiumTerminalManager("test")
        manager._initialized = True
        manager._context = mock_context

        page = await manager.new_page(url="https://example.com")

        mock_context.new_page.assert_called_once()
        mock_page.goto.assert_called_once_with("https://example.com")
        assert page is mock_page

    @pytest.mark.asyncio
    async def test_new_page_no_context_raises(self, mock_playwright):
        """Test new_page raises RuntimeError when no context available."""
        manager = ChromiumTerminalManager("test")
        manager._initialized = True
        manager._context = None

        with pytest.raises(RuntimeError, match="Browser context not available"):
            await manager.new_page()

    @pytest.mark.asyncio
    async def test_close_page(self, mock_playwright):
        """Test close_page closes the specified page."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = ChromiumTerminalManager("test")
        manager._initialized = True
        manager._context = mock_context

        await manager.close_page(mock_page)

        mock_page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_pages(self, mock_playwright):
        """Test get_all_pages returns all open pages."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright
        mock_page2 = AsyncMock()
        mock_context.pages = [mock_page, mock_page2]

        manager = ChromiumTerminalManager("test")
        manager._context = mock_context

        pages = await manager.get_all_pages()

        assert pages == [mock_page, mock_page2]

    @pytest.mark.asyncio
    async def test_get_all_pages_no_context(self):
        """Test get_all_pages returns empty list when no context."""
        manager = ChromiumTerminalManager("test")
        manager._context = None

        pages = await manager.get_all_pages()

        assert pages == []


class TestCleanupFunctionality(TestChromiumTerminalManagerBase):
    """Test cleanup and close functionality."""

    @pytest.mark.asyncio
    async def test_cleanup_closes_context(self, mock_playwright):
        """Test that cleanup closes browser context."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        # Add manager to active managers
        _active_managers["cleanup-test"] = None  # placeholder

        manager = ChromiumTerminalManager("cleanup-test")
        manager._initialized = True
        manager._context = mock_context
        manager._browser = mock_browser
        manager._playwright = mock_pw

        # Register in active managers
        _active_managers["cleanup-test"] = manager

        await manager._cleanup()

        mock_context.close.assert_called_once()
        assert manager._initialized is False
        assert "cleanup-test" not in _active_managers

    @pytest.mark.asyncio
    async def test_cleanup_handles_exception(self, mock_playwright):
        """Test that cleanup handles exceptions gracefully."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright
        mock_context.close = AsyncMock(side_effect=Exception("Close failed"))

        manager = ChromiumTerminalManager("test")
        manager._initialized = True
        manager._context = mock_context
        manager._browser = mock_browser
        manager._playwright = mock_pw

        # Should not raise
        await manager._cleanup()

        # Should still mark as not initialized
        assert manager._initialized is False

    @pytest.mark.asyncio
    async def test_cleanup_no_context(self):
        """Test cleanup works when there's no browser context."""
        manager = ChromiumTerminalManager("test")
        manager._initialized = True
        manager._context = None
        manager._browser = None
        manager._playwright = None

        # Should not raise
        await manager._cleanup()

        assert manager._initialized is False

    @pytest.mark.asyncio
    async def test_close_method(self, mock_playwright):
        """Test close method calls cleanup."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = ChromiumTerminalManager("test")
        manager._initialized = True
        manager._context = mock_context
        manager._browser = mock_browser
        manager._playwright = mock_pw

        await manager.close()

        mock_context.close.assert_called_once()
        assert manager._initialized is False

    def test_del_method_best_effort(self):
        """Test manager can be created and destroyed without raising."""
        manager = ChromiumTerminalManager("test")
        manager._initialized = True

        # Manager should be deletable without error
        del manager
