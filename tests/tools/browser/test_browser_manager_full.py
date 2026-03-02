"""Full coverage tests for browser_manager.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestLoadPluginBrowserTypes:
    def test_load_plugin_browser_types_success(self):
        from code_puppy.tools.browser import browser_manager as bm

        bm._BROWSER_TYPES_LOADED = False
        bm._CUSTOM_BROWSER_TYPES = {}

        with patch(
            "code_puppy.tools.browser.browser_manager.on_register_browser_types",
            create=True,
        ):
            # Patch the import inside the function
            with patch.dict(
                "sys.modules",
                {
                    "code_puppy.callbacks": MagicMock(
                        on_register_browser_types=MagicMock(
                            return_value=[{"custom": lambda: None}]
                        )
                    )
                },
            ):
                bm._BROWSER_TYPES_LOADED = False
                bm._load_plugin_browser_types()
                assert bm._BROWSER_TYPES_LOADED is True

    def test_load_plugin_browser_types_already_loaded(self):
        from code_puppy.tools.browser import browser_manager as bm

        bm._BROWSER_TYPES_LOADED = True
        bm._load_plugin_browser_types()  # Should return immediately

    def test_load_plugin_browser_types_exception(self):
        from code_puppy.tools.browser import browser_manager as bm

        bm._BROWSER_TYPES_LOADED = False
        with patch.dict(
            "sys.modules",
            {
                "code_puppy.callbacks": MagicMock(
                    on_register_browser_types=MagicMock(side_effect=Exception("fail"))
                )
            },
        ):
            bm._load_plugin_browser_types()  # Should not raise
            assert bm._BROWSER_TYPES_LOADED is True


class TestSessionContextVars:
    def test_set_and_get_browser_session(self):
        from code_puppy.tools.browser.browser_manager import (
            get_browser_session,
            set_browser_session,
        )

        set_browser_session("test-session")
        assert get_browser_session() == "test-session"
        # Reset
        set_browser_session(None)

    def test_get_session_browser_manager(self):
        from code_puppy.tools.browser.browser_manager import (
            get_session_browser_manager,
            set_browser_session,
        )

        set_browser_session("mgr-test")
        mgr = get_session_browser_manager()
        assert mgr.session_id == "mgr-test"
        set_browser_session(None)


class TestInitializeBrowser:
    @pytest.mark.asyncio
    async def test_initialize_browser_default_chromium(self):
        """Test default browser initialization uses Chromium backend."""
        from code_puppy.tools.browser.browser_manager import BrowserManager

        mgr = BrowserManager("init-test")
        mgr.browser_type = None  # default

        mock_pw_instance = AsyncMock()
        mock_context = AsyncMock()
        mock_context.browser = AsyncMock()
        mock_pw_instance.chromium.launch_persistent_context.return_value = mock_context

        mock_pw_class = AsyncMock()
        mock_pw_class.start.return_value = mock_pw_instance

        with (
            patch(
                "code_puppy.tools.browser.browser_manager._load_plugin_browser_types"
            ),
            patch("code_puppy.tools.browser.browser_manager.emit_info"),
            patch("playwright.async_api.async_playwright", return_value=mock_pw_class),
        ):
            await mgr._initialize_browser()
            assert mgr._initialized is True
            assert mgr._context is mock_context

    @pytest.mark.asyncio
    async def test_initialize_browser_custom_type(self):
        """Test custom registered browser type initialization path."""
        from code_puppy.tools.browser import browser_manager as bm
        from code_puppy.tools.browser.browser_manager import BrowserManager

        async def custom_init(manager):
            manager._context = AsyncMock()
            manager._browser = AsyncMock()

        bm._CUSTOM_BROWSER_TYPES["custom"] = custom_init
        bm._BROWSER_TYPES_LOADED = True

        mgr = BrowserManager("custom-test")
        mgr.browser_type = "custom"

        with patch("code_puppy.tools.browser.browser_manager.emit_info"):
            await mgr._initialize_browser()
            assert mgr._initialized is True

        del bm._CUSTOM_BROWSER_TYPES["custom"]

    @pytest.mark.asyncio
    async def test_initialize_browser_lightpanda_type(self):
        """Test `browser_type=lightpanda` dispatches to Lightpanda initializer."""
        from code_puppy.tools.browser.browser_manager import BrowserManager

        mgr = BrowserManager("lightpanda-test")
        mgr.browser_type = "lightpanda"

        with (
            patch(
                "code_puppy.tools.browser.browser_manager._load_plugin_browser_types"
            ),
            patch("code_puppy.tools.browser.browser_manager.emit_info"),
            patch.object(
                mgr,
                "_initialize_lightpanda_browser",
                new=AsyncMock(),
            ) as mock_init_lightpanda,
        ):
            await mgr._initialize_browser()
            mock_init_lightpanda.assert_called_once()
            assert mgr._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_lightpanda_browser_sets_context(self):
        """Test Lightpanda init sets Playwright, browser, and context references."""
        from code_puppy.tools.browser.browser_manager import BrowserManager

        mgr = BrowserManager("lightpanda-init")

        mock_pw_instance = AsyncMock()
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_browser.contexts = [mock_context]
        mock_pw_instance.chromium.connect_over_cdp.return_value = mock_browser

        mock_pw_class = AsyncMock()
        mock_pw_class.start.return_value = mock_pw_instance

        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.stderr = AsyncMock()

        with (
            patch("code_puppy.tools.browser.browser_manager.emit_info"),
            patch(
                "code_puppy.tools.browser.browser_manager.asyncio.create_subprocess_exec",
                return_value=mock_process,
            ),
            patch("playwright.async_api.async_playwright", return_value=mock_pw_class),
            patch.object(mgr, "_build_lightpanda_command", return_value=["lightpanda"]),
            patch.object(mgr, "_get_lightpanda_host", return_value="127.0.0.1"),
            patch.object(mgr, "_get_lightpanda_port", return_value=9222),
        ):
            await mgr._initialize_lightpanda_browser()

        assert mgr._playwright is mock_pw_instance
        assert mgr._browser is mock_browser
        assert mgr._context is mock_context
        assert mgr._lightpanda_endpoint == "http://127.0.0.1:9222"

    @pytest.mark.asyncio
    async def test_initialize_lightpanda_retries_on_auto_port_failure(self):
        """Test Lightpanda retries startup when an auto-port attempt fails."""
        from code_puppy.tools.browser.browser_manager import BrowserManager

        mgr = BrowserManager("lightpanda-retry")

        mock_pw_instance = AsyncMock()
        mock_pw_class = AsyncMock()
        mock_pw_class.start.return_value = mock_pw_instance

        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_browser.contexts = [mock_context]

        mock_process_a = AsyncMock()
        mock_process_a.returncode = None
        mock_process_a.stderr = AsyncMock()
        mock_process_b = AsyncMock()
        mock_process_b.returncode = None
        mock_process_b.stderr = AsyncMock()

        with (
            patch("code_puppy.tools.browser.browser_manager.emit_info"),
            patch("code_puppy.tools.browser.browser_manager.emit_warning"),
            patch("playwright.async_api.async_playwright", return_value=mock_pw_class),
            patch(
                "code_puppy.tools.browser.browser_manager.asyncio.create_subprocess_exec",
                side_effect=[mock_process_a, mock_process_b],
            ),
            patch.object(mgr, "_get_lightpanda_host", return_value="127.0.0.1"),
            patch.object(mgr, "_get_lightpanda_port", side_effect=[9222, 9223]),
            patch.object(mgr, "_get_lightpanda_startup_retries", return_value=2),
            patch.object(mgr, "_build_lightpanda_command", return_value=["lightpanda"]),
            patch.object(
                mgr,
                "_connect_lightpanda_over_cdp",
                side_effect=[RuntimeError("bind fail"), mock_browser],
            ),
            patch.object(mgr, "_stop_lightpanda_process", new=AsyncMock()) as mock_stop,
            patch.dict("os.environ", {"LIGHTPANDA_PORT": ""}, clear=False),
        ):
            await mgr._initialize_lightpanda_browser()

        assert mock_stop.await_count == 1
        assert mgr._context is mock_context

    @pytest.mark.asyncio
    async def test_initialize_browser_unknown_type_raises(self):
        """Test unsupported built-in browser types fail fast with clear error."""
        from code_puppy.tools.browser.browser_manager import BrowserManager

        mgr = BrowserManager("bad-browser-type")
        mgr.browser_type = "unknown-browser"

        with (
            patch(
                "code_puppy.tools.browser.browser_manager._load_plugin_browser_types"
            ),
            pytest.raises(ValueError, match="Unsupported browser_type"),
        ):
            await mgr._initialize_browser()

    def test_get_lightpanda_port_rejects_invalid_range(self):
        """Test LIGHTPANDA_PORT values outside valid TCP range are rejected."""
        from code_puppy.tools.browser.browser_manager import BrowserManager

        mgr = BrowserManager("bad-port")

        with patch.dict("os.environ", {"LIGHTPANDA_PORT": "70000"}, clear=False):
            with pytest.raises(
                RuntimeError, match="LIGHTPANDA_PORT must be between 1 and 65535"
            ):
                mgr._get_lightpanda_port()


class TestCleanupSilent:
    @pytest.mark.asyncio
    async def test_cleanup_silent_mode(self):
        from code_puppy.tools.browser.browser_manager import BrowserManager

        mgr = BrowserManager("silent-test")
        mgr._initialized = True
        mgr._context = AsyncMock()
        mgr._context.storage_state = AsyncMock(side_effect=Exception("fail"))
        mgr._browser = AsyncMock()

        # Silent mode should not emit warnings
        with (
            patch("code_puppy.tools.browser.browser_manager.emit_warning") as mock_warn,
            patch("code_puppy.tools.browser.browser_manager.emit_success") as mock_succ,
        ):
            await mgr._cleanup(silent=True)
            mock_warn.assert_not_called()
            mock_succ.assert_not_called()
            assert mgr._initialized is False

    @pytest.mark.asyncio
    async def test_cleanup_non_silent_storage_success(self):
        from code_puppy.tools.browser.browser_manager import BrowserManager

        mgr = BrowserManager("succ-test")
        mgr._initialized = True
        mgr._context = AsyncMock()
        mgr._context.storage_state = AsyncMock()
        mgr._browser = AsyncMock()

        with (
            patch("code_puppy.tools.browser.browser_manager.emit_success") as mock_succ,
            patch("code_puppy.tools.browser.browser_manager.emit_warning"),
            patch("code_puppy.tools.browser.browser_manager.emit_info"),
        ):
            await mgr._cleanup(silent=False)
            assert mock_succ.called

    @pytest.mark.asyncio
    async def test_cleanup_outer_exception(self):
        """Test cleanup handles outer exception in non-silent mode."""
        from code_puppy.tools.browser.browser_manager import BrowserManager

        mgr = BrowserManager("outer-err")
        mgr._initialized = True
        # Make _context a property that raises
        mgr._context = MagicMock()
        mgr._context.storage_state = AsyncMock()
        mgr._context.close = AsyncMock(side_effect=Exception("ctx close fail"))
        mgr._browser = MagicMock()
        mgr._browser.close = AsyncMock(side_effect=Exception("browser close fail"))

        with (
            patch("code_puppy.tools.browser.browser_manager.emit_success"),
            patch("code_puppy.tools.browser.browser_manager.emit_warning"),
        ):
            await mgr._cleanup(silent=False)
            assert mgr._initialized is False

    @pytest.mark.asyncio
    async def test_cleanup_stops_lightpanda_and_playwright(self):
        """Test cleanup stops both Playwright and Lightpanda process."""
        from code_puppy.tools.browser.browser_manager import BrowserManager

        mgr = BrowserManager("lightpanda-cleanup")
        mgr._initialized = True
        mgr._context = AsyncMock()
        mgr._context.storage_state = AsyncMock()
        mgr._browser = AsyncMock()
        mock_playwright = AsyncMock()
        mgr._playwright = mock_playwright
        mgr._lightpanda_process = AsyncMock()

        with (
            patch("code_puppy.tools.browser.browser_manager.emit_success"),
            patch("code_puppy.tools.browser.browser_manager.emit_warning"),
            patch.object(
                mgr, "_stop_lightpanda_process", new=AsyncMock()
            ) as mock_stop_lightpanda,
        ):
            await mgr._cleanup(silent=True)

        mock_playwright.stop.assert_called_once()
        mock_stop_lightpanda.assert_called_once()


class TestSyncCleanup:
    def test_sync_cleanup_with_active_managers(self):
        from code_puppy.tools.browser import browser_manager as bm

        bm._cleanup_done = False
        mgr = bm.get_browser_manager("sync-active")
        mgr._initialized = True
        mgr._context = AsyncMock()
        mgr._context.storage_state = AsyncMock()
        mgr._browser = AsyncMock()

        with (
            patch("code_puppy.tools.browser.browser_manager.emit_info"),
            patch("code_puppy.tools.browser.browser_manager.emit_success"),
            patch("code_puppy.tools.browser.browser_manager.emit_warning"),
        ):
            bm._sync_cleanup_browsers()


class TestBackwardsCompat:
    def test_aliases(self):
        from code_puppy.tools.browser.browser_manager import (
            BrowserManager,
            CamoufoxManager,
            get_browser_manager,
            get_camoufox_manager,
        )

        assert CamoufoxManager is BrowserManager
        assert get_camoufox_manager is get_browser_manager
