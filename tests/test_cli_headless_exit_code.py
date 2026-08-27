"""Headless ``-p`` runs must report failure to the shell.

Regression coverage for a headless run that printed an error and still exited
0. ``code-puppy -p "..." && next-step`` ran ``next-step`` after the agent had
done nothing, because ``execute_single_prompt`` swallowed the exception and
returned ``None`` (which ``main_entry`` maps to exit status 0).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.cli_runner import execute_single_prompt


def _headless_patches(agent, run_result):
    """Patch set matching tests/test_cli_usage_file.py's harness."""
    return (
        patch(
            "code_puppy.command_line.shell_passthrough.is_shell_passthrough",
            return_value=False,
        ),
        patch(
            "code_puppy.cli_runner.parse_prompt_attachments",
            return_value=SimpleNamespace(prompt="do it"),
        ),
        patch("code_puppy.cli_runner.get_current_agent", return_value=agent),
        patch(
            "code_puppy.cli_runner.run_prompt_with_attachments",
            new=run_result,
        ),
        patch("code_puppy.messaging.get_message_bus"),
        patch("code_puppy.session_lifecycle.persist_named_session"),
        patch("code_puppy.config.record_quick_resume_sessions"),
    )


@pytest.mark.anyio
async def test_agent_failure_returns_nonzero():
    """An exception during the agent run must surface as exit code 1."""
    agent = MagicMock()
    renderer = MagicMock()
    boom = AsyncMock(side_effect=RuntimeError("No valid model could be loaded."))

    p1, p2, p3, p4, p5, p6, p7 = _headless_patches(agent, boom)
    with p1, p2, p3, p4, p5, p6, p7:
        rc = await execute_single_prompt("do it", renderer)

    assert rc == 1, "a failed headless run must not report success to the shell"


@pytest.mark.anyio
async def test_successful_run_returns_zero():
    """The success path keeps exit code 0."""
    result = MagicMock(output="done")
    result.usage = SimpleNamespace()
    result.all_messages.return_value = []
    agent = MagicMock()
    renderer = MagicMock()
    ok = AsyncMock(return_value=(result, MagicMock()))

    p1, p2, p3, p4, p5, p6, p7 = _headless_patches(agent, ok)
    with p1, p2, p3, p4, p5, p6, p7:
        rc = await execute_single_prompt("do it", renderer)

    assert rc == 0


@pytest.mark.anyio
async def test_cancellation_keeps_zero_status():
    """Cancellation is not an error; it keeps its previous 0 status.

    Pinned deliberately: this fix narrowed itself to paths that emit an
    *error*. If the maintainer decides a cancelled headless run should also be
    non-zero (e.g. 130), this is the test to change on purpose rather than by
    accident.
    """
    agent = MagicMock()
    renderer = MagicMock()
    cancelled = AsyncMock(side_effect=__import__("asyncio").CancelledError())

    p1, p2, p3, p4, p5, p6, p7 = _headless_patches(agent, cancelled)
    with p1, p2, p3, p4, p5, p6, p7:
        rc = await execute_single_prompt("do it", renderer)

    assert rc == 0


@pytest.mark.anyio
async def test_failing_slash_command_returns_nonzero():
    """A slash command that raises is also an error path that returned 0."""
    renderer = MagicMock()

    with (
        patch(
            "code_puppy.command_line.shell_passthrough.is_shell_passthrough",
            return_value=False,
        ),
        patch(
            "code_puppy.cli_runner.parse_prompt_attachments",
            return_value=SimpleNamespace(prompt="/bogus"),
        ),
        patch(
            "code_puppy.command_line.command_handler.handle_command",
            side_effect=RuntimeError("nope"),
        ),
    ):
        rc = await execute_single_prompt("/bogus", renderer)

    assert rc == 1


@pytest.mark.anyio
async def test_handled_slash_command_returns_zero():
    """A slash command handled without an agent run is a success."""
    renderer = MagicMock()

    with (
        patch(
            "code_puppy.command_line.shell_passthrough.is_shell_passthrough",
            return_value=False,
        ),
        patch(
            "code_puppy.cli_runner.parse_prompt_attachments",
            return_value=SimpleNamespace(prompt="/help"),
        ),
        patch(
            "code_puppy.command_line.command_handler.handle_command",
            return_value=True,
        ),
    ):
        rc = await execute_single_prompt("/help", renderer)

    assert rc == 0


def test_no_model_error_names_a_real_command():
    """The stuck-user error must not name a command that does not exist.

    ``config set`` was never a registered command; the real ones are
    ``/add_model`` and ``/model``. Telling a blocked user to run a
    non-existent command is worse than saying nothing.
    """
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "code_puppy" / "agents" / "_builder.py"
    )
    text = source.read_text(encoding="utf-8")

    assert "`config set`" not in text, "config set is not a real command"
    assert "/add_model" in text
