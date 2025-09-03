from typing import Any, List

# Legacy global state - maintained for backward compatibility
_message_history: List[Any] = []
_compacted_message_hashes = set()

# Flag to control whether to use agent-specific history (True) or global history (False)
_use_agent_specific_history = True
_tui_mode: bool = False
_tui_app_instance: Any = None


def add_compacted_message_hash(message_hash: str) -> None:
    """Add a message hash to the set of compacted message hashes."""
    if _use_agent_specific_history:
        try:
            from code_puppy.agents.agent_manager import (
                add_current_agent_compacted_message_hash,
            )

            add_current_agent_compacted_message_hash(message_hash)
            return
        except Exception:
            # Fallback to global if agent system fails
            pass
    _compacted_message_hashes.add(message_hash)


def get_compacted_message_hashes():
    """Get the set of compacted message hashes."""
    if _use_agent_specific_history:
        try:
            from code_puppy.agents.agent_manager import (
                get_current_agent_compacted_message_hashes,
            )

            return get_current_agent_compacted_message_hashes()
        except Exception:
            # Fallback to global if agent system fails
            pass
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
    """Get message history - uses agent-specific history if enabled, otherwise global."""
    if _use_agent_specific_history:
        try:
            from code_puppy.agents.agent_manager import (
                get_current_agent_message_history,
            )

            return get_current_agent_message_history()
        except Exception:
            # Fallback to global if agent system fails
            return _message_history
    return _message_history


def set_message_history(history: List[Any]) -> None:
    """Set message history - uses agent-specific history if enabled, otherwise global."""
    if _use_agent_specific_history:
        try:
            from code_puppy.agents.agent_manager import (
                set_current_agent_message_history,
            )

            set_current_agent_message_history(history)
            return
        except Exception:
            # Fallback to global if agent system fails
            pass
    global _message_history
    _message_history = history


def clear_message_history() -> None:
    """Clear message history - uses agent-specific history if enabled, otherwise global."""
    if _use_agent_specific_history:
        try:
            from code_puppy.agents.agent_manager import (
                clear_current_agent_message_history,
            )

            clear_current_agent_message_history()
            return
        except Exception:
            # Fallback to global if agent system fails
            pass
    global _message_history
    _message_history = []


def append_to_message_history(message: Any) -> None:
    """Append to message history - uses agent-specific history if enabled, otherwise global."""
    if _use_agent_specific_history:
        try:
            from code_puppy.agents.agent_manager import (
                append_to_current_agent_message_history,
            )

            append_to_current_agent_message_history(message)
            return
        except Exception:
            # Fallback to global if agent system fails
            pass
    _message_history.append(message)


def extend_message_history(history: List[Any]) -> None:
    """Extend message history - uses agent-specific history if enabled, otherwise global."""
    if _use_agent_specific_history:
        try:
            from code_puppy.agents.agent_manager import (
                extend_current_agent_message_history,
            )

            extend_current_agent_message_history(history)
            return
        except Exception:
            # Fallback to global if agent system fails
            pass
    _message_history.extend(history)


def set_use_agent_specific_history(enabled: bool) -> None:
    """Enable or disable agent-specific message history.

    Args:
        enabled: True to use per-agent history, False to use global history.
    """
    global _use_agent_specific_history
    _use_agent_specific_history = enabled


def is_using_agent_specific_history() -> bool:
    """Check if agent-specific message history is enabled.

    Returns:
        True if using per-agent history, False if using global history.
    """
    return _use_agent_specific_history


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
