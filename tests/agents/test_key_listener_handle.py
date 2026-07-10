"""Tests for KeyListenerHandle mechanics (no real listener thread).

These tests don't actually spawn the platform listener — they exercise the
handle contract directly with fake events. The actual stdin reading is
inherently TTY-dependent and not testable in CI.
"""

from __future__ import annotations

import threading
import time

import pytest

from code_puppy.agents._key_listeners import (
    KeyListenerHandle,
    _wait_while_suspended,
    get_active_handle,
    set_active_handle,
)


# =============================================================================
# KeyListenerHandle basic mechanics
# =============================================================================


def _make_handle() -> KeyListenerHandle:
    """Build a handle with a no-op thread (the thread is never .start()'d).

    Tests inspect the events directly; they don't care about the thread.
    """
    return KeyListenerHandle(
        thread=threading.Thread(target=lambda: None),
        stop_event=threading.Event(),
    )


def test_suspend_sets_suspend_event_and_blocks_until_released():
    handle = _make_handle()

    # Have a "fake listener" thread that observes suspend_event and
    # acknowledges by setting released_event after a short delay.
    def fake_listener() -> None:
        if handle.suspend_event.wait(timeout=1.0):
            time.sleep(0.05)  # simulate work releasing stdin
            handle.released_event.set()

    t = threading.Thread(target=fake_listener, daemon=True)
    t.start()

    assert handle.suspend(timeout=1.0) is True
    assert handle.suspend_event.is_set() is True

    t.join(timeout=1.0)


def test_suspend_returns_false_when_listener_never_acks():
    handle = _make_handle()
    # No fake-listener thread → released_event never gets set.
    assert handle.suspend(timeout=0.05) is False


def test_wait_while_suspended_sleeps_instead_of_busy_spinning(monkeypatch):
    """Regression: parking used to wait on ``suspend_event`` — which is SET
    while suspended, so ``Event.wait()`` returned instantly and the loop
    busy-spun at 100% CPU, hogging the GIL and lagging the steering prompt.

    The park loop must block on ``stop_event`` (genuinely unset) instead.
    """
    stop = threading.Event()
    suspend = threading.Event()
    suspend.set()
    released = threading.Event()

    sleep_calls: list[float] = []
    real_wait = stop.wait

    def counting_wait(timeout=None):
        sleep_calls.append(timeout)
        if len(sleep_calls) >= 3:
            suspend.clear()  # resume → loop must exit
        return real_wait(0)  # don't actually sleep in tests

    monkeypatch.setattr(stop, "wait", counting_wait)

    _wait_while_suspended(stop, suspend, released)

    assert released.is_set()
    assert sleep_calls, "park loop never blocked — that's a busy-spin"
    assert all(t == 0.05 for t in sleep_calls)


def test_wait_while_suspended_re_acks_after_back_to_back_resuspend():
    """Regression (the '/resume' false warning): suspend → resume → suspend
    faster than one 50ms poll lap. The parked loop never observes the
    brief suspend_event clear, so an entry-only (edge-triggered) ack
    would leave the new suspend()'s freshly-cleared released_event unset
    forever — a false 'Key listener did not release stdin in time'
    timeout while stdin was in fact released the whole time. The ack
    must be level-triggered: re-asserted on every poll lap.
    """
    stop = threading.Event()
    suspend = threading.Event()
    released = threading.Event()
    suspend.set()

    parked = threading.Thread(
        target=_wait_while_suspended, args=(stop, suspend, released), daemon=True
    )
    parked.start()
    try:
        # First suspension acks normally.
        assert released.wait(timeout=1.0), "initial park never acked"

        # Back-to-back re-suspension racing ahead of the 50ms poll:
        # resume + immediate suspend — the park loop never sees the gap.
        # (suspend() clears released_event then sets suspend_event; the
        # event stays set throughout, exactly like the live race.)
        released.clear()

        # The parked loop must re-assert the ack within a few laps.
        assert released.wait(timeout=1.0), (
            "parked listener never re-acked after re-suspend — "
            "edge-triggered ack regression"
        )
    finally:
        stop.set()
        parked.join(timeout=1.0)


def test_wait_while_suspended_tolerates_missing_released_event():
    """Inline call sites pass ``released_event=None`` — must not crash."""
    stop = threading.Event()
    suspend = threading.Event()  # not set → returns immediately

    _wait_while_suspended(stop, suspend, None)


def test_resume_clears_suspend_event():
    handle = _make_handle()
    handle.suspend_event.set()
    handle.released_event.set()

    handle.resume()
    assert handle.suspend_event.is_set() is False


def test_stop_sets_stop_event_and_clears_suspend():
    handle = _make_handle()
    handle.suspend_event.set()
    handle.stop()
    assert handle.stop_event.is_set() is True
    # Stop also clears suspend so a parked listener can exit immediately.
    assert handle.suspend_event.is_set() is False


def test_suspend_clears_stale_released_event_on_entry():
    """Repeated suspend() calls should each wait for a fresh ack."""
    handle = _make_handle()
    # Stale ack from a previous cycle.
    handle.released_event.set()

    # No listener acking this time — must NOT return True from the stale set.
    assert handle.suspend(timeout=0.05) is False


# =============================================================================
# Module-level singleton
# =============================================================================


@pytest.fixture(autouse=True)
def _reset_singleton():
    set_active_handle(None)
    yield
    set_active_handle(None)


def test_get_active_handle_returns_none_by_default():
    assert get_active_handle() is None


def test_set_and_get_active_handle_round_trip():
    h = _make_handle()
    set_active_handle(h)
    assert get_active_handle() is h
    set_active_handle(None)
    assert get_active_handle() is None


def test_set_active_handle_replaces_previous():
    h1 = _make_handle()
    h2 = _make_handle()
    set_active_handle(h1)
    set_active_handle(h2)
    assert get_active_handle() is h2


# =============================================================================
# Pure-keybinding Ctrl+C: the listener ALWAYS resolves the cancel char
# =============================================================================


def test_resolve_cancel_char_resolves_ctrl_c_on_every_platform(monkeypatch):
    """Ctrl+C is a pure keybinding: SIGINT never owns cancel, so the
    listener must resolve \\x03 as the cancel hotkey even on POSIX
    (where the tty INTR char is disabled while the listener owns stdin)."""
    import code_puppy.keymap as keymap
    from code_puppy.agents._key_listeners import _resolve_cancel_char

    monkeypatch.setattr(keymap, "get_cancel_agent_key", lambda: "ctrl+c")
    assert _resolve_cancel_char(None) == "\x03"
    assert _resolve_cancel_char(lambda: None) == "\x03"


def test_resolve_cancel_char_resolves_remapped_key(monkeypatch):
    import code_puppy.keymap as keymap
    from code_puppy.agents._key_listeners import _resolve_cancel_char

    monkeypatch.setattr(keymap, "get_cancel_agent_key", lambda: "ctrl+k")
    assert _resolve_cancel_char(None) == "\x0b"
