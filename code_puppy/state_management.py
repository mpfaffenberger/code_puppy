"""
Global state management for Code Puppy.

This module provides a centralized location for global state that needs to be
accessed across different modules in the application. This includes TUI mode
tracking and message history management.
"""

from typing import Any, List

# Global variable to track TUI mode
_tui_mode = False

# Global variable to store message history for interactive sessions
_message_history: List[Any] = []


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


def get_message_history() -> List[Any]:
    """Get the current message history.

    Returns:
        A list of messages from the current session
    """
    return _message_history


def set_message_history(history: List[Any]) -> None:
    """Set the message history.

    Args:
        history: List of messages to set as the current history
    """
    global _message_history
    _message_history = history


def clear_message_history() -> None:
    """Clear the message history."""
    global _message_history
    _message_history = []


def append_to_message_history(message: Any) -> None:
    """Add a message to the history.

    Args:
        message: Message to add to the history
    """
    _message_history.append(message)


def extend_message_history(messages: List[Any]) -> None:
    """Extend the message history with multiple messages.

    Args:
        messages: List of messages to add to the history
    """
    _message_history.extend(messages)
