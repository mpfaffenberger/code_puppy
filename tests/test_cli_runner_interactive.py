"""Coverage for interactive_runner.py::interactive_mode() single-turn and
command-handling branches (exit/quit/clear/slash-command/prompt execution,
autosave-load, onboarding triggers).

Split out of test_cli_runner_full_coverage.py; shared helpers live in
``tests/cli_runner_fixtures.py``.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.cli_runner_fixtures import (
    _interactive_patches,
    _mock_clipboard,
    _mock_parse_result,
    _mock_renderer,
    _run_interactive,
    _scripted_input,
)


# ---------------------------------------------------------------------------
# interactive_mode() tests
# ---------------------------------------------------------------------------


class TestInteractiveMode:
    """Test interactive_mode() single-turn and command branches."""

    @pytest.mark.anyio
    async def test_exit_command(self):
        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            AsyncMock(return_value="/exit"),
        )

    @pytest.mark.anyio
    async def test_startup_shows_single_press_tab_line(self):
        """Startup used to dump ~12 tip lines; now it's one pointer to the
        Tab overlay. That content moved, it isn't gone."""
        emit_system_message = MagicMock()

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            AsyncMock(return_value="/exit"),
            extra_patches={
                "code_puppy.messaging.emit_system_message": emit_system_message,
            },
        )

        messages = [call.args[0] for call in emit_system_message.call_args_list]
        assert any("Tab" in message for message in messages), messages
        # The old per-topic tip lines must be gone from startup output.
        assert not any("newline: Shift+Enter" in message for message in messages)
        assert not any(
            "Ctrl+X Ctrl+E to open $EDITOR" in message for message in messages
        )
        assert not any(
            "Type /help to view all commands" in message for message in messages
        )

    @pytest.mark.anyio
    async def test_quit_command(self):
        agent = MagicMock()
        agent.get_user_prompt.return_value = None  # test None prompt branch
        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            AsyncMock(return_value="quit"),
            agent=agent,
        )

    @pytest.mark.anyio
    async def test_eof_exits(self):
        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            AsyncMock(side_effect=EOFError),
        )

    @pytest.mark.anyio
    async def test_keyboard_interrupt_continues(self):
        fake_input = _scripted_input(KeyboardInterrupt)

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={},
        )

    @pytest.mark.anyio
    async def test_keyboard_interrupt_notifies_continuation_plugins(self):
        fake_input = _scripted_input(KeyboardInterrupt)

        mock_cancel = AsyncMock()
        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.callbacks.on_interactive_turn_cancel": mock_cancel,
            },
        )
        mock_cancel.assert_awaited()

    @pytest.mark.anyio
    async def test_clear_command(self):
        fake_input = _scripted_input("/clear")

        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            agent=agent,
            extra_patches={
                "code_puppy.prompt_runner.get_current_agent": MagicMock(
                    return_value=agent
                ),
                # /clear lives in session_commands and lazy-imports the clipboard
                # manager + autosave rotation — patch at the source modules.
                "code_puppy.command_line.clipboard.get_clipboard_manager": MagicMock(
                    return_value=_mock_clipboard([b"img"])
                ),
                "code_puppy.config.finalize_autosave_session": MagicMock(
                    return_value="session-1"
                ),
            },
        )
        agent.clear_message_history.assert_called()

    @pytest.mark.anyio
    async def test_slash_command_handled(self):
        fake_input = _scripted_input("/help")

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.command_line.command_handler.handle_command": MagicMock(
                    return_value=True
                ),
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("/help")
                ),
            },
        )

    @pytest.mark.anyio
    async def test_slash_command_returns_prompt(self):
        fake_input = _scripted_input("/custom")

        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.command_line.command_handler.handle_command": MagicMock(
                    return_value="run this"
                ),
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("/custom")
                ),
                "code_puppy.interactive_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(mock_result, MagicMock())
                ),
            },
        )

    @pytest.mark.anyio
    async def test_slash_command_exception(self):
        fake_input = _scripted_input("/bad")

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.command_line.command_handler.handle_command": MagicMock(
                    side_effect=RuntimeError("cmd error")
                ),
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("/bad")
                ),
            },
        )

    @pytest.mark.anyio
    async def test_normal_prompt_execution(self):
        fake_input = _scripted_input("write hello")

        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.interactive_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(mock_result, MagicMock())
                ),
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
            },
        )

    @pytest.mark.anyio
    async def test_prompt_returns_none_cancelled(self):
        fake_input = _scripted_input("write hello")
        mock_autosave = MagicMock()

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.interactive_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(None, MagicMock())
                ),
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
                "code_puppy.interactive_runner._save_autosave_snapshot": mock_autosave,
            },
        )
        mock_autosave.assert_called()

    @pytest.mark.anyio
    async def test_prompt_cancelled_notifies_continuation_plugins(self):
        fake_input = _scripted_input("write hello")

        mock_cancel = AsyncMock()
        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.interactive_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(None, MagicMock())
                ),
                "code_puppy.callbacks.on_interactive_turn_cancel": mock_cancel,
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
            },
        )
        mock_cancel.assert_awaited()

    @pytest.mark.anyio
    async def test_prompt_exception(self):
        fake_input = _scripted_input("write hello")

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.interactive_runner.run_prompt_with_attachments": AsyncMock(
                    side_effect=RuntimeError("agent error")
                ),
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
                "code_puppy.messaging.queue_console.get_queue_console": MagicMock(
                    return_value=MagicMock()
                ),
            },
        )

    @pytest.mark.anyio
    async def test_prompt_keyboard_interrupt_mid_turn_autosaves(self):
        """A bare KeyboardInterrupt mid-turn must not lose history: the
        'defense-in-depth' cancel branch should still persist before
        continuing the loop."""
        fake_input = _scripted_input("write hello")
        mock_autosave = MagicMock()

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.interactive_runner.run_prompt_with_attachments": AsyncMock(
                    side_effect=KeyboardInterrupt()
                ),
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("write hello")
                ),
                "code_puppy.interactive_runner._save_autosave_snapshot": mock_autosave,
            },
        )
        mock_autosave.assert_called()

    @pytest.mark.anyio
    async def test_empty_input_skipped(self):
        fake_input = _scripted_input("   ")

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("   ")
                ),
            },
        )

    @pytest.mark.anyio
    async def test_initial_command_success(self):
        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"
        mock_result = MagicMock(output="done")
        mock_result.all_messages.return_value = []

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            AsyncMock(return_value="/exit"),
            agent=agent,
            initial_command="do stuff",
            extra_patches={
                "code_puppy.prompt_runner.get_current_agent": MagicMock(
                    return_value=agent
                ),
                "code_puppy.interactive_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(mock_result, MagicMock())
                ),
            },
        )

    @pytest.mark.anyio
    async def test_initial_command_error(self):
        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            AsyncMock(return_value="/exit"),
            agent=agent,
            initial_command="do stuff",
            extra_patches={
                "code_puppy.prompt_runner.get_current_agent": MagicMock(
                    return_value=agent
                ),
                "code_puppy.interactive_runner.run_prompt_with_attachments": AsyncMock(
                    side_effect=RuntimeError("fail")
                ),
            },
        )

    @pytest.mark.anyio
    async def test_initial_command_returns_none(self):
        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            AsyncMock(return_value="/exit"),
            agent=agent,
            initial_command="do stuff",
            extra_patches={
                "code_puppy.prompt_runner.get_current_agent": MagicMock(
                    return_value=agent
                ),
                "code_puppy.interactive_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(None, MagicMock())
                ),
            },
        )

    @pytest.mark.anyio
    async def test_autosave_load_non_tty(self):
        fake_input = _scripted_input("/autosave_load")

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdout = MagicMock()
        mock_stdout.isatty.return_value = False

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.command_line.command_handler.handle_command": MagicMock(
                    return_value="__AUTOSAVE_LOAD__"
                ),
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("/autosave_load")
                ),
                "sys.stdin": mock_stdin,
                "sys.stdout": mock_stdout,
            },
        )

    @pytest.mark.anyio
    async def test_autosave_load_tty_cancelled(self):
        fake_input = _scripted_input("/autosave_load")

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        mock_stdout = MagicMock()
        mock_stdout.isatty.return_value = True

        with patch.dict(os.environ, {"CODE_PUPPY_NO_TUI": ""}, clear=False):
            await _run_interactive(
                _mock_renderer(),
                _interactive_patches(),
                fake_input,
                extra_patches={
                    "code_puppy.command_line.command_handler.handle_command": MagicMock(
                        return_value="__AUTOSAVE_LOAD__"
                    ),
                    "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                        return_value=_mock_parse_result("/autosave_load")
                    ),
                    "sys.stdin": mock_stdin,
                    "sys.stdout": mock_stdout,
                    "code_puppy.command_line.autosave_menu.interactive_autosave_picker": AsyncMock(
                        return_value=None
                    ),
                },
            )

    @pytest.mark.anyio
    async def test_autosave_load_tty_success(self):
        fake_input = _scripted_input("/autosave_load")

        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"
        agent.estimate_tokens_for_message.return_value = 10

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        mock_stdout = MagicMock()
        mock_stdout.isatty.return_value = True

        with patch.dict(os.environ, {"CODE_PUPPY_NO_TUI": ""}, clear=False):
            await _run_interactive(
                _mock_renderer(),
                _interactive_patches(),
                fake_input,
                agent=agent,
                extra_patches={
                    "code_puppy.command_line.command_handler.handle_command": MagicMock(
                        return_value="__AUTOSAVE_LOAD__"
                    ),
                    "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                        return_value=_mock_parse_result("/autosave_load")
                    ),
                    "sys.stdin": mock_stdin,
                    "sys.stdout": mock_stdout,
                    "code_puppy.command_line.autosave_menu.interactive_autosave_picker": AsyncMock(
                        return_value="my-session"
                    ),
                    "code_puppy.session_storage.load_session": MagicMock(
                        return_value=[MagicMock()]
                    ),
                    "code_puppy.config.set_current_autosave_from_session_name": MagicMock(),
                    "code_puppy.command_line.autosave_menu.display_resumed_history": MagicMock(),
                    "code_puppy.prompt_runner.get_current_agent": MagicMock(
                        return_value=agent
                    ),
                },
            )

    @pytest.mark.anyio
    async def test_autosave_load_damaged_session_changes_nothing(self, tmp_path):
        """Repeated /resume of a damaged file names it and leaves all state alone."""
        from code_puppy.config import get_current_session_name

        session_file = tmp_path / "damaged.json"
        session_file.write_bytes(b'{"format": 2, "messages": ["\n"]}')
        original = session_file.read_bytes()
        session_before = get_current_session_name()
        agent = MagicMock()
        agent.get_user_prompt.return_value = "task:"
        tty = MagicMock()
        tty.isatty.return_value = True
        mock_emit_error = MagicMock()

        with patch.dict(os.environ, {"CODE_PUPPY_NO_TUI": ""}, clear=False):
            await _run_interactive(
                _mock_renderer(),
                _interactive_patches(),
                _scripted_input("/resume", "/resume"),
                agent=agent,
                extra_patches={
                    "code_puppy.command_line.command_handler.handle_command": MagicMock(
                        return_value="__AUTOSAVE_LOAD__"
                    ),
                    "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                        return_value=_mock_parse_result("/resume")
                    ),
                    "sys.stdin": tty,
                    "sys.stdout": tty,
                    "code_puppy.interactive_runner.AUTOSAVE_DIR": str(tmp_path),
                    "code_puppy.command_line.autosave_menu.interactive_autosave_picker": AsyncMock(
                        return_value="damaged"
                    ),
                    "code_puppy.messaging.emit_error": mock_emit_error,
                },
            )

        failures = [
            str(c.args[0])
            for c in mock_emit_error.call_args_list
            if str(session_file) in str(c.args[0])
            and "Invalid control character" in str(c.args[0])
        ]
        assert len(failures) == 2
        agent.set_message_history.assert_not_called()
        assert get_current_session_name() == session_before
        assert session_file.read_bytes() == original

    @pytest.mark.anyio
    async def test_autosave_load_non_tty_warns_instead_of_prompting(self):
        """Non-TTY /autosave_load points at -r NAME instead of prompting."""
        fake_input = _scripted_input("/autosave_load")

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        mock_stdout = MagicMock()
        mock_stdout.isatty.return_value = False

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.command_line.command_handler.handle_command": MagicMock(
                    return_value="__AUTOSAVE_LOAD__"
                ),
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("/autosave_load")
                ),
                "sys.stdin": mock_stdin,
                "sys.stdout": mock_stdout,
            },
        )

    @pytest.mark.anyio
    async def test_slash_command_returns_false(self):
        """Command returns False = not recognized, fall through."""
        fake_input = _scripted_input("/unknown")

        mock_result = MagicMock(output="ok")
        mock_result.all_messages.return_value = []

        await _run_interactive(
            _mock_renderer(),
            _interactive_patches(),
            fake_input,
            extra_patches={
                "code_puppy.command_line.command_handler.handle_command": MagicMock(
                    return_value=False
                ),
                "code_puppy.interactive_runner.parse_prompt_attachments": MagicMock(
                    return_value=_mock_parse_result("/unknown")
                ),
                "code_puppy.interactive_runner.run_prompt_with_attachments": AsyncMock(
                    return_value=(mock_result, MagicMock())
                ),
            },
        )
