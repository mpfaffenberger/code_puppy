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


def pause_all_spinners():
    """Pause all active spinners."""
    for spinner in _active_spinners:
        try:
            spinner.pause()
        except Exception:
            # Ignore errors if a spinner can't be paused
            pass


def resume_all_spinners():
    """Resume all active spinners."""
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
    "pause_all_spinners",
    "resume_all_spinners",
    "update_spinner_context",
    "clear_spinner_context",
]
