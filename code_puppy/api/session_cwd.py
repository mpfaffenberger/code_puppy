"""Per-agent-run working-directory ContextVar helpers.

The WebSocket chat UI stores a session working directory on the runtime/session
metadata. Shell command execution needs access to that value without calling
``os.chdir()``, because multiple browser sessions may run concurrently in one
server process.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_session_working_directory: ContextVar[Optional[str]] = ContextVar(
    "code_puppy_session_working_directory",
    default=None,
)


def set_session_working_directory(directory: str | None) -> object:
    """Set the current agent-run working directory and return reset token."""
    value = directory or None
    return _session_working_directory.set(value)


def get_session_working_directory() -> str | None:
    """Return the current agent-run working directory, if one is set."""
    return _session_working_directory.get(None)


def clear_session_working_directory(token: object | None = None) -> None:
    """Clear or reset the current agent-run working directory."""
    if token is not None:
        try:
            _session_working_directory.reset(token)  # type: ignore[arg-type]
            return
        except Exception:
            pass
    _session_working_directory.set(None)
