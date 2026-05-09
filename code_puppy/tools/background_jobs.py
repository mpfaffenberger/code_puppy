"""Minimal background job registry with bounded log access.

Provides safe tracking of detached shell processes started via
``run_shell_command(background=True)``.  Jobs are stored in a
process-wide dict keyed by PID.  Log tailing is bounded to avoid
unbounded reads.
"""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass
class BackgroundJob:
    pid: int
    command: str
    cwd: str | None
    log_file: str
    start_time: float = field(default_factory=lambda: os.times()[0])


# In-memory registry of background jobs keyed by PID
_BACKGROUND_JOBS: Dict[int, BackgroundJob] = {}

# Maximum bytes to read when tailing a background log
_MAX_TAIL_BYTES = 32_768

# Maximum lines to return from a tail
_MAX_TAIL_LINES = 256


def register_background_job(
    pid: int, command: str, cwd: str | None, log_file: str
) -> None:
    """Register a new background job."""
    _BACKGROUND_JOBS[pid] = BackgroundJob(
        pid=pid,
        command=command,
        cwd=cwd,
        log_file=log_file,
    )


def list_background_jobs() -> List[BackgroundJob]:
    """Return a list of registered background jobs."""
    # Prune jobs whose log files no longer exist (rough heuristic)
    stale: List[int] = []
    for pid, job in list(_BACKGROUND_JOBS.items()):
        try:
            if not os.path.exists(job.log_file):
                stale.append(pid)
        except OSError:
            stale.append(pid)
    for pid in stale:
        _BACKGROUND_JOBS.pop(pid, None)
    return list(_BACKGROUND_JOBS.values())


def stop_background_job(pid: int) -> bool:
    """Attempt to terminate a background job by PID.

    Returns True if the job was known and a signal was sent.
    """
    import signal

    job = _BACKGROUND_JOBS.pop(pid, None)
    if job is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass
    return True


def tail_background_job_log(pid: int, max_lines: int = _MAX_TAIL_LINES) -> str:
    """Return the tail of a background job's log file.

    Reads at most ``_MAX_TAIL_BYTES`` from the end of the log to avoid
    loading massive files into memory.
    """
    job = _BACKGROUND_JOBS.get(pid)
    if job is None:
        return ""
    try:
        path = Path(job.log_file)
        if not path.exists():
            return ""
        size = path.stat().st_size
        read_size = min(_MAX_TAIL_BYTES, size)
        with open(path, "rb") as f:
            f.seek(max(0, size - read_size))
            raw = f.read()
        text = raw.decode("utf-8", errors="replace")
        lines = deque(text.splitlines(), maxlen=max_lines)
        return "\n".join(lines)
    except (OSError, ValueError):
        return ""
