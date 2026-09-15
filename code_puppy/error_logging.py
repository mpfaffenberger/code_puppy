"""Error logging utility for code_puppy.

Logs unexpected errors to XDG_STATE_HOME/code_puppy/logs/ for debugging purposes.
Per XDG spec, logs are "state data" (actions history), not configuration.
Because even good puppies make mistakes sometimes! 🐶
"""

import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

from code_puppy.config import STATE_DIR

# Logs directory within the state directory (per XDG spec, logs are state data)
LOGS_DIR = os.path.join(STATE_DIR, "logs")
ERROR_LOG_FILE = os.path.join(LOGS_DIR, "errors.log")
MAX_LOG_SIZE = 5 * 1024 * 1024  # 5MB


def _rotate_log_if_needed() -> None:
    """Rotate the error log file if it exceeds MAX_LOG_SIZE."""
    try:
        if (
            os.path.exists(ERROR_LOG_FILE)
            and os.path.getsize(ERROR_LOG_FILE) > MAX_LOG_SIZE
        ):
            rotated = ERROR_LOG_FILE + ".1"
            os.replace(ERROR_LOG_FILE, rotated)
    except OSError:
        pass


def _ensure_logs_dir() -> None:
    """Create the logs directory if it doesn't exist (with 0700 perms per XDG spec)."""
    Path(LOGS_DIR).mkdir(parents=True, exist_ok=True, mode=0o700)


def _build_error_log_entry(
    error: Exception,
    context: Optional[str],
    include_traceback: bool,
) -> str:
    """Render the ``errors.log`` entry for *error*.

    Split out of :func:`log_error` so the local-file sink and the observation
    hook can fail independently. The output format is unchanged.
    """
    timestamp = datetime.now().isoformat()
    error_type = type(error).__name__
    error_msg = str(error)

    log_entry_parts = [
        f"\n{'=' * 80}",
        f"Timestamp: {timestamp}",
        f"Error Type: {error_type}",
        f"Error Message: {error_msg}",
    ]

    if context:
        log_entry_parts.append(f"Context: {context}")

    if include_traceback:
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        log_entry_parts.append(f"Traceback:\n{''.join(tb)}")

    if hasattr(error, "args") and error.args:
        log_entry_parts.append(f"Args: {error.args}")

    log_entry_parts.append(f"{'=' * 80}\n")

    return "\n".join(log_entry_parts)


def _notify_error_logged(
    error: Exception,
    context: Optional[str],
    include_traceback: bool,
) -> None:
    """Best-effort dispatch of the ``error_logged`` observation phase.

    Imported lazily: ``callbacks`` pulls in pydantic-ai, and importing it at
    module scope would create an import cycle through ``config``.

    Core registers no subscriber, so this is a no-op in a stock install.
    """
    try:
        from code_puppy.callbacks import on_error_logged

        on_error_logged(
            error,
            context=context,
            include_traceback=include_traceback,
        )
    except Exception:
        # An observer must never turn "we hit an error" into "we crashed while
        # writing down that we hit an error".
        pass


def log_error(
    error: Exception,
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
    """
    try:
        _ensure_logs_dir()
        _rotate_log_if_needed()

        log_entry = _build_error_log_entry(error, context, include_traceback)

        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)

    except Exception:
        # If we can't log, we silently fail - don't want logging errors
        # to cause more problems than they solve!
        pass

    _notify_error_logged(error, context, include_traceback)


def log_error_message(
    message: str,
    context: Optional[str] = None,
) -> None:
    """Log a simple error message without an exception object.

    Args:
        message: The error message to log
        context: Optional context string describing where the error occurred
    """
    try:
        _ensure_logs_dir()
        _rotate_log_if_needed()

        timestamp = datetime.now().isoformat()

        log_entry_parts = [
            f"\n{'=' * 80}",
            f"Timestamp: {timestamp}",
            f"Message: {message}",
        ]

        if context:
            log_entry_parts.append(f"Context: {context}")

        log_entry_parts.append(f"{'=' * 80}\n")

        log_entry = "\n".join(log_entry_parts)

        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)

    except Exception:
        # Silent fail - same reasoning as above
        pass


def get_log_file_path() -> str:
    """Return the path to the error log file."""
    return ERROR_LOG_FILE


def get_logs_dir() -> str:
    """Return the path to the logs directory."""
    return LOGS_DIR
