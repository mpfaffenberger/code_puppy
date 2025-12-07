"""Agent manager for handling different agent configurations."""

import importlib
import json
import os
import pkgutil
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Type, Union

from pydantic_ai.messages import ModelMessage

from code_puppy.agents.base_agent import BaseAgent
from code_puppy.agents.json_agent import JSONAgent, discover_json_agents
from code_puppy.callbacks import on_agent_reload
from code_puppy.messaging import emit_warning

# Registry of available agents (Python classes and JSON file paths)
_AGENT_REGISTRY: Dict[str, Union[Type[BaseAgent], str]] = {}
_AGENT_HISTORIES: Dict[str, List[ModelMessage]] = {}
_CURRENT_AGENT: Optional[BaseAgent] = None

# Terminal session-based agent selection
_SESSION_AGENTS_CACHE: dict[str, str] = {}
_SESSION_FILE_LOADED: bool = False


# Session persistence file path
def _get_session_file_path() -> Path:
    """Get the path to the terminal sessions file."""
    from ..config import STATE_DIR

    return Path(STATE_DIR) / "terminal_sessions.json"


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
    """Check if a process with the given PID is still alive, cross-platform.

    Args:
        pid: Process ID to check

    Returns:
        bool: True if process likely exists, False otherwise
    """
    try:
        if os.name == "nt":
            # Windows: use OpenProcess to probe liveness safely
            import ctypes
            from ctypes import wintypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            kernel32.OpenProcess.argtypes = [
                wintypes.DWORD,
                wintypes.BOOL,
                wintypes.DWORD,
            ]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
            )
            if handle:
                kernel32.CloseHandle(handle)
                return True
            # If access denied, process likely exists but we can't query it
            last_error = kernel32.GetLastError()
            # ERROR_ACCESS_DENIED = 5
            if last_error == 5:
                return True
            return False
        else:
            # Unix-like: signal 0 does not deliver a signal but checks existence
            os.kill(int(pid), 0)
            return True
    except PermissionError:
        # No permission to signal -> process exists
        return True
    except (OSError, ProcessLookupError):
        # Process does not exist
        return False
    except ValueError:
        # Invalid signal or pid format
        return False
    except Exception:
        # Be conservative – don't crash session cleanup due to platform quirks
        return True


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
        The name of the current agent for this session.
        Priority: session agent > config default > 'code-puppy'.
    """
    _ensure_session_cache_loaded()
    session_id = get_terminal_session_id()

    # First check for session-specific agent
    session_agent = _SESSION_AGENTS_CACHE.get(session_id)
    if session_agent:
        return session_agent

    # Fall back to config default
    from ..config import get_default_agent

    return get_default_agent()


def set_current_agent(agent_name: str) -> bool:
    """Set the current agent by name.

    Args:
        agent_name: The name of the agent to set as current.

    Returns:
        True if the agent was set successfully, False if agent not found.
    """
    global _CURRENT_AGENT
    curr_agent = get_current_agent()
    if curr_agent is not None:
        # Store a shallow copy so future mutations don't affect saved history
        _AGENT_HISTORIES[curr_agent.name] = list(curr_agent.get_message_history())
    # Generate a message group ID for agent switching
    message_group_id = str(uuid.uuid4())
    _discover_agents(message_group_id=message_group_id)

    # Save current agent's history before switching

    # Clear the cached config when switching agents
    agent_obj = load_agent(agent_name)
    _CURRENT_AGENT = agent_obj

    # Update session-based agent selection and persist to disk
    _ensure_session_cache_loaded()
    session_id = get_terminal_session_id()
    _SESSION_AGENTS_CACHE[session_id] = agent_name
    _save_session_data(_SESSION_AGENTS_CACHE)
    if agent_obj.name in _AGENT_HISTORIES:
        # Restore a copy to avoid sharing the same list instance
        agent_obj.set_message_history(list(_AGENT_HISTORIES[agent_obj.name]))
    on_agent_reload(agent_obj.id, agent_name)
    return True


def get_current_agent() -> BaseAgent:
    """Get the current agent configuration.

    Returns:
        The current agent configuration instance.
    """
    global _CURRENT_AGENT

    if _CURRENT_AGENT is None:
        agent_name = get_current_agent_name()
        _CURRENT_AGENT = load_agent(agent_name)

    return _CURRENT_AGENT


def load_agent(agent_name: str) -> BaseAgent:
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


def refresh_agents():
    """Refresh the agent discovery to pick up newly created agents.

    This clears the agent registry cache and forces a rediscovery of all agents.
    """
    # Generate a message group ID for agent refreshing
    message_group_id = str(uuid.uuid4())
    _discover_agents(message_group_id=message_group_id)
