"""
Shared spinner implementation for CLI mode.

This module provides consistent spinner animations across different UI modes.
Also provides pause coordination with PauseManager for pause+steer feature.
"""

import logging

from .console_spinner import ConsoleSpinner
from .spinner_base import SpinnerBase

logger = logging.getLogger(__name__)

# Keep track of all active spinners to manage them globally
_active_spinners = []

# Track if we've registered the pause callback
_pause_callback_registered = False


def register_spinner(spinner):
    """Register an active spinner to be managed globally."""
    if spinner not in _active_spinners:
        _active_spinners.append(spinner)


def unregister_spinner(spinner):
    """Remove a spinner from global management."""
    if spinner in _active_spinners:
        _active_spinners.remove(spinner)


def pause_all_spinners():
    """Pause all active spinners.

    No-op when called from a sub-agent context to prevent
    parallel sub-agents from interfering with the main spinner.
    """
    # Lazy import to avoid circular dependency
    from code_puppy.tools.subagent_context import is_subagent

    if is_subagent():
        return  # Sub-agents don't control the main spinner
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
    """
    # Lazy import to avoid circular dependency
    from code_puppy.tools.subagent_context import is_subagent

    if is_subagent():
        return  # Sub-agents don't control the main spinner
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


def _on_pause_state_change(is_paused: bool) -> None:
    """Callback for PauseManager to pause/resume spinners.

    Args:
        is_paused: True if pause requested, False if resume requested
    """
    if is_paused:
        pause_all_spinners()
    else:
        resume_all_spinners()


def setup_pause_coordination() -> None:
    """Setup pause coordination with PauseManager.

    Registers a callback so spinners are automatically paused when
    the PauseManager requests a global pause, and resumed on resume.

    Safe to call multiple times - only registers once.
    """
    global _pause_callback_registered
    if _pause_callback_registered:
        return

    try:
        from code_puppy.pause_manager import get_pause_manager

        pm = get_pause_manager()
        pm.add_pause_callback(_on_pause_state_change)
        _pause_callback_registered = True
        logger.debug("Spinner pause coordination registered with PauseManager")
    except ImportError:
        logger.debug("PauseManager not available, skipping pause coordination")
    except Exception as e:
        logger.debug(f"Error setting up pause coordination: {e}")


def teardown_pause_coordination() -> None:
    """Teardown pause coordination (for testing)."""
    global _pause_callback_registered
    if not _pause_callback_registered:
        return

    try:
        from code_puppy.pause_manager import get_pause_manager

        pm = get_pause_manager()
        pm.remove_pause_callback(_on_pause_state_change)
        _pause_callback_registered = False
        logger.debug("Spinner pause coordination unregistered")
    except Exception as e:
        logger.debug(f"Error tearing down pause coordination: {e}")


__all__ = [
    "SpinnerBase",
    "ConsoleSpinner",
    "register_spinner",
    "unregister_spinner",
    "pause_all_spinners",
    "resume_all_spinners",
    "update_spinner_context",
    "clear_spinner_context",
    "setup_pause_coordination",
    "teardown_pause_coordination",
]
