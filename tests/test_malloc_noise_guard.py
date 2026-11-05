"""Tests for the macOS MallocStackLogging stderr noise guard."""

from __future__ import annotations

import os
import select
import signal
import subprocess
import sys
import time
from unittest.mock import patch

import pytest

from code_puppy import malloc_noise_guard as guard

NOISE = (
    b"python(99930) MallocStackLogging: can't turn off malloc stack logging"
    b" because it was not enabled.\n"
)

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX fds")
macos_only = pytest.mark.skipif(sys.platform != "darwin", reason="macOS only")


class TestStripMallocNoise:
    @pytest.mark.parametrize(
        "progname",
        ["python(99930)", "Python(1)", "python3.14(5)", "zsh (figterm)(7164)"],
    )
    def test_drops_the_line_for_any_program(self, progname: str):
        line = NOISE.replace(b"python(99930)", progname.encode())
        assert guard.strip_malloc_noise(b"before\n" + line + b"after\n") == (
            b"before\nafter\n"
        )

    def test_keeps_real_stderr_and_partial_lines(self):
        data = b"Traceback (most recent call last):\nprogress 50%" + NOISE + b"\r60%"
        assert guard.strip_malloc_noise(data) == (
            b"Traceback (most recent call last):\nprogress 50%\r60%"
        )

    def test_keeps_other_malloc_stack_logging_output(self):
        # A user who deliberately enabled MSL must still see what it reports.
        line = (
            b"python(7) MallocStackLogging: recording malloc (and VM allocation)"
            b" stacks using lite mode\n"
        )
        assert guard.strip_malloc_noise(line) == line


@posix_only
class TestForwarder:
    def _spawn(self) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [sys.executable, "-I", "-S", "-c", guard._FORWARDER_SOURCE]
            + [guard.MALLOC_NOISE_PATTERN.decode()],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )

    def test_filters_noise_and_forwards_everything_else(self):
        proc = self._spawn()
        out, _ = proc.communicate(NOISE + b"real error\n" + NOISE + b"tail", timeout=10)
        assert out == b"real error\ntail"
        assert proc.returncode == 0

    def test_survives_ctrl_c(self):
        proc = self._spawn()
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(b"ready\n")
        proc.stdin.flush()
        assert proc.stdout.readline() == b"ready\n"  # handlers are installed
        proc.send_signal(signal.SIGINT)
        out, _ = proc.communicate(b"still here\n", timeout=10)
        assert out == b"still here\n"
        assert proc.returncode == 0


class TestInstallNoOps:
    def test_off_macos(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(guard.sys, "platform", "linux")
        with patch.object(guard.os, "pipe") as pipe:
            assert guard.install_malloc_noise_guard() is False
        pipe.assert_not_called()

    @pytest.mark.parametrize("isatty", [lambda fd: False, OSError("bad fd")])
    def test_when_stderr_is_not_a_terminal(self, monkeypatch, isatty):
        monkeypatch.setattr(guard.sys, "platform", "darwin")
        with (
            patch.object(guard.os, "isatty", side_effect=isatty),
            patch.object(guard.os, "pipe") as pipe,
        ):
            assert guard.install_malloc_noise_guard() is False
        pipe.assert_not_called()

    @posix_only
    def test_spawn_failure_leaves_fd2_alone(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(guard.sys, "platform", "darwin")
        before = os.fstat(2)
        stderr_before = sys.stderr
        with (
            patch.object(guard.os, "isatty", return_value=True),
            patch.object(guard.os, "posix_spawn", side_effect=OSError("nope")),
        ):
            assert guard.install_malloc_noise_guard() is False
        after = os.fstat(2)
        assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
        assert sys.stderr is stderr_before


def _read_until(master_fd: int, needles: list[bytes], timeout: float = 10) -> bytes:
    seen = b""
    deadline = time.monotonic() + timeout
    while not all(n in seen for n in needles) and time.monotonic() < deadline:
        ready, _, _ = select.select([master_fd], [], [], 0.1)
        if ready:
            seen += os.read(master_fd, 65536)
    return seen


@macos_only
def test_installed_guard_keeps_noise_off_the_terminal(monkeypatch: pytest.MonkeyPatch):
    """End to end: fd 2 on a real pty, the way the TUI runs."""
    master_fd, slave_fd = os.openpty()
    saved_fd2 = os.dup(2)
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    monkeypatch.setattr(sys, "__stderr__", sys.__stderr__)
    os.dup2(slave_fd, 2)
    try:
        assert guard.install_malloc_noise_guard() is True
        # Python-level stderr talks to the terminal directly...
        assert sys.stderr.isatty()
        sys.stderr.write("python-level line\n")
        # ...while fd 2, which every fork child inherits, is the filter pipe.
        assert not os.isatty(2)
        os.write(2, NOISE + b"native line\n")
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os, sys; os.write(2, sys.stdin.buffer.read());"
                " print(os.isatty(2))",
            ],
            input=NOISE + b"child line\n",
            stdout=subprocess.PIPE,
            check=True,
        )
        assert child.stdout.strip() == b"False"  # child stderr is not the TTY
        sys.stderr.close()
    finally:
        os.dup2(saved_fd2, 2)
        os.close(saved_fd2)
        os.close(slave_fd)
    try:
        seen = _read_until(
            master_fd, [b"python-level line", b"native line", b"child line"]
        )
    finally:
        os.close(master_fd)
    assert b"python-level line" in seen
    assert b"native line" in seen
    assert b"child line" in seen
    assert b"MallocStackLogging" not in seen


def test_main_entry_installs_the_guard_first():
    from code_puppy import cli_runner

    with (
        patch.object(cli_runner, "install_malloc_noise_guard") as install,
        patch("asyncio.run", side_effect=lambda coro: coro.close()),
        patch.object(cli_runner, "reset_unix_terminal"),
        pytest.raises(SystemExit),
    ):
        cli_runner.main_entry()
    install.assert_called_once_with()
