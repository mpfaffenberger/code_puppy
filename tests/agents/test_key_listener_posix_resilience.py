"""POSIX key-listener resilience (2026-07-05 stdin-wedge follow-up).

The listener must survive TRANSIENT stdin read errors (EIO while another
process group briefly owns the tty, EINTR, EAGAIN) and must NEVER die —
the supervisor warns once per outage, backs off, keeps retrying until
the tty works again, and announces recovery. A silent death restores
cooked termios, after which every keystroke echoes raw and the prompt
is dead with zero diagnostics.
"""

import codecs
import errno
import os
import select as select_mod
import sys
import threading
import time

import pytest

try:
    import termios
    import tty
except ImportError:  # Windows: a bare import here would abort COLLECTION
    termios = tty = None  # of the whole test run, not just skip this module

from code_puppy.agents import _key_listeners as kl

pytestmark = pytest.mark.skipif(
    termios is None or not hasattr(select_mod, "select") or os.name == "nt",
    reason="POSIX listener only",
)


# =========================================================================
# _read_chunk classification
# =========================================================================


def _decoder():
    return codecs.getincrementaldecoder("utf-8")(errors="replace")


def test_read_chunk_transient_errors_return_empty(monkeypatch):
    for eno in (errno.EINTR, errno.EIO, errno.EAGAIN):

        def boom(fd, n, _e=eno):
            raise OSError(_e, "transient")

        monkeypatch.setattr(os, "read", boom)
        assert kl._read_chunk(0, _decoder()) == ""


def test_read_chunk_fatal_error_returns_none(monkeypatch):
    def boom(fd, n):
        raise OSError(errno.EBADF, "fd gone")

    monkeypatch.setattr(os, "read", boom)
    assert kl._read_chunk(0, _decoder()) is None


def test_read_chunk_eof_returns_none(monkeypatch):
    monkeypatch.setattr(os, "read", lambda fd, n: b"")
    assert kl._read_chunk(0, _decoder()) is None


def test_read_chunk_split_multibyte_buffers_then_completes(monkeypatch):
    dec = _decoder()
    monkeypatch.setattr(os, "read", lambda fd, n: b"\xc3")  # first half of é
    assert kl._read_chunk(0, dec) == ""
    monkeypatch.setattr(os, "read", lambda fd, n: b"\xa9")  # second half
    assert kl._read_chunk(0, dec) == "é"


# =========================================================================
# _listen_posix supervisor behavior (driven with faked tty/select/read)
# =========================================================================


class _FakeStdin:
    def fileno(self):
        return 0


class _Harness:
    """Scripted _listen_posix run. ``reads``: bytes payloads or OSError
    instances consumed one per os.read call; when exhausted the stop
    event is set and a transient error is raised so the loop notices
    the stop cleanly."""

    def __init__(self, monkeypatch, reads, stop_on_warning=False):
        self.dispatched, self.warnings, self.infos = [], [], []
        self.stop = threading.Event()

        def warn(msg):
            self.warnings.append(msg)
            if stop_on_warning:
                self.stop.set()

        monkeypatch.setattr(kl, "emit_warning", warn)
        monkeypatch.setattr(kl, "emit_info", self.infos.append)
        monkeypatch.setattr(
            kl, "_dispatch_key", lambda ch, *a, **kw: self.dispatched.append(ch)
        )
        monkeypatch.setattr(kl, "_tick_line_editor", lambda: None)
        monkeypatch.setattr(kl, "_RECOVERY_INITIAL_BACKOFF_S", 0.0)
        monkeypatch.setattr(kl, "_RECOVERY_MAX_BACKOFF_S", 0.0)
        monkeypatch.setattr(sys, "stdin", _FakeStdin())
        monkeypatch.setattr(termios, "tcgetattr", lambda fd: ["fake-attrs"] * 7)
        monkeypatch.setattr(termios, "tcsetattr", lambda *a: None)
        monkeypatch.setattr(tty, "setcbreak", lambda fd: None)
        monkeypatch.setattr(select_mod, "select", lambda r, w, x, t: (list(r), [], []))
        monkeypatch.setattr(time, "sleep", lambda s: None)

        seq = iter(reads)

        def fake_read(fd, n):
            item = next(seq, None)
            if item is None:
                self.stop.set()
                raise OSError(errno.EIO, "post-script transient")
            if isinstance(item, BaseException):
                raise item
            return item

        monkeypatch.setattr(os, "read", fake_read)

    def run(self):
        kl._listen_posix(self.stop, on_escape=lambda: None)
        return self


def test_listener_survives_transient_eio_and_recovers(monkeypatch):
    """The wedge scenario: a couple of EIO reads (foreground-group
    shuffle during a shell command) must NOT kill the listener — the
    keystrokes after recovery still dispatch, with zero warnings."""
    h = _Harness(
        monkeypatch,
        [OSError(errno.EIO, "bg pgrp"), OSError(errno.EIO, "bg pgrp"), b"hi"],
    ).run()
    assert h.dispatched == ["h", "i"]
    assert h.warnings == []


def test_supervisor_recovers_after_eio_storm_and_announces(monkeypatch):
    """A whole session dying of persistent EIO must not end input: the
    supervisor warns ONCE, retries, and announces recovery on the first
    successful read of the next session."""
    monkeypatch.setattr(kl, "_MAX_TRANSIENT_READS", 3)
    h = _Harness(
        monkeypatch,
        [
            OSError(errno.EIO, "storm"),
            OSError(errno.EIO, "storm"),
            OSError(errno.EIO, "storm"),  # session 1 exhausts and yields
            b"ok",  # session 2 succeeds
        ],
    ).run()
    assert h.dispatched == ["o", "k"]
    assert len(h.warnings) == 1
    assert "recovering automatically" in h.warnings[0]
    assert "persistent EIO" in h.warnings[0]
    assert h.infos == ["Key listener recovered — keyboard input restored."]


def test_supervisor_warns_once_per_outage(monkeypatch):
    """Back-to-back failed sessions produce exactly ONE warning."""
    monkeypatch.setattr(kl, "_MAX_TRANSIENT_READS", 1)
    reads = [OSError(errno.EIO, "storm")] * 3 + [b"x"]
    h = _Harness(monkeypatch, reads).run()
    assert h.dispatched == ["x"]
    assert len(h.warnings) == 1
    assert len(h.infos) == 1


def test_supervisor_retries_after_fatal_read_error(monkeypatch):
    """Even 'fatal' stdin errors are retried — stdin may come back."""
    h = _Harness(
        monkeypatch,
        [OSError(errno.EBADF, "stdin gone"), b"y"],
    ).run()
    assert h.dispatched == ["y"]
    assert len(h.warnings) == 1
    assert "EOF or fatal read error" in h.warnings[0]
    assert len(h.infos) == 1


def test_supervisor_exits_promptly_on_stop_during_outage(monkeypatch):
    """stop_event set while in outage backoff → clean exit, no spin."""
    h = _Harness(
        monkeypatch,
        [OSError(errno.EBADF, "stdin gone")],
        stop_on_warning=True,
    ).run()
    assert h.dispatched == []
    assert len(h.warnings) == 1


def test_supervisor_warns_on_select_failure(monkeypatch):
    h = _Harness(monkeypatch, [], stop_on_warning=True)

    def bad_select(r, w, x, t):
        raise ValueError("fd went negative")

    monkeypatch.setattr(select_mod, "select", bad_select)
    h.run()
    assert len(h.warnings) == 1
    assert "select failed" in h.warnings[0]
