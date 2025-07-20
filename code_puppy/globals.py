"""
Global variables and state management for Code Puppy.

This module provides a centralized location for global state that needs to be
accessed across different modules in the application.
"""

# Global variable to track TUI mode
_tui_mode = False


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


def get_tui_mode() -> bool:
    """Get the current TUI mode state.
    
    Returns:
        True if running in TUI mode, False otherwise
    """
    return _tui_mode