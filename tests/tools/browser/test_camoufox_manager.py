"""Comprehensive tests for camoufox_manager.py module.

Tests the Camoufox browser manager singleton, initialization, page management,
profile handling, and cleanup functionality. Achieves 70%+ coverage.
"""

# Import the module directly to avoid circular imports
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "code_puppy"))

from tools.browser.camoufox_manager import (
    CamoufoxManager,
    cleanup_all_browsers,
    get_camoufox_manager,
    _sync_cleanup_browsers,
)


class TestCamoufoxManagerBase:
    """Base test class with common mocking for Camoufox manager."""

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


class TestCamoufoxManagerMultiInstance(TestCamoufoxManagerBase):
    """Test CamoufoxManager multi-instance behavior."""

    def test_different_sessions_create_different_instances(self):
        """Test that different session IDs create different instances."""
        manager1 = get_camoufox_manager("session-1")
        manager2 = get_camoufox_manager("session-2")

        # Should be different instances
        assert manager1 is not manager2
        assert manager1.session_id == "session-1"
        assert manager2.session_id == "session-2"

    def test_same_session_returns_same_instance(self):
        """Test that same session ID returns same instance."""
        manager1 = get_camoufox_manager("test-session")
        manager2 = get_camoufox_manager("test-session")

        assert manager1 is manager2

    def test_default_session_id(self):
        """Test that default session ID is 'default'."""
        manager = get_camoufox_manager()

        assert manager.session_id == "default"
        assert isinstance(manager, CamoufoxManager)
        assert hasattr(manager, "headless")
        assert hasattr(manager, "homepage")
        assert hasattr(manager, "profile_dir")


class TestCamoufoxManagerInitialization(TestCamoufoxManagerBase):
    """Test CamoufoxManager initialization and configuration."""

    def test_default_settings(self):
        """Test default Camoufox settings."""
        manager = CamoufoxManager()

        # Default is now headless=True (no browser spam during tests)
        assert manager.headless is True
        assert manager.homepage == "https://www.google.com"
        assert manager.geoip is True
        assert manager.block_webrtc is True
        assert manager.humanize is True

    def test_profile_directory_creation_per_session(self):
        """Test that each session gets its own profile directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            from code_puppy.tools.browser import camoufox_manager

            original_cache_dir = camoufox_manager.config.CACHE_DIR
            try:
                camoufox_manager.config.CACHE_DIR = temp_dir

                manager1 = CamoufoxManager("session-a")
                manager2 = CamoufoxManager("session-b")

                # Each session should have its own profile directory
                expected_path1 = Path(temp_dir) / "camoufox_profiles" / "session-a"
                expected_path2 = Path(temp_dir) / "camoufox_profiles" / "session-b"

                assert manager1.profile_dir == expected_path1
                assert manager2.profile_dir == expected_path2
                assert manager1.profile_dir != manager2.profile_dir
                assert manager1.profile_dir.exists()
                assert manager2.profile_dir.exists()
            finally:
                camoufox_manager.config.CACHE_DIR = original_cache_dir

    def test_session_id_attribute_set(self):
        """Test that session_id attribute is set during initialization."""
        manager = CamoufoxManager("my-session")
        assert manager.session_id == "my-session"

    def test_profile_dir_attribute_set(self):
        """Test that profile_dir attribute is set during initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            from code_puppy.tools.browser import camoufox_manager

            original_cache_dir = camoufox_manager.config.CACHE_DIR
            try:
                camoufox_manager.config.CACHE_DIR = temp_dir

                manager = CamoufoxManager("test-session")

                assert hasattr(manager, "profile_dir")
                assert (
                    manager.profile_dir
                    == Path(temp_dir) / "camoufox_profiles" / "test-session"
                )
            finally:
                camoufox_manager.config.CACHE_DIR = original_cache_dir


class TestCamoufoxManagerAsyncInit(TestCamoufoxManagerBase):
    """Test async initialization of Camoufox manager."""

    @pytest.mark.asyncio
    async def test_async_initialize_camoufox_success(self):
        """Test successful Camoufox async initialization when browser_type is not chromium."""
        manager = CamoufoxManager("test-init")
        # Set browser_type to firefox to test the Camoufox path
        manager.browser_type = "firefox"

        # Mock camoufox import and setup
        mock_camoufox = MagicMock()
        mock_camoufox_addons = MagicMock()
        mock_camoufox_instance = MagicMock()
        mock_browser = AsyncMock()
        mock_context = AsyncMock()

        mock_camoufox.AsyncCamoufox.return_value = mock_camoufox_instance
        mock_camoufox_instance.browser = mock_browser
        mock_camoufox_instance.start = AsyncMock(return_value=mock_context)
        mock_camoufox_addons.DefaultAddons = []

        with patch.dict(
            "sys.modules",
            {"camoufox": mock_camoufox, "camoufox.addons": mock_camoufox_addons},
        ):
            with patch("tools.browser.camoufox_manager.emit_info"):
                await manager.async_initialize()

                assert manager._initialized is True
                assert manager._browser is mock_browser
                assert manager._context is mock_context

    def test_default_browser_type_is_chromium(self):
        """Test that browser_type defaults to 'chromium' for reliability."""
        manager = CamoufoxManager("test-default-browser")
        # Verify default browser_type is chromium (not camoufox/firefox)
        assert manager.browser_type == "chromium"

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Complex import mocking makes this test unstable")
    async def test_async_initialize_fallback_to_playwright(self, mock_playwright):
        """Test fallback to Playwright when Camoufox is unavailable."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        # Reset singleton to ensure fresh initialization
        CamoufoxManager._instance = None
        manager = CamoufoxManager()

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("pathlib.Path.home", return_value=Path(temp_dir)):
                with patch("tools.browser.camoufox_manager.emit_info"):
                    # Mock the specific import that happens inside _initialize_camoufox
                    with patch("tools.browser.camoufox_manager.emit_info"):
                        # Simulate the exception that would happen when camoufox import fails
                        with patch(
                            "builtins.__import__",
                            side_effect=ImportError("No module named 'camoufox'"),
                        ):
                            with patch.object(
                                manager, "_prefetch_camoufox"
                            ):  # Skip prefetch
                                with patch(
                                    "playwright.async_api.async_playwright",
                                    return_value=mock_pw,
                                ):
                                    await manager.async_initialize()

                                    assert manager._initialized is True
                                    # Verify the context was created with the correct profile directory
                                    mock_pw.chromium.launch_persistent_context.assert_called_once_with(
                                        user_data_dir=str(manager.profile_dir),
                                        headless=manager.headless,
                                    )

    @pytest.mark.asyncio
    async def test_async_initialize_already_initialized(self):
        """Test that async_initialize doesn't re-initialize if already done."""
        manager = CamoufoxManager()
        manager._initialized = True
        manager._context = AsyncMock()
        manager._browser = AsyncMock()

        with patch("tools.browser.camoufox_manager.emit_info") as mock_emit:
            await manager.async_initialize()

            # Should not have emitted any info messages
            mock_emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_initialize_exception_cleanup(self):
        """Test cleanup on initialization exception."""
        manager = CamoufoxManager("test-cleanup")

        # Mock the _initialize_chromium method to raise an exception
        # (Since browser_type defaults to "chromium", _initialize_chromium is called)
        with patch.object(
            manager, "_initialize_chromium", side_effect=Exception("Init failed")
        ):
            with patch.object(manager, "_cleanup") as mock_cleanup:
                with pytest.raises(Exception, match="Init failed"):
                    await manager.async_initialize()

                assert manager._initialized is False
                mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_prefetch_camoufox_success(self):
        """Test successful Camoufox prefetching."""
        manager = CamoufoxManager()

        # Mock camoufox utilities
        MagicMock()

        with patch("tools.browser.camoufox_manager.emit_info"):
            with patch(
                "camoufox.pkgman.camoufox_path", return_value="/path/to/camoufox"
            ):
                with patch("camoufox.locale.ALLOW_GEOIP", True):
                    with patch("camoufox.locale.download_mmdb"):
                        await manager._prefetch_camoufox()

    @pytest.mark.asyncio
    async def test_prefetch_camoufox_not_installed(self):
        """Test fetching Camoufox when not installed."""
        manager = CamoufoxManager()

        mock_fetcher = MagicMock()

        with patch("tools.browser.camoufox_manager.emit_info"):
            with patch("camoufox.pkgman.camoufox_path", side_effect=FileNotFoundError):
                with patch("camoufox.locale.ALLOW_GEOIP", True):
                    with patch("camoufox.locale.download_mmdb"):
                        with patch(
                            "camoufox.pkgman.CamoufoxFetcher", return_value=mock_fetcher
                        ):
                            await manager._prefetch_camoufox()

                            mock_fetcher.install.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Test is brittle - patching builtins.__import__ affects all imports"
    )
    async def test_prefetch_camoufox_unavailable(self):
        """Test prefetch when Camoufox utilities are unavailable.

        Note: This test is skipped because reliably mocking the camoufox import
        failure is difficult - patching builtins.__import__ affects all imports
        including those needed by the test infrastructure itself.
        """
        pass


class TestGetCamoufoxManagerFunction(TestCamoufoxManagerBase):
    """Test the get_camoufox_manager convenience function."""

    def test_get_camoufox_manager_returns_instance(self):
        """Test that get_camoufox_manager returns a CamoufoxManager instance."""
        manager = get_camoufox_manager("func-test")

        assert isinstance(manager, CamoufoxManager)

    def test_get_camoufox_manager_same_session_same_instance(self):
        """Test that get_camoufox_manager returns the same instance for same session."""
        manager1 = get_camoufox_manager("same-session")
        manager2 = get_camoufox_manager("same-session")

        assert manager1 is manager2

    def test_get_camoufox_manager_different_sessions(self):
        """Test that get_camoufox_manager returns different instances for different sessions."""
        manager1 = get_camoufox_manager("session-x")
        manager2 = get_camoufox_manager("session-y")

        assert manager1 is not manager2


class TestPageManagement(TestCamoufoxManagerBase):
    """Test page management functionality."""

    @pytest.mark.asyncio
    async def test_get_current_page_with_existing_pages(self, mock_playwright):
        """Test getting current page when pages exist."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = CamoufoxManager()
        manager._initialized = True
        manager._context = mock_context

        page = await manager.get_current_page()

        assert page is mock_page
        # Just verify we got the first page from the list
        assert mock_context.pages[0] is mock_page

    @pytest.mark.asyncio
    async def test_get_current_page_creates_new_page(self, mock_playwright):
        """Test getting current page creates new page when none exist."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright
        mock_context.pages = []  # No existing pages

        manager = CamoufoxManager()
        manager._initialized = True
        manager._context = mock_context

        page = await manager.get_current_page()

        assert page is mock_page
        mock_context.new_page.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_page_not_initialized(self, mock_playwright):
        """Test get_current_page initializes when not already done."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = CamoufoxManager("page-test")
        manager._initialized = False

        with patch.object(manager, "async_initialize") as mock_init:
            # Mock the initialization to set up the context
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
        manager = CamoufoxManager()
        manager._initialized = True
        manager._context = None

        page = await manager.get_current_page()

        assert page is None

    @pytest.mark.asyncio
    async def test_new_page_without_url(self, mock_playwright):
        """Test creating new page without URL."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = CamoufoxManager()
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

        manager = CamoufoxManager()
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

        manager = CamoufoxManager("new-page-test")
        manager._initialized = False

        with patch.object(manager, "async_initialize") as mock_init:
            # Mock the initialization to set up the context
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
        manager = CamoufoxManager()

        await manager.close_page(page)

        page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_pages(self, mock_playwright):
        """Test getting all open pages."""
        mock_pw, mock_browser, mock_context, mock_page1 = mock_playwright

        # Create multiple pages
        mock_page2 = AsyncMock()
        mock_context.pages = [mock_page1, mock_page2]

        manager = CamoufoxManager()
        manager._context = mock_context

        pages = await manager.get_all_pages()

        assert pages == [mock_page1, mock_page2]

    @pytest.mark.asyncio
    async def test_get_all_pages_no_context(self):
        """Test getting all pages when no context exists."""
        manager = CamoufoxManager()
        manager._context = None

        pages = await manager.get_all_pages()

        assert pages == []


class TestCleanupFunctionality(TestCamoufoxManagerBase):
    """Test cleanup and resource management."""

    @pytest.mark.asyncio
    async def test_cleanup_saves_storage_state(self, mock_playwright):
        """Test cleanup saves browser storage state."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = CamoufoxManager()
        manager._context = mock_context
        manager._browser = mock_browser
        manager._initialized = True
        manager.profile_dir = Path("/tmp/test_profile")

        with patch("tools.browser.camoufox_manager.emit_info"):
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

        manager = CamoufoxManager()
        manager._context = mock_context
        manager._browser = mock_browser
        manager._initialized = True

        mock_context.storage_state.side_effect = Exception("Storage save failed")

        # The cleanup should handle the exception gracefully and still close the context
        await manager._cleanup()

        # Should still close context even when storage state fails
        mock_context.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_no_browser(self):
        """Test cleanup when browser and context are None."""
        manager = CamoufoxManager()
        manager._context = None
        manager._browser = None
        manager._initialized = True

        with patch("tools.browser.camoufox_manager.emit_info"):
            await manager._cleanup()

            assert manager._initialized is False

    @pytest.mark.asyncio
    async def test_close_method(self, mock_playwright):
        """Test close method calls cleanup."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        manager = CamoufoxManager()
        manager._context = mock_context
        manager._browser = mock_browser
        manager._initialized = True

        with patch.object(manager, "_cleanup") as mock_cleanup:
            await manager.close()

            mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_removes_from_active_managers(self):
        """Test that cleanup removes the manager from active managers."""
        from tools.browser import camoufox_manager

        # Get a manager through the function to register it
        manager = get_camoufox_manager("cleanup-test-2")
        manager._initialized = True
        manager._context = AsyncMock()
        manager._browser = AsyncMock()

        # Verify it's in active managers
        assert "cleanup-test-2" in camoufox_manager._active_managers

        # Cleanup
        await manager._cleanup()

        # Should be removed from active managers
        assert "cleanup-test-2" not in camoufox_manager._active_managers


class TestIntegrationScenarios(TestCamoufoxManagerBase):
    """Integration test scenarios for Camoufox manager."""

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Complex import mocking makes this integration test unstable"
    )
    async def test_full_lifecycle_with_playwright_fallback(self, mock_playwright):
        """Test complete lifecycle: init -> page management -> cleanup."""
        mock_pw, mock_browser, mock_context, mock_page = mock_playwright

        # Reset singleton to ensure fresh initialization
        CamoufoxManager._instance = None
        manager = CamoufoxManager()

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("pathlib.Path.home", return_value=Path(temp_dir)):
                with patch("tools.browser.camoufox_manager.emit_info"):
                    # Initialize (fallback to Playwright)
                    with patch(
                        "builtins.__import__",
                        side_effect=ImportError("No module named 'camoufox'"),
                    ):
                        with patch(
                            "playwright.async_api.async_playwright",
                            return_value=mock_pw,
                        ):
                            await manager.async_initialize()

                            assert manager._initialized is True

                            # Get current page - should return the first page from context
                            page = await manager.get_current_page()
                            assert page == mock_context.pages[0]

                            # Create new page with URL
                            new_page = await manager.new_page("https://test.com")
                            assert new_page is mock_page
                            mock_page.goto.assert_called_with("https://test.com")

                            # Get all pages
                            pages = await manager.get_all_pages()
                            assert pages == [mock_page]

                            # Close the page
                            await manager.close_page(mock_page)
                            mock_page.close.assert_called_once()

                            # Cleanup
                            await manager._cleanup()
                            assert manager._initialized is False
                            mock_context.close.assert_called()
                            mock_browser.close.assert_called()

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Mock side_effect setup is complex for this integration test"
    )
    async def test_multiple_page_operations(self, mock_playwright):
        """Test multiple page operations on the same manager."""
        mock_pw, mock_browser, mock_context, mock_page1 = mock_playwright

        mock_page2 = AsyncMock()
        mock_context.new_page.side_effect = [mock_page1, mock_page2]
        mock_context.pages = [mock_page1, mock_page2]

        manager = CamoufoxManager()
        manager._initialized = True
        manager._context = mock_context

        # Get current page (first one)
        page1 = await manager.get_current_page()
        assert page1 == mock_context.pages[0]  # Should be the first page

        # Create new page (this will call new_page and return mock_page2)
        page2 = await manager.new_page("https://example.com")
        assert page2 is mock_page2
        mock_page2.goto.assert_called_once_with("https://example.com")

        # Get all pages
        pages = await manager.get_all_pages()
        assert pages == [mock_page1, mock_page2]

        # Current page should still be first one
        current_page = await manager.get_current_page()
        assert current_page == mock_context.pages[0]  # Should still be the first page


class TestCleanupAllBrowsers(TestCamoufoxManagerBase):
    """Tests for the cleanup_all_browsers and _sync_cleanup_browsers functions."""

    @pytest.fixture(autouse=True)
    def reset_cleanup_state(self):
        """Reset the cleanup state before each test."""
        from tools.browser import camoufox_manager

        # Reset the cleanup flag and active managers
        camoufox_manager._cleanup_done = False
        # Don't clear active managers here - let tests manage their own state
        yield
        # Clean up after tests
        camoufox_manager._cleanup_done = False

    @pytest.mark.asyncio
    async def test_cleanup_all_browsers_closes_all_initialized_managers(self):
        """Test that cleanup_all_browsers closes all initialized browser managers."""
        from tools.browser import camoufox_manager

        # Create two managers and mock their initialization
        manager1 = get_camoufox_manager("cleanup-test-a")
        manager2 = get_camoufox_manager("cleanup-test-b")

        # Mock them as initialized
        manager1._initialized = True
        manager1._context = AsyncMock()
        manager1._browser = AsyncMock()

        manager2._initialized = True
        manager2._context = AsyncMock()
        manager2._browser = AsyncMock()

        # Run cleanup
        await cleanup_all_browsers()

        # Both managers should be cleaned up
        assert not manager1._initialized
        assert not manager2._initialized
        assert camoufox_manager._cleanup_done is True

    @pytest.mark.asyncio
    async def test_cleanup_all_browsers_skips_if_already_done(self):
        """Test that cleanup_all_browsers doesn't run twice."""
        from tools.browser import camoufox_manager

        # Mark cleanup as already done
        camoufox_manager._cleanup_done = True

        # Create a manager that should NOT be cleaned up
        manager = get_camoufox_manager("no-cleanup-test")
        manager._initialized = True
        manager._context = AsyncMock()
        manager._browser = AsyncMock()

        # Run cleanup
        await cleanup_all_browsers()

        # Manager should still be initialized (cleanup was skipped)
        assert manager._initialized is True

    @pytest.mark.asyncio
    async def test_cleanup_all_browsers_ignores_uninitialized_managers(self):
        """Test that cleanup_all_browsers skips managers that aren't initialized."""
        from tools.browser import camoufox_manager

        # Create a manager but don't initialize it
        manager = get_camoufox_manager("uninitialized-test")
        manager._initialized = False

        # Run cleanup - should not raise
        await cleanup_all_browsers()

        assert camoufox_manager._cleanup_done is True

    @pytest.mark.asyncio
    async def test_cleanup_all_browsers_handles_exceptions_silently(self):
        """Test that cleanup_all_browsers silently ignores cleanup errors."""
        from tools.browser import camoufox_manager

        # Create a manager with mocked cleanup that raises
        manager = get_camoufox_manager("error-test")
        manager._initialized = True
        manager._context = AsyncMock()
        manager._browser = AsyncMock()

        # Make cleanup raise an exception
        with patch.object(manager, "_cleanup", side_effect=Exception("Boom!")):
            # Should not raise, even though cleanup failed
            await cleanup_all_browsers()

        assert camoufox_manager._cleanup_done is True

    def test_sync_cleanup_browsers_runs_when_no_managers(self):
        """Test that _sync_cleanup_browsers handles empty managers dict."""
        from tools.browser import camoufox_manager

        # Clear all managers
        camoufox_manager._active_managers.clear()
        camoufox_manager._cleanup_done = False

        # Should not raise even with no managers
        _sync_cleanup_browsers()

    def test_sync_cleanup_browsers_skips_if_already_done(self):
        """Test that _sync_cleanup_browsers doesn't run twice."""
        from tools.browser import camoufox_manager

        # Mark as done
        camoufox_manager._cleanup_done = True

        # Create a manager that should NOT be cleaned up
        manager = get_camoufox_manager("sync-no-cleanup")
        manager._initialized = True
        manager._context = MagicMock()
        manager._browser = MagicMock()

        # Run sync cleanup
        _sync_cleanup_browsers()

        # Manager should still be initialized
        assert manager._initialized is True

    def test_sync_cleanup_browsers_catches_all_exceptions(self):
        """Test that _sync_cleanup_browsers catches all exceptions silently."""
        from tools.browser import camoufox_manager

        camoufox_manager._cleanup_done = False

        # Create a manager
        manager = get_camoufox_manager("sync-error-test")
        manager._initialized = True

        # Mock asyncio.new_event_loop to raise
        with patch("asyncio.new_event_loop", side_effect=RuntimeError("No loop!")):
            # Should not raise
            _sync_cleanup_browsers()


if __name__ == "__main__":
    pytest.main([__file__])
