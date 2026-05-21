"""Tests for remaining uncovered lines across browser tool files."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ===== browser_manager.py =====

MOD_MGR = "code_puppy.tools.browser.browser_manager"


class TestBrowserManagerRemainingLines:
    @pytest.mark.asyncio
    async def test_initialize_success_sets_initialized(self):
        """Cover line 154: _initialized set to True after successful _initialize_browser."""
        from code_puppy.tools.browser.browser_manager import BrowserManager

        mgr = BrowserManager.__new__(BrowserManager)
        mgr.session_id = "test-success"
        mgr._initialized = False
        mgr._cleanup = AsyncMock()
        mgr._initialize_browser = AsyncMock()  # succeeds

        with patch(f"{MOD_MGR}.emit_info"):
            await mgr.async_initialize()
            assert mgr._initialized is True
            mgr._cleanup.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_cleanup_on_exception(self):
        """Cover exception branch in async_initialize."""
        from code_puppy.tools.browser.browser_manager import BrowserManager

        mgr = BrowserManager.__new__(BrowserManager)
        mgr.session_id = "test"
        mgr._initialized = False
        mgr._cleanup = AsyncMock()
        mgr._initialize_browser = AsyncMock(side_effect=RuntimeError("fail"))

        with patch(f"{MOD_MGR}.emit_info"):
            with pytest.raises(RuntimeError):
                await mgr.async_initialize()
            mgr._cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_exception_branch(self):
        """Cover lines 267-269: outer exception during cleanup with silent=False."""
        from code_puppy.tools.browser.browser_manager import BrowserManager
        import code_puppy.tools.browser.browser_manager as bm_mod

        mgr = BrowserManager.__new__(BrowserManager)
        mgr.session_id = "test-exc-outer"
        mgr._initialized = True
        mgr._context = None
        mgr._browser = None

        # Replace _active_managers with a dict that raises on 'in'
        original_managers = bm_mod._active_managers
        bad_managers = MagicMock()
        bad_managers.__contains__ = MagicMock(side_effect=RuntimeError("boom"))
        bm_mod._active_managers = bad_managers

        try:
            with patch(f"{MOD_MGR}.emit_warning") as mock_warn:
                await mgr._cleanup(silent=False)
                mock_warn.assert_called()
        finally:
            bm_mod._active_managers = original_managers

    @pytest.mark.asyncio
    async def test_atexit_cleanup_with_running_loop(self):
        """Cover lines 353-354: atexit handler when event loop is running."""
        from code_puppy.tools.browser.browser_manager import (
            _sync_cleanup_browsers,
            _active_managers,
        )
        import code_puppy.tools.browser.browser_manager as bm_mod

        # Ensure early-exit guards don't trigger
        old_cleanup_done = bm_mod._cleanup_done
        bm_mod._cleanup_done = False
        _active_managers["dummy"] = MagicMock()

        try:
            with patch(f"{MOD_MGR}.cleanup_all_browsers", new_callable=AsyncMock):
                # We're inside a running loop (pytest-asyncio), so the branch fires
                _sync_cleanup_browsers()
        finally:
            _active_managers.pop("dummy", None)
            bm_mod._cleanup_done = old_cleanup_done

    def test_atexit_cleanup_no_running_loop(self):
        """Cover the no-running-loop path."""
        from code_puppy.tools.browser.browser_manager import _sync_cleanup_browsers
        import code_puppy.tools.browser.browser_manager as bm_mod

        old_cleanup_done = bm_mod._cleanup_done
        bm_mod._cleanup_done = False
        bm_mod._active_managers["dummy"] = MagicMock()

        try:
            with (
                patch(f"{MOD_MGR}.cleanup_all_browsers", new_callable=AsyncMock),
                patch("asyncio.get_running_loop", side_effect=RuntimeError),
                patch("asyncio.new_event_loop") as mock_loop,
                patch("asyncio.set_event_loop"),
            ):
                mock_loop.return_value = MagicMock()
                _sync_cleanup_browsers()
        finally:
            bm_mod._active_managers.pop("dummy", None)
            bm_mod._cleanup_done = old_cleanup_done


# ===== browser_scripts.py line 155 =====

MOD_SCRIPTS = "code_puppy.tools.browser.browser_scripts"


class TestBrowserScriptsRemainingLines:
    @pytest.mark.asyncio
    async def test_scroll_to_element_no_page(self):
        """Cover line 155: scroll_to_element returns error when no active page."""
        from code_puppy.tools.browser.browser_scripts import scroll_to_element

        mgr = AsyncMock()
        mgr.get_current_page.return_value = None
        with (
            patch(f"{MOD_SCRIPTS}.get_session_browser_manager", return_value=mgr),
            patch(f"{MOD_SCRIPTS}.emit_info"),
        ):
            r = await scroll_to_element(selector="#x")
            assert r["success"] is False
            assert "No active browser page" in r["error"]


# ===== browser_workflows.py =====

MOD_WF = "code_puppy.tools.browser.browser_workflows"


class TestBrowserWorkflowsRemainingLines:
    @pytest.mark.asyncio
    async def test_list_workflows_file_error(self, tmp_path):
        """Cover exception reading a workflow file."""
        from code_puppy.tools.browser.browser_workflows import list_workflows

        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir()
        bad_file = wf_dir / "bad.md"
        bad_file.write_text("test")

        with (
            patch(f"{MOD_WF}.get_workflows_directory", return_value=wf_dir),
            patch(f"{MOD_WF}.emit_info"),
            patch(f"{MOD_WF}.emit_warning") as mock_warn,
            patch(f"{MOD_WF}.emit_success"),
            patch.object(type(bad_file), "stat", side_effect=OSError("fail")),
        ):
            r = await list_workflows()
            assert r["success"] is True
            mock_warn.assert_called()
