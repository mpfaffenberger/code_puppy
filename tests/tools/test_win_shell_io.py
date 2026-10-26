"""Windows shell wedge regressions: ``cmd /c "... && start server"`` used to brick
the puppy (blocking drain + close() on the CRT fd lock), and Ctrl+C couldn't
reach orphaned grandchildren. See ``code_puppy/tools/win_shell_io.py``."""

import os
import subprocess
import sys
import threading
import time
from unittest.mock import Mock

import pytest

from code_puppy.tools import command_runner

windows_only = pytest.mark.skipif(
    not sys.platform.startswith("win"), reason="Windows pipe/job semantics"
)


def _sleeper(pidfile, seconds=60) -> str:
    """Python one-liner that records its PID, then lingers."""
    code = (
        f"import os,time; open(r'{pidfile}','w').write(str(os.getpid())); "
        f"time.sleep({seconds})"
    )
    return f'"{sys.executable}" -c "{code}"'


def _wait_for_pid(pidfile, timeout=15.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with open(pidfile, encoding="utf-8") as fh:
                return int(fh.read())
        except (OSError, ValueError):
            time.sleep(0.1)
    raise AssertionError("sleeper never reported its PID")


def _pid_alive(pid: int) -> bool:
    # os.kill(pid, 0) TERMINATES on Windows, hence the ctypes probe.
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32")
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    k32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = k32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = wintypes.DWORD()
    try:
        k32.GetExitCodeProcess(handle, ctypes.byref(code))
    finally:
        k32.CloseHandle(handle)
    return code.value == 259  # STILL_ACTIVE


def _run_in_thread(command):
    """Run the real sync tool path on a watchdog-able thread."""
    box = {}

    def target():
        box["result"] = command_runner._run_command_sync(
            command, cwd=None, timeout=30, group_id="win-io", silent=True
        )

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, box


def _taskkill(pid):
    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)


@windows_only
def test_start_orphan_holding_pipes_does_not_wedge_the_tool(tmp_path):
    pidfile = tmp_path / "orphan.pid"
    command = f'echo before-start && start "" /b {_sleeper(pidfile)}'
    thread, box = _run_in_thread(command)
    thread.join(timeout=20)
    orphan = _wait_for_pid(pidfile)
    try:
        assert not thread.is_alive(), "tool call wedged on an inherited pipe"
        assert "before-start" in box["result"].stdout
        # Returning promptly must NOT kill what the user deliberately started.
        assert _pid_alive(orphan)
    finally:
        _taskkill(orphan)


@windows_only
def test_kill_all_returns_and_reaches_orphaned_grandchildren(tmp_path):
    pidfile = tmp_path / "orphan.pid"
    # The inner cmd exits right away, which leaves the sleeper with a dead
    # parent: taskkill /T from the root can't see it, only the job can.
    long_sleep = f'"{sys.executable}" -c "import time; time.sleep(60)"'
    command = f'cmd /c start "" /b {_sleeper(pidfile)} && {long_sleep}'
    thread, box = _run_in_thread(command)
    orphan = _wait_for_pid(pidfile)
    try:
        killer = threading.Thread(
            target=command_runner.kill_all_running_shell_processes, daemon=True
        )
        killer.start()
        killer.join(timeout=15)
        assert not killer.is_alive(), "Ctrl+C kill path wedged"
        thread.join(timeout=15)
        assert not thread.is_alive(), "tool call never returned after kill"
        deadline = time.monotonic() + 5
        while _pid_alive(orphan) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not _pid_alive(orphan), "orphaned grandchild survived the kill"
    finally:
        _taskkill(orphan)


class _Pipe:
    def __init__(self, fd):
        self._fd = fd

    def fileno(self):
        return self._fd


@pytest.fixture
def pipe_pair():
    read_fd, write_fd = os.pipe()
    from code_puppy.tools.win_shell_io import NonBlockingPipeReader

    reader = NonBlockingPipeReader(_Pipe(read_fd))
    yield reader, write_fd
    for fd in (read_fd, write_fd):
        try:
            os.close(fd)
        except OSError:
            pass


@windows_only
def test_reader_never_blocks_on_empty_or_partial_pipe(pipe_pair):
    reader, write_fd = pipe_pair
    started = time.monotonic()
    assert reader.read_available() == []
    os.write(write_fd, b"no newline yet")
    assert reader.read_available() == []  # held back, not blocked on
    assert time.monotonic() - started < 1.0
    assert reader.drained and not reader.eof


@windows_only
def test_reader_splits_like_universal_newlines_across_chunks(pipe_pair):
    reader, write_fd = pipe_pair
    # A CRLF split across writes must stay ONE line break, and the UTF-8
    # multibyte char split across writes must decode intact.
    os.write(write_fd, b"one\r")
    first = reader.read_available()
    os.write(write_fd, b"\ntwo\rthree\n caf\xc3")
    second = reader.read_available()
    os.write(write_fd, b"\xa9 tail")
    os.close(write_fd)
    third = reader.read_available()
    assert first + second + third == ["one", "two", "three", " café tail"]
    assert reader.eof
    assert reader.finish() == []  # idempotent


def test_close_pipes_refuses_while_a_reader_is_alive():
    process = Mock(stdout=Mock(closed=False), stderr=None, stdin=None)
    alive = Mock(is_alive=Mock(return_value=True))
    assert command_runner._close_pipes(process, (alive, None)) is False
    process.stdout.close.assert_not_called()

    dead = Mock(is_alive=Mock(return_value=False))
    assert command_runner._close_pipes(process, (dead, None)) is True
    process.stdout.close.assert_called_once()


def test_job_helpers_are_safe_on_unattached_processes():
    from code_puppy.tools.win_shell_io import release_job, terminate_job

    process = Mock(spec=subprocess.Popen)
    assert terminate_job(process) is False
    release_job(process)  # must not raise
