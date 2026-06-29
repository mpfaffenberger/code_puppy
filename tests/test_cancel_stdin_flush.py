"""Tests for the cancel-path stdin drain.

Background: while an agent turn runs, a key-listener thread holds the
terminal in cbreak mode and reads stdin one byte at a time. On Ctrl+C the
listener keeps eating bytes until it sees the stop event, so the leading
characters of any follow-up the user types get swallowed and the truncated
tail would be submitted as a corrupt prompt. ``flush_stdin_input`` drains
the tty input queue on cancel so the next prompt starts from a clean slate.

These tests use a real pseudo-terminal so ``termios.tcflush`` actually
runs -- no mocking the very primitive whose behavior we care about.
"""

import os
import select
import sys
import time

import pytest

from code_puppy.agents._key_listeners import flush_stdin_input

pytestmark = pytest.mark.skipif(
    sys.platform.startswith("win"),
    reason="pty/termios drain test is POSIX-only",
)


class _FakeStdin:
    """Minimal stdin stand-in backed by a real terminal fd."""

    def __init__(self, fd: int, *, isatty: bool = True) -> None:
        self._fd = fd
        self._isatty = isatty

    def fileno(self) -> int:
        return self._fd

    def isatty(self) -> bool:
        return self._isatty


def _has_pending(fd: int) -> bool:
    """True if there are unread bytes waiting on ``fd`` (non-blocking)."""
    read_ready, _, _ = select.select([fd], [], [], 0.2)
    return bool(read_ready)


def test_flush_drains_pending_input(monkeypatch):
    """Bytes typed-ahead during cancel are discarded by the flush."""
    import pty

    master, slave = pty.openpty()
    try:
        # Simulate the user mashing a follow-up instruction while the turn
        # is still unwinding -- it lands in the slave's input queue.
        os.write(master, b"this is my real follow up instruction\n")
        # Give the kernel a beat to move the bytes into the input queue.
        time.sleep(0.05)
        assert _has_pending(slave), "precondition: bytes should be queued"

        monkeypatch.setattr(sys, "stdin", _FakeStdin(slave))
        flush_stdin_input()

        assert not _has_pending(slave), "flush should have drained the queue"
    finally:
        os.close(master)
        os.close(slave)


def test_without_flush_input_survives(monkeypatch):
    """Control: without flushing, the queued bytes remain readable.

    Proves the test harness genuinely buffers input, so the assertion in
    the flush test isn't passing for some unrelated reason.
    """
    import pty

    master, slave = pty.openpty()
    try:
        os.write(master, b"leftover\n")
        time.sleep(0.05)
        assert _has_pending(slave), "bytes should be queued without a flush"
    finally:
        os.close(master)
        os.close(slave)


def test_flush_noops_on_non_tty(monkeypatch):
    """A non-TTY stdin must not raise (and must not flush anything)."""
    r, w = os.pipe()
    try:
        os.write(w, b"pipe data\n")
        monkeypatch.setattr(sys, "stdin", _FakeStdin(r, isatty=False))
        # Should be a clean no-op -- no exception, data untouched.
        flush_stdin_input()
        assert _has_pending(r), "non-tty input must be left alone"
    finally:
        os.close(r)
        os.close(w)


def test_flush_survives_missing_stdin(monkeypatch):
    """If stdin is None / weird, flush degrades to a silent no-op."""
    monkeypatch.setattr(sys, "stdin", None)
    flush_stdin_input()  # must not raise
