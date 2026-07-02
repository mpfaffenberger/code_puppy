"""Tests for the Phase A persistent prompt (bottom bar = THE prompt).

Covers: idle-vs-running submission routing, Ctrl+D EOF semantics,
run-active flag toggling across consecutive runs, non-TTY degrade,
classic-flag fallback, cancel-hotkey arming, and the transcript echo in
the interactive loop's persistent branch.
"""

import asyncio
import io
import os
from unittest.mock import patch

import pytest

import code_puppy.messaging.run_ui as run_ui_mod
from code_puppy.agents import _key_listeners
from code_puppy.messaging import bottom_bar as bottom_bar_mod
from code_puppy.messaging.pause_controller import (
    get_pause_controller,
    reset_pause_controller,
)


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


class FakePipe(io.StringIO):
    def isatty(self):
        return False


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    # Never let tests spawn a REAL cbreak stdin listener.
    monkeypatch.setattr(run_ui_mod, "_spawn_persistent_listener", lambda: None)
    run_ui_mod.stop_persistent_ui()
    run_ui_mod.stop_run_ui()
    reset_pause_controller()
    yield
    run_ui_mod.stop_persistent_ui()
    run_ui_mod.stop_run_ui()
    reset_pause_controller()
    _key_listeners.set_cancel_handler(None)
    bottom_bar_mod.reset_bottom_bar()


def install_tty_bar():
    bottom_bar_mod.reset_bottom_bar()
    tty = FakeTTY()
    bottom_bar_mod._bottom_bar = bottom_bar_mod.BottomBar(
        stream=tty, get_size=lambda: (80, 24)
    )
    return tty


def feed_line(editor, text):
    for ch in text:
        editor.feed(ch)
    editor.feed("\r")


# =========================================================================
# Persistent lifecycle
# =========================================================================


async def test_start_persistent_ui_builds_editor_and_is_idempotent():
    install_tty_bar()
    assert run_ui_mod.start_persistent_ui(prompt_prefix=">> ") is True
    editor = run_ui_mod.get_run_editor()
    assert editor is not None
    assert run_ui_mod.is_persistent() is True
    assert run_ui_mod.is_run_active() is False
    assert run_ui_mod.start_persistent_ui() is True  # idempotent
    assert run_ui_mod.get_run_editor() is editor


async def test_non_tty_degrades_to_classic():
    bottom_bar_mod.reset_bottom_bar()
    bottom_bar_mod._bottom_bar = bottom_bar_mod.BottomBar(
        stream=FakePipe(), get_size=lambda: (80, 24)
    )
    assert run_ui_mod.start_persistent_ui() is False
    assert run_ui_mod.is_persistent() is False
    assert run_ui_mod.get_run_editor() is None


async def test_run_ui_toggles_run_active_but_keeps_editor():
    install_tty_bar()
    run_ui_mod.start_persistent_ui()
    editor = run_ui_mod.get_run_editor()

    # Two consecutive "runs": editor + bar survive both.
    for _ in range(2):
        assert run_ui_mod.start_run_ui() is editor
        assert run_ui_mod.is_run_active() is True
        run_ui_mod.stop_run_ui()
        assert run_ui_mod.is_run_active() is False
        assert run_ui_mod.get_run_editor() is editor
        assert bottom_bar_mod.get_bottom_bar().is_active() is True


async def test_stop_persistent_ui_full_teardown():
    install_tty_bar()
    run_ui_mod.start_persistent_ui()
    run_ui_mod.stop_persistent_ui()
    assert run_ui_mod.is_persistent() is False
    assert run_ui_mod.get_run_editor() is None
    assert bottom_bar_mod.get_bottom_bar().is_active() is False


# =========================================================================
# Submission routing: idle -> new turn, running -> steer / slash drain
# =========================================================================


async def test_idle_submission_becomes_repl_line():
    install_tty_bar()
    run_ui_mod.start_persistent_ui()
    editor = run_ui_mod.get_run_editor()
    feed_line(editor, "write me a haiku")
    task = await asyncio.wait_for(run_ui_mod.wait_for_idle_submission(), 2.0)
    assert task == "write me a haiku"
    # NOT a steer: the pause controller queues stay empty.
    assert get_pause_controller().has_pending_steer() is False


async def test_idle_slash_goes_to_repl_not_drain_queue():
    install_tty_bar()
    run_ui_mod.start_persistent_ui()
    editor = run_ui_mod.get_run_editor()
    feed_line(editor, "/help")
    task = await asyncio.wait_for(run_ui_mod.wait_for_idle_submission(), 2.0)
    assert task == "/help"
    assert editor.get_pending_command() is None  # drain queue untouched


async def test_running_submission_queues_by_default():
    install_tty_bar()
    run_ui_mod.start_persistent_ui()
    editor = run_ui_mod.get_run_editor()
    run_ui_mod.start_run_ui()
    feed_line(editor, "focus on the tests")
    pc = get_pause_controller()
    # Enter mid-run QUEUES (next turn); nothing lands in the now-queue.
    assert pc.drain_pending_steer_now() == []
    assert pc.drain_pending_steer_queued() == ["focus on the tests"]


async def test_running_steer_command_injects_now():
    install_tty_bar()
    run_ui_mod.start_persistent_ui()
    editor = run_ui_mod.get_run_editor()
    run_ui_mod.start_run_ui()
    feed_line(editor, "/steer focus on the tests")
    pc = get_pause_controller()
    # /steer fast path: straight to the now-queue, no drain, no pause.
    assert pc.drain_pending_steer_now() == ["focus on the tests"]
    assert editor.get_pending_command() is None


async def test_running_slash_goes_to_drain_queue():
    install_tty_bar()
    run_ui_mod.start_persistent_ui()
    editor = run_ui_mod.get_run_editor()
    run_ui_mod.start_run_ui()
    feed_line(editor, "/status")
    assert editor.get_pending_command() == "/status"
    assert get_pause_controller().has_pending_steer() is False


async def test_routing_flips_back_after_run_ends():
    install_tty_bar()
    run_ui_mod.start_persistent_ui()
    editor = run_ui_mod.get_run_editor()
    run_ui_mod.start_run_ui()
    run_ui_mod.stop_run_ui()
    feed_line(editor, "back to idle")
    task = await asyncio.wait_for(run_ui_mod.wait_for_idle_submission(), 2.0)
    assert task == "back to idle"


# =========================================================================
# Ctrl+D EOF semantics
# =========================================================================


async def test_ctrl_d_on_empty_buffer_raises_eof():
    install_tty_bar()
    run_ui_mod.start_persistent_ui()
    editor = run_ui_mod.get_run_editor()
    editor.feed("\x04")
    with pytest.raises(EOFError):
        await asyncio.wait_for(run_ui_mod.wait_for_idle_submission(), 2.0)


async def test_ctrl_d_with_text_is_ignored():
    install_tty_bar()
    run_ui_mod.start_persistent_ui()
    editor = run_ui_mod.get_run_editor()
    for ch in "draft":
        editor.feed(ch)
    editor.feed("\x04")
    assert editor.buffer == "draft"  # untouched, no EOF queued
    editor.feed("\r")
    task = await asyncio.wait_for(run_ui_mod.wait_for_idle_submission(), 2.0)
    assert task == "draft"


async def test_ctrl_d_during_run_is_ignored():
    install_tty_bar()
    run_ui_mod.start_persistent_ui()
    editor = run_ui_mod.get_run_editor()
    run_ui_mod.start_run_ui()
    editor.feed("\x04")  # must NOT queue an EOF for later
    run_ui_mod.stop_run_ui()
    feed_line(editor, "still alive")
    task = await asyncio.wait_for(run_ui_mod.wait_for_idle_submission(), 2.0)
    assert task == "still alive"  # no EOF sneaked in ahead of it


# =========================================================================
# Ctrl+C-at-idle buffer clear (SIGINT guard hook)
# =========================================================================


async def test_clear_idle_buffer_wipes_typed_text():
    install_tty_bar()
    run_ui_mod.start_persistent_ui()
    editor = run_ui_mod.get_run_editor()
    for ch in "oops":
        editor.feed(ch)
    run_ui_mod.clear_idle_buffer()
    assert editor.buffer == ""


async def test_clear_idle_buffer_noop_during_run():
    install_tty_bar()
    run_ui_mod.start_persistent_ui()
    editor = run_ui_mod.get_run_editor()
    run_ui_mod.start_run_ui()
    for ch in "steer draft":
        editor.feed(ch)
    run_ui_mod.clear_idle_buffer()
    assert editor.buffer == "steer draft"  # per-run handlers own Ctrl+C


# =========================================================================
# Per-run cancel hotkey arming (persistent listener semantics)
# =========================================================================


def test_cancel_hotkey_flips_across_two_runs():
    fired = []
    # Run 1: armed -> dispatch fires the handler.
    _key_listeners.set_cancel_handler(lambda: fired.append(1))
    _key_listeners._dispatch_key("\x0b", lambda: None, "\x0b", None)
    assert fired == [1]
    # Between runs: disarmed -> cancel key is inert AND not fed anywhere.
    _key_listeners.set_cancel_handler(None)
    _key_listeners._dispatch_key("\x0b", lambda: None, "\x0b", None)
    assert fired == [1]
    # Run 2: re-armed -> fires again.
    _key_listeners.set_cancel_handler(lambda: fired.append(2))
    _key_listeners._dispatch_key("\x0b", lambda: None, "\x0b", None)
    assert fired == [1, 2]


# =========================================================================
# Classic-flag / non-TTY fallback selection
# =========================================================================


def test_classic_env_flag_selects_old_path(monkeypatch):
    from code_puppy.cli_runner import _use_persistent_prompt

    monkeypatch.setattr("sys.stdin", FakeTTY())
    monkeypatch.setattr("sys.stdout", FakeTTY())
    with patch.dict(os.environ, {"CODE_PUPPY_CLASSIC_PROMPT": "1"}):
        assert _use_persistent_prompt() is False


def test_no_tui_env_selects_old_path(monkeypatch):
    from code_puppy.cli_runner import _use_persistent_prompt

    monkeypatch.setattr("sys.stdin", FakeTTY())
    monkeypatch.setattr("sys.stdout", FakeTTY())
    with patch.dict(os.environ, {"CODE_PUPPY_NO_TUI": "1"}):
        assert _use_persistent_prompt() is False


def test_non_tty_selects_old_path(monkeypatch):
    from code_puppy.cli_runner import _use_persistent_prompt

    monkeypatch.setattr("sys.stdin", FakePipe())
    monkeypatch.setattr("sys.stdout", FakePipe())
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("CODE_PUPPY_CLASSIC_PROMPT", None)
        assert _use_persistent_prompt() is False


def test_tty_without_flags_selects_new_path(monkeypatch):
    from code_puppy.cli_runner import _use_persistent_prompt

    monkeypatch.setattr("sys.stdin", FakeTTY())
    monkeypatch.setattr("sys.stdout", FakeTTY())
    monkeypatch.delenv("CODE_PUPPY_CLASSIC_PROMPT", raising=False)
    monkeypatch.delenv("CODE_PUPPY_NO_TUI", raising=False)
    assert _use_persistent_prompt() is True
