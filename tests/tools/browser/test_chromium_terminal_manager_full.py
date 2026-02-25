"""Full coverage tests for chromium_terminal_manager.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.browser.chromium_terminal_manager import (
    ChromiumTerminalManager,
)


class TestChromiumTerminalManagerCoverage:
    @pytest.mark.asyncio
    async def test_get_current_page_no_context_after_init(self):
        """Cover line 149: context is None after init attempt."""
        mgr = ChromiumTerminalManager("no-ctx")
        mgr._initialized = False

        with patch.object(mgr, "async_initialize") as mock_init:

            async def init_noop():
                mgr._initialized = True
                mgr._context = None  # Still None after init

            mock_init.side_effect = init_noop
            page = await mgr.get_current_page()
            assert page is None

    @pytest.mark.asyncio
    async def test_new_page_no_context_raises(self):
        """Cover lines 198-199: RuntimeError when context unavailable."""
        mgr = ChromiumTerminalManager("no-ctx2")
        mgr._initialized = False

        with patch.object(mgr, "async_initialize") as mock_init:

            async def init_noop():
                mgr._initialized = True
                mgr._context = None

            mock_init.side_effect = init_noop
            with pytest.raises(RuntimeError, match="not available"):
                await mgr.new_page()

    @pytest.mark.asyncio
    async def test_cleanup_with_playwright(self):
        """Cover lines 205-206: cleanup stops playwright."""
        mgr = ChromiumTerminalManager("pw-cleanup")
        mgr._initialized = True
        mgr._context = AsyncMock()
        mgr._browser = AsyncMock()
        mgr._playwright = AsyncMock()

        await mgr._cleanup()
        assert mgr._playwright is None
        assert mgr._initialized is False

    @pytest.mark.asyncio
    async def test_cleanup_silent_exception(self):
        """Cover lines 220-222: outer exception in silent cleanup."""
        mgr = ChromiumTerminalManager("silent-err")
        mgr._initialized = True
        mgr._context = MagicMock()
        mgr._context.close = AsyncMock(side_effect=Exception("ctx err"))
        mgr._browser = MagicMock()
        mgr._browser.close = AsyncMock(side_effect=Exception("browser err"))
        mgr._playwright = MagicMock()
        mgr._playwright.stop = AsyncMock(side_effect=Exception("pw err"))

        # Should not raise
        await mgr._cleanup(silent=True)
        assert mgr._initialized is False

    @pytest.mark.asyncio
    async def test_cleanup_non_silent_warning(self):
        """Cover line 220-222: warning in non-silent cleanup."""

        mgr = ChromiumTerminalManager("warn-test")
        mgr._initialized = True
        # Set context to something that will cause the outer try to fail
        mgr._context = None
        mgr._browser = None
        mgr._playwright = None

        await mgr._cleanup(silent=False)
        assert mgr._initialized is False
