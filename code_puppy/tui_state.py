# TUI State Management
# This module contains functions for managing the global TUI state

from typing import Any

# Global TUI state variables
_tui_mode: bool = False
_tui_app_instance: Any = None


def set_tui_mode(enabled: bool) -> None:
    """Set the global TUI mode state.

    Args:
        enabled: True if running in TUI mode, False otherwise
    """
    global _tui_mode
    _tui_mode = enabled


def is_tui_mode() -> bool:
    """Check if the application is running in TUI mode.

    Returns:
        True if running in TUI mode, False otherwise
    """
    return _tui_mode


def set_tui_app_instance(app_instance: Any) -> None:
    """Set the global TUI app instance reference.

    Args:
        app_instance: The TUI app instance
    """
    global _tui_app_instance
    _tui_app_instance = app_instance


def get_tui_app_instance() -> Any:
    """Get the current TUI app instance.

    Returns:
        The TUI app instance if available, None otherwise
    """
    return _tui_app_instance


def get_tui_mode() -> bool:
    """Get the current TUI mode state.

    Returns:
        True if running in TUI mode, False otherwise
    """
    return _tui_mode
