"""Regression tests: ``-r NAME`` re-renders recent history on interactive resume.

The ``-r``/``--resume`` startup path used to load the saved session into the
agent's context but never paint it, leaving a blank screen after e.g. a
reboot-driven relaunch (tmux-resurrect). Every *other* resume path (``/load``,
``/load_context``, and the interactive autosave picker) calls
``display_resumed_history``; ``-r`` now does too -- but only in interactive
mode (a real TTY and not headless ``-p``) so scripted/piped runs stay quiet.

These tests drive ``cli_runner.main()`` with a fully mocked resume so we assert
purely on whether ``display_resumed_history`` is invoked.
"""

import os
import pathlib
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_renderer():
    r = MagicMock()
    r.console = MagicMock()
    r.console.file = MagicMock()
    r.console.file.flush = MagicMock()
    r.start = MagicMock()
    r.stop = MagicMock()
    return r


def _base_main_patches():
    """Common patches so main() can run without touching the real system."""
    return {
        "code_puppy.cli_runner.find_available_port": MagicMock(return_value=8090),
        "code_puppy.cli_runner.ensure_config_exists": MagicMock(),
        "code_puppy.cli_runner.validate_cancel_agent_key": MagicMock(),
        "code_puppy.cli_runner.initialize_command_history_file": MagicMock(),
        "code_puppy.cli_runner.default_version_mismatch_behavior": MagicMock(),
        "code_puppy.cli_runner.print_truecolor_warning": MagicMock(),
        "code_puppy.cli_runner.reset_unix_terminal": MagicMock(),
        "code_puppy.cli_runner.reset_windows_terminal_ansi": MagicMock(),
        "code_puppy.cli_runner.reset_windows_terminal_full": MagicMock(),
        "code_puppy.cli_runner.callbacks": MagicMock(
            on_startup=AsyncMock(),
            on_shutdown=AsyncMock(),
            on_version_check=AsyncMock(),
            get_callbacks=MagicMock(return_value=[]),
        ),
        "code_puppy.cli_runner.plugins": MagicMock(),
        "code_puppy.config.load_api_keys_to_environment": MagicMock(),
    }


def _resume_patches(mock_display, agent):
    """Patches that make the -r resume block resolve + load a fake session."""
    return {
        "code_puppy.session_lifecycle.resolve_or_create_resume_target": MagicMock(
            return_value=("my-session", pathlib.Path("/tmp/autosaves"), False)
        ),
        "code_puppy.session_storage.load_session": MagicMock(
            return_value=[MagicMock(), MagicMock()]
        ),
        "code_puppy.config.pin_current_session_name": MagicMock(),
        "code_puppy.agents.agent_manager.get_current_agent": MagicMock(
            return_value=agent
        ),
        "code_puppy.command_line.autosave_menu.display_resumed_history": mock_display,
    }


async def _run_main(argv, extra_patches):
    patches = _base_main_patches()
    patches.update(extra_patches)
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {"NO_VERSION_UPDATE": "1"}))
        stack.enter_context(patch("sys.argv", argv))
        stack.enter_context(
            patch(
                "code_puppy.messaging.SynchronousInteractiveRenderer",
                return_value=_mock_renderer(),
            )
        )
        stack.enter_context(
            patch(
                "code_puppy.messaging.RichConsoleRenderer",
                return_value=_mock_renderer(),
            )
        )
        stack.enter_context(
            patch("code_puppy.messaging.get_global_queue", return_value=MagicMock())
        )
        stack.enter_context(
            patch("code_puppy.messaging.get_message_bus", return_value=MagicMock())
        )
        for target, value in patches.items():
            stack.enter_context(patch(target, value))
        from code_puppy.cli_runner import main

        await main()


@pytest.mark.anyio
async def test_resume_interactive_renders_history():
    """-r NAME on an interactive TTY re-renders the recent conversation."""
    mock_inter = AsyncMock()
    mock_display = MagicMock()
    agent = MagicMock()
    agent.estimate_tokens_for_message.return_value = 1
    mock_stdout = MagicMock()
    mock_stdout.isatty.return_value = True

    extra = {
        "code_puppy.cli_runner.interactive_mode": mock_inter,
        "pyfiglet.figlet_format": MagicMock(return_value="LOGO\n\n"),
        "sys.stdout": mock_stdout,
    }
    extra.update(_resume_patches(mock_display, agent))

    await _run_main(["code-puppy", "-r", "my-session"], extra)

    mock_display.assert_called_once()


@pytest.mark.anyio
async def test_resume_headless_skips_history():
    """-r NAME with -p (headless) must NOT dump history to stdout."""
    mock_exec = AsyncMock()
    mock_display = MagicMock()
    agent = MagicMock()
    agent.estimate_tokens_for_message.return_value = 1
    mock_stdout = MagicMock()
    mock_stdout.isatty.return_value = True  # even on a TTY, -p suppresses it

    extra = {
        "code_puppy.cli_runner.execute_single_prompt": mock_exec,
        "sys.stdout": mock_stdout,
    }
    extra.update(_resume_patches(mock_display, agent))

    await _run_main(["code-puppy", "-r", "my-session", "-p", "hi"], extra)

    mock_display.assert_not_called()
