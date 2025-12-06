"""ACP session and connection state management.

This module manages the global state for ACP connections, including:
- Protocol negotiation state
- Active sessions and their message histories
- Client capabilities
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ACPSession:
    """Represents an ACP session.

    Each session maintains its own conversation history and context,
    allowing multiple independent coding sessions within the same
    ACP connection.

    Attributes:
        session_id: Unique identifier for this session
        cwd: Working directory for file operations
        agent_name: Name of the agent handling this session
        message_history: Conversation history for this session
        mcp_servers: MCP server configurations for this session
    """

    session_id: str
    cwd: str
    agent_name: str = "code-puppy"
    message_history: List[Any] = field(default_factory=list)
    mcp_servers: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ACPState:
    """Global state for the ACP agent.

    Tracks the overall connection state, including protocol version
    negotiation and all active sessions.

    Attributes:
        initialized: Whether the connection has been initialized
        protocol_version: Negotiated protocol version
        client_capabilities: Capabilities reported by the client
        sessions: Map of session_id to ACPSession objects
    """

    initialized: bool = False
    protocol_version: int = 1
    client_capabilities: Dict[str, Any] = field(default_factory=dict)
    sessions: Dict[str, ACPSession] = field(default_factory=dict)


# Global state instance - singleton pattern for ACP connection
_state: Optional[ACPState] = None


def get_state() -> ACPState:
    """Get the global ACP state, creating if needed.

    Returns:
        The global ACPState instance
    """
    global _state
    if _state is None:
        _state = ACPState()
    return _state


def reset_state() -> None:
    """Reset the global state (primarily for testing).

    This clears all sessions and resets initialization state.
    """
    global _state
    _state = None


def get_session(session_id: str) -> Optional[ACPSession]:
    """Get a session by ID.

    Args:
        session_id: The session identifier to look up

    Returns:
        The ACPSession if found, None otherwise
    """
    state = get_state()
    return state.sessions.get(session_id)


def create_session(
    session_id: str, cwd: str, agent_name: str = "code-puppy"
) -> ACPSession:
    """Create a new session and add it to the state.

    Args:
        session_id: Unique identifier for the session
        cwd: Working directory for the session
        agent_name: Name of the agent to use

    Returns:
        The newly created ACPSession
    """
    state = get_state()
    session = ACPSession(
        session_id=session_id,
        cwd=cwd,
        agent_name=agent_name,
    )
    state.sessions[session_id] = session
    return session


def remove_session(session_id: str) -> bool:
    """Remove a session from the state.

    Args:
        session_id: The session to remove

    Returns:
        True if session was found and removed, False otherwise
    """
    state = get_state()
    if session_id in state.sessions:
        del state.sessions[session_id]
        return True
    return False
