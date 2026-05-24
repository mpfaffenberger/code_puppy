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
