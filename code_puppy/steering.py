"""SteeringManager - Global pause and steer control for multi-agent orchestration.

Provides a singleton manager that allows pausing all agents, queuing steering
messages (prompts), and tracking active agents. This enables a "Pause & Steer"
pattern where a supervisor can halt execution, inject new instructions, and
resume.

Usage:
    >>> manager = get_steering_manager()
    >>> manager.register_agent("session-123", "husky", "claude-3-5-sonnet")
    >>> manager.pause_all()  # Pauses all agents
    >>> manager.queue_message("session-123", "Focus on the login feature first")
    >>> manager.resume_all()  # Agents resume and receive queued messages

Async Usage (in agent code):
    >>> async def agent_loop():
    ...     manager = get_steering_manager()
    ...     while running:
    ...         await manager.wait_for_resume()  # Blocks if paused
    ...         messages = manager.get_queued_messages(session_id)
    ...         # Process messages...
"""

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# =============================================================================
# Agent Info Tracking
# =============================================================================


@dataclass
class AgentInfo:
    """Information about a registered agent.

    Stores metadata about an active agent for tracking and display purposes.
    """

    session_id: str
    agent_name: str
    model_name: str
    registered_at: float = field(default_factory=lambda: __import__("time").time())

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "model_name": self.model_name,
            "registered_at": self.registered_at,
        }


# =============================================================================
# Steering Manager Singleton
# =============================================================================


class SteeringManager:
    """Singleton manager for pause/resume control and steering messages.

    Provides centralized control for multi-agent orchestration:
    - Pause/resume all agents globally using an asyncio.Event
    - Queue steering messages (prompts) for specific agents
    - Track active agents and their metadata

    Thread Safety:
        All mutable state is protected by an RLock. The asyncio.Event is
        lazily initialized when first needed to ensure it's created in
        the correct event loop context.

    Pause Semantics:
        - Event SET = agents are NOT paused (can proceed)
        - Event CLEAR = agents ARE paused (wait_for_resume blocks)
        - Default state is SET (not paused)
    """

    _instance: Optional["SteeringManager"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        """Initialize the SteeringManager.

        Note: Use get_instance() or get_steering_manager() instead of
        direct instantiation to ensure singleton behavior.
        """
        self._state_lock = threading.RLock()  # Protects all mutable state
        self._pause_event: Optional[asyncio.Event] = None  # Lazy init
        self._paused: bool = False  # Track pause state independently
        self._message_queues: Dict[str, List[str]] = {}  # session_id -> messages
        self._agents: Dict[str, AgentInfo] = {}  # session_id -> AgentInfo

    @classmethod
    def get_instance(cls) -> "SteeringManager":
        """Get or create the singleton instance.

        Thread-safe singleton pattern using double-checked locking.

        Returns:
            The singleton SteeringManager instance.
        """
        if cls._instance is None:
            with cls._lock:
                # Double-check inside lock
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (primarily for testing).

        Clears the singleton and all its state.
        """
        with cls._lock:
            if cls._instance is not None:
                # Clear internal state
                with cls._instance._state_lock:
                    cls._instance._agents.clear()
                    cls._instance._message_queues.clear()
                    cls._instance._paused = False
                    cls._instance._pause_event = None
                cls._instance = None

    # =========================================================================
    # Pause Event Management
    # =========================================================================

    def _get_or_create_event(self) -> asyncio.Event:
        """Get or create the asyncio.Event for pause control.

        Lazily initializes the event to ensure it's created in the correct
        event loop context. The event starts in SET state (not paused).

        Returns:
            The asyncio.Event for pause control.
        """
        with self._state_lock:
            if self._pause_event is None:
                self._pause_event = asyncio.Event()
                # Start in SET state (not paused) unless we're already paused
                if not self._paused:
                    self._pause_event.set()
            return self._pause_event

    def pause_all(self) -> None:
        """Pause all agents.

        Clears the pause event, causing all agents calling wait_for_resume()
        to block until resume_all() is called.
        """
        with self._state_lock:
            self._paused = True
            if self._pause_event is not None:
                self._pause_event.clear()

    def resume_all(self) -> None:
        """Resume all paused agents.

        Sets the pause event, unblocking all agents waiting in
        wait_for_resume().
        """
        with self._state_lock:
            self._paused = False
            if self._pause_event is not None:
                self._pause_event.set()

    def is_paused(self) -> bool:
        """Check if agents are currently paused.

        Returns:
            True if pause_all() has been called and resume_all() has not
            been called since, False otherwise.
        """
        with self._state_lock:
            return self._paused

    async def wait_for_resume(self) -> None:
        """Wait until agents are resumed.

        Agents should call this method periodically to check if they should
        pause. If the manager is not paused, this returns immediately.
        If paused, this blocks until resume_all() is called.

        This is safe to call even if the event hasn't been created yet.
        """
        event = self._get_or_create_event()
        await event.wait()

    # =========================================================================
    # Message Queueing
    # =========================================================================

    def queue_message(self, session_id: str, message: str) -> None:
        """Queue a steering message for a specific agent.

        Messages are accumulated until the agent retrieves them with
        get_queued_messages().

        Args:
            session_id: The session ID of the target agent.
            message: The steering message/prompt to queue.
        """
        with self._state_lock:
            if session_id not in self._message_queues:
                self._message_queues[session_id] = []
            self._message_queues[session_id].append(message)

    def get_queued_messages(self, session_id: str) -> List[str]:
        """Get and clear all queued messages for an agent.

        Returns all pending steering messages for the specified agent and
        clears the queue. If no messages are queued, returns an empty list.

        Args:
            session_id: The session ID of the agent.

        Returns:
            List of queued messages (may be empty).
        """
        with self._state_lock:
            if session_id not in self._message_queues:
                return []
            messages = self._message_queues[session_id]
            self._message_queues[session_id] = []
            return messages

    # =========================================================================
    # Agent Tracking
    # =========================================================================

    def register_agent(
        self, session_id: str, agent_name: str, model_name: str
    ) -> None:
        """Register an active agent for tracking.

        Args:
            session_id: Unique identifier for this agent session.
            agent_name: Name of the agent (e.g., 'husky', 'pack-leader').
            model_name: Name of the model being used (e.g., 'claude-3-5-sonnet').
        """
        with self._state_lock:
            self._agents[session_id] = AgentInfo(
                session_id=session_id,
                agent_name=agent_name,
                model_name=model_name,
            )

    def unregister_agent(self, session_id: str) -> None:
        """Remove an agent from tracking.

        Also clears any queued messages for the agent.

        Args:
            session_id: The session ID of the agent to remove.
        """
        with self._state_lock:
            if session_id in self._agents:
                del self._agents[session_id]
            # Also clear any queued messages
            if session_id in self._message_queues:
                del self._message_queues[session_id]

    def get_active_agents(self) -> List[dict]:
        """Get information about all active agents.

        Returns:
            List of dictionaries containing agent info with keys:
            - session_id: The agent's session ID
            - agent_name: The agent's name
            - model_name: The model being used
            - registered_at: Timestamp when agent was registered
        """
        with self._state_lock:
            return [agent.to_dict() for agent in self._agents.values()]

    def get_agent(self, session_id: str) -> Optional[AgentInfo]:
        """Get information about a specific agent.

        Args:
            session_id: The session ID to look up.

        Returns:
            AgentInfo if found, None otherwise.
        """
        with self._state_lock:
            return self._agents.get(session_id)


# =============================================================================
# Convenience Functions
# =============================================================================


def get_steering_manager() -> SteeringManager:
    """Get the singleton SteeringManager instance.

    Convenience function for accessing the manager.

    Returns:
        The singleton SteeringManager.
    """
    return SteeringManager.get_instance()


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "AgentInfo",
    "SteeringManager",
    "get_steering_manager",
]
