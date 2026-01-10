"""Comprehensive unit tests for ParallelOutputBuffer.

Tests the parallel output buffering system used by Pack Leader
to manage messages from multiple concurrent agent sessions.
"""

import threading

import pytest

from code_puppy.messaging.messages import MessageLevel, TextMessage
from code_puppy.messaging.parallel_buffer import ParallelOutputBuffer

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def buffer() -> ParallelOutputBuffer:
    """Create a fresh ParallelOutputBuffer instance."""
    return ParallelOutputBuffer()


@pytest.fixture
def sample_message() -> TextMessage:
    """Create a sample TextMessage with a session_id."""
    return TextMessage(
        level=MessageLevel.INFO, text="Test message", session_id="test-session"
    )


# =============================================================================
# Basic Functionality Tests
# =============================================================================


def test_start_session_creates_session(buffer: ParallelOutputBuffer) -> None:
    """Starting a session adds it to the active sessions list."""
    buffer.start_session("session-1")
    assert buffer.is_session_active("session-1")
    assert "session-1" in buffer.get_active_sessions()


def test_is_parallel_mode_empty(buffer: ParallelOutputBuffer) -> None:
    """Returns False when no sessions are active."""
    assert buffer.is_parallel_mode() is False


def test_is_parallel_mode_with_session(buffer: ParallelOutputBuffer) -> None:
    """Returns True when at least one session is active."""
    buffer.start_session("session-1")
    assert buffer.is_parallel_mode() is True


def test_get_active_sessions(buffer: ParallelOutputBuffer) -> None:
    """Returns list of all active session IDs."""
    buffer.start_session("session-1")
    buffer.start_session("session-2")
    buffer.start_session("session-3")

    sessions = buffer.get_active_sessions()
    assert len(sessions) == 3
    assert "session-1" in sessions
    assert "session-2" in sessions
    assert "session-3" in sessions


def test_is_session_active(buffer: ParallelOutputBuffer) -> None:
    """Check individual session active status."""
    buffer.start_session("session-1")
    assert buffer.is_session_active("session-1") is True
    assert buffer.is_session_active("session-2") is False


# =============================================================================
# Buffering Tests
# =============================================================================


def test_buffer_message_active_session(buffer: ParallelOutputBuffer) -> None:
    """Returns True and buffers message for active session."""
    buffer.start_session("test-session")
    msg = TextMessage(
        level=MessageLevel.INFO, text="Hello", session_id="test-session"
    )

    result = buffer.buffer_message(msg)
    assert result is True

    # Verify message was buffered by ending session and checking returned messages
    messages = buffer.end_session("test-session")
    assert len(messages) == 1
    assert messages[0] == msg


def test_buffer_message_inactive_session(buffer: ParallelOutputBuffer) -> None:
    """Returns False and does not buffer message for inactive session."""
    msg = TextMessage(
        level=MessageLevel.INFO, text="Hello", session_id="inactive-session"
    )

    result = buffer.buffer_message(msg)
    assert result is False

    # Verify nothing was buffered
    messages = buffer.end_session("inactive-session")
    assert len(messages) == 0


def test_buffer_message_uses_session_id_from_message(
    buffer: ParallelOutputBuffer,
) -> None:
    """Buffers message to correct session based on message.session_id."""
    buffer.start_session("session-1")
    buffer.start_session("session-2")

    msg1 = TextMessage(level=MessageLevel.INFO, text="For S1", session_id="session-1")
    msg2 = TextMessage(level=MessageLevel.INFO, text="For S2", session_id="session-2")

    buffer.buffer_message(msg1)
    buffer.buffer_message(msg2)

    # Verify messages went to correct sessions
    messages1 = buffer.end_session("session-1")
    messages2 = buffer.end_session("session-2")

    assert len(messages1) == 1
    assert messages1[0].text == "For S1"
    assert len(messages2) == 1
    assert messages2[0].text == "For S2"


def test_buffer_multiple_messages(buffer: ParallelOutputBuffer) -> None:
    """Multiple messages for same session are all buffered in order."""
    buffer.start_session("session-1")

    messages_to_buffer = [
        TextMessage(level=MessageLevel.INFO, text="First", session_id="session-1"),
        TextMessage(level=MessageLevel.INFO, text="Second", session_id="session-1"),
        TextMessage(level=MessageLevel.INFO, text="Third", session_id="session-1"),
    ]

    for msg in messages_to_buffer:
        result = buffer.buffer_message(msg)
        assert result is True

    retrieved = buffer.end_session("session-1")
    assert len(retrieved) == 3
    assert retrieved[0].text == "First"
    assert retrieved[1].text == "Second"
    assert retrieved[2].text == "Third"


def test_buffer_messages_different_sessions(buffer: ParallelOutputBuffer) -> None:
    """Messages from different sessions are isolated from each other."""
    buffer.start_session("session-1")
    buffer.start_session("session-2")

    # Send multiple messages to each session in interleaved fashion
    buffer.buffer_message(
        TextMessage(level=MessageLevel.INFO, text="S1-1", session_id="session-1")
    )
    buffer.buffer_message(
        TextMessage(level=MessageLevel.INFO, text="S2-1", session_id="session-2")
    )
    buffer.buffer_message(
        TextMessage(level=MessageLevel.INFO, text="S1-2", session_id="session-1")
    )
    buffer.buffer_message(
        TextMessage(level=MessageLevel.INFO, text="S2-2", session_id="session-2")
    )

    # Verify isolation
    messages1 = buffer.end_session("session-1")
    messages2 = buffer.end_session("session-2")

    assert len(messages1) == 2
    assert messages1[0].text == "S1-1"
    assert messages1[1].text == "S1-2"

    assert len(messages2) == 2
    assert messages2[0].text == "S2-1"
    assert messages2[1].text == "S2-2"


# =============================================================================
# End Session Tests
# =============================================================================


def test_end_session_returns_messages(buffer: ParallelOutputBuffer) -> None:
    """Ending a session returns all buffered messages."""
    buffer.start_session("session-1")

    msg1 = TextMessage(level=MessageLevel.INFO, text="First", session_id="session-1")
    msg2 = TextMessage(level=MessageLevel.INFO, text="Second", session_id="session-1")

    buffer.buffer_message(msg1)
    buffer.buffer_message(msg2)

    messages = buffer.end_session("session-1")
    assert len(messages) == 2
    assert messages[0] == msg1
    assert messages[1] == msg2


def test_end_session_clears_buffer(buffer: ParallelOutputBuffer) -> None:
    """Buffer is empty after ending session."""
    buffer.start_session("session-1")

    msg = TextMessage(level=MessageLevel.INFO, text="Test", session_id="session-1")
    buffer.buffer_message(msg)

    # End session once - should get the message
    messages1 = buffer.end_session("session-1")
    assert len(messages1) == 1

    # End session again (already ended) - should get empty list
    messages2 = buffer.end_session("session-1")
    assert len(messages2) == 0


def test_end_session_removes_from_active(buffer: ParallelOutputBuffer) -> None:
    """Session is no longer active after ending."""
    buffer.start_session("session-1")
    assert buffer.is_session_active("session-1") is True
    assert buffer.is_parallel_mode() is True

    buffer.end_session("session-1")
    assert buffer.is_session_active("session-1") is False
    assert buffer.is_parallel_mode() is False


def test_end_session_nonexistent(buffer: ParallelOutputBuffer) -> None:
    """Ending a non-existent session returns empty list without error."""
    messages = buffer.end_session("nonexistent-session")
    assert len(messages) == 0
    assert isinstance(messages, list)


# =============================================================================
# Edge Cases
# =============================================================================


def test_start_session_duplicate(buffer: ParallelOutputBuffer) -> None:
    """Starting an already-active session is idempotent (doesn't clear buffer)."""
    buffer.start_session("session-1")

    msg1 = TextMessage(level=MessageLevel.INFO, text="First", session_id="session-1")
    buffer.buffer_message(msg1)

    # Start the same session again
    buffer.start_session("session-1")

    # Original message should still be there
    msg2 = TextMessage(level=MessageLevel.INFO, text="Second", session_id="session-1")
    buffer.buffer_message(msg2)

    messages = buffer.end_session("session-1")
    assert len(messages) == 2
    assert messages[0].text == "First"
    assert messages[1].text == "Second"


def test_thread_safety(buffer: ParallelOutputBuffer) -> None:
    """Concurrent operations don't corrupt state."""
    num_threads = 10
    messages_per_thread = 50

    def worker(thread_id: int) -> None:
        session_id = f"thread-{thread_id}"
        buffer.start_session(session_id)

        for i in range(messages_per_thread):
            msg = TextMessage(
                level=MessageLevel.INFO,
                text=f"Message {i} from thread {thread_id}",
                session_id=session_id,
            )
            buffer.buffer_message(msg)

    # Start all threads
    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    # Wait for all threads to complete
    for t in threads:
        t.join()

    # Verify all sessions are active
    active_sessions = buffer.get_active_sessions()
    assert len(active_sessions) == num_threads

    # Verify each session has the correct number of messages
    for i in range(num_threads):
        session_id = f"thread-{i}"
        messages = buffer.end_session(session_id)
        assert len(messages) == messages_per_thread

    # Verify no sessions are active after ending all
    assert buffer.is_parallel_mode() is False


def test_buffer_message_no_session_id(buffer: ParallelOutputBuffer) -> None:
    """Message without session_id is not buffered."""
    buffer.start_session("session-1")

    # Create message without session_id
    msg = TextMessage(level=MessageLevel.INFO, text="No session")
    assert msg.session_id is None

    result = buffer.buffer_message(msg)
    assert result is False

    # Verify nothing was buffered
    messages = buffer.end_session("session-1")
    assert len(messages) == 0


def test_buffer_message_empty_session_id(buffer: ParallelOutputBuffer) -> None:
    """Message with empty string session_id is not buffered (unless session exists)."""
    # Don't create a session with empty string
    msg = TextMessage(level=MessageLevel.INFO, text="Empty session", session_id="")

    result = buffer.buffer_message(msg)
    assert result is False

    # Now create a session with empty string and verify it works
    buffer.start_session("")
    msg2 = TextMessage(level=MessageLevel.INFO, text="Empty session 2", session_id="")
    result2 = buffer.buffer_message(msg2)
    assert result2 is True

    messages = buffer.end_session("")
    assert len(messages) == 1
    assert messages[0].text == "Empty session 2"


def test_multiple_end_session_calls(buffer: ParallelOutputBuffer) -> None:
    """Multiple calls to end_session for same session are safe."""
    buffer.start_session("session-1")
    msg = TextMessage(level=MessageLevel.INFO, text="Test", session_id="session-1")
    buffer.buffer_message(msg)

    # First end - should return message
    messages1 = buffer.end_session("session-1")
    assert len(messages1) == 1

    # Subsequent ends - should return empty list
    messages2 = buffer.end_session("session-1")
    messages3 = buffer.end_session("session-1")
    assert len(messages2) == 0
    assert len(messages3) == 0


def test_concurrent_start_and_end(buffer: ParallelOutputBuffer) -> None:
    """Concurrent start and end operations are thread-safe."""
    num_iterations = 100

    def start_end_worker() -> None:
        for i in range(num_iterations):
            session_id = f"session-{threading.get_ident()}-{i}"
            buffer.start_session(session_id)
            msg = TextMessage(
                level=MessageLevel.INFO, text=f"Test {i}", session_id=session_id
            )
            buffer.buffer_message(msg)
            messages = buffer.end_session(session_id)
            assert len(messages) == 1

    threads = [threading.Thread(target=start_end_worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All sessions should be ended
    assert buffer.is_parallel_mode() is False


def test_get_active_sessions_returns_copy(buffer: ParallelOutputBuffer) -> None:
    """get_active_sessions returns a copy, not internal state."""
    buffer.start_session("session-1")
    buffer.start_session("session-2")

    sessions1 = buffer.get_active_sessions()
    sessions2 = buffer.get_active_sessions()

    # Should be equal but not the same object
    assert sessions1 == sessions2
    assert sessions1 is not sessions2

    # Modifying returned list shouldn't affect buffer
    sessions1.append("fake-session")
    assert "fake-session" not in buffer.get_active_sessions()
