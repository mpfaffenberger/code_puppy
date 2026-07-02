"""Tests for code_puppy.messaging.run_ui — the composed run-time UI.

Covers: start/stop idempotency, non-TTY degradation, key-listener feed
registration, run_ui() exception safety, and suspended_run_ui() nesting.
"""

import io

import pytest

import code_puppy.messaging.run_ui as run_ui_mod
from code_puppy.agents import _key_listeners
from code_puppy.messaging import bottom_bar as bottom_bar_mod


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


class FakePipe(io.StringIO):
    def isatty(self):
        return False


@pytest.fixture(autouse=True)
def clean_run_ui_state():
    """Every test starts and ends with no editor + no feed target."""
    run_ui_mod.stop_run_ui()
    _key_listeners.set_line_editor(None)
    yield
    run_ui_mod.stop_run_ui()
    _key_listeners.set_line_editor(None)


def install_bar(stream):
    """Install a fresh global BottomBar bound to ``stream``."""
    bottom_bar_mod.reset_bottom_bar()
    bar = bottom_bar_mod.BottomBar(stream=stream, get_size=lambda: (80, 24))
    bottom_bar_mod._bottom_bar = bar
    return bar


@pytest.fixture
def tty_bar():
    tty = FakeTTY()
    bar = install_bar(tty)
    yield bar, tty
    bottom_bar_mod.reset_bottom_bar()


@pytest.fixture
def pipe_bar():
    pipe = FakePipe()
    bar = install_bar(pipe)
    yield bar, pipe
    bottom_bar_mod.reset_bottom_bar()


# =========================================================================
# start / stop
# =========================================================================


def test_start_creates_editor_and_registers_feed_target(tty_bar):
    bar, _tty = tty_bar
    editor = run_ui_mod.start_run_ui()
    assert editor is not None
    assert bar.is_active() is True
    assert _key_listeners.get_line_editor() is editor
    assert run_ui_mod.get_run_editor() is editor


def test_start_is_idempotent(tty_bar):
    editor1 = run_ui_mod.start_run_ui()
    editor2 = run_ui_mod.start_run_ui()
    assert editor1 is editor2


def test_stop_unregisters_and_stops_bar(tty_bar):
    bar, _tty = tty_bar
    run_ui_mod.start_run_ui()
    run_ui_mod.stop_run_ui()
    assert bar.is_active() is False
    assert _key_listeners.get_line_editor() is None
    assert run_ui_mod.get_run_editor() is None


def test_stop_is_idempotent(tty_bar):
    run_ui_mod.start_run_ui()
    run_ui_mod.stop_run_ui()
    run_ui_mod.stop_run_ui()  # must not raise
    assert run_ui_mod.get_run_editor() is None


def test_stop_clears_stale_token_status(tty_bar):
    """Run over (finished or cancelled): the token/context status line
    must not linger under the idle prompt."""
    bar, _tty = tty_bar
    run_ui_mod.start_run_ui()
    bar.set_status("5.5k/500k tokens (1%)")
    run_ui_mod.stop_run_ui()
    assert bar._status == ""


def test_stop_clears_status_in_persistent_mode(tty_bar, monkeypatch):
    """Persistent prompt: stop_run_ui only flips routing, but the stale
    status line must STILL be dropped."""
    bar, _tty = tty_bar
    run_ui_mod.start_run_ui()
    monkeypatch.setattr(run_ui_mod, "_persistent", True)
    bar.set_status("5.5k/500k tokens (1%)")
    run_ui_mod.stop_run_ui()
    assert bar._status == ""
    assert run_ui_mod.is_run_active() is False
    monkeypatch.setattr(run_ui_mod, "_persistent", False)


def test_non_tty_creates_no_editor(pipe_bar):
    bar, pipe = pipe_bar
    editor = run_ui_mod.start_run_ui()
    assert editor is None
    assert run_ui_mod.get_run_editor() is None
    assert _key_listeners.get_line_editor() is None
    assert pipe.getvalue() == ""  # zero escape bytes in headless mode


# =========================================================================
# run_ui() context manager
# =========================================================================


def test_run_ui_context_manager_cleans_up(tty_bar):
    bar, _tty = tty_bar
    with run_ui_mod.run_ui() as editor:
        assert editor is not None
        assert bar.is_active() is True
    assert bar.is_active() is False
    assert _key_listeners.get_line_editor() is None


def test_run_ui_cleans_up_on_exception(tty_bar):
    bar, _tty = tty_bar
    with pytest.raises(RuntimeError):
        with run_ui_mod.run_ui():
            raise RuntimeError("agent exploded")
    assert bar.is_active() is False
    assert _key_listeners.get_line_editor() is None


# =========================================================================
# suspended_run_ui()
# =========================================================================


def test_suspended_run_ui_suspends_and_restores_bar(tty_bar):
    bar, tty = tty_bar
    run_ui_mod.start_run_ui()
    tty.truncate(0)
    tty.seek(0)
    with run_ui_mod.suspended_run_ui():
        assert "\x1b[r" in tty.getvalue()  # region reset while suspended
        tty.truncate(0)
        tty.seek(0)
    assert "\x1b[1;22r" in tty.getvalue()  # region re-established


def test_suspended_run_ui_noop_when_inactive(pipe_bar):
    with run_ui_mod.suspended_run_ui():
        pass  # must not raise, must not write


# =========================================================================
# Key-listener → editor feed routing
# =========================================================================


def test_listener_feed_helpers_route_to_installed_editor(tty_bar):
    editor = run_ui_mod.start_run_ui()
    _key_listeners._feed_line_editor("h")
    _key_listeners._feed_line_editor("i")
    assert editor.buffer == "hi"


def test_feed_helper_is_noop_without_editor():
    _key_listeners._feed_line_editor("x")  # must not raise
    _key_listeners._tick_line_editor()  # must not raise


def test_tick_helper_resolves_esc_timeout(tty_bar):
    editor = run_ui_mod.start_run_ui()
    fake_now = [100.0]
    editor._now = lambda: fake_now[0]
    _key_listeners._feed_line_editor("\x1b")
    fake_now[0] += 1.0  # ESC window long expired
    _key_listeners._tick_line_editor()
    _key_listeners._feed_line_editor("\r")  # plain Enter, not Alt+Enter
    # Empty buffer + Enter = no-op submit; the point is no stuck ESC state.
    assert editor.buffer == ""


def test_dispatch_routes_non_hotkeys_to_editor(tty_bar):
    editor = run_ui_mod.start_run_ui()
    _key_listeners._dispatch_key("a", lambda: None, "\x0b", lambda: None)
    assert editor.buffer == "a"


def test_dispatch_gives_ctrl_x_priority_over_editor(tty_bar):
    editor = run_ui_mod.start_run_ui()
    escapes = []
    _key_listeners._dispatch_key("\x18", lambda: escapes.append(1), None, None)
    assert escapes == [1]
    assert editor.buffer == ""  # Ctrl+X never reaches the editor


def test_dispatch_gives_cancel_key_priority_over_editor(tty_bar):
    editor = run_ui_mod.start_run_ui()
    cancels = []
    _key_listeners._dispatch_key(
        "\x0b", lambda: None, "\x0b", lambda: cancels.append(1)
    )
    assert cancels == [1]
    assert editor.buffer == ""  # cancel key never reaches the editor


def test_broken_editor_does_not_kill_feed(tty_bar):
    class ExplodingEditor:
        def feed(self, key):
            raise RuntimeError("boom")

        def check_timeout(self):
            raise RuntimeError("boom")

    _key_listeners.set_line_editor(ExplodingEditor())
    try:
        _key_listeners._feed_line_editor("x")  # must not raise
        _key_listeners._tick_line_editor()  # must not raise
    finally:
        _key_listeners.set_line_editor(None)
