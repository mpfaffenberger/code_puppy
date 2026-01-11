"""Comprehensive tests for chromium_terminal_manager.py module.

Tests the ChromiumTerminalManager singleton, initialization, page management,
profile handling, and cleanup functionality.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "code_puppy"))

from tools.browser.chromium_terminal_manager import (
    ChromiumTerminalManager,
    get_chromium_terminal_manager,
)


class TestChromiumTerminalManagerBase:
    """Base test class with common mocking for Chromium terminal manager."""

    @pytest.fixture
    def temp_profile_dir(self):
        """Create a temporary directory for browser profiles."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

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
        mock_context.browser = mock_browser
        mock_context.storage_state = AsyncMock()
        mock_context.close = AsyncMock()

        mock_chromium = AsyncMock()
        mock_chromium.launch_persistent_context.return_value = mock_context
        mock_pw.chromium = mock_chromium
        mock_pw.stop = AsyncMock()

        return mock_pw, mock_browser, mock_context, mock_page

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton state before each test."""
        # Reset the singleton before each test
        ChromiumTerminalManager._instance = None
        ChromiumTerminalManager._browser = None
        ChromiumTerminalManager._context = None
        ChromiumTerminalManager._playwright = None
        ChromiumTerminalManager._initialized = False
        yield
        # Clean up after test
        ChromiumTerminalManager._instance = None
        ChromiumTerminalManager._browser = None
        ChromiumTerminalManager._context = None
        ChromiumTerminalManager._playwright = None
        ChromiumTerminalManager._initialized = False


class TestChromiumTerminalManagerSingleton(TestChromiumTerminalManagerBase):
    """Test ChromiumTerminalManager singleton behavior."""

    def test_singleton_pattern(self):
        """Test that ChromiumTerminalManager follows singleton pattern."""
        manager1 = ChromiumTerminalManager()
        manager2 = ChromiumTerminalManager()
        manager3 = ChromiumTerminalManager.get_instance()

        # All should be the same instance
        assert manager1 is manager2
        assert manager2 is manager3

    def test_get_instance_returns_new_instance(self):
        """Test get_instance returns a valid instance."""
        manager = ChromiumTerminalManager.get_instance()

        assert isinstance(manager, ChromiumTerminalManager)
        assert hasattr(manager, "headless")
        assert hasattr(manager, "profile_dir")

    def test_multiple_get_instance_calls(self):
        """Test that multiple get_instance calls return same instance."""
        manager1 = ChromiumTerminalManager.get_instance()
        manager2 = ChromiumTerminalManager.get_instance()
        manager3 = ChromiumTerminalManager.get_instance()

        assert manager1 is manager2
        assert manager2 is manager3


class TestChromiumTerminalManagerInitialization(TestChromiumTerminalManagerBase):
    """Test ChromiumTerminalManager initialization and settings."""

    def test_default_settings(self):
        """Test default configuration values."""
        manager = ChromiumTerminalManager()

        # Default headless should be False (for terminal use)
        assert manager.headless is False
        assert isinstance(manager.profile_dir, Path)

    @patch.dict("os.environ", {"CHROMIUM_HEADLESS": "true"})
    def test_headless_env_override(self):
        """Test that CHROMIUM_HEADLESS env var overrides default."""
        # Need to recreate instance to pick up new env var
        ChromiumTerminalManager._instance = None
        manager = ChromiumTerminalManager()

        assert manager.headless is True

    def test_profile_directory_creation(self, temp_profile_dir):
        """Test that profile directory is created correctly."""
        manager = ChromiumTerminalManager()

        # Profile directory should be a Path object
        assert isinstance(manager.profile_dir, Path)
        # It should contain 'chromium_terminal_profile'
        assert "chromium_terminal_profile" in str(manager.profile_dir)

    def test_init_only_once(self):
        """Test that __init__ only runs once despite multiple calls."""
        manager = ChromiumTerminalManager()
        initial_profile = manager.profile_dir

        # Call init again (via new instance attempt)
        manager2 = ChromiumTerminalManager()

        # Should be same instance with same profile
        assert manager is manager2
        assert manager.profile_dir == initial_profile


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

            manager = ChromiumTerminalManager()
            await manager.async_initialize()

            assert manager._initialized is True
            assert manager._context is mock_context

    @pytest.mark.asyncio
    async def test_async_initialize_already_initialized(self, mock_playwright):
        """Test that async_initialize skips if already initialized."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = ChromiumTerminalManager()
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

            manager = ChromiumTerminalManager()

            with pytest.raises(Exception, match="Failed"):
                await manager.async_initialize()

            # Should have cleaned up
            assert manager._initialized is False


class TestGetChromiumTerminalManagerFunction(TestChromiumTerminalManagerBase):
    """Test the convenience function get_chromium_terminal_manager."""

    def test_get_chromium_terminal_manager_returns_instance(self):
        """Test that get_chromium_terminal_manager returns valid instance."""
        manager = get_chromium_terminal_manager()

        assert isinstance(manager, ChromiumTerminalManager)

    def test_get_chromium_terminal_manager_same_instance(self):
        """Test that repeated calls return same instance."""
        manager1 = get_chromium_terminal_manager()
        manager2 = get_chromium_terminal_manager()

        assert manager1 is manager2


class TestPageManagement(TestChromiumTerminalManagerBase):
    """Test page management functionality."""

    @pytest.mark.asyncio
    async def test_get_current_page_with_existing_pages(self, mock_playwright):
        """Test get_current_page returns first page when pages exist."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = ChromiumTerminalManager()
        manager._initialized = True
        manager._context = mock_context

        page = await manager.get_current_page()

        assert page is mock_page

    @pytest.mark.asyncio
    async def test_get_current_page_creates_new_page(self, mock_playwright):
        """Test get_current_page creates new page when none exist."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright
        mock_context.pages = []  # No existing pages

        manager = ChromiumTerminalManager()
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

            manager = ChromiumTerminalManager()
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

        manager = ChromiumTerminalManager()
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

        manager = ChromiumTerminalManager()
        manager._initialized = True
        manager._context = mock_context

        page = await manager.new_page(url="https://example.com")

        mock_context.new_page.assert_called_once()
        mock_page.goto.assert_called_once_with("https://example.com")
        assert page is mock_page

    @pytest.mark.asyncio
    async def test_new_page_no_context_raises(self, mock_playwright):
        """Test new_page raises RuntimeError when no context available."""
        manager = ChromiumTerminalManager()
        manager._initialized = True
        manager._context = None

        with pytest.raises(RuntimeError, match="Browser context not available"):
            await manager.new_page()

    @pytest.mark.asyncio
    async def test_close_page(self, mock_playwright):
        """Test close_page closes the specified page."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = ChromiumTerminalManager()
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

        manager = ChromiumTerminalManager()
        manager._context = mock_context

        pages = await manager.get_all_pages()

        assert pages == [mock_page, mock_page2]

    @pytest.mark.asyncio
    async def test_get_all_pages_no_context(self):
        """Test get_all_pages returns empty list when no context."""
        manager = ChromiumTerminalManager()
        manager._context = None

        pages = await manager.get_all_pages()

        assert pages == []


class TestCleanupFunctionality(TestChromiumTerminalManagerBase):
    """Test cleanup and close functionality."""

    @pytest.mark.asyncio
    async def test_cleanup_saves_storage_state(self, mock_playwright, temp_profile_dir):
        """Test that cleanup saves browser storage state."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = ChromiumTerminalManager()
        manager._initialized = True
        manager._context = mock_context
        manager._browser = mock_browser
        manager._playwright = mock_pw
        manager.profile_dir = Path(temp_profile_dir)

        await manager._cleanup()

        mock_context.storage_state.assert_called_once()
        mock_context.close.assert_called_once()
        assert manager._initialized is False

    @pytest.mark.asyncio
    async def test_cleanup_handles_storage_exception(self, mock_playwright):
        """Test that cleanup handles storage_state exceptions gracefully."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright
        mock_context.storage_state = AsyncMock(side_effect=Exception("Storage failed"))

        manager = ChromiumTerminalManager()
        manager._initialized = True
        manager._context = mock_context
        manager._browser = mock_browser
        manager._playwright = mock_pw

        # Should not raise
        await manager._cleanup()

        # Context should still be closed
        mock_context.close.assert_called_once()
        assert manager._initialized is False

    @pytest.mark.asyncio
    async def test_cleanup_no_context(self):
        """Test cleanup works when there's no browser context."""
        manager = ChromiumTerminalManager()
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

        manager = ChromiumTerminalManager()
        manager._initialized = True
        manager._context = mock_context
        manager._browser = mock_browser
        manager._playwright = mock_pw

        await manager.close()

        mock_context.close.assert_called_once()
        assert manager._initialized is False

    def test_del_method_best_effort(self):
        """Test __del__ makes best effort cleanup attempt."""
        manager = ChromiumTerminalManager()
        manager._initialized = True

        # __del__ should not raise even if cleanup can't run
        try:
            manager.__del__()
        except Exception:
            pytest.fail("__del__ should not raise exceptions")
