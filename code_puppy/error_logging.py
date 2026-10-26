"""Error logging utility for code_puppy.

Logs unexpected errors to XDG_STATE_HOME/code_puppy/logs/ for debugging purposes.
Per XDG spec, logs are "state data" (actions history), not configuration.
Because even good puppies make mistakes sometimes! 🐶
"""

import logging
import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from code_puppy.config import STATE_DIR
from code_puppy.error_format import cap_entry, render_error_entry, render_message_entry

logger = logging.getLogger(__name__)

# Logs directory within the state directory (per XDG spec, logs are state data)
LOGS_DIR = os.path.join(STATE_DIR, "logs")
ERROR_LOG_FILE = os.path.join(LOGS_DIR, "errors.log")
MAX_LOG_SIZE = 5 * 1024 * 1024  # 5MB


def _rotate_log_if_needed(incoming: int = 0) -> None:
    """Rotate the error log when it plus *incoming* bytes would pass MAX_LOG_SIZE.

    With no argument it rotates a file that is already over the limit. Two
    processes rotating at once is tolerated: ``os.replace`` is atomic and a late
    write simply lands in the backup.
    """
    try:
        size = os.path.getsize(ERROR_LOG_FILE)
        if size > 0 and size + incoming > MAX_LOG_SIZE:
            os.replace(ERROR_LOG_FILE, ERROR_LOG_FILE + ".1")
    except OSError:
        pass


def _ensure_logs_dir() -> None:
    """Create the logs directory if it doesn't exist (with 0700 perms per XDG spec)."""
    Path(LOGS_DIR).mkdir(parents=True, exist_ok=True, mode=0o700)


def _append_entry(entry: str) -> None:
    """Cap *entry*, rotate if it would pass MAX_LOG_SIZE, append it.

    The one path every write takes, so even the bare fallback entries are capped.
    Lone surrogates are written as backslash escapes: they cannot be encoded.
    """
    data = cap_entry(entry).encode("utf-8", "backslashreplace")
    _ensure_logs_dir()
    _rotate_log_if_needed(len(data))
    with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(data.decode("utf-8"))


# Dedupe stamp: an exception object is written to errors.log once, so the
# innermost handler's context wins and an outer handler's repeat is a no-op.
# The stamp lives on the exception because builtin exceptions cannot be weakly
# referenced. Exceptions that refuse ``setattr`` fall back to a bounded table
# that holds a strong reference, which keeps ``id()`` unique while it is there.
_STAMP = "__code_puppy_logged__"
_FALLBACK_MAX = 128
_fallback: "OrderedDict[int, BaseException]" = OrderedDict()
_fallback_lock = threading.Lock()


def was_logged(error: BaseException) -> bool:
    """Return True when *error* was already passed to :func:`log_error`.

    Never raises: any failure is logged at DEBUG and reads as "not logged".
    """
    try:
        if getattr(error, _STAMP, False) is True:
            return True
        with _fallback_lock:
            return _fallback.get(id(error)) is error
    except Exception:
        logger.debug("was_logged failed", exc_info=True)
        return False


def _mark_logged(error: BaseException) -> None:
    """Stamp *error* as logged; never raises."""
    try:
        setattr(error, _STAMP, True)
        return
    except Exception:
        logger.debug("stamping an exception failed; using the fallback", exc_info=True)
    try:
        with _fallback_lock:
            _fallback[id(error)] = error
            while len(_fallback) > _FALLBACK_MAX:
                _fallback.popitem(last=False)
    except Exception:
        logger.debug("recording an exception in the fallback failed", exc_info=True)


# Guards against a subscriber that calls ``log_error()`` from inside the
# ``error_logged`` dispatch, which would otherwise re-enter this phase until
# CPython's recursion limit trips -- roughly 199 nested dispatches, each one
# appending a full traceback to the local log.
#
# Thread-local rather than a module global: a subscriber running on one thread
# must not blind the hook for an unrelated error on another.
_notify_state = threading.local()


def _notify_error_logged(
    error: BaseException,
    context: Optional[str],
    include_traceback: bool,
) -> None:
    """Best-effort dispatch of the ``error_logged`` observation phase.

    Imported lazily: ``callbacks`` pulls in pydantic-ai, and importing it at
    module scope would create an import cycle through ``config``.

    Core registers no subscriber, so this is a no-op in a stock install.

    Latched per thread, so a subscriber that logs an error of its own is
    observed once rather than recursing. ``log_error_message()`` closes the
    same door from the other side by never firing this phase at all.
    """
    if getattr(_notify_state, "active", False):
        return

    _notify_state.active = True
    try:
        from code_puppy.callbacks import on_error_logged

        on_error_logged(
            error,
            context=context,
            include_traceback=include_traceback,
        )
    except Exception:
        # An observer must never turn "we hit an error" into "we crashed while
        # writing down that we hit an error" -- but leave a breadcrumb.
        #
        # ``_trigger_callbacks_sync`` already isolates and logs each
        # subscriber's own failures, so reaching here means the dispatch
        # itself broke: the lazy import failed, most plausibly.
        #
        # warning, not debug: the root logger sits at WARNING in a stock
        # install, so a debug record is discarded and the "breadcrumb" this
        # comment promises would not exist. This branch is unreachable in
        # normal operation, so it cannot become noise.
        logger.warning("error_logged dispatch failed", exc_info=True)
    finally:
        _notify_state.active = False


def log_error(
    error: BaseException,
    context: Optional[str] = None,
    include_traceback: bool = True,
) -> None:
    """Log an error to the error log file.

    Writes to the local log and notifies the ``error_logged`` observation
    phase. The two sinks are independent: a full disk cannot suppress the
    hook, and a misbehaving plugin cannot suppress the local log.

    Args:
        error: The exception to log
        context: Optional context string describing where the error occurred
        include_traceback: Whether to include the full traceback (default True)

    A second call for the same exception object is a no-op (see ``was_logged``):
    it writes nothing and does not fire the ``error_logged`` phase.
    """
    if was_logged(error):
        return

    try:
        _append_entry(render_error_entry(error, context, include_traceback))
    except Exception:
        # If we can't log, we silently fail - don't want logging errors
        # to cause more problems than they solve!
        pass

    # Stamp even when the write failed: never retry a failing sink.
    _mark_logged(error)

    _notify_error_logged(error, context, include_traceback)


def log_error_message(
    message: str,
    context: Optional[str] = None,
) -> bool:
    """Log a simple error message without an exception object.

    Args:
        message: The error message to log
        context: Optional context string describing where the error occurred

    Returns:
        True after a successful write, False when the write raised. Never
        raises and never fires the ``error_logged`` phase.
    """
    try:
        _append_entry(render_message_entry(message, context))
        return True
    except Exception:
        # Silent fail - same reasoning as above
        return False


def get_log_file_path() -> str:
    """Return the path to the error log file."""
    return ERROR_LOG_FILE


def get_logs_dir() -> str:
    """Return the path to the logs directory."""
    return LOGS_DIR
