import json
from types import ModuleType
from typing import Any, List, Set

import pydantic

_tui_mode: bool = False
_tui_app_instance: Any = None


def _require_agent_manager() -> ModuleType:
    """Import the agent manager module, raising if it is unavailable."""
    try:
        from code_puppy.agents import agent_manager
    except Exception as error:  # pragma: no cover - import errors surface immediately
        raise RuntimeError("Agent manager module unavailable") from error
    return agent_manager


def add_compacted_message_hash(message_hash: str) -> None:
    """Add a message hash to the set of compacted message hashes."""
    manager = _require_agent_manager()
    manager.add_current_agent_compacted_message_hash(message_hash)


def get_compacted_message_hashes() -> Set[str]:
    """Get the set of compacted message hashes."""
    manager = _require_agent_manager()
    return manager.get_current_agent_compacted_message_hashes()


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
    """Get message history for the active agent."""
    manager = _require_agent_manager()
    return manager.get_current_agent_message_history()


def set_message_history(history: List[Any]) -> None:
    """Replace the message history for the active agent."""
    manager = _require_agent_manager()
    manager.set_current_agent_message_history(history)


def clear_message_history() -> None:
    """Clear message history for the active agent."""
    manager = _require_agent_manager()
    manager.clear_current_agent_message_history()


def append_to_message_history(message: Any) -> None:
    """Append a message to the active agent's history."""
    manager = _require_agent_manager()
    manager.append_to_current_agent_message_history(message)


def extend_message_history(history: List[Any]) -> None:
    """Extend the active agent's message history."""
    manager = _require_agent_manager()
    manager.extend_current_agent_message_history(history)


def _stringify_part(part: Any) -> str:
    """Create a stable string representation for a message part.

    We deliberately ignore timestamps so identical content hashes the same even when
    emitted at different times. This prevents status updates from blowing up the
    history when they are repeated with new timestamps."""

    attributes: List[str] = [part.__class__.__name__]

    # Role/instructions help disambiguate parts that otherwise share content
    if hasattr(part, "role") and part.role:
        attributes.append(f"role={part.role}")
    if hasattr(part, "instructions") and part.instructions:
        attributes.append(f"instructions={part.instructions}")

    if hasattr(part, "tool_call_id") and part.tool_call_id:
        attributes.append(f"tool_call_id={part.tool_call_id}")

    if hasattr(part, "tool_name") and part.tool_name:
        attributes.append(f"tool_name={part.tool_name}")

    content = getattr(part, "content", None)
    if content is None:
        attributes.append("content=None")
    elif isinstance(content, str):
        attributes.append(f"content={content}")
    elif isinstance(content, pydantic.BaseModel):
        attributes.append(f"content={json.dumps(content.model_dump(), sort_keys=True)}")
    elif isinstance(content, dict):
        attributes.append(f"content={json.dumps(content, sort_keys=True)}")
    else:
        attributes.append(f"content={repr(content)}")

    return "|".join(attributes)


def hash_message(message: Any) -> int:
    """Create a stable hash for a model message that ignores timestamps."""
    role = getattr(message, "role", None)
    instructions = getattr(message, "instructions", None)
    header_bits: List[str] = []
    if role:
        header_bits.append(f"role={role}")
    if instructions:
        header_bits.append(f"instructions={instructions}")

    part_strings = [_stringify_part(part) for part in getattr(message, "parts", [])]
    canonical = "||".join(header_bits + part_strings)
    return hash(canonical)
