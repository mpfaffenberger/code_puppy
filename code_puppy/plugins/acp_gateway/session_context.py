"""Session-scoped context variables for ACP multi-session isolation.

Provides ContextVar-based isolation for per-session state that needs
to be visible to downstream tool modules (file_operations,
file_modifications, command_runner) without passing session objects
through every call.

Follows the same ContextVar pattern used by
``code_puppy.tools.subagent_context`` for sub-agent depth tracking.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from contextlib import contextmanager
from typing import Generator

__all__ = [
    "session_cwd",
    "session_model",
    "session_aware_abspath",
    "session_context",
    "get_session_cwd",
    "get_session_model",
]

# Per-session working directory.  When set, ``session_aware_abspath``
# resolves relative paths against this instead of ``os.getcwd()``.
session_cwd: ContextVar[str | None] = ContextVar("session_cwd", default=None)

# Per-session model override.  When set, ``get_session_model`` returns
# this instead of the global model from ``config.get_global_model_name()``.
session_model: ContextVar[str | None] = ContextVar("session_model", default=None)


def get_session_cwd() -> str | None:
    """Return the current session's working directory, or None."""
    return session_cwd.get()


def get_session_model() -> str | None:
    """Return the current session's model override, or None."""
    return session_model.get()


def session_aware_abspath(path: str) -> str:
    """Resolve *path* against the session CWD if available.

    Drop-in replacement for ``os.path.abspath`` that is multi-session
    safe.  When no session CWD is active, falls back to the standard
    ``os.path.abspath`` (which uses ``os.getcwd()``).

    >>> import os
    >>> session_cwd.set("/tmp/project")
    >>> session_aware_abspath("src/main.py")
    '/tmp/project/src/main.py'
    """
    if os.path.isabs(path):
        return os.path.normpath(path)
    cwd = session_cwd.get()
    if cwd is not None:
        return os.path.normpath(os.path.join(cwd, path))
    return os.path.abspath(path)


@contextmanager
def session_context(
    cwd: str | None = None,
    model: str | None = None,
) -> Generator[None, None, None]:
    """Set session-scoped context variables for the duration of a block.

    Uses token-based reset for proper async isolation, matching the
    pattern in ``subagent_context.py``.

    Args:
        cwd: Working directory for this session (or None to leave unset).
        model: Model override for this session (or None to leave unset).
    """
    cwd_token = session_cwd.set(cwd) if cwd is not None else None
    model_token = session_model.set(model) if model is not None else None
    try:
        yield
    finally:
        if cwd_token is not None:
            session_cwd.reset(cwd_token)
        if model_token is not None:
            session_model.reset(model_token)


def install_session_aware_abspath() -> None:
    """Monkey-patch ``os.path.abspath`` in file tool modules.

    Replaces ``os.path.abspath`` with ``session_aware_abspath`` in
    ``code_puppy.tools.file_operations`` and
    ``code_puppy.tools.file_modifications`` so that relative paths
    resolve against the session CWD when active.

    This is called once during gateway startup.
    """
    import importlib

    for mod_name in (
        "code_puppy.tools.file_operations",
        "code_puppy.tools.file_modifications",
    ):
        try:
            mod = importlib.import_module(mod_name)
            mod.os.path.abspath = session_aware_abspath  # type: ignore[attr-defined]
        except (ImportError, AttributeError):
            pass
