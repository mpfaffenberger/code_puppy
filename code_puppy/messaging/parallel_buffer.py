"""ParallelOutputBuffer - Buffer messages from parallel agent sessions.

When multiple agents run in parallel (e.g., via Pack Leader), their output
can interleave chaotically. This buffer allows messages from parallel sessions
to be held back and displayed sequentially after agent completion.

Example:
    >>> buffer = ParallelOutputBuffer()
    >>> buffer.start_session("session-1")
    >>> buffer.start_session("session-2")
    >>>
    >>> # Messages from active sessions get buffered
    >>> msg = TextMessage(level=MessageLevel.INFO, text="Hello", session_id="session-1")
    >>> buffer.buffer_message(msg)  # Returns True (buffered)
    >>>
    >>> # End session and get all buffered messages
    >>> messages = buffer.end_session("session-1")
    >>> len(messages)  # 1
"""

import threading
from typing import Dict, List

from .messages import AnyMessage


class ParallelOutputBuffer:
    """Thread-safe buffer for messages from parallel agent sessions.

    Allows messages tagged with a session_id to be buffered during execution
    and released sequentially when the session completes. This prevents output
    from multiple parallel agents from interleaving chaotically.

    Attributes:
        _buffers: Dictionary mapping session_id to list of buffered messages.
        _lock: Thread lock for safe concurrent access.
    """

    def __init__(self) -> None:
        """Initialize an empty parallel output buffer."""
        self._buffers: Dict[str, List[AnyMessage]] = {}
        self._lock = threading.Lock()

    def start_session(self, session_id: str) -> None:
        """Register a new parallel session for buffering.

        Args:
            session_id: Unique identifier for the agent session.

        Example:
            >>> buffer = ParallelOutputBuffer()
            >>> buffer.start_session("agent-123")
            >>> buffer.is_session_active("agent-123")  # True
        """
        with self._lock:
            if session_id not in self._buffers:
                self._buffers[session_id] = []

    def buffer_message(self, message: AnyMessage) -> bool:
        """Buffer a message if it belongs to an active session.

        Args:
            message: The message to potentially buffer.

        Returns:
            True if the message was buffered (belongs to active session),
            False if it should be displayed immediately (no active session).

        Example:
            >>> buffer = ParallelOutputBuffer()
            >>> buffer.start_session("session-1")
            >>> msg = TextMessage(
            ...     level=MessageLevel.INFO,
            ...     text="Test",
            ...     session_id="session-1"
            ... )
            >>> buffer.buffer_message(msg)  # True (buffered)
            >>> msg2 = TextMessage(
            ...     level=MessageLevel.INFO,
            ...     text="Test2",
            ...     session_id="session-2"  # Not active
            ... )
            >>> buffer.buffer_message(msg2)  # False (not buffered)
        """
        # Only buffer if message has a session_id and that session is active
        if message.session_id is None:
            return False

        with self._lock:
            if message.session_id in self._buffers:
                self._buffers[message.session_id].append(message)
                return True
            return False

    def end_session(self, session_id: str) -> List[AnyMessage]:
        """End a session and return all buffered messages.

        Args:
            session_id: The session to end.

        Returns:
            List of all messages that were buffered for this session.
            Returns empty list if session was not active.

        Example:
            >>> buffer = ParallelOutputBuffer()
            >>> buffer.start_session("session-1")
            >>> msg1 = TextMessage(
            ...     level=MessageLevel.INFO,
            ...     text="First",
            ...     session_id="session-1"
            ... )
            >>> msg2 = TextMessage(
            ...     level=MessageLevel.INFO,
            ...     text="Second",
            ...     session_id="session-1"
            ... )
            >>> buffer.buffer_message(msg1)
            >>> buffer.buffer_message(msg2)
            >>> messages = buffer.end_session("session-1")
            >>> len(messages)  # 2
            >>> buffer.is_session_active("session-1")  # False
        """
        with self._lock:
            messages = self._buffers.pop(session_id, [])
            return messages

    def is_parallel_mode(self) -> bool:
        """Check if any sessions are currently active.

        Returns:
            True if at least one session is active (parallel mode enabled),
            False if no sessions are active.

        Example:
            >>> buffer = ParallelOutputBuffer()
            >>> buffer.is_parallel_mode()  # False
            >>> buffer.start_session("session-1")
            >>> buffer.is_parallel_mode()  # True
            >>> buffer.end_session("session-1")
            >>> buffer.is_parallel_mode()  # False
        """
        with self._lock:
            return len(self._buffers) > 0

    def get_active_sessions(self) -> List[str]:
        """Get a list of all active session IDs.

        Returns:
            List of session IDs that are currently active.

        Example:
            >>> buffer = ParallelOutputBuffer()
            >>> buffer.start_session("session-1")
            >>> buffer.start_session("session-2")
            >>> sessions = buffer.get_active_sessions()
            >>> len(sessions)  # 2
            >>> "session-1" in sessions  # True
            >>> "session-2" in sessions  # True
        """
        with self._lock:
            return list(self._buffers.keys())

    def is_session_active(self, session_id: str) -> bool:
        """Check if a specific session is currently active.

        Args:
            session_id: The session ID to check.

        Returns:
            True if the session is active, False otherwise.

        Example:
            >>> buffer = ParallelOutputBuffer()
            >>> buffer.is_session_active("session-1")  # False
            >>> buffer.start_session("session-1")
            >>> buffer.is_session_active("session-1")  # True
            >>> buffer.end_session("session-1")
            >>> buffer.is_session_active("session-1")  # False
        """
        with self._lock:
            return session_id in self._buffers


__all__ = ["ParallelOutputBuffer"]
