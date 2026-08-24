"""Double-Ctrl+C-to-quit at the idle prompt (mirrors Ctrl+D).

Covers all three arrival paths:

- persistent mode via SIGINT   -> run_ui.note_idle_ctrl_c
- persistent mode via raw \\x03 -> line_editor ctrl_c handler -> run_ui
- classic prompt_toolkit mode  -> cli_runner's KeyboardInterrupt branch

Escape / Ctrl+X raise the same KeyboardInterrupt as a real Ctrl+C on the
classic path but must never trigger the quit (they mark themselves via
mark_non_ctrl_c_cancel).
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

import code_puppy.cli_runner as cli_runner
import code_puppy.messaging.run_ui as run_ui
from code_puppy.command_line.prompt_toolkit_completion import (
    mark_non_ctrl_c_cancel,
    pop_non_ctrl_c_cancel,
)
from code_puppy.messaging.line_editor import RunningLineEditor


# ---------------------------------------------------------------------------
# run_ui.note_idle_ctrl_c (persistent mode, SIGINT + raw paths converge here)
# ---------------------------------------------------------------------------


@pytest.fixture
def idle_persistent(monkeypatch):
    """Force idle persistent-mode state with the side effects spied."""
    monkeypatch.setattr(run_ui, "_persistent", True)
    monkeypatch.setattr(run_ui, "_run_active", False)
    monkeypatch.setattr(run_ui, "_last_idle_ctrl_c", 0.0)
    cleared = []
    pushed = []
    monkeypatch.setattr(run_ui, "clear_idle_buffer", lambda: cleared.append(True))
    monkeypatch.setattr(run_ui, "_push_idle", lambda item: pushed.append(item))
    monkeypatch.setattr(run_ui, "get_bottom_bar", MagicMock())
    return cleared, pushed


def test_single_ctrl_c_clears_and_arms(idle_persistent):
    cleared, pushed = idle_persistent
    assert run_ui.note_idle_ctrl_c(now=100.0) is False
    assert cleared and not pushed


def test_double_ctrl_c_within_window_quits(idle_persistent):
    _, pushed = idle_persistent
    assert run_ui.note_idle_ctrl_c(now=100.0) is False
    assert run_ui.note_idle_ctrl_c(now=100.4) is True
    assert pushed == [run_ui._EOF]


def test_double_ctrl_c_after_window_does_not_quit(idle_persistent):
    _, pushed = idle_persistent
    assert run_ui.note_idle_ctrl_c(now=100.0) is False
    assert run_ui.note_idle_ctrl_c(now=100.6) is False
    assert not pushed


def test_quit_resets_the_arm(idle_persistent):
    """The press that quits must not leave a live timestamp behind."""
    _, pushed = idle_persistent
    run_ui.note_idle_ctrl_c(now=100.0)
    assert run_ui.note_idle_ctrl_c(now=100.4) is True
    # A hypothetical third press right after must re-arm, not double-quit.
    assert run_ui.note_idle_ctrl_c(now=100.5) is False
    assert pushed == [run_ui._EOF]


def test_ctrl_c_ignored_while_run_active(idle_persistent, monkeypatch):
    cleared, pushed = idle_persistent
    monkeypatch.setattr(run_ui, "_run_active", True)
    assert run_ui.note_idle_ctrl_c(now=100.0) is False
    assert run_ui.note_idle_ctrl_c(now=100.1) is False
    assert not cleared and not pushed


def test_ctrl_c_ignored_in_classic_mode(idle_persistent, monkeypatch):
    cleared, pushed = idle_persistent
    monkeypatch.setattr(run_ui, "_persistent", False)
    assert run_ui.note_idle_ctrl_c(now=100.0) is False
    assert not cleared and not pushed


# ---------------------------------------------------------------------------
# Raw-\x03 path (Windows clamp): editor delegates to the installed handler
# ---------------------------------------------------------------------------


def test_editor_raw_ctrl_c_uses_installed_handler():
    editor = RunningLineEditor(bar=MagicMock())
    calls = []
    editor.set_ctrl_c_handler(lambda: calls.append(True))
    editor._buffer = "half-typed"
    editor._feed_one("\x03")
    assert calls == [True]
    # Policy moved to the handler; the editor must not also wipe the buffer.
    assert editor._buffer == "half-typed"


def test_editor_raw_ctrl_c_without_handler_clears_buffer():
    editor = RunningLineEditor(bar=MagicMock())
    editor._buffer = "half-typed"
    editor._feed_one("\x03")
    assert editor._buffer == ""


def test_handle_raw_ctrl_c_idle_delegates_to_note(monkeypatch):
    noted = []
    monkeypatch.setattr(run_ui, "_persistent", True)
    monkeypatch.setattr(run_ui, "_run_active", False)
    monkeypatch.setattr(run_ui, "note_idle_ctrl_c", lambda: noted.append(True))
    run_ui._handle_raw_ctrl_c()
    assert noted == [True]


def test_handle_raw_ctrl_c_mid_run_only_clears(monkeypatch):
    editor = MagicMock()
    monkeypatch.setattr(run_ui, "_persistent", True)
    monkeypatch.setattr(run_ui, "_run_active", True)
    monkeypatch.setattr(run_ui, "get_run_editor", lambda: editor)
    noted = []
    monkeypatch.setattr(run_ui, "note_idle_ctrl_c", lambda: noted.append(True))
    run_ui._handle_raw_ctrl_c()
    editor.clear_buffer.assert_called_once()
    assert not noted


# ---------------------------------------------------------------------------
# Classic prompt_toolkit mode: the REPL's KeyboardInterrupt branch
# ---------------------------------------------------------------------------


class _FakeTime:
    """Deterministic stand-in for cli_runner's ``time`` module."""

    def __init__(self, values):
        self._values = list(values)

    def monotonic(self):
        return self._values.pop(0) if self._values else 1e9


@pytest.fixture
def renderer():
    r = MagicMock()
    r.console = MagicMock()
    return r


def _force_classic(monkeypatch):
    monkeypatch.setattr(cli_runner, "_use_persistent_prompt", lambda: True)
    monkeypatch.setattr(
        "code_puppy.messaging.run_ui.start_persistent_ui",
        lambda prompt_prefix=None, prefix_sgrs=None: False,
    )
    monkeypatch.setattr(cli_runner, "print_truecolor_warning", lambda console: None)
    monkeypatch.setattr(cli_runner, "record_terminal_session", lambda *a, **k: None)


@pytest.mark.asyncio
async def test_classic_double_ctrl_c_quits(monkeypatch, renderer):
    _force_classic(monkeypatch)
    pop_non_ctrl_c_cancel()  # hygiene: never inherit a stale marker
    monkeypatch.setattr(cli_runner, "time", _FakeTime([100.0, 100.3]))

    async def fake_classic_input(*a, **k):
        raise KeyboardInterrupt

    successes = []
    with (
        patch(
            "code_puppy.command_line.prompt_toolkit_completion.get_input_with_combined_completion",
            fake_classic_input,
        ),
        patch("code_puppy.messaging.emit_info", lambda msg, **k: None),
        patch("code_puppy.messaging.emit_warning", lambda msg, **k: None),
        patch(
            "code_puppy.messaging.emit_success",
            lambda msg, **k: successes.append(str(msg)),
        ),
    ):
        await asyncio.wait_for(
            cli_runner.interactive_mode(renderer, initial_command=None), 10.0
        )

    assert any("Ctrl+D" in s for s in successes)  # exited via the quit path


@pytest.mark.asyncio
async def test_classic_slow_ctrl_c_taps_do_not_quit(monkeypatch, renderer):
    _force_classic(monkeypatch)
    pop_non_ctrl_c_cancel()
    # Two taps 0.6 s apart, then /exit ends the loop normally.
    monkeypatch.setattr(cli_runner, "time", _FakeTime([100.0, 100.6]))
    events = iter([KeyboardInterrupt, KeyboardInterrupt, "/exit"])

    async def fake_classic_input(*a, **k):
        item = next(events)
        if item is KeyboardInterrupt:
            raise KeyboardInterrupt
        return item

    successes = []
    with (
        patch(
            "code_puppy.command_line.prompt_toolkit_completion.get_input_with_combined_completion",
            fake_classic_input,
        ),
        patch("code_puppy.messaging.emit_info", lambda msg, **k: None),
        patch("code_puppy.messaging.emit_warning", lambda msg, **k: None),
        patch(
            "code_puppy.messaging.emit_success",
            lambda msg, **k: successes.append(str(msg)),
        ),
    ):
        await asyncio.wait_for(
            cli_runner.interactive_mode(renderer, initial_command=None), 10.0
        )

    assert not any("Ctrl+D" in s for s in successes)  # quit came from /exit


@pytest.mark.asyncio
async def test_classic_double_escape_never_quits(monkeypatch, renderer):
    """Escape marks itself non-Ctrl+C; two fast Escapes must not exit."""
    _force_classic(monkeypatch)
    pop_non_ctrl_c_cancel()
    monkeypatch.setattr(cli_runner, "time", _FakeTime([100.0, 100.1]))
    events = iter(["esc", "esc", "/exit"])

    async def fake_classic_input(*a, **k):
        item = next(events)
        if item == "esc":
            mark_non_ctrl_c_cancel()  # what the Escape keybinding does
            raise KeyboardInterrupt
        return item

    successes = []
    with (
        patch(
            "code_puppy.command_line.prompt_toolkit_completion.get_input_with_combined_completion",
            fake_classic_input,
        ),
        patch("code_puppy.messaging.emit_info", lambda msg, **k: None),
        patch("code_puppy.messaging.emit_warning", lambda msg, **k: None),
        patch(
            "code_puppy.messaging.emit_success",
            lambda msg, **k: successes.append(str(msg)),
        ),
    ):
        await asyncio.wait_for(
            cli_runner.interactive_mode(renderer, initial_command=None), 10.0
        )

    assert not any("Ctrl+D" in s for s in successes)


def test_cancel_source_marker_round_trip():
    assert pop_non_ctrl_c_cancel() is False
    mark_non_ctrl_c_cancel()
    assert pop_non_ctrl_c_cancel() is True
    assert pop_non_ctrl_c_cancel() is False
