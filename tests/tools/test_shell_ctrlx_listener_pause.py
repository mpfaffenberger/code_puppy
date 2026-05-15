"""Tests for pause-awareness in the shell-command Ctrl+X listener.

While a shell command is running, ``command_runner`` spawns a small
``_listen_for_ctrl_x_*`` daemon that grabs stdin in cbreak mode looking
for Ctrl+X to interrupt the process. That listener used to read stdin
unconditionally — which meant when the user hit Ctrl+T to steer, every
other keystroke typed into the steering editor got eaten by this thread.

These tests lock in the new contract: when the PauseController is paused,
the listener must NOT consume stdin (POSIX: drop cbreak and sleep;
Windows: skip the kbhit() drain).
"""

from __future__ import annotations

import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.messaging.pause_controller import (
    get_pause_controller,
    reset_pause_controller,
)


@pytest.fixture(autouse=True)
def _reset_pause_singleton():
    reset_pause_controller()
    yield
    reset_pause_controller()


# =============================================================================
# POSIX listener
# =============================================================================


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX-only test")
def test_posix_listener_drops_cbreak_while_paused():
    """When paused, the listener must call termios.tcsetattr to restore
    the original terminal attrs (i.e. drop cbreak) so the steering editor
    can take over stdin cleanly.
    """
    from code_puppy.tools import command_runner

    stop_event = threading.Event()
    on_escape = MagicMock()

    # Mock all the tty plumbing so we can run this in CI without a real TTY.
    fake_fd = 7
    fake_attrs = ["original"]

    fake_stdin = MagicMock()
    fake_stdin.fileno.return_value = fake_fd

    with (
        patch.object(command_runner.sys, "stdin", fake_stdin),
        patch("termios.tcgetattr", return_value=fake_attrs) as mock_tcget,
        patch("termios.tcsetattr") as mock_tcset,
        patch("tty.setcbreak") as mock_setcbreak,
        patch("select.select", return_value=([], [], [])),
    ):
        # Pause BEFORE starting so the listener enters its paused branch
        # on the first iteration.
        get_pause_controller().pause()

        def stop_after_a_tick():
            time.sleep(0.15)
            stop_event.set()

        stopper = threading.Thread(target=stop_after_a_tick)
        stopper.start()

        command_runner._listen_for_ctrl_x_posix(stop_event, on_escape)
        stopper.join()

    # Cbreak entered once at the top, then dropped on pause detection.
    assert mock_setcbreak.called
    # tcsetattr called to restore original attrs (drop cbreak) — at least
    # once during pause handling + once in finally.
    assert mock_tcset.call_count >= 1
    # We never read stdin or fired the escape callback.
    on_escape.assert_not_called()
    assert mock_tcget.called


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX-only test")
def test_posix_listener_reads_stdin_when_not_paused():
    """Sanity check: when NOT paused, the listener should still call
    select.select on stdin (i.e. it isn't permanently stuck in the
    paused branch).
    """
    from code_puppy.tools import command_runner

    stop_event = threading.Event()
    on_escape = MagicMock()
    fake_stdin = MagicMock()
    fake_stdin.fileno.return_value = 7

    select_call_count = {"n": 0}

    def fake_select(*_args, **_kwargs):
        select_call_count["n"] += 1
        if select_call_count["n"] >= 2:
            stop_event.set()
        return ([], [], [])

    with (
        patch.object(command_runner.sys, "stdin", fake_stdin),
        patch("termios.tcgetattr", return_value=["orig"]),
        patch("termios.tcsetattr"),
        patch("tty.setcbreak"),
        patch("select.select", side_effect=fake_select),
    ):
        # Not paused — listener should poll stdin.
        command_runner._listen_for_ctrl_x_posix(stop_event, on_escape)

    assert select_call_count["n"] >= 2


# =============================================================================
# Windows listener
# =============================================================================


def test_windows_listener_skips_kbhit_while_paused(monkeypatch):
    """While paused, the Windows listener must NOT call msvcrt.kbhit().

    This test runs cross-platform by stubbing msvcrt as a fake module.
    """
    fake_msvcrt = MagicMock()
    fake_msvcrt.kbhit.return_value = False
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

    from code_puppy.tools import command_runner

    stop_event = threading.Event()
    on_escape = MagicMock()

    get_pause_controller().pause()

    def stop_after_a_tick():
        time.sleep(0.15)
        stop_event.set()

    stopper = threading.Thread(target=stop_after_a_tick)
    stopper.start()
    command_runner._listen_for_ctrl_x_windows(stop_event, on_escape)
    stopper.join()

    fake_msvcrt.kbhit.assert_not_called()
    on_escape.assert_not_called()
