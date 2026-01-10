"""
Comprehensive tests for MessageQueue functionality.

Tests cover message queueing, buffering, rendering state, and async operations.
"""

import threading
from datetime import datetime, timezone

from rich.table import Table
from rich.text import Text

from code_puppy.messaging.message_queue import MessageQueue, MessageType, UIMessage


class TestUIMessage:
    """Test UIMessage dataclass functionality."""

    def test_ui_message_creation(self):
        """Test creating a UIMessage."""
        msg = UIMessage(type=MessageType.INFO, content="Hello")
        assert msg.type == MessageType.INFO
        assert msg.content == "Hello"
        assert msg.timestamp is not None
        assert msg.metadata == {}

    def test_ui_message_with_custom_timestamp(self):
        """Test creating a UIMessage with custom timestamp."""
        ts = datetime.now(timezone.utc)
        msg = UIMessage(type=MessageType.INFO, content="Test", timestamp=ts)
        assert msg.timestamp == ts

    def test_ui_message_with_metadata(self):
        """Test creating a UIMessage with metadata."""
        meta = {"key": "value", "count": 42}
        msg = UIMessage(type=MessageType.INFO, content="Test", metadata=meta)
        assert msg.metadata == meta

    def test_ui_message_with_rich_text(self):
        """Test creating a UIMessage with Rich Text content."""
        text = Text("Styled content", style="bold red")
        msg = UIMessage(type=MessageType.ERROR, content=text)
        assert msg.content is text
        assert msg.type == MessageType.ERROR

    def test_ui_message_with_table(self):
        """Test creating a UIMessage with a Rich Table."""
        table = Table(title="Data")
        table.add_column("Name")
        table.add_row("Item 1")
        msg = UIMessage(type=MessageType.TOOL_OUTPUT, content=table)
        assert msg.content is table

    def test_message_type_enum(self):
        """Test MessageType enum values."""
        assert MessageType.INFO.value == "info"
        assert MessageType.ERROR.value == "error"
        assert MessageType.SUCCESS.value == "success"
        assert MessageType.WARNING.value == "warning"
        assert MessageType.AGENT_REASONING.value == "agent_reasoning"


class TestMessageQueueBasic:
    """Test basic MessageQueue functionality."""

    def test_queue_initialization(self):
        """Test MessageQueue initialization."""
        queue = MessageQueue()
        assert queue._running is False
        assert queue._has_active_renderer is False
        assert queue._startup_buffer == []
        assert queue._listeners == []

    def test_queue_initialization_custom_maxsize(self):
        """Test MessageQueue with custom maxsize."""
        queue = MessageQueue(maxsize=500)
        assert queue._queue.maxsize == 500

    def test_emit_message(self):
        """Test emitting a message to the queue."""
        queue = MessageQueue()
        queue.mark_renderer_active()
        msg = UIMessage(type=MessageType.INFO, content="Test")
        queue.emit(msg)
        assert not queue._queue.empty()

    def test_get_message_nowait(self):
        """Test getting a message without blocking."""
        queue = MessageQueue()
        queue.mark_renderer_active()
        msg = UIMessage(type=MessageType.INFO, content="Test")
        queue.emit(msg)
        retrieved = queue.get_nowait()
        assert retrieved.content == "Test"

    def test_get_message_nowait_empty(self):
        """Test getting message without blocking when queue is empty."""
        queue = MessageQueue()
        queue.mark_renderer_active()
        retrieved = queue.get_nowait()
        assert retrieved is None

    def test_queue_empty(self):
        """Test checking if queue is empty."""
        queue = MessageQueue()
        assert queue._queue.empty()
        queue.mark_renderer_active()
        msg = UIMessage(type=MessageType.INFO, content="Test")
        queue.emit(msg)
        assert not queue._queue.empty()

    def test_queue_qsize(self):
        """Test getting queue size."""
        queue = MessageQueue()
        queue.mark_renderer_active()
        assert queue._queue.qsize() == 0
        for i in range(3):
            msg = UIMessage(type=MessageType.INFO, content=f"Msg {i}")
            queue.emit(msg)
        assert queue._queue.qsize() == 3


class TestMessageQueueBuffering:
    """Test message buffering when no renderer is active."""

    def test_buffer_messages_before_renderer(self):
        """Test that messages are buffered before renderer activation."""
        queue = MessageQueue()
        assert not queue._has_active_renderer
        msg = UIMessage(type=MessageType.INFO, content="Buffered")
        queue.emit(msg)
        assert msg in queue._startup_buffer
        assert queue._queue.empty()

    def test_get_buffered_messages(self):
        """Test retrieving buffered messages."""
        queue = MessageQueue()
        msgs = []
        for i in range(3):
            msg = UIMessage(type=MessageType.INFO, content=f"Msg {i}")
            msgs.append(msg)
            queue.emit(msg)
        buffered = queue.get_buffered_messages()
        assert len(buffered) == 3
        assert all(m in buffered for m in msgs)

    def test_get_buffered_messages_empty(self):
        """Test getting buffered messages when none exist."""
        queue = MessageQueue()
        buffered = queue.get_buffered_messages()
        assert buffered == []

    def test_buffer_then_activate_renderer(self):
        """Test that messages are buffered, then flushed when renderer activates."""
        queue = MessageQueue()
        msg1 = UIMessage(type=MessageType.INFO, content="First")
        queue.emit(msg1)
        assert len(queue._startup_buffer) == 1

        queue.mark_renderer_active()
        msg2 = UIMessage(type=MessageType.INFO, content="Second")
        queue.emit(msg2)

        # First message should still be buffered
        # Second message should go directly to queue
        assert msg1 in queue._startup_buffer
        assert not queue._queue.empty()
        retrieved = queue._queue.get_nowait()
        assert retrieved.content == "Second"

    def test_clear_buffer(self):
        """Test clearing the message buffer."""
        queue = MessageQueue()
        for i in range(3):
            msg = UIMessage(type=MessageType.INFO, content=f"Msg {i}")
            queue.emit(msg)
        assert len(queue._startup_buffer) == 3
        queue.clear_startup_buffer()
        assert len(queue._startup_buffer) == 0


class TestRendererMarking:
    """Test renderer activation/deactivation."""

    def test_mark_renderer_active(self):
        """Test marking renderer as active."""
        queue = MessageQueue()
        assert not queue._has_active_renderer
        queue.mark_renderer_active()
        assert queue._has_active_renderer

    def test_mark_renderer_inactive(self):
        """Test marking renderer as inactive."""
        queue = MessageQueue()
        queue.mark_renderer_active()
        assert queue._has_active_renderer
        queue.mark_renderer_inactive()
        assert not queue._has_active_renderer

    def test_multiple_renderer_marks(self):
        """Test multiple renderer activation/deactivation cycles."""
        queue = MessageQueue()
        for _ in range(3):
            queue.mark_renderer_active()
            assert queue._has_active_renderer
            queue.mark_renderer_inactive()
            assert not queue._has_active_renderer


class TestMessageQueueTypes:
    """Test different message types."""

    def test_info_message(self):
        """Test INFO message type."""
        queue = MessageQueue()
        queue.mark_renderer_active()
        msg = UIMessage(type=MessageType.INFO, content="Info")
        queue.emit(msg)
        retrieved = queue.get_nowait()
        assert retrieved.type == MessageType.INFO

    def test_error_message(self):
        """Test ERROR message type."""
        queue = MessageQueue()
        queue.mark_renderer_active()
        msg = UIMessage(type=MessageType.ERROR, content="Error")
        queue.emit(msg)
        retrieved = queue.get_nowait()
        assert retrieved.type == MessageType.ERROR

    def test_success_message(self):
        """Test SUCCESS message type."""
        queue = MessageQueue()
        queue.mark_renderer_active()
        msg = UIMessage(type=MessageType.SUCCESS, content="Success")
        queue.emit(msg)
        retrieved = queue.get_nowait()
        assert retrieved.type == MessageType.SUCCESS

    def test_warning_message(self):
        """Test WARNING message type."""
        queue = MessageQueue()
        queue.mark_renderer_active()
        msg = UIMessage(type=MessageType.WARNING, content="Warning")
        queue.emit(msg)
        retrieved = queue.get_nowait()
        assert retrieved.type == MessageType.WARNING

    def test_tool_output_message(self):
        """Test TOOL_OUTPUT message type."""
        queue = MessageQueue()
        queue.mark_renderer_active()
        msg = UIMessage(type=MessageType.TOOL_OUTPUT, content="Output")
        queue.emit(msg)
        retrieved = queue.get_nowait()
        assert retrieved.type == MessageType.TOOL_OUTPUT

    def test_agent_reasoning_message(self):
        """Test AGENT_REASONING message type."""
        queue = MessageQueue()
        queue.mark_renderer_active()
        msg = UIMessage(type=MessageType.AGENT_REASONING, content="Thinking")
        queue.emit(msg)
        retrieved = queue.get_nowait()
        assert retrieved.type == MessageType.AGENT_REASONING

    def test_divider_message(self):
        """Test DIVIDER message type."""
        queue = MessageQueue()
        queue.mark_renderer_active()
        msg = UIMessage(type=MessageType.DIVIDER, content="---")
        queue.emit(msg)
        retrieved = queue.get_nowait()
        assert retrieved.type == MessageType.DIVIDER


class TestQueueThreadSafety:
    """Test thread-safety of MessageQueue."""

    def test_concurrent_emit(self):
        """Test concurrent message emission."""
        queue = MessageQueue(maxsize=1000)
        queue.mark_renderer_active()
        results = []

        def insert_messages(thread_id):
            for i in range(10):
                msg = UIMessage(
                    type=MessageType.INFO, content=f"thread-{thread_id}-msg-{i}"
                )
                queue.emit(msg)
                results.append(msg)

        threads = [
            threading.Thread(target=insert_messages, args=(i,)) for i in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 30
        assert queue._queue.qsize() == 30

    def test_concurrent_get_nowait(self):
        """Test concurrent message retrieval without blocking."""
        queue = MessageQueue()
        queue.mark_renderer_active()

        # Insert messages
        for i in range(20):
            msg = UIMessage(type=MessageType.INFO, content=f"Msg {i}")
            queue.emit(msg)

        retrieved = []

        def get_messages():
            while True:
                msg = queue.get_nowait()
                if msg is None:
                    break
                retrieved.append(msg)

        threads = [threading.Thread(target=get_messages) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(retrieved) == 20


class TestQueueEdgeCases:
    """Test edge cases and error conditions."""

    def test_emit_many_messages(self):
        """Test emitting many messages in the queue."""
        queue = MessageQueue(maxsize=100)
        queue.mark_renderer_active()

        # Emit 50 messages
        for i in range(50):
            msg = UIMessage(type=MessageType.INFO, content=f"Msg {i}")
            queue.emit(msg)

        # Get them all back
        for i in range(50):
            retrieved = queue.get_nowait()
            assert retrieved.content == f"Msg {i}"

    def test_message_with_none_content(self):
        """Test handling of message with None content."""
        queue = MessageQueue()
        queue.mark_renderer_active()
        msg = UIMessage(type=MessageType.INFO, content=None)
        queue.emit(msg)
        retrieved = queue.get_nowait()
        assert retrieved.content is None

    def test_message_with_empty_metadata(self):
        """Test message with empty metadata dict."""
        queue = MessageQueue()
        queue.mark_renderer_active()
        msg = UIMessage(type=MessageType.INFO, content="Test", metadata={})
        queue.emit(msg)
        retrieved = queue.get_nowait()
        assert retrieved.metadata == {}

    def test_emit_when_queue_full(self):
        """Test emitting message when queue is full."""
        queue = MessageQueue(maxsize=2)
        queue.mark_renderer_active()

        # Fill the queue
        msg1 = UIMessage(type=MessageType.INFO, content="Msg1")
        msg2 = UIMessage(type=MessageType.INFO, content="Msg2")
        queue.emit(msg1)
        queue.emit(msg2)

        # Emit another message when full - should drop oldest
        msg3 = UIMessage(type=MessageType.INFO, content="Msg3")
        queue.emit(msg3)

        # Queue should have msg2 and msg3
        retrieved1 = queue.get_nowait()
        retrieved2 = queue.get_nowait()
        assert retrieved1.content == "Msg2"
        assert retrieved2.content == "Msg3"


class TestMessageQueueLifecycle:
    """Test queue lifecycle and state management."""

    def test_initial_state(self):
        """Test queue initial state."""
        queue = MessageQueue()
        assert queue._running is False
        assert queue._has_active_renderer is False
        assert queue._startup_buffer == []
        assert queue._thread is None

    def test_buffer_clears_on_access(self):
        """Test that buffer persists until explicitly cleared."""
        queue = MessageQueue()
        msg1 = UIMessage(type=MessageType.INFO, content="Buffered")
        queue.emit(msg1)

        # Buffer should still have message
        assert msg1 in queue._startup_buffer

        # Get buffered messages
        buffered = queue.get_buffered_messages()
        assert len(buffered) == 1

        # Buffer still there until cleared
        assert msg1 in queue._startup_buffer

        # Clear it
        queue.clear_startup_buffer()
        assert queue._startup_buffer == []

    def test_renderer_state_affects_buffering(self):
        """Test that renderer state controls message destination."""
        queue = MessageQueue()

        # With no renderer, messages buffer
        msg1 = UIMessage(type=MessageType.INFO, content="Msg1")
        queue.emit(msg1)
        assert msg1 in queue._startup_buffer
        assert queue._queue.empty()

        # Activate renderer
        queue.mark_renderer_active()

        # New messages go to queue
        msg2 = UIMessage(type=MessageType.INFO, content="Msg2")
        queue.emit(msg2)
        assert msg2 not in queue._startup_buffer
        assert not queue._queue.empty()

    def test_emit_simple(self):
        """Test the emit_simple convenience method."""
        queue = MessageQueue()
        queue.mark_renderer_active()
        queue.emit_simple(MessageType.INFO, "Test content", key="value")

        retrieved = queue.get_nowait()
        assert retrieved.type == MessageType.INFO
        assert retrieved.content == "Test content"
        assert retrieved.metadata["key"] == "value"
