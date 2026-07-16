"""Additional coverage tests for cli_runner.py - uncovered branches.

Focuses on: run_prompt_with_attachments, execute_single_prompt, main_entry,
and interactive_mode branches.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _resolved(text="", warnings=None, files=None, clips=None, links=None):
    """Build a stub ResolvedUserPrompt for patching resolve_user_prompt."""
    m = MagicMock()
    m.text = text
    m.warnings = warnings or []
    m.file_attachments = files or []
    m.clipboard_images = clips or []
    m.link_attachments = links or []
    m.attachments = (files or []) + (clips or [])
    return m


class TestRunPromptWithAttachments:
    """Test run_prompt_with_attachments function."""

    @pytest.mark.anyio
    async def test_empty_prompt_returns_none(self):
        from code_puppy.cli_runner import run_prompt_with_attachments

        # A prompt that becomes empty after attachment parsing
        mock_agent = MagicMock()
        with patch("code_puppy.cli_runner.resolve_user_prompt") as mock_resolve:
            mock_resolve.return_value = _resolved(text="")

            result, task = await run_prompt_with_attachments(mock_agent, "")
            assert result is None
            assert task is None

    @pytest.mark.anyio
    async def test_with_attachments_and_run_ui(self):
        from code_puppy.cli_runner import run_prompt_with_attachments

        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_agent.run_with_mcp = AsyncMock(return_value=mock_result)

        mock_attachment = MagicMock()
        mock_attachment.content = b"image-data"
        mock_link = MagicMock()
        mock_link.url_part = "https://example.com"

        with (
            patch("code_puppy.cli_runner.resolve_user_prompt") as mock_resolve,
            patch("code_puppy.agents.event_stream_handler.set_streaming_console"),
            patch("code_puppy.messaging.run_ui.run_ui") as mock_run_ui,
        ):
            mock_resolve.return_value = _resolved(
                text="do stuff",
                warnings=["warn1"],
                files=[mock_attachment.content],
                clips=[b"clip-img"],
                links=[mock_link.url_part],
            )

            console = MagicMock()
            result, task = await run_prompt_with_attachments(
                mock_agent, "do stuff", display_console=console, use_run_ui=True
            )
            assert result is mock_result
            mock_run_ui.assert_called_once()

    @pytest.mark.anyio
    async def test_cancelled_with_run_ui(self):
        from code_puppy.cli_runner import run_prompt_with_attachments

        mock_agent = MagicMock()
        mock_agent.run_with_mcp = AsyncMock(side_effect=asyncio.CancelledError)

        with (
            patch("code_puppy.cli_runner.resolve_user_prompt") as mock_resolve,
            patch("code_puppy.agents.event_stream_handler.set_streaming_console"),
            patch("code_puppy.messaging.run_ui.run_ui") as mock_run_ui,
        ):
            mock_resolve.return_value = _resolved(text="do stuff")

            console = MagicMock()
            result, task = await run_prompt_with_attachments(
                mock_agent, "do stuff", display_console=console, use_run_ui=True
            )
            assert result is None
            mock_run_ui.assert_called_once()

    @pytest.mark.anyio
    async def test_cancelled_without_spinner(self):
        from code_puppy.cli_runner import run_prompt_with_attachments

        mock_agent = MagicMock()
        mock_agent.run_with_mcp = AsyncMock(side_effect=asyncio.CancelledError)

        with (
            patch("code_puppy.cli_runner.resolve_user_prompt") as mock_resolve,
            patch("code_puppy.agents.event_stream_handler.set_streaming_console"),
        ):
            mock_resolve.return_value = _resolved(text="do stuff")

            result, task = await run_prompt_with_attachments(
                mock_agent, "do stuff", use_run_ui=False
            )
            assert result is None

    @pytest.mark.anyio
    async def test_clipboard_placeholder_cleaned(self):
        from code_puppy.cli_runner import run_prompt_with_attachments

        mock_agent = MagicMock()
        mock_result = MagicMock()
        mock_agent.run_with_mcp = AsyncMock(return_value=mock_result)

        # End-to-end through the REAL resolver: only the clipboard manager
        # is stubbed, so this covers placeholder stripping in
        # resolve_user_prompt as consumed by run_prompt_with_attachments.
        placeholder = "[clipboard image 1]"
        with (
            patch(
                "code_puppy.command_line.clipboard.get_clipboard_manager"
            ) as mock_clip,
            patch("code_puppy.agents.event_stream_handler.set_streaming_console"),
        ):
            clip_mgr = MagicMock()
            clip_mgr.get_pending_images.return_value = [b"img"]
            mock_clip.return_value = clip_mgr

            result, task = await run_prompt_with_attachments(
                mock_agent, f"{placeholder} describe this", use_run_ui=False
            )
            # The cleaned prompt should have placeholder removed
            call_args = mock_agent.run_with_mcp.call_args
            assert "clipboard image" not in call_args[0][0]
            assert "describe this" in call_args[0][0]
            # The pending image must ride along as an attachment
            assert call_args[1]["attachments"] == [b"img"]
            clip_mgr.clear_pending.assert_called_once()


class TestExecuteSinglePrompt:
    @pytest.mark.anyio
    async def test_success(self):
        from code_puppy.cli_runner import execute_single_prompt

        mock_renderer = MagicMock()
        mock_renderer.console = MagicMock()

        mock_result = MagicMock()
        mock_result.output = "done!"

        with (
            patch("code_puppy.cli_runner.get_current_agent"),
            patch(
                "code_puppy.cli_runner.run_prompt_with_attachments",
                new_callable=AsyncMock,
            ) as mock_run,
            patch("code_puppy.cli_runner.emit_info"),
        ):
            mock_run.return_value = (mock_result, MagicMock())
            await execute_single_prompt("hello", mock_renderer)

    @pytest.mark.anyio
    async def test_none_response(self):
        from code_puppy.cli_runner import execute_single_prompt

        mock_renderer = MagicMock()
        mock_renderer.console = MagicMock()

        with (
            patch("code_puppy.cli_runner.get_current_agent"),
            patch(
                "code_puppy.cli_runner.run_prompt_with_attachments",
                new_callable=AsyncMock,
            ) as mock_run,
            patch("code_puppy.cli_runner.emit_info"),
        ):
            mock_run.return_value = None
            await execute_single_prompt("hello", mock_renderer)

    @pytest.mark.anyio
    async def test_cancelled(self):
        from code_puppy.cli_runner import execute_single_prompt

        mock_renderer = MagicMock()
        mock_renderer.console = MagicMock()

        with (
            patch("code_puppy.cli_runner.get_current_agent"),
            patch(
                "code_puppy.cli_runner.run_prompt_with_attachments",
                new_callable=AsyncMock,
                side_effect=asyncio.CancelledError,
            ),
            patch("code_puppy.cli_runner.emit_info"),
        ):
            await execute_single_prompt("hello", mock_renderer)

    @pytest.mark.anyio
    async def test_exception(self):
        from code_puppy.cli_runner import execute_single_prompt

        mock_renderer = MagicMock()
        mock_renderer.console = MagicMock()

        with (
            patch("code_puppy.cli_runner.get_current_agent"),
            patch(
                "code_puppy.cli_runner.run_prompt_with_attachments",
                new_callable=AsyncMock,
                side_effect=RuntimeError("boom"),
            ),
            patch("code_puppy.cli_runner.emit_info"),
        ):
            await execute_single_prompt("hello", mock_renderer)


class TestMainEntry:
    @patch("asyncio.run")
    def test_normal_exit(self, mock_run):
        import pytest

        from code_puppy.cli_runner import main_entry

        # main() returning None must map to a clean exit code of 0.
        mock_run.return_value = None
        with patch("code_puppy.cli_runner.reset_unix_terminal"):
            with pytest.raises(SystemExit) as exc_info:
                main_entry()
        assert exc_info.value.code == 0

    @patch("asyncio.run")
    def test_nonzero_exit_code_propagates(self, mock_run):
        import pytest

        from code_puppy.cli_runner import main_entry

        # A handle_cli_args plugin asking for exit_code 7 flows up through
        # main() -> main_entry() and must become the process exit code.
        mock_run.return_value = 7
        with patch("code_puppy.cli_runner.reset_unix_terminal"):
            with pytest.raises(SystemExit) as exc_info:
                main_entry()
        assert exc_info.value.code == 7

    @patch("asyncio.run", side_effect=KeyboardInterrupt)
    def test_keyboard_interrupt(self, mock_run):
        from code_puppy.cli_runner import main_entry

        with patch("code_puppy.cli_runner.reset_unix_terminal"):
            result = main_entry()
        assert result == 0
