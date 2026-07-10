"""Tests for atomic listener acquisition + suspend-failure hardening.

Covers the fixes for the "keystrokes vanish while steering" audit:

* ``acquire_listener`` makes reuse-or-spawn atomic AND registers the
  spawned handle, so no code path can end up with two cbreak readers on
  one stdin.
* ``suspended_key_listener`` no longer fails silently when the listener
  doesn't release stdin in time — it retries once, then warns.
* ``run_ui.stop_run_ui`` self-heals a dead persistent listener so the
  idle prompt never goes permanently deaf.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.agents import _key_listeners
from code_puppy.agents._key_listeners import (
    KeyListenerHandle,
    acquire_listener,
    get_active_handle,
    set_active_handle,
    suspended_key_listener,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    set_active_handle(None)
    yield
    set_active_handle(None)


def _make_handle(alive: bool = True, stopped: bool = False) -> KeyListenerHandle:
    thread = MagicMock(spec=threading.Thread)
    thread.is_alive.return_value = alive
    handle = KeyListenerHandle(thread=thread, stop_event=threading.Event())
    if stopped:
        handle.stop_event.set()
    return handle


# =============================================================================
# acquire_listener
# =============================================================================


def test_acquire_reuses_live_listener():
    existing = _make_handle(alive=True)
    set_active_handle(existing)

    with patch.object(_key_listeners, "spawn_key_listener") as mock_spawn:
        handle, spawned = acquire_listener(threading.Event(), on_escape=lambda: None)

    mock_spawn.assert_not_called()
    assert handle is existing
    assert spawned is False


def test_acquire_spawns_and_registers_when_absent():
    new_handle = _make_handle(alive=True)
    with patch.object(
        _key_listeners, "spawn_key_listener", return_value=new_handle
    ) as mock_spawn:
        handle, spawned = acquire_listener(threading.Event(), on_escape=lambda: None)

    mock_spawn.assert_called_once()
    assert handle is new_handle
    assert spawned is True
    # THE fix: the spawned listener is registered so other stdin
    # consumers can see (and suspend) it.
    assert get_active_handle() is new_handle


def test_acquire_spawns_over_dead_listener():
    corpse = _make_handle(alive=False)
    set_active_handle(corpse)
    replacement = _make_handle(alive=True)

    with patch.object(_key_listeners, "spawn_key_listener", return_value=replacement):
        handle, spawned = acquire_listener(threading.Event(), on_escape=lambda: None)

    assert handle is replacement
    assert spawned is True
    assert get_active_handle() is replacement


def test_acquire_spawns_over_stopped_listener():
    stopping = _make_handle(alive=True, stopped=True)
    set_active_handle(stopping)
    replacement = _make_handle(alive=True)

    with patch.object(_key_listeners, "spawn_key_listener", return_value=replacement):
        handle, spawned = acquire_listener(threading.Event(), on_escape=lambda: None)

    assert handle is replacement
    assert spawned is True


def test_acquire_returns_none_true_without_tty():
    """spawn returned None (no TTY): nothing registered, spawned=True."""
    with patch.object(_key_listeners, "spawn_key_listener", return_value=None):
        handle, spawned = acquire_listener(threading.Event(), on_escape=lambda: None)

    assert handle is None
    assert spawned is True
    assert get_active_handle() is None


# =============================================================================
# suspended_key_listener suspend-failure hardening
# =============================================================================


def test_suspended_key_listener_warns_when_listener_never_releases():
    handle = _make_handle(alive=True)
    set_active_handle(handle)

    with (
        patch.object(handle, "suspend", return_value=False) as mock_suspend,
        patch.object(handle.released_event, "wait", return_value=False) as mock_wait,
        patch.object(_key_listeners, "emit_warning") as mock_warn,
    ):
        with suspended_key_listener(timeout=0.01):
            pass

    mock_suspend.assert_called_once()
    mock_wait.assert_called_once()
    mock_warn.assert_called_once()


def test_suspended_key_listener_grace_period_recovers_silently():
    """Slow-but-eventual release: no warning."""
    handle = _make_handle(alive=True)
    set_active_handle(handle)

    with (
        patch.object(handle, "suspend", return_value=False),
        patch.object(handle.released_event, "wait", return_value=True),
        patch.object(_key_listeners, "emit_warning") as mock_warn,
    ):
        with suspended_key_listener(timeout=0.01):
            pass

    mock_warn.assert_not_called()


def test_suspended_key_listener_happy_path_no_warning():
    handle = _make_handle(alive=True)
    set_active_handle(handle)

    with (
        patch.object(handle, "suspend", return_value=True),
        patch.object(_key_listeners, "emit_warning") as mock_warn,
    ):
        with suspended_key_listener(timeout=0.01):
            pass

    mock_warn.assert_not_called()


# =============================================================================
# run_ui persistent-listener self-healing
# =============================================================================


def test_stop_run_ui_respawns_dead_persistent_listener(monkeypatch):
    from code_puppy.messaging import run_ui

    corpse = _make_handle(alive=False)
    replacement = _make_handle(alive=True)
    monkeypatch.setattr(run_ui, "_persistent", True)
    monkeypatch.setattr(run_ui, "_listener_handle", corpse)
    set_active_handle(corpse)

    with patch.object(_key_listeners, "spawn_key_listener", return_value=replacement):
        run_ui.stop_run_ui()

    try:
        assert run_ui._listener_handle is replacement
        assert get_active_handle() is replacement
    finally:
        monkeypatch.setattr(run_ui, "_listener_handle", None)


def test_stop_run_ui_leaves_healthy_persistent_listener_alone(monkeypatch):
    from code_puppy.messaging import run_ui

    healthy = _make_handle(alive=True)
    monkeypatch.setattr(run_ui, "_persistent", True)
    monkeypatch.setattr(run_ui, "_listener_handle", healthy)
    set_active_handle(healthy)

    with patch.object(_key_listeners, "spawn_key_listener") as mock_spawn:
        run_ui.stop_run_ui()

    mock_spawn.assert_not_called()
    assert run_ui._listener_handle is healthy
