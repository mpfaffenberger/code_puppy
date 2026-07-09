"""Mid-flight backgrounding for streaming shell commands (Ctrl+X Ctrl+B).

Split from ``command_runner`` (600-line cap): the generation counter the
streaming pumps poll, and the divert-log plumbing that keeps a detached
process's pipes drained.

Contract: ``request_background_all()`` bumps a generation; every
``run_shell_command_streaming`` pump captured the generation at start
and detaches when it changes -- readers divert remaining output into a
``DivertLog``, the tool call returns ``background=True`` immediately,
and the process keeps running outside the kill-all registry.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time

# Bumping the generation tells every in-flight streaming pump to detach.
_BACKGROUND_GENERATION = 0
_BACKGROUND_GENERATION_LOCK = threading.Lock()


def request_background_all() -> None:
    """Detach every currently-streaming foreground shell (Ctrl+X Ctrl+B)."""
    global _BACKGROUND_GENERATION
    with _BACKGROUND_GENERATION_LOCK:
        _BACKGROUND_GENERATION += 1


def background_generation() -> int:
    """Current generation -- pumps capture this at start and poll for drift."""
    with _BACKGROUND_GENERATION_LOCK:
        return _BACKGROUND_GENERATION


class DivertLog:
    """Thread-safe line sink for a backgrounded shell's remaining output.

    Both reader threads write here after detach; the janitor thread
    appends the exit footer and closes the handle once the process
    finishes. Every line is flushed so ``tail -f`` works immediately.
    """

    def __init__(self, command: str) -> None:
        fd, self.path = tempfile.mkstemp(prefix="code_puppy_bg_", suffix=".log")
        self._fh = os.fdopen(fd, "w", encoding="utf-8", errors="replace")
        self._lock = threading.Lock()
        self.write_line("meta", f"backgrounded shell: {command}")

    def write_line(self, stream: str, line: str) -> None:
        prefix = "" if stream == "stdout" else f"[{stream}] "
        with self._lock:
            if self._fh.closed:
                return
            try:
                self._fh.write(prefix + line + "\n")
                self._fh.flush()
            except (OSError, ValueError):
                pass

    def close(self) -> None:
        with self._lock:
            try:
                self._fh.close()
            except Exception:
                pass


def close_divert_log_on_exit(process: subprocess.Popen, log: DivertLog) -> None:
    """Janitor for a backgrounded shell: exit footer + close the log.

    Runs on a daemon thread; the grace sleep lets the reader threads
    drain the final pipe contents before the footer lands.
    """
    try:
        process.wait()
        time.sleep(1.0)
        log.write_line("meta", f"process exited with code {process.returncode}")
    except Exception:
        pass
    finally:
        log.close()


__all__ = [
    "DivertLog",
    "background_generation",
    "close_divert_log_on_exit",
    "request_background_all",
]
