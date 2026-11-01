"""Shell approval gate: an installed approval backend must work without a TTY."""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from code_puppy.tools import command_runner
from code_puppy.tools.common import (
    can_prompt_for_approval,
    set_approval_backend,
)
from code_puppy.tools.command_runner import ShellCommandOutput
from code_puppy.tools.file_permission_state import PermissionNotDecided
from code_puppy.tools.subagent_context import subagent_context

REJECTED = "User rejected the command!"


class _FakeStdin:
    def __init__(self, tty: bool):
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.fixture(autouse=True)
def _no_backend_leak():
    set_approval_backend(None)
    yield
    set_approval_backend(None)


@pytest.fixture
def executor(monkeypatch):
    run = AsyncMock(
        return_value=ShellCommandOutput(
            success=True,
            command="echo hi",
            stdout="hi\n",
            stderr="",
            exit_code=0,
            execution_time=0.0,
        )
    )
    monkeypatch.setattr(command_runner, "_execute_shell_command", run)
    monkeypatch.setattr(
        "code_puppy.callbacks.on_run_shell_command", AsyncMock(return_value=[])
    )
    return run


# Default yolo_mode is True (config.get_yolo_mode), which skips the gate entirely.
@pytest.fixture(autouse=True)
def set_yolo(monkeypatch):
    def _set(enabled: bool):
        monkeypatch.setattr("code_puppy.config.get_yolo_mode", lambda: enabled)

    _set(False)
    return _set


@pytest.fixture
def non_tty(monkeypatch):
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty=False))


async def _run_echo():
    return await command_runner.run_shell_command(MagicMock(), "echo hi")


@pytest.mark.parametrize(
    "approved, feedback, expect_executed, expected_error",
    [
        (True, None, True, None),
        (False, None, False, REJECTED),
        (False, "too risky", False, "USER REJECTED: too risky"),
    ],
    ids=["approve-executes", "reject-returns-rejection", "reject-with-feedback"],
)
async def test_backend_gates_shell_command_without_tty(
    non_tty, executor, approved, feedback, expect_executed, expected_error
):
    backend = MagicMock(return_value=(approved, feedback))
    set_approval_backend(backend)

    result = await _run_echo()

    backend.assert_called_once()
    title, message, _preview = backend.call_args.args
    assert title == "Shell Command"
    assert "echo hi" in message
    assert executor.await_count == (1 if expect_executed else 0)
    if expected_error:
        assert result.success is False
        assert result.error == expected_error
    else:
        assert result.success is True


async def test_not_decided_denial_is_not_reported_as_user_rejection(non_tty, executor):
    set_approval_backend(
        MagicMock(return_value=(False, PermissionNotDecided("Request cancelled.")))
    )

    result = await _run_echo()

    assert executor.await_count == 0
    assert result.success is False
    assert result.error == (
        "PERMISSION NOT GRANTED: Request cancelled. The command was not run. "
        "The user did not reject it; do not say they did."
    )
    assert "USER REJECTED" not in result.error
    assert result.user_feedback is None


@pytest.mark.parametrize(
    "yolo, in_subagent",
    [(True, False), (False, True)],
    ids=["yolo-skips-prompt", "subagent-skips-prompt"],
)
async def test_backend_not_consulted_when_gate_is_skipped(
    non_tty, executor, set_yolo, yolo, in_subagent
):
    backend = MagicMock(return_value=(False, None))
    set_approval_backend(backend)
    set_yolo(yolo)

    if in_subagent:
        with subagent_context("test-agent"):
            result = await _run_echo()
    else:
        result = await _run_echo()

    backend.assert_not_called()
    assert executor.await_count == 1
    assert result.success is True


async def test_no_backend_and_no_tty_runs_without_prompt(
    non_tty, executor, monkeypatch
):
    prompt = AsyncMock()
    monkeypatch.setattr(command_runner, "get_user_approval_async", prompt)

    result = await _run_echo()

    prompt.assert_not_awaited()
    assert executor.await_count == 1
    assert result.success is True


@pytest.mark.parametrize(
    "backend_installed, tty, expected",
    [
        (False, False, False),
        (False, True, True),
        (True, False, True),
        (True, True, True),
    ],
    ids=["none", "tty-only", "backend-only", "backend-and-tty"],
)
def test_can_prompt_for_approval_truth_table(
    monkeypatch, backend_installed, tty, expected
):
    monkeypatch.setattr(sys, "stdin", _FakeStdin(tty=tty))
    if backend_installed:
        set_approval_backend(MagicMock(return_value=(True, None)))

    assert can_prompt_for_approval() is expected
