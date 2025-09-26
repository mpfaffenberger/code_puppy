from types import ModuleType
from typing import Any, List, Set

from code_puppy.messaging import emit_info


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



