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


class TestExecuteSinglePromptRegression:
    """Focused regression tests for the freshly-updated execute_single_prompt.

    Four cases:
      1. Handled slash command → handle_command called, no agent run, no persist.
      2. Slash command returning replacement → replacement forwarded to agent.
      3. Ordinary headless turn → persist_named_session called with AUTOSAVE_DIR
         and full result.all_messages() history; both auto and explicit session.
      4. Shell ! pass-through → execute_shell_passthrough called, no persist.
    """

    def _renderer(self):
        r = MagicMock()
        r.console = MagicMock()
        return r

    def _parsed(self, text):
        """Stub for parse_prompt_attachments result."""
        m = MagicMock()
        m.prompt = text
        return m

    @pytest.mark.anyio
    async def test_slash_handled_skips_run_and_persist(self):
        """Case 1: handle_command returns True → no agent run, no session persist."""
        from code_puppy.cli_runner import execute_single_prompt

        with (
            patch(
                "code_puppy.command_line.shell_passthrough.is_shell_passthrough",
                return_value=False,
            ),
            patch(
                "code_puppy.cli_runner.parse_prompt_attachments",
                return_value=self._parsed("/help"),
            ),
            patch(
                "code_puppy.command_line.command_handler.handle_command",
                return_value=True,
            ) as mock_handle,
            patch(
                "code_puppy.cli_runner.run_prompt_with_attachments",
                new_callable=AsyncMock,
            ) as mock_run,
            patch("code_puppy.session_lifecycle.persist_named_session") as mock_persist,
            patch("code_puppy.messaging.emit_info"),
            patch("code_puppy.messaging.emit_error"),
            patch("code_puppy.messaging.emit_warning"),
            patch("code_puppy.messaging.get_message_bus", return_value=MagicMock()),
        ):
            await execute_single_prompt("/help", self._renderer())

        mock_handle.assert_called_once_with("/help")
        mock_run.assert_not_called()
        mock_persist.assert_not_called()

    @pytest.mark.anyio
    async def test_slash_replacement_prompt_forwarded_to_agent(self):
        """Case 2: handle_command returning a string sends that string to agent."""
        from code_puppy.cli_runner import execute_single_prompt

        replacement = "refactor all dead code"
        mock_result = MagicMock()
        mock_result.output = "done"
        mock_result.all_messages.return_value = []
        mock_agent = MagicMock()
        mock_agent.set_message_history = MagicMock()

        with (
            patch(
                "code_puppy.command_line.shell_passthrough.is_shell_passthrough",
                return_value=False,
            ),
            patch(
                "code_puppy.cli_runner.parse_prompt_attachments",
                return_value=self._parsed("/do-stuff"),
            ),
            patch(
                "code_puppy.command_line.command_handler.handle_command",
                return_value=replacement,
            ),
            patch("code_puppy.cli_runner.get_current_agent", return_value=mock_agent),
            patch(
                "code_puppy.cli_runner.run_prompt_with_attachments",
                new_callable=AsyncMock,
                return_value=(mock_result, MagicMock()),
            ) as mock_run,
            patch("code_puppy.session_lifecycle.persist_named_session"),
            patch(
                "code_puppy.config.get_current_session_name",
                return_value="auto_session_test",
            ),
            patch("code_puppy.messaging.emit_info"),
            patch("code_puppy.messaging.emit_error"),
            patch("code_puppy.messaging.emit_warning"),
            patch("code_puppy.messaging.get_message_bus", return_value=MagicMock()),
            patch("code_puppy.messaging.messages.AgentResponseMessage", MagicMock()),
        ):
            await execute_single_prompt("/do-stuff", self._renderer())

        mock_run.assert_called_once()
        # Second positional arg to run_prompt_with_attachments is the prompt.
        assert mock_run.call_args[0][1] == replacement
        # Headless mode must always pass use_run_ui=False.
        assert mock_run.call_args[1].get("use_run_ui") is False

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "explicit_session",
        [None, "headless-explicit"],
        ids=["default-session", "explicit-session"],
    )
    async def test_ordinary_turn_persists_to_disk(self, tmp_path, explicit_session):
        """Case 3: real persist_named_session + load_session prove history reloadable.

        Covers both sub-cases:
        - default-session: session_name=None uses get_current_session_name().
        - explicit-session: session_name provided; get_current_session_name never called.

        Uses a temp AUTOSAVE_DIR so the real I/O path runs end-to-end and the
        completed result.all_messages() history is verifiable after a roundtrip.
        External messaging is mocked; persist_named_session and load_session are real.
        """
        from code_puppy.cli_runner import execute_single_prompt
        from code_puppy.session_storage import load_session

        autosaves_dir = tmp_path / "autosaves"
        auto_session = "auto_session_20240101_120000"

        # Plain strings are picklable — survive persist/load roundtrip faithfully.
        fake_msgs = ["user: write some code", "assistant: here is the code"]

        # Wire the mock agent so set_message_history feeds get_message_history,
        # giving the real persist_named_session genuine data to pickle.
        history_store: list = []

        def _set(msgs):
            history_store.clear()
            history_store.extend(msgs)

        mock_agent = MagicMock()
        mock_agent.set_message_history.side_effect = _set
        mock_agent.get_message_history.side_effect = lambda: list(history_store)
        mock_agent.estimate_tokens_for_message.return_value = 0

        mock_result = MagicMock()
        mock_result.output = "here is the code"
        mock_result.all_messages.return_value = fake_msgs

        with (
            patch(
                "code_puppy.command_line.shell_passthrough.is_shell_passthrough",
                return_value=False,
            ),
            patch(
                "code_puppy.cli_runner.parse_prompt_attachments",
                return_value=self._parsed("write some code"),
            ),
            patch("code_puppy.cli_runner.get_current_agent", return_value=mock_agent),
            patch(
                "code_puppy.cli_runner.run_prompt_with_attachments",
                new_callable=AsyncMock,
                return_value=(mock_result, MagicMock()),
            ),
            # Redirect AUTOSAVE_DIR to our temp tree so real I/O stays isolated.
            patch("code_puppy.config.AUTOSAVE_DIR", str(autosaves_dir)),
            patch(
                "code_puppy.config.get_current_session_name",
                return_value=auto_session,
            ) as mock_gcsn,
            patch("code_puppy.messaging.emit_info"),
            patch("code_puppy.messaging.emit_error"),
            patch("code_puppy.messaging.emit_warning"),
            patch("code_puppy.messaging.get_message_bus", return_value=MagicMock()),
            patch("code_puppy.messaging.messages.AgentResponseMessage", MagicMock()),
        ):
            await execute_single_prompt(
                "write some code", self._renderer(), session_name=explicit_session
            )

        # ── session-name routing assertions ──────────────────────────────────
        expected_session = explicit_session or auto_session
        if explicit_session is None:
            # Default path: auto-generated name must be fetched.
            mock_gcsn.assert_called_once()
        else:
            # Explicit name short-circuits get_current_session_name entirely.
            mock_gcsn.assert_not_called()

        # ── agent history populated before persist ────────────────────────────
        mock_agent.set_message_history.assert_called_once_with(fake_msgs)

        # ── real disk roundtrip: load_session must reproduce the full history ─
        loaded = load_session(expected_session, autosaves_dir)
        assert loaded == fake_msgs, (
            f"Disk roundtrip mismatch for session {expected_session!r}: {loaded!r}"
        )

    @pytest.mark.anyio
    async def test_shell_passthrough_skips_agent_and_persist(self):
        """Case 4: ! prefix routes to execute_shell_passthrough; nothing else fires."""
        from code_puppy.cli_runner import execute_single_prompt

        with (
            patch(
                "code_puppy.command_line.shell_passthrough.is_shell_passthrough",
                return_value=True,
            ) as mock_is_shell,
            patch(
                "code_puppy.command_line.shell_passthrough.execute_shell_passthrough"
            ) as mock_exec_shell,
            patch(
                "code_puppy.cli_runner.run_prompt_with_attachments",
                new_callable=AsyncMock,
            ) as mock_run,
            patch("code_puppy.session_lifecycle.persist_named_session") as mock_persist,
        ):
            await execute_single_prompt("!ls -la", self._renderer())

        mock_is_shell.assert_called_once_with("!ls -la")
        mock_exec_shell.assert_called_once_with("!ls -la")
        mock_run.assert_not_called()
        mock_persist.assert_not_called()


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
