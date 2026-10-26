"""Windows shell-pipe I/O and process-tree control that cannot wedge the puppy.

Split from ``command_runner`` (600-line cap). It handles two Windows hazards:

1. **Inherited pipe handles.** ``cmd /c "build && start server"`` exits at
   once, but ``start``'s child inherits our pipe write-ends, so EOF never
   arrives. A blocking ``read()``/``readline()`` then hangs forever. Worse,
   ``close()`` on that fd blocks too: it needs the CRT per-fd lock that the
   stuck read holds. That wedges both the tool call and the Ctrl+C kill
   path. ``NonBlockingPipeReader`` only ``ReadFile``s the bytes that
   ``PeekNamedPipe`` already reports as available, and goes through
   ``_winapi`` on the raw OS handle, so it never blocks and never takes the
   CRT lock.

2. **Orphaned grandchildren.** ``taskkill /T`` walks parent PIDs, so once an
   intermediate shell exits, its children can't be reached. The ``*_job``
   helpers put each shell in a Job Object so a kill reaches the whole tree.
   There is deliberately no ``KILL_ON_JOB_CLOSE``: releasing the job after a
   normal finish must leave processes the user started on purpose alone.
   Small race: anything the shell spawns before ``attach_job`` runs (a few
   ms after ``CreateProcess``) stays outside the job, and ``taskkill /T``
   still covers those.

Every helper is a safe no-op off Windows, so callers don't need to branch.
"""

from __future__ import annotations

import codecs
import io
import subprocess
import sys
import threading

IS_WINDOWS = sys.platform.startswith("win")

if IS_WINDOWS:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    import _winapi

    # Private WinDLL: setting argtypes on the shared ctypes.windll would leak
    # into every other module that uses kernel32.
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _kernel32.TerminateJobObject.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.CloseHandle.restype = wintypes.BOOL


class NonBlockingPipeReader:
    """Line reader over a Windows anonymous pipe that never blocks.

    Splits on ``\\r\\n``, ``\\r`` and ``\\n``, the same as the
    ``TextIOWrapper(newline="")`` readline it replaces, and keeps a trailing
    ``\\r`` that lands at a chunk boundary until the next chunk arrives.
    Decodes as UTF-8 with replacement characters.
    """

    _CHUNK = 64 * 1024
    #: Bounded so a firehose writer can't keep us from rechecking stop_event.
    _MAX_CHUNKS_PER_CALL = 16

    def __init__(self, pipe) -> None:
        self._handle = msvcrt.get_osfhandle(pipe.fileno())
        utf8 = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._decoder = io.IncrementalNewlineDecoder(utf8, translate=True)
        self._partial = ""
        self._finished = False
        #: Every write-end is closed (or our handle is gone).
        self.eof = False
        #: The last ``read_available`` call emptied the pipe.
        self.drained = False

    def read_available(self) -> list[str]:
        """Return the complete lines in the pipe right now. Never blocks."""
        chunks: list[str] = []
        self.drained = False
        for _ in range(self._MAX_CHUNKS_PER_CALL):
            try:
                available, _left = _winapi.PeekNamedPipe(self._handle)
                if not available:
                    self.drained = True
                    break
                data, _err = _winapi.ReadFile(self._handle, min(available, self._CHUNK))
            except OSError:  # ERROR_BROKEN_PIPE: no writers left. Real EOF.
                self.eof = self.drained = True
                break
            chunks.append(self._decoder.decode(data))
        lines = self._split("".join(chunks))
        return lines + self.finish() if self.eof else lines

    def finish(self) -> list[str]:
        """Flush the decoder and the trailing partial line. Idempotent."""
        if self._finished:
            return []
        self._finished = True
        lines = self._split(self._decoder.decode(b"", final=True))
        if self._partial:
            lines.append(self._partial)
            self._partial = ""
        return lines

    def _split(self, text: str) -> list[str]:
        lines = (self._partial + text).split("\n")
        self._partial = lines.pop()
        return lines


# Job handles keyed by Popen, held only while the shell is in the foreground.
_JOBS: dict[subprocess.Popen, int] = {}
_JOBS_LOCK = threading.Lock()


def attach_job(proc: subprocess.Popen) -> None:
    """Put ``proc`` (and everything it spawns afterwards) in a fresh Job Object."""
    if not IS_WINDOWS:
        return
    job = _kernel32.CreateJobObjectW(None, None)
    if not job:
        return
    # Popen._handle is the real process handle, which avoids any PID-reuse race.
    if not _kernel32.AssignProcessToJobObject(job, int(proc._handle)):
        _kernel32.CloseHandle(job)  # e.g. the process already exited
        return
    with _JOBS_LOCK:
        _JOBS[proc] = job


def terminate_job(proc: subprocess.Popen) -> bool:
    """Kill every process in ``proc``'s job, orphans included."""
    if not IS_WINDOWS:
        return False
    with _JOBS_LOCK:
        job = _JOBS.get(proc)
    return bool(job) and bool(_kernel32.TerminateJobObject(job, 1))


def release_job(proc: subprocess.Popen) -> None:
    """Drop our job handle. Doesn't kill anything (no KILL_ON_JOB_CLOSE)."""
    if not IS_WINDOWS:
        return
    with _JOBS_LOCK:
        job = _JOBS.pop(proc, None)
    if job:
        _kernel32.CloseHandle(job)


__all__ = [
    "IS_WINDOWS",
    "NonBlockingPipeReader",
    "attach_job",
    "release_job",
    "terminate_job",
]
