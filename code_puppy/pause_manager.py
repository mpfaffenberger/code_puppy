"""PauseManager: registry, steering queues, and pause barrier for pause+steer.

Also includes OutputQuiescenceTracker for tracking active output streams.
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional

from code_puppy.config import get_use_dbos

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# Output Quiescence Tracker
# =============================================================================


class OutputQuiescenceTracker:
    """Tracks active output streams to determine when output is quiescent.

    This is used to coordinate pause operations - we want to wait until
    all active output streams are complete before displaying pause UI.

    Thread-safe: All operations are protected by locks.

    Usage:
        tracker = get_output_quiescence_tracker()
        tracker.start_stream()  # Called when streaming begins
        # ... stream content ...
        tracker.end_stream()    # Called when streaming ends

        # Check if quiescent:
        if tracker.is_quiescent():
            # Safe to show pause menu

        # Wait for quiescence:
        await tracker.wait_for_quiescence(timeout=5.0)
    """

    _instance: Optional["OutputQuiescenceTracker"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "OutputQuiescenceTracker":
        """Singleton pattern - ensure only one instance exists."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the tracker (only runs once due to singleton)."""
        if getattr(self, "_initialized", False):
            return

        # Counter for active streams
        self._active_count = 0
        self._count_lock = threading.Lock()

        # Event for quiescence signaling (sync)
        self._quiescent_event = threading.Event()
        self._quiescent_event.set()  # Initially quiescent (no streams)

        # Async event for async waiters
        self._async_quiescent_event: Optional[asyncio.Event] = None

        # Callbacks for quiescence state changes
        self._callbacks: List[Callable[[bool], None]] = []

        self._initialized = True
        logger.debug("OutputQuiescenceTracker initialized")

    def start_stream(self) -> None:
        """Signal that an output stream has started.

        Increments the active stream counter and clears the quiescent event.
        """
        with self._count_lock:
            self._active_count += 1
            if self._active_count == 1:
                # Transitioning from quiescent to active
                self._quiescent_event.clear()
                self._notify_callbacks(is_quiescent=False)
            logger.debug(f"Stream started, active count: {self._active_count}")

    def end_stream(self) -> None:
        """Signal that an output stream has ended.

        Decrements the active stream counter. Sets quiescent event if count hits 0.
        """
        with self._count_lock:
            if self._active_count > 0:
                self._active_count -= 1
            else:
                logger.warning("end_stream called with no active streams")

            if self._active_count == 0:
                # Transitioning to quiescent state
                self._quiescent_event.set()
                self._notify_callbacks(is_quiescent=True)
                # Also set async event if it exists
                if self._async_quiescent_event is not None:
                    try:
                        self._async_quiescent_event.set()
                    except Exception:
                        pass  # Event might be from different loop

            logger.debug(f"Stream ended, active count: {self._active_count}")

    def is_quiescent(self) -> bool:
        """Check if output is currently quiescent (no active streams).

        Returns:
            True if no streams are active, False otherwise.
        """
        with self._count_lock:
            return self._active_count == 0

    def active_stream_count(self) -> int:
        """Get the current number of active streams.

        Returns:
            Number of active output streams.
        """
        with self._count_lock:
            return self._active_count

    def wait_for_quiescence(self, timeout: Optional[float] = None) -> bool:
        """Block until output becomes quiescent or timeout.

        Args:
            timeout: Maximum time to wait in seconds. None = wait forever.

        Returns:
            True if quiescent, False if timeout occurred.
        """
        return self._quiescent_event.wait(timeout=timeout)

    async def async_wait_for_quiescence(self, timeout: Optional[float] = None) -> bool:
        """Async version of wait_for_quiescence.

        Args:
            timeout: Maximum time to wait in seconds. None = wait forever.

        Returns:
            True if quiescent, False if timeout occurred.
        """
        # Fast path: already quiescent
        if self.is_quiescent():
            return True

        # Create or get async event
        if self._async_quiescent_event is None:
            self._async_quiescent_event = asyncio.Event()
            if self.is_quiescent():
                self._async_quiescent_event.set()

        try:
            if timeout is not None:
                await asyncio.wait_for(
                    self._async_quiescent_event.wait(), timeout=timeout
                )
            else:
                await self._async_quiescent_event.wait()
            return True
        except asyncio.TimeoutError:
            return False

    def add_callback(self, callback: Callable[[bool], None]) -> None:
        """Add a callback for quiescence state changes.

        Args:
            callback: Function taking bool (True = quiescent, False = active)
        """
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[bool], None]) -> bool:
        """Remove a quiescence callback.

        Args:
            callback: The callback to remove

        Returns:
            True if callback was found and removed
        """
        try:
            self._callbacks.remove(callback)
            return True
        except ValueError:
            return False

    def _notify_callbacks(self, is_quiescent: bool) -> None:
        """Notify all callbacks of state change."""
        for callback in self._callbacks:
            try:
                callback(is_quiescent)
            except Exception as e:
                logger.error(f"Quiescence callback error: {e}")

    def reset(self) -> None:
        """Reset the tracker state (for testing)."""
        with self._count_lock:
            self._active_count = 0
            self._quiescent_event.set()
            self._async_quiescent_event = None
            self._callbacks.clear()
            logger.debug("OutputQuiescenceTracker reset")


# Module-level singleton accessor for quiescence tracker
_quiescence_tracker: Optional[OutputQuiescenceTracker] = None
_quiescence_lock = threading.Lock()


def get_output_quiescence_tracker() -> OutputQuiescenceTracker:
    """Get the singleton OutputQuiescenceTracker instance.

    Returns:
        The global OutputQuiescenceTracker instance
    """
    global _quiescence_tracker
    if _quiescence_tracker is None:
        with _quiescence_lock:
            if _quiescence_tracker is None:
                _quiescence_tracker = OutputQuiescenceTracker()
    return _quiescence_tracker


def reset_output_quiescence_tracker() -> None:
    """Reset the global OutputQuiescenceTracker (for testing)."""
    global _quiescence_tracker
    if _quiescence_tracker is not None:
        _quiescence_tracker.reset()


class AgentStatus(Enum):
    """Status of an agent in the registry."""

    RUNNING = auto()
    PAUSED = auto()
    PAUSE_REQUESTED = auto()


@dataclass
class AgentEntry:
    """Entry in the agent registry tracking an agent's state."""

    agent_id: str
    name: str
    status: AgentStatus = AgentStatus.RUNNING
    registered_at: float = field(default_factory=time.time)
    pause_requested_at: Optional[float] = None
    # Steering queue for this agent - created lazily
    _steering_queue: Optional[asyncio.Queue] = field(default=None, repr=False)

    @property
    def steering_queue(self) -> asyncio.Queue:
        """Get or create the steering queue for this agent."""
        if self._steering_queue is None:
            self._steering_queue = asyncio.Queue()
        return self._steering_queue


class PauseManager:
    """Manager for pause+steer functionality with agent registry.

    Provides:
    - Agent registration/unregistration
    - Pause request with DBOS guard
    - Steering queue per agent
    - Pause checkpoint/barrier mechanism

    This is a singleton - use get_pause_manager() to access.
    """

    _instance: Optional["PauseManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "PauseManager":
        """Singleton pattern - ensure only one instance exists."""
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the pause manager (only runs once due to singleton)."""
        if getattr(self, "_initialized", False):
            return

        # Thread safety for registry operations
        self._registry_lock = threading.RLock()

        # Agent registry: agent_id -> AgentEntry
        self._agents: Dict[str, AgentEntry] = {}

        # Global pause state
        self._global_pause_requested = False
        self._pause_event = threading.Event()
        self._async_pause_event: Optional[asyncio.Event] = None

        # Callbacks for pause state changes
        self._pause_callbacks: List[Callable[[bool], None]] = []

        self._initialized = True
        logger.debug("PauseManager initialized")

    # -------------------------------------------------------------------------
    # Agent Registry Methods
    # -------------------------------------------------------------------------

    def register(self, agent_id: str, name: str) -> bool:
        """Register an agent as running.

        Args:
            agent_id: Unique identifier for the agent
            name: Human-readable name for the agent

        Returns:
            True if registered successfully, False if already registered
        """
        with self._registry_lock:
            if agent_id in self._agents:
                logger.warning(f"Agent {agent_id} ({name}) already registered")
                return False

            entry = AgentEntry(agent_id=agent_id, name=name)
            self._agents[agent_id] = entry
            logger.info(f"Registered agent: {name} (ID: {agent_id})")
            return True

    def unregister(self, agent_id: str) -> bool:
        """Unregister an agent.

        Args:
            agent_id: ID of the agent to unregister

        Returns:
            True if unregistered successfully, False if not found
        """
        with self._registry_lock:
            if agent_id not in self._agents:
                logger.warning(f"Agent {agent_id} not found in registry")
                return False

            entry = self._agents.pop(agent_id)
            logger.info(f"Unregistered agent: {entry.name} (ID: {agent_id})")
            return True

    def get_agent(self, agent_id: str) -> Optional[AgentEntry]:
        """Get an agent entry by ID.

        Args:
            agent_id: ID of the agent to get

        Returns:
            AgentEntry if found, None otherwise
        """
        with self._registry_lock:
            return self._agents.get(agent_id)

    def list_agents(self) -> List[AgentEntry]:
        """List all registered agents.

        Returns:
            List of AgentEntry objects (copies to prevent external mutation)
        """
        with self._registry_lock:
            return list(self._agents.values())

    def list_running_agents(self) -> List[AgentEntry]:
        """List agents currently in RUNNING status.

        Returns:
            List of running AgentEntry objects
        """
        with self._registry_lock:
            return [
                entry
                for entry in self._agents.values()
                if entry.status == AgentStatus.RUNNING
            ]

    def list_paused_agents(self) -> List[AgentEntry]:
        """List agents currently paused.

        Returns:
            List of paused AgentEntry objects
        """
        with self._registry_lock:
            return [
                entry
                for entry in self._agents.values()
                if entry.status == AgentStatus.PAUSED
            ]

    def agent_count(self) -> int:
        """Get the total number of registered agents.

        Returns:
            Number of registered agents
        """
        with self._registry_lock:
            return len(self._agents)

    # -------------------------------------------------------------------------
    # Pause Request Methods (with DBOS Guard)
    # -------------------------------------------------------------------------

    def request_pause(self, agent_id: Optional[str] = None) -> bool:
        """Request pause for a specific agent or all agents.

        If DBOS is enabled, this will warn and return False (no-op).
        DBOS durability requires deterministic execution, which conflicts
        with interactive pause+steer.

        Args:
            agent_id: Optional specific agent to pause. If None, requests
                     global pause for all agents.

        Returns:
            True if pause was requested, False if DBOS guard blocked it
        """
        # DBOS guard - pause conflicts with durability
        if get_use_dbos():
            logger.warning(
                "Pause requested but DBOS is enabled. "
                "Pause+steer is incompatible with DBOS durability. "
                "Disable DBOS to use pause functionality."
            )
            return False

        with self._registry_lock:
            if agent_id is not None:
                # Pause specific agent
                entry = self._agents.get(agent_id)
                if entry is None:
                    logger.warning(f"Cannot pause unknown agent: {agent_id}")
                    return False

                if entry.status == AgentStatus.RUNNING:
                    entry.status = AgentStatus.PAUSE_REQUESTED
                    entry.pause_requested_at = time.time()
                    logger.info(f"Pause requested for agent: {entry.name}")
                    return True
                else:
                    logger.debug(f"Agent {entry.name} already in status {entry.status}")
                    return True  # Already pausing/paused is still success
            else:
                # Global pause request
                self._global_pause_requested = True
                self._pause_event.set()
                for entry in self._agents.values():
                    if entry.status == AgentStatus.RUNNING:
                        entry.status = AgentStatus.PAUSE_REQUESTED
                        entry.pause_requested_at = time.time()

                logger.info(f"Global pause requested for {len(self._agents)} agents")

                # Notify callbacks
                for callback in self._pause_callbacks:
                    try:
                        callback(True)
                    except Exception as e:
                        logger.error(f"Pause callback error: {e}")

                return True

    def request_resume(self, agent_id: Optional[str] = None) -> bool:
        """Request resume for a specific agent or all agents.

        Args:
            agent_id: Optional specific agent to resume. If None, requests
                     global resume for all agents.

        Returns:
            True if resume was requested
        """
        with self._registry_lock:
            if agent_id is not None:
                # Resume specific agent
                entry = self._agents.get(agent_id)
                if entry is None:
                    logger.warning(f"Cannot resume unknown agent: {agent_id}")
                    return False

                if entry.status in (AgentStatus.PAUSED, AgentStatus.PAUSE_REQUESTED):
                    entry.status = AgentStatus.RUNNING
                    entry.pause_requested_at = None
                    logger.info(f"Resumed agent: {entry.name}")
                    return True
                else:
                    logger.debug(f"Agent {entry.name} already running")
                    return True
            else:
                # Global resume
                self._global_pause_requested = False
                self._pause_event.clear()
                for entry in self._agents.values():
                    if entry.status in (
                        AgentStatus.PAUSED,
                        AgentStatus.PAUSE_REQUESTED,
                    ):
                        entry.status = AgentStatus.RUNNING
                        entry.pause_requested_at = None

                logger.info("Global resume requested")

                # Notify callbacks
                for callback in self._pause_callbacks:
                    try:
                        callback(False)
                    except Exception as e:
                        logger.error(f"Resume callback error: {e}")

                return True

    def is_pause_requested(self, agent_id: Optional[str] = None) -> bool:
        """Check if pause has been requested.

        Args:
            agent_id: Optional agent ID to check. If None, checks global state.

        Returns:
            True if pause is requested
        """
        with self._registry_lock:
            if agent_id is not None:
                entry = self._agents.get(agent_id)
                if entry is None:
                    return False
                return entry.status in (
                    AgentStatus.PAUSE_REQUESTED,
                    AgentStatus.PAUSED,
                )
            return self._global_pause_requested

    def add_pause_callback(self, callback: Callable[[bool], None]) -> None:
        """Add a callback to be notified of pause state changes.

        Args:
            callback: Function taking bool (True=paused, False=resumed)
        """
        self._pause_callbacks.append(callback)

    def remove_pause_callback(self, callback: Callable[[bool], None]) -> bool:
        """Remove a pause state callback.

        Args:
            callback: The callback to remove

        Returns:
            True if callback was found and removed
        """
        try:
            self._pause_callbacks.remove(callback)
            return True
        except ValueError:
            return False

    # -------------------------------------------------------------------------
    # Pause Checkpoint / Barrier Methods
    # -------------------------------------------------------------------------

    def pause_checkpoint(self, agent_id: str) -> bool:
        """Check pause state at a checkpoint in agent execution.

        This should be called by agents at natural pause points (e.g., between
        tool calls) to check if they should pause.

        Args:
            agent_id: ID of the agent checking

        Returns:
            True if the agent should pause, False to continue
        """
        with self._registry_lock:
            # Check DBOS guard first
            if get_use_dbos():
                return False

            entry = self._agents.get(agent_id)
            if entry is None:
                return self._global_pause_requested

            if entry.status == AgentStatus.PAUSE_REQUESTED:
                entry.status = AgentStatus.PAUSED
                logger.info(f"Agent {entry.name} entered paused state")
                return True

            return entry.status == AgentStatus.PAUSED

    async def async_pause_checkpoint(self, agent_id: str) -> bool:
        """Async version of pause_checkpoint for async agents.

        Args:
            agent_id: ID of the agent checking

        Returns:
            True if the agent should pause, False to continue
        """
        # Just call the sync version - it's lock-protected and fast
        return self.pause_checkpoint(agent_id)

    def wait_for_resume(self, agent_id: str, timeout: Optional[float] = None) -> bool:
        """Block until the agent is resumed or timeout.

        Args:
            agent_id: ID of the agent waiting
            timeout: Optional timeout in seconds

        Returns:
            True if resumed, False if timed out
        """
        entry = self.get_agent(agent_id)
        if entry is None:
            return True  # Unknown agent, don't block

        start = time.time()
        while entry.status == AgentStatus.PAUSED:
            elapsed = time.time() - start
            if timeout is not None and elapsed >= timeout:
                return False

            # Short sleep to check status periodically
            time.sleep(0.1)

            # Re-fetch status
            with self._registry_lock:
                entry = self._agents.get(agent_id)
                if entry is None or entry.status == AgentStatus.RUNNING:
                    return True

        return True

    async def async_wait_for_resume(
        self, agent_id: str, timeout: Optional[float] = None
    ) -> bool:
        """Async version of wait_for_resume.

        Args:
            agent_id: ID of the agent waiting
            timeout: Optional timeout in seconds

        Returns:
            True if resumed, False if timed out
        """
        entry = self.get_agent(agent_id)
        if entry is None:
            return True

        start = time.time()
        while entry.status == AgentStatus.PAUSED:
            elapsed = time.time() - start
            if timeout is not None and elapsed >= timeout:
                return False

            # Async sleep
            await asyncio.sleep(0.1)

            # Re-fetch status
            with self._registry_lock:
                entry = self._agents.get(agent_id)
                if entry is None or entry.status == AgentStatus.RUNNING:
                    return True

        return True

    # -------------------------------------------------------------------------
    # Steering Queue Methods
    # -------------------------------------------------------------------------

    def get_steering_queue(self, agent_id: str) -> Optional[asyncio.Queue]:
        """Get the steering queue for a specific agent.

        Args:
            agent_id: ID of the agent

        Returns:
            The agent's steering queue, or None if agent not found
        """
        entry = self.get_agent(agent_id)
        if entry is None:
            return None
        return entry.steering_queue

    def send_steering_input(self, agent_id: str, input_data: Any) -> bool:
        """Send steering input to a paused agent.

        Args:
            agent_id: ID of the agent to steer
            input_data: The steering input (can be any type)

        Returns:
            True if input was queued, False if agent not found
        """
        entry = self.get_agent(agent_id)
        if entry is None:
            logger.warning(f"Cannot send steering input to unknown agent: {agent_id}")
            return False

        try:
            entry.steering_queue.put_nowait(input_data)
            logger.debug(f"Sent steering input to agent {entry.name}: {input_data}")
            return True
        except asyncio.QueueFull:
            logger.warning(f"Steering queue full for agent {entry.name}")
            return False

    async def receive_steering_input(
        self, agent_id: str, timeout: Optional[float] = None
    ) -> Optional[Any]:
        """Receive steering input from the queue (for agent use).

        Args:
            agent_id: ID of the agent receiving
            timeout: Optional timeout in seconds

        Returns:
            The steering input, or None if timeout/not found
        """
        entry = self.get_agent(agent_id)
        if entry is None:
            return None

        try:
            if timeout is not None:
                return await asyncio.wait_for(
                    entry.steering_queue.get(), timeout=timeout
                )
            else:
                return await entry.steering_queue.get()
        except asyncio.TimeoutError:
            return None

    def clear_steering_queue(self, agent_id: str) -> int:
        """Clear all pending steering inputs for an agent.

        Args:
            agent_id: ID of the agent

        Returns:
            Number of items cleared
        """
        entry = self.get_agent(agent_id)
        if entry is None:
            return 0

        count = 0
        while not entry.steering_queue.empty():
            try:
                entry.steering_queue.get_nowait()
                count += 1
            except asyncio.QueueEmpty:
                break

        return count

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def is_dbos_enabled(self) -> bool:
        """Check if DBOS is enabled (pause is incompatible).

        Returns:
            True if DBOS is enabled
        """
        return get_use_dbos()

    def reset(self) -> None:
        """Reset the pause manager state (for testing).

        Clears all agents and resets pause state.
        """
        with self._registry_lock:
            self._agents.clear()
            self._global_pause_requested = False
            self._pause_event.clear()
            self._pause_callbacks.clear()
            logger.debug("PauseManager reset")


# Module-level singleton accessor
_pause_manager: Optional[PauseManager] = None
_singleton_lock = threading.Lock()


def get_pause_manager() -> PauseManager:
    """Get the singleton PauseManager instance.

    Returns:
        The global PauseManager instance
    """
    global _pause_manager
    if _pause_manager is None:
        with _singleton_lock:
            if _pause_manager is None:
                _pause_manager = PauseManager()
    return _pause_manager


def reset_pause_manager() -> None:
    """Reset the global PauseManager (for testing).

    This resets the singleton state, clearing all agents and pause state.
    """
    global _pause_manager
    if _pause_manager is not None:
        _pause_manager.reset()
