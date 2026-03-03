"""Full coverage tests for terminal_command_tools.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai import ToolReturn

from code_puppy.tools.browser.terminal_command_tools import (
    _focus_terminal,
    _normalize_modifier,
    register_run_terminal_command,
    register_send_terminal_keys,
    register_wait_terminal_output,
    run_terminal_command,
    send_terminal_keys,
    wait_for_terminal_output,
)

MOD = "code_puppy.tools.browser.terminal_command_tools"


@pytest.fixture(autouse=True)
def _suppress():
    with (
        patch(f"{MOD}.emit_info"),
        patch(f"{MOD}.emit_error"),
        patch(f"{MOD}.emit_success"),
    ):
        yield


class TestFocusTerminal:
    @pytest.mark.asyncio
    async def test_js_success(self):
        page = AsyncMock()
        page.evaluate.return_value = {"success": True, "method": "textarea_focus"}
        r = await _focus_terminal(page)
        assert r["success"] is True

    @pytest.mark.asyncio
    async def test_js_fail_fallback(self):
        page = AsyncMock()
        page.evaluate.return_value = {"success": False}
        # Fallback: query_selector returns element for first selector
        elem = AsyncMock()
        page.query_selector.side_effect = [elem, None, None, None, None]
        with patch("asyncio.sleep", new_callable=AsyncMock):
            r = await _focus_terminal(page)
            assert r["success"] is True

    @pytest.mark.asyncio
    async def test_js_fail_no_fallback(self):
        page = AsyncMock()
        page.evaluate.return_value = {"success": False}
        page.query_selector.return_value = None
        with patch("asyncio.sleep", new_callable=AsyncMock):
            r = await _focus_terminal(page)
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_exception(self):
        page = AsyncMock()
        page.evaluate.side_effect = RuntimeError("err")
        r = await _focus_terminal(page)
        assert r["success"] is False

    @pytest.mark.asyncio
    async def test_fallback_non_textarea_focuses_textarea(self):
        """Cover the branch where we click a non-textarea then try to focus textarea."""
        page = AsyncMock()
        page.evaluate.return_value = {"success": False}
        # First query (textarea) returns None, second (.xterm-viewport) returns element
        textarea = AsyncMock()
        viewport = AsyncMock()
        page.query_selector.side_effect = [None, viewport, textarea]
        with patch("asyncio.sleep", new_callable=AsyncMock):
            r = await _focus_terminal(page)
            assert r["success"] is True


class TestNormalizeModifier:
    def test_known(self):
        assert _normalize_modifier("ctrl") == "Control"
        assert _normalize_modifier("cmd") == "Meta"
        assert _normalize_modifier("shift") == "Shift"

    def test_unknown(self):
        assert _normalize_modifier("Unknown") == "Unknown"


class TestRunTerminalCommand:
    @pytest.mark.asyncio
    async def test_no_page(self):
        mgr = AsyncMock()
        mgr.get_current_page.return_value = None
        with patch(f"{MOD}.get_session_manager", return_value=mgr):
            r = await run_terminal_command("ls")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_success_no_screenshot(self):
        page = AsyncMock()
        page.evaluate.return_value = {"success": True}
        mgr = AsyncMock()
        mgr.get_current_page.return_value = page
        with (
            patch(f"{MOD}.get_session_manager", return_value=mgr),
            patch(f"{MOD}._focus_terminal", return_value={"success": True}),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            r = await run_terminal_command("ls")
            assert r["success"] is True

    @pytest.mark.asyncio
    async def test_with_screenshot_tool_return(self):
        page = AsyncMock()
        page.evaluate.return_value = {"success": True}
        mgr = AsyncMock()
        mgr.get_current_page.return_value = page

        mock_tool_return = ToolReturn(
            return_value="ok",
            content=["test"],
            metadata={"screenshot_path": "/tmp/shot.png"},
        )

        with (
            patch(f"{MOD}.get_session_manager", return_value=mgr),
            patch(f"{MOD}._focus_terminal", return_value={"success": True}),
            patch(f"{MOD}.terminal_screenshot", return_value=mock_tool_return),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            r = await run_terminal_command("ls", capture_screenshot=True)
            assert r["success"] is True
            assert "screenshot_path" in r

    @pytest.mark.asyncio
    async def test_with_screenshot_dict(self):
        page = AsyncMock()
        page.evaluate.return_value = {"success": True}
        mgr = AsyncMock()
        mgr.get_current_page.return_value = page

        with (
            patch(f"{MOD}.get_session_manager", return_value=mgr),
            patch(f"{MOD}._focus_terminal", return_value={"success": True}),
            patch(
                f"{MOD}.terminal_screenshot",
                return_value={"success": True, "screenshot_path": "/tmp/s.png"},
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            r = await run_terminal_command("ls", capture_screenshot=True)
            assert r["success"] is True

    @pytest.mark.asyncio
    async def test_exception(self):
        mgr = AsyncMock()
        mgr.get_current_page.side_effect = RuntimeError("boom")
        with patch(f"{MOD}.get_session_manager", return_value=mgr):
            r = await run_terminal_command("ls")
            assert r["success"] is False


class TestSendTerminalKeys:
    @pytest.mark.asyncio
    async def test_no_page(self):
        mgr = AsyncMock()
        mgr.get_current_page.return_value = None
        with patch(f"{MOD}.get_session_manager", return_value=mgr):
            r = await send_terminal_keys("Enter")
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_success_with_modifiers(self):
        page = AsyncMock()
        mgr = AsyncMock()
        mgr.get_current_page.return_value = page
        with (
            patch(f"{MOD}.get_session_manager", return_value=mgr),
            patch(f"{MOD}._focus_terminal", return_value={"success": True}),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            r = await send_terminal_keys("c", modifiers=["Control"])
            assert r["success"] is True

    @pytest.mark.asyncio
    async def test_success_repeat(self):
        page = AsyncMock()
        mgr = AsyncMock()
        mgr.get_current_page.return_value = page
        with (
            patch(f"{MOD}.get_session_manager", return_value=mgr),
            patch(f"{MOD}._focus_terminal", return_value={"success": True}),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            r = await send_terminal_keys("ArrowDown", repeat=3)
            assert r["success"] is True
            assert r["repeat_count"] == 3

    @pytest.mark.asyncio
    async def test_success_single_lowercase(self):
        page = AsyncMock()
        mgr = AsyncMock()
        mgr.get_current_page.return_value = page
        with (
            patch(f"{MOD}.get_session_manager", return_value=mgr),
            patch(f"{MOD}._focus_terminal", return_value={"success": True}),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            r = await send_terminal_keys("a")
            assert r["success"] is True
            page.keyboard.type.assert_called()

    @pytest.mark.asyncio
    async def test_exception(self):
        mgr = AsyncMock()
        mgr.get_current_page.side_effect = RuntimeError("boom")
        with patch(f"{MOD}.get_session_manager", return_value=mgr):
            r = await send_terminal_keys("Enter")
            assert r["success"] is False


class TestWaitForTerminalOutput:
    @pytest.mark.asyncio
    async def test_read_fails(self):
        with patch(
            f"{MOD}.terminal_read_output",
            return_value={"success": False, "error": "no page"},
        ):
            r = await wait_for_terminal_output()
            assert r["success"] is False

    @pytest.mark.asyncio
    async def test_no_pattern(self):
        with patch(
            f"{MOD}.terminal_read_output",
            return_value={"success": True, "output": "hello", "line_count": 1},
        ):
            r = await wait_for_terminal_output()
            assert r["success"] is True
            assert r["matched"] is True

    @pytest.mark.asyncio
    async def test_pattern_regex_match(self):
        with patch(
            f"{MOD}.terminal_read_output",
            return_value={"success": True, "output": "hello world", "line_count": 1},
        ):
            r = await wait_for_terminal_output(pattern="hel+o")
            assert r["matched"] is True

    @pytest.mark.asyncio
    async def test_pattern_no_match(self):
        with patch(
            f"{MOD}.terminal_read_output",
            return_value={"success": True, "output": "hello", "line_count": 1},
        ):
            r = await wait_for_terminal_output(pattern="xyz")
            assert r["matched"] is False

    @pytest.mark.asyncio
    async def test_pattern_invalid_regex_falls_back(self):
        with patch(
            f"{MOD}.terminal_read_output",
            return_value={"success": True, "output": "hello [world", "line_count": 1},
        ):
            r = await wait_for_terminal_output(pattern="[world")
            assert r["matched"] is True  # substring match

    @pytest.mark.asyncio
    async def test_with_screenshot_tool_return(self):
        mock_tr = ToolReturn(
            return_value="ok",
            content=["test"],
            metadata={"screenshot_path": "/tmp/s.png"},
        )
        with (
            patch(
                f"{MOD}.terminal_read_output",
                return_value={"success": True, "output": "hello", "line_count": 1},
            ),
            patch(f"{MOD}.terminal_screenshot", return_value=mock_tr),
        ):
            r = await wait_for_terminal_output(capture_screenshot=True)
            assert "screenshot_path" in r

    @pytest.mark.asyncio
    async def test_with_screenshot_dict(self):
        with (
            patch(
                f"{MOD}.terminal_read_output",
                return_value={"success": True, "output": "hello", "line_count": 1},
            ),
            patch(
                f"{MOD}.terminal_screenshot",
                return_value={"success": True, "screenshot_path": "/tmp/s.png"},
            ),
        ):
            r = await wait_for_terminal_output(capture_screenshot=True)
            assert "screenshot_path" in r

    @pytest.mark.asyncio
    async def test_exception(self):
        with patch(f"{MOD}.terminal_read_output", side_effect=RuntimeError("boom")):
            r = await wait_for_terminal_output()
            assert r["success"] is False


class TestRegisterFunctions:
    def test_all(self):
        for fn in [
            register_run_terminal_command,
            register_send_terminal_keys,
            register_wait_terminal_output,
        ]:
            agent = MagicMock()
            fn(agent)
            agent.tool.assert_called_once()
