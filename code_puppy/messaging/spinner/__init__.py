"""
Shared spinner implementation for CLI mode.

This module provides consistent spinner animations across different UI modes.
"""

from .console_spinner import ConsoleSpinner
from .spinner_base import SpinnerBase

# Keep track of all active spinners to manage them globally
_active_spinners = []


def register_spinner(spinner):
    """Register an active spinner to be managed globally."""
    if spinner not in _active_spinners:
        _active_spinners.append(spinner)


def unregister_spinner(spinner):
    """Remove a spinner from global management."""
    if spinner in _active_spinners:
        _active_spinners.remove(spinner)


def get_active_spinner():
    """Return the most-recently registered active spinner, or ``None``.

    Used by the event-stream handler and the activity plugin to find the
    ``ConsoleSpinner`` whose ``Live`` owns the current turn's output — they
    hand streamed text / stacked step rows to its ``print_above`` so the
    footer stays pinned and uncorrupted.
    """
    if not _active_spinners:
        return None
    # Return the most recent (top of stack) — matches the LIFO nature of
    # nested spinner contexts.
    return _active_spinners[-1]


def pause_all_spinners():
    """Pause all active spinners.

    No-op when called from a sub-agent context to prevent
    parallel sub-agents from interfering with the main spinner.

    Exception: in ``high`` output mode, sub-agent streams render
    inline and need spinner coordination to avoid visual corruption.

    Also a no-op when compact-steps (Option B) is active: the spinner's
    ``Live`` region owns the whole turn's output, and Rich coordinates
    above-prints automatically, so pausing the Live would just kill the
    heartbeat footer without buying us anything.
    """
    # Lazy import to avoid circular dependency
    from code_puppy.tools.subagent_context import is_subagent

    if is_subagent():
        from code_puppy.config import get_output_level

        if get_output_level() != "high":
            return  # Sub-agents don't control the main spinner
    # Option B: never pause the Live-owned footer — Rich coordinates prints.
    if SpinnerBase.is_ledger_active():
        return
    for spinner in _active_spinners:
        try:
            spinner.pause()
        except Exception:
            # Ignore errors if a spinner can't be paused
            pass


def resume_all_spinners():
    """Resume all active spinners.

    No-op when called from a sub-agent context to prevent
    parallel sub-agents from interfering with the main spinner.

    Exception: in ``high`` output mode, sub-agent streams render
    inline and need spinner coordination to avoid visual corruption.

    Also a no-op when compact-steps (Option B) is active — see
    :func:`pause_all_spinners`.
    """
    # Lazy import to avoid circular dependency
    from code_puppy.tools.subagent_context import is_subagent

    if is_subagent():
        from code_puppy.config import get_output_level

        if get_output_level() != "high":
            return  # Sub-agents don't control the main spinner
    # Option B: nothing to resume — we never paused.
    if SpinnerBase.is_ledger_active():
        return
    for spinner in _active_spinners:
        try:
            spinner.resume()
        except Exception:
            # Ignore errors if a spinner can't be resumed
            pass


def update_spinner_context(info: str) -> None:
    """Update the shared context information displayed beside active spinners."""
    SpinnerBase.set_context_info(info)


def clear_spinner_context() -> None:
    """Clear any context information displayed beside active spinners."""
    SpinnerBase.clear_context_info()


__all__ = [
    "SpinnerBase",
    "ConsoleSpinner",
    "register_spinner",
    "unregister_spinner",
    "get_active_spinner",
    "pause_all_spinners",
    "resume_all_spinners",
    "update_spinner_context",
    "clear_spinner_context",
]
