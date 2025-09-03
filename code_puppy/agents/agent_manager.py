"""Agent manager for handling different agent configurations."""

import importlib
import json
import os
import pkgutil
import uuid
from pathlib import Path
from typing import Dict, Optional, Type, Union

from ..callbacks import on_agent_reload
from ..messaging import emit_warning
from .base_agent import BaseAgent
from .json_agent import JSONAgent, discover_json_agents

# Registry of available agents (Python classes and JSON file paths)
_AGENT_REGISTRY: Dict[str, Union[Type[BaseAgent], str]] = {}
_CURRENT_AGENT_CONFIG: Optional[BaseAgent] = None

# Terminal session-based agent selection
_SESSION_AGENTS_CACHE: dict[str, str] = {}
_SESSION_FILE_LOADED: bool = False


# Session persistence file path
def _get_session_file_path() -> Path:
    """Get the path to the terminal sessions file."""
    from ..config import CONFIG_DIR

    return Path(CONFIG_DIR) / "terminal_sessions.json"


def get_terminal_session_id() -> str:
    """Get a unique identifier for the current terminal session.

    Uses parent process ID (PPID) as the session identifier.
    This works across all platforms and provides session isolation.

    Returns:
        str: Unique session identifier (e.g., "session_12345")
    """
    try:
        ppid = os.getppid()
        return f"session_{ppid}"
    except (OSError, AttributeError):
        # Fallback to current process ID if PPID unavailable
        return f"fallback_{os.getpid()}"


def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID is still alive.

    Args:
        pid: Process ID to check

    Returns:
        bool: True if process exists, False otherwise
    """
    try:
        # On Unix: os.kill(pid, 0) raises OSError if process doesn't exist
        # On Windows: This also works with signal 0
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _cleanup_dead_sessions(sessions: dict[str, str]) -> dict[str, str]:
    """Remove sessions for processes that no longer exist.

    Args:
        sessions: Dictionary of session_id -> agent_name

    Returns:
        dict: Cleaned sessions dictionary
    """
    cleaned = {}
    for session_id, agent_name in sessions.items():
        if session_id.startswith("session_"):
            try:
                pid_str = session_id.replace("session_", "")
                pid = int(pid_str)
                if _is_process_alive(pid):
                    cleaned[session_id] = agent_name
                # else: skip dead session
            except (ValueError, TypeError):
                # Invalid session ID format, keep it anyway
                cleaned[session_id] = agent_name
        else:
            # Non-standard session ID (like "fallback_"), keep it
            cleaned[session_id] = agent_name
    return cleaned


def _load_session_data() -> dict[str, str]:
    """Load terminal session data from the JSON file.

    Returns:
        dict: Session ID to agent name mapping
    """
    session_file = _get_session_file_path()
    try:
        if session_file.exists():
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Clean up dead sessions while loading
                return _cleanup_dead_sessions(data)
        return {}
    except (json.JSONDecodeError, IOError, OSError):
        # File corrupted or permission issues, start fresh
        return {}


def _save_session_data(sessions: dict[str, str]) -> None:
    """Save terminal session data to the JSON file.

    Args:
        sessions: Session ID to agent name mapping
    """
    session_file = _get_session_file_path()
    try:
        # Ensure the config directory exists
        session_file.parent.mkdir(parents=True, exist_ok=True)

        # Clean up dead sessions before saving
        cleaned_sessions = _cleanup_dead_sessions(sessions)

        # Write to file atomically (write to temp file, then rename)
        temp_file = session_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(cleaned_sessions, f, indent=2)

        # Atomic rename (works on all platforms)
        temp_file.replace(session_file)

    except (IOError, OSError):
        # File permission issues, etc. - just continue without persistence
        pass


def _ensure_session_cache_loaded() -> None:
    """Ensure the session cache is loaded from disk."""
    global _SESSION_AGENTS_CACHE, _SESSION_FILE_LOADED
    if not _SESSION_FILE_LOADED:
        _SESSION_AGENTS_CACHE.update(_load_session_data())
        _SESSION_FILE_LOADED = True


# Persistent storage for agent message histories
_AGENT_HISTORIES: Dict[str, Dict[str, any]] = {}
# Structure: {agent_name: {"message_history": [...], "compacted_hashes": set(...)}}


def _save_agent_history(agent_name: str, agent: BaseAgent) -> None:
    """Save an agent's message history to persistent storage.

    Args:
        agent_name: The name of the agent
        agent: The agent instance to save history from
    """
    global _AGENT_HISTORIES
    _AGENT_HISTORIES[agent_name] = {
        "message_history": agent.get_message_history().copy(),
        "compacted_hashes": agent.get_compacted_message_hashes().copy(),
    }


def _restore_agent_history(agent_name: str, agent: BaseAgent) -> None:
    """Restore an agent's message history from persistent storage.

    Args:
        agent_name: The name of the agent
        agent: The agent instance to restore history to
    """
    global _AGENT_HISTORIES
    if agent_name in _AGENT_HISTORIES:
        stored_data = _AGENT_HISTORIES[agent_name]
        agent.set_message_history(stored_data["message_history"])
        # Restore compacted hashes
        for hash_val in stored_data["compacted_hashes"]:
            agent.add_compacted_message_hash(hash_val)


def _discover_agents(message_group_id: Optional[str] = None):
    """Dynamically discover all agent classes and JSON agents."""
    # Always clear the registry to force refresh
    _AGENT_REGISTRY.clear()

    # 1. Discover Python agent classes in the agents package
    import code_puppy.agents as agents_package

    # Iterate through all modules in the agents package
    for _, modname, _ in pkgutil.iter_modules(agents_package.__path__):
        if modname.startswith("_") or modname in [
            "base_agent",
            "json_agent",
            "agent_manager",
        ]:
            continue

        try:
            # Import the module
            module = importlib.import_module(f"code_puppy.agents.{modname}")

            # Look for BaseAgent subclasses
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseAgent)
                    and attr not in [BaseAgent, JSONAgent]
                ):
                    # Create an instance to get the name
                    agent_instance = attr()
                    _AGENT_REGISTRY[agent_instance.name] = attr

        except Exception as e:
            # Skip problematic modules
            emit_warning(
                f"Warning: Could not load agent module {modname}: {e}",
                message_group=message_group_id,
            )
            continue

    # 2. Discover JSON agents in user directory
    try:
        json_agents = discover_json_agents()

        # Add JSON agents to registry (store file path instead of class)
        for agent_name, json_path in json_agents.items():
            _AGENT_REGISTRY[agent_name] = json_path

    except Exception as e:
        emit_warning(
            f"Warning: Could not discover JSON agents: {e}",
            message_group=message_group_id,
        )


def get_available_agents() -> Dict[str, str]:
    """Get a dictionary of available agents with their display names.

    Returns:
        Dict mapping agent names to display names.
    """
    # Generate a message group ID for this operation
    message_group_id = str(uuid.uuid4())
    _discover_agents(message_group_id=message_group_id)

    agents = {}
    for name, agent_ref in _AGENT_REGISTRY.items():
        try:
            if isinstance(agent_ref, str):  # JSON agent (file path)
                agent_instance = JSONAgent(agent_ref)
            else:  # Python agent (class)
                agent_instance = agent_ref()
            agents[name] = agent_instance.display_name
        except Exception:
            agents[name] = name.title()  # Fallback

    return agents


def get_current_agent_name() -> str:
    """Get the name of the currently active agent for this terminal session.

    Returns:
        The name of the current agent for this session, defaults to 'code-puppy'.
    """
    _ensure_session_cache_loaded()
    session_id = get_terminal_session_id()
    return _SESSION_AGENTS_CACHE.get(session_id, "code-puppy")


def set_current_agent(agent_name: str) -> bool:
    """Set the current agent by name.

    Args:
        agent_name: The name of the agent to set as current.

    Returns:
        True if the agent was set successfully, False if agent not found.
    """
    # Generate a message group ID for agent switching
    message_group_id = str(uuid.uuid4())
    _discover_agents(message_group_id=message_group_id)

    # Save current agent's history before switching
    global _CURRENT_AGENT_CONFIG, _CURRENT_AGENT_NAME
    if _CURRENT_AGENT_CONFIG is not None:
        _save_agent_history(_CURRENT_AGENT_CONFIG.name, _CURRENT_AGENT_CONFIG)

    # Clear the cached config when switching agents
    _CURRENT_AGENT_CONFIG = None
    agent_obj = load_agent_config(agent_name)

    # Restore the agent's history if it exists
    _restore_agent_history(agent_name, agent_obj)

    # Update session-based agent selection and persist to disk
    _ensure_session_cache_loaded()
    session_id = get_terminal_session_id()
    _SESSION_AGENTS_CACHE[session_id] = agent_name
    _save_session_data(_SESSION_AGENTS_CACHE)

    on_agent_reload(agent_obj.id, agent_name)
    return True


def get_current_agent_config() -> BaseAgent:
    """Get the current agent configuration.

    Returns:
        The current agent configuration instance.
    """
    global _CURRENT_AGENT_CONFIG

    if _CURRENT_AGENT_CONFIG is None:
        agent_name = get_current_agent_name()
        _CURRENT_AGENT_CONFIG = load_agent_config(agent_name)
        # Restore the agent's history if it exists
        _restore_agent_history(agent_name, _CURRENT_AGENT_CONFIG)

    return _CURRENT_AGENT_CONFIG


def load_agent_config(agent_name: str) -> BaseAgent:
    """Load an agent configuration by name.

    Args:
        agent_name: The name of the agent to load.

    Returns:
        The agent configuration instance.

    Raises:
        ValueError: If the agent is not found.
    """
    # Generate a message group ID for agent loading
    message_group_id = str(uuid.uuid4())
    _discover_agents(message_group_id=message_group_id)

    if agent_name not in _AGENT_REGISTRY:
        # Fallback to code-puppy if agent not found
        if "code-puppy" in _AGENT_REGISTRY:
            agent_name = "code-puppy"
        else:
            raise ValueError(
                f"Agent '{agent_name}' not found and no fallback available"
            )

    agent_ref = _AGENT_REGISTRY[agent_name]
    if isinstance(agent_ref, str):  # JSON agent (file path)
        return JSONAgent(agent_ref)
    else:  # Python agent (class)
        return agent_ref()


def get_agent_descriptions() -> Dict[str, str]:
    """Get descriptions for all available agents.

    Returns:
        Dict mapping agent names to their descriptions.
    """
    # Generate a message group ID for this operation
    message_group_id = str(uuid.uuid4())
    _discover_agents(message_group_id=message_group_id)

    descriptions = {}
    for name, agent_ref in _AGENT_REGISTRY.items():
        try:
            if isinstance(agent_ref, str):  # JSON agent (file path)
                agent_instance = JSONAgent(agent_ref)
            else:  # Python agent (class)
                agent_instance = agent_ref()
            descriptions[name] = agent_instance.description
        except Exception:
            descriptions[name] = "No description available"

    return descriptions


def clear_agent_cache():
    """Clear the cached agent configuration to force reload."""
    global _CURRENT_AGENT_CONFIG
    _CURRENT_AGENT_CONFIG = None


def reset_to_default_agent():
    """Reset the current agent to the default (code-puppy) for this terminal session.

    This is useful for testing or when you want to start fresh.
    """
    global _CURRENT_AGENT_CONFIG
    _ensure_session_cache_loaded()
    session_id = get_terminal_session_id()
    if session_id in _SESSION_AGENTS_CACHE:
        del _SESSION_AGENTS_CACHE[session_id]
        _save_session_data(_SESSION_AGENTS_CACHE)
    _CURRENT_AGENT_CONFIG = None


def refresh_agents():
    """Refresh the agent discovery to pick up newly created agents.

    This clears the agent registry cache and forces a rediscovery of all agents.
    """
    # Generate a message group ID for agent refreshing
    message_group_id = str(uuid.uuid4())
    _discover_agents(message_group_id=message_group_id)


def clear_all_agent_histories():
    """Clear all agent message histories from persistent storage.

    This is useful for debugging or when you want a fresh start.
    """
    global _AGENT_HISTORIES
    _AGENT_HISTORIES.clear()
    # Also clear the current agent's history
    if _CURRENT_AGENT_CONFIG is not None:
        _CURRENT_AGENT_CONFIG.messages = []


def cleanup_dead_terminal_sessions() -> int:
    """Clean up terminal sessions for processes that no longer exist.

    Returns:
        int: Number of dead sessions removed
    """
    _ensure_session_cache_loaded()
    original_count = len(_SESSION_AGENTS_CACHE)
    cleaned_cache = _cleanup_dead_sessions(_SESSION_AGENTS_CACHE)

    if len(cleaned_cache) != original_count:
        _SESSION_AGENTS_CACHE.clear()
        _SESSION_AGENTS_CACHE.update(cleaned_cache)
        _save_session_data(_SESSION_AGENTS_CACHE)

    return original_count - len(cleaned_cache)


# Agent-aware message history functions
def get_current_agent_message_history():
    """Get the message history for the currently active agent.

    Returns:
        List of messages from the current agent's conversation history.
    """
    current_agent = get_current_agent_config()
    return current_agent.get_message_history()


def set_current_agent_message_history(history):
    """Set the message history for the currently active agent.

    Args:
        history: List of messages to set as the current agent's conversation history.
    """
    current_agent = get_current_agent_config()
    current_agent.set_message_history(history)
    # Also update persistent storage
    _save_agent_history(current_agent.name, current_agent)


def clear_current_agent_message_history():
    """Clear the message history for the currently active agent."""
    current_agent = get_current_agent_config()
    current_agent.clear_message_history()
    # Also clear from persistent storage
    global _AGENT_HISTORIES
    if current_agent.name in _AGENT_HISTORIES:
        _AGENT_HISTORIES[current_agent.name] = {
            "message_history": [],
            "compacted_hashes": set(),
        }


def append_to_current_agent_message_history(message):
    """Append a message to the currently active agent's history.

    Args:
        message: Message to append to the current agent's conversation history.
    """
    current_agent = get_current_agent_config()
    current_agent.append_to_message_history(message)
    # Also update persistent storage
    _save_agent_history(current_agent.name, current_agent)


def extend_current_agent_message_history(history):
    """Extend the currently active agent's message history with multiple messages.

    Args:
        history: List of messages to append to the current agent's conversation history.
    """
    current_agent = get_current_agent_config()
    current_agent.extend_message_history(history)
    # Also update persistent storage
    _save_agent_history(current_agent.name, current_agent)


def get_current_agent_compacted_message_hashes():
    """Get the set of compacted message hashes for the currently active agent.

    Returns:
        Set of hashes for messages that have been compacted/summarized.
    """
    current_agent = get_current_agent_config()
    return current_agent.get_compacted_message_hashes()


def add_current_agent_compacted_message_hash(message_hash: str):
    """Add a message hash to the current agent's set of compacted message hashes.

    Args:
        message_hash: Hash of a message that has been compacted/summarized.
    """
    current_agent = get_current_agent_config()
    current_agent.add_compacted_message_hash(message_hash)
    # Also update persistent storage
    _save_agent_history(current_agent.name, current_agent)
