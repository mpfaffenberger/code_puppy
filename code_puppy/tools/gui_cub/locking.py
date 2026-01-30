"""Simple guard to prevent multiple GUI-Cub agents from running simultaneously.

Desktop automation (mouse, keyboard, windows) cannot run in parallel.
This module provides a simple check to ensure only ONE GUI-Cub agent runs at a time.

Why This Matters:
- Can't control mouse/keyboard from multiple agents simultaneously
- Would cause unpredictable behavior and race conditions
- Desktop automation MUST be single-instance

Usage:
    from code_puppy.tools.gui_cub.locking import gui_cub_agent_guard

    # In agent initialization:
    with gui_cub_agent_guard():
        # Agent runs here
        # If another agent tries to start, it will raise GuiCubAlreadyRunningError
        ...
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Generator

__all__ = ["GuiCubAlreadyRunningError", "gui_cub_agent_guard", "is_gui_cub_active"]

# Global lock to prevent multiple GUI-Cub agents
_GUI_CUB_ACTIVE_LOCK = threading.Lock()
_gui_cub_is_active = False


class GuiCubAlreadyRunningError(RuntimeError):
    """Raised when trying to start a GUI-Cub agent while another is already running."""

    def __init__(self):
        super().__init__(
            "Another GUI-Cub agent is already running!\n"
            "Desktop automation cannot run in parallel.\n"
            "Please wait for the other agent to finish, or use /quit to stop it."
        )


@contextmanager
def gui_cub_agent_guard() -> Generator[None, None, None]:
    """Context manager to ensure only one GUI-Cub agent runs at a time.

    Raises:
        GuiCubAlreadyRunningError: If another GUI-Cub agent is already active

    Example:
        with gui_cub_agent_guard():
            # Run GUI-Cub agent
            # Guaranteed no other GUI-Cub agent is running
            ...
    """
    global _gui_cub_is_active

    with _GUI_CUB_ACTIVE_LOCK:
        if _gui_cub_is_active:
            raise GuiCubAlreadyRunningError()
        _gui_cub_is_active = True

    try:
        yield
    finally:
        with _GUI_CUB_ACTIVE_LOCK:
            _gui_cub_is_active = False


def is_gui_cub_active() -> bool:
    """Check if a GUI-Cub agent is currently running.

    Returns:
        True if a GUI-Cub agent is active, False otherwise
    """
    with _GUI_CUB_ACTIVE_LOCK:
        return _gui_cub_is_active
