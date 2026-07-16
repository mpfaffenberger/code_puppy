"""Register callbacks for the ``stack_dump`` plugin.

Wedge forensics: when Code Puppy hangs hard (deadlock, stuck lock
acquire, wedged event loop), ``kill -USR1 <pid>`` dumps EVERY thread's
Python stack to ``<state>/logs/stacks.log`` — no debugger, no py-spy,
no sudo required.

Why ``faulthandler`` and not a Python-level ``signal.signal`` handler:
Python signal handlers only run on the main thread between bytecodes.
A main thread stuck in a C-level ``lock.acquire()`` never reaches a
bytecode boundary, so a Python handler would hang right along with it
— the exact scenario we need to diagnose. ``faulthandler.register``
installs a C-level handler that writes stacks async-signal-safely,
even while the main thread is wedged.

POSIX-only (``SIGUSR1`` doesn't exist on Windows); silently no-ops
there and on any registration failure — never crash the app over
diagnostics plumbing.
"""

from __future__ import annotations

import logging
import os

from code_puppy.callbacks import register_callback

logger = logging.getLogger(__name__)

#: Kept module-global on purpose: faulthandler holds the raw fd, so the
#: file object must outlive the whole process. Never close it.
_dump_file = None


def _stacks_log_path() -> str:
    """Path of the dump log, next to the existing error log."""
    from code_puppy.error_logging import LOGS_DIR

    return os.path.join(LOGS_DIR, "stacks.log")


def _on_startup() -> None:
    """Arm SIGUSR1 → all-thread stack dump (best-effort, POSIX only)."""
    global _dump_file
    import faulthandler
    import signal

    if not hasattr(signal, "SIGUSR1") or not hasattr(faulthandler, "register"):
        return  # Windows: no SIGUSR1 / no faulthandler.register
    if _dump_file is not None:
        return  # already armed (idempotent across repeated startups)
    try:
        from code_puppy.error_logging import _ensure_logs_dir

        _ensure_logs_dir()
        path = _stacks_log_path()
        _dump_file = open(path, "a", encoding="utf-8")
        # Human breadcrumb: faulthandler output has no pid/timestamp of
        # its own, so mark which process armed the handler and when.
        from datetime import datetime

        _dump_file.write(
            f"\n=== stack_dump armed: pid={os.getpid()} "
            f"at {datetime.now().isoformat()} "
            f"(kill -USR1 {os.getpid()} to dump all threads) ===\n"
        )
        _dump_file.flush()
        faulthandler.register(signal.SIGUSR1, file=_dump_file, all_threads=True)
    except Exception:
        logger.debug("stack_dump: failed to arm SIGUSR1 handler", exc_info=True)
        try:
            if _dump_file is not None:
                _dump_file.close()
        except Exception:
            pass
        _dump_file = None


register_callback("startup", _on_startup)
