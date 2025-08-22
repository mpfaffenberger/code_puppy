from typing import Any, List

_message_history: List[Any] = []
_compacted_message_hashes = set()
_tui_mode: bool = False
_tui_app_instance: Any = None


def add_compacted_message_hash(message_hash: str) -> None:
    """Add a message hash to the set of compacted message hashes."""
    _compacted_message_hashes.add(message_hash)


def get_compacted_message_hashes():
    """Get the set of compacted message hashes."""
    return _compacted_message_hashes


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


def get_message_history() -> List[Any]:
    return _message_history


def set_message_history(history: List[Any]) -> None:
    global _message_history
    _message_history = history


def clear_message_history() -> None:
    global _message_history
    _message_history = []


def append_to_message_history(message: Any) -> None:
    _message_history.append(message)


def extend_message_history(history: List[Any]) -> None:
    _message_history.extend(history)


def hash_message(message):
    hashable_entities = []
    for part in message.parts:
        if hasattr(part, "timestamp"):
            hashable_entities.append(part.timestamp.isoformat())
        elif hasattr(part, "tool_call_id"):
            hashable_entities.append(part.tool_call_id)
        else:
            hashable_entities.append(part.content)
    return hash(",".join(hashable_entities))
