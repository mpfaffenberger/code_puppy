"""Tests for shell Ctrl+X handling via the unified key listener.

Historically ``command_runner`` spawned its OWN cbreak listener thread per
shell command, alongside the agent run's key listener — two readers on one
stdin. That's how CPR replies got eaten ("your terminal doesn't support
cursor position requests") and keystrokes went missing.

The new contract, locked in here:

* There is exactly ONE listener implementation
  (``code_puppy.agents._key_listeners``).
* ``command_runner`` routes Ctrl+X through
  ``_key_listeners.set_escape_handler()`` instead of spawning a rival
  thread when an agent-run listener is already active.
* The unified listener parks (drops cbreak, stops reading) while its
  ``suspend_event`` is set — replacing the old pause-controller polling.
"""

from __future__ import annotations

import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.agents import _key_listeners


@pytest.fixture(autouse=True)
def _reset_escape_handler():
    _key_listeners.set_escape_handler(None)
    yield
    _key_listeners.set_escape_handler(None)


# =============================================================================
# Dynamic escape-handler registry
# =============================================================================


def test_resolve_escape_handler_prefers_dynamic():
    fallback = MagicMock()
    dynamic = MagicMock()

    assert _key_listeners._resolve_escape_handler(fallback) is fallback
    _key_listeners.set_escape_handler(dynamic)
    assert _key_listeners._resolve_escape_handler(fallback) is dynamic
    _key_listeners.set_escape_handler(None)
    assert _key_listeners._resolve_escape_handler(fallback) is fallback


# =============================================================================
# command_runner routing (no second listener thread)
# =============================================================================


def test_start_keyboard_listener_routes_instead_of_spawning():
    """With an active agent-run listener, _start_keyboard_listener must NOT
    spawn a second thread — it just points Ctrl+X dispatch at the shell
    kill handler.
    """
    from code_puppy.tools import command_runner

    fake_handle = MagicMock()
    with (
        patch.object(_key_listeners, "get_active_handle", return_value=fake_handle),
        patch.object(command_runner, "_spawn_ctrl_x_key_listener") as mock_spawn,
        patch("signal.signal", return_value=None),
    ):
        command_runner._start_keyboard_listener()
        try:
            mock_spawn.assert_not_called()
            assert (
                _key_listeners._resolve_escape_handler(MagicMock())
                is command_runner._handle_ctrl_x_press
            )
        finally:
            command_runner._stop_keyboard_listener()

    # Handler cleared on stop.
    fallback = MagicMock()
    assert _key_listeners._resolve_escape_handler(fallback) is fallback


def test_start_keyboard_listener_spawns_when_headless():
    """Without an active agent-run listener, the shim spawn is used."""
    from code_puppy.tools import command_runner

    with (
        patch.object(_key_listeners, "get_active_handle", return_value=None),
        patch.object(
            command_runner, "_spawn_ctrl_x_key_listener", return_value=None
        ) as mock_spawn,
        patch("signal.signal", return_value=None),
    ):
        command_runner._start_keyboard_listener()
        try:
            mock_spawn.assert_called_once()
        finally:
            command_runner._stop_keyboard_listener()


def test_spawn_shim_delegates_to_unified_listener():
    """The compat shim must delegate to _key_listeners.spawn_key_listener."""
    from code_puppy.tools import command_runner

    stop = threading.Event()
    on_escape = MagicMock()

    fake_handle = MagicMock()
    with patch.object(
        _key_listeners, "spawn_key_listener", return_value=fake_handle
    ) as mock_spawn:
        result = command_runner._spawn_ctrl_x_key_listener(stop, on_escape)

    mock_spawn.assert_called_once_with(stop, on_escape=on_escape)
    assert result is fake_handle.thread


def test_spawn_shim_returns_none_without_tty():
    """No TTY -> unified spawn returns None -> shim returns None."""
    from code_puppy.tools import command_runner

    stop = threading.Event()
    with patch.object(_key_listeners, "spawn_key_listener", return_value=None):
        assert command_runner._spawn_ctrl_x_key_listener(stop, MagicMock()) is None


# =============================================================================
# Unified POSIX listener behaviour
# =============================================================================


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX-only test")
def test_posix_listener_parks_while_suspended():
    """While suspend_event is set, the listener must drop cbreak (restore
    termios) and never read stdin — so another stdin consumer (e.g. a
    prompt_toolkit app) can own the terminal cleanly.
    """
    stop_event = threading.Event()
    suspend_event = threading.Event()
    released_event = threading.Event()
    on_escape = MagicMock()

    fake_stdin = MagicMock()
    fake_stdin.fileno.return_value = 7

    with (
        patch.object(sys, "stdin", fake_stdin),
        patch("termios.tcgetattr", return_value=["original"]),
        patch("termios.tcsetattr") as mock_tcset,
        patch("tty.setcbreak") as mock_setcbreak,
        patch("select.select", return_value=([], [], [])),
    ):
        # Suspend BEFORE starting so the listener parks on its first lap.
        suspend_event.set()

        def stop_after_a_tick():
            time.sleep(0.15)
            stop_event.set()

        stopper = threading.Thread(target=stop_after_a_tick)
        stopper.start()

        _key_listeners._listen_posix(
            stop_event,
            on_escape,
            suspend_event=suspend_event,
            released_event=released_event,
        )
        stopper.join()

    assert mock_setcbreak.called
    # tcsetattr restores attrs on suspend + again in finally.
    assert mock_tcset.call_count >= 1
    # Parked listener confirmed it released stdin and never read it.
    assert released_event.is_set()
    fake_stdin.read.assert_not_called()
    on_escape.assert_not_called()


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX-only test")
def test_posix_listener_dispatches_ctrl_x_to_dynamic_handler():
    """Ctrl+X must dispatch to the dynamically registered handler (shell
    kill switch) in preference to the spawn-time on_escape callback.
    """
    stop_event = threading.Event()
    fallback = MagicMock()
    dynamic = MagicMock()

    fake_stdin = MagicMock()
    fake_stdin.fileno.return_value = 7

    reads = iter(["\x18"])

    def fake_read(_n):
        try:
            return next(reads)
        finally:
            stop_event.set()

    fake_stdin.read.side_effect = fake_read

    _key_listeners.set_escape_handler(dynamic)
    with (
        patch.object(sys, "stdin", fake_stdin),
        patch("termios.tcgetattr", return_value=["original"]),
        patch("termios.tcsetattr"),
        patch("tty.setcbreak"),
        patch("select.select", return_value=([fake_stdin], [], [])),
    ):
        _key_listeners._listen_posix(stop_event, fallback)

    dynamic.assert_called_once()
    fallback.assert_not_called()


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX-only test")
def test_posix_listener_polls_stdin_when_not_suspended():
    """Sanity check: unsuspended listener keeps select()-ing stdin."""
    stop_event = threading.Event()
    fake_stdin = MagicMock()
    fake_stdin.fileno.return_value = 7

    select_call_count = {"n": 0}

    def fake_select(*_args, **_kwargs):
        select_call_count["n"] += 1
        if select_call_count["n"] >= 2:
            stop_event.set()
        return ([], [], [])

    with (
        patch.object(sys, "stdin", fake_stdin),
        patch("termios.tcgetattr", return_value=["orig"]),
        patch("termios.tcsetattr"),
        patch("tty.setcbreak"),
        patch("select.select", side_effect=fake_select),
    ):
        _key_listeners._listen_posix(stop_event, MagicMock())

    assert select_call_count["n"] >= 2


# =============================================================================
# Unified Windows listener behaviour
# =============================================================================


def test_windows_listener_skips_kbhit_while_suspended(monkeypatch):
    """While suspended, the Windows listener must NOT drain msvcrt.kbhit().

    Runs cross-platform by stubbing msvcrt as a fake module.
    """
    fake_msvcrt = MagicMock()
    fake_msvcrt.kbhit.return_value = False
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

    stop_event = threading.Event()
    suspend_event = threading.Event()
    released_event = threading.Event()
    on_escape = MagicMock()

    suspend_event.set()

    def stop_after_a_tick():
        time.sleep(0.15)
        stop_event.set()

    stopper = threading.Thread(target=stop_after_a_tick)
    stopper.start()
    _key_listeners._listen_windows(
        stop_event,
        on_escape,
        suspend_event=suspend_event,
        released_event=released_event,
    )
    stopper.join()

    fake_msvcrt.kbhit.assert_not_called()
    on_escape.assert_not_called()
    assert released_event.is_set()
