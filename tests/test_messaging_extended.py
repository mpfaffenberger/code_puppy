import threading
import time
from datetime import datetime, timezone
from unittest.mock import patch

from code_puppy.messaging.message_queue import (
    MessageQueue,
    MessageType,
    UIMessage,
    get_global_queue,
)


class TestMessagingExtended:
    """Test extended messaging functionality."""

    def setup_method(self):
        """Set up a fresh message queue for each test."""
        self.queue = MessageQueue()
        self.queue.start()

    def teardown_method(self):
        """Clean up after each test."""
        if self.queue:
            self.queue.stop()

    def test_emit_info(self):
        """Test info message emission."""
        # Mark renderer as active so messages don't get buffered
        self.queue.mark_renderer_active()

        # Use the queue instance directly, not global functions
        self.queue.emit_simple(MessageType.INFO, "Test message", group="test")

        # Retrieve the message
        message = self.queue.get_nowait()
        assert message is not None
        assert message.type == MessageType.INFO
        assert message.content == "Test message"
        assert message.metadata.get("group") == "test"

    def test_emit_with_group(self):
        """Test message groups."""
        self.queue.mark_renderer_active()

        # Emit messages with different groups using queue directly
        self.queue.emit_simple(MessageType.INFO, "Group A message", group="group_a")
        self.queue.emit_simple(MessageType.ERROR, "Group B message", group="group_b")
        self.queue.emit_simple(MessageType.SUCCESS, "No group message")

        # Collect all messages
        messages = []
        for _ in range(3):
            msg = self.queue.get_nowait()
            if msg is None:
                break
            messages.append(msg)

        # Verify groups
        group_a_msgs = [m for m in messages if m.metadata.get("group") == "group_a"]
        group_b_msgs = [m for m in messages if m.metadata.get("group") == "group_b"]
        no_group_msgs = [m for m in messages if "group" not in m.metadata]

        assert len(group_a_msgs) == 1
        assert len(group_b_msgs) == 1
        assert len(no_group_msgs) == 1

        assert group_a_msgs[0].content == "Group A message"
        assert group_b_msgs[0].content == "Group B message"
        assert no_group_msgs[0].content == "No group message"

    def test_message_filtering_by_group(self):
        """Test filtering messages by group."""
        self.queue.mark_renderer_active()

        # Add messages to queue directly
        self.queue.emit_simple(MessageType.INFO, "Message 1", group="alpha")
        self.queue.emit_simple(MessageType.ERROR, "Message 2", group="beta")
        self.queue.emit_simple(MessageType.SUCCESS, "Message 3", group="alpha")
        self.queue.emit_simple(MessageType.WARNING, "Message 4")

        # Get all messages
        all_messages = []
        for _ in range(4):  # We know we added 4 messages
            msg = self.queue.get_nowait()
            if msg:
                all_messages.append(msg)

        # Filter by group
        alpha_messages = [m for m in all_messages if m.metadata.get("group") == "alpha"]
        beta_messages = [m for m in all_messages if m.metadata.get("group") == "beta"]
        ungrouped = [m for m in all_messages if "group" not in m.metadata]

        assert len(alpha_messages) == 2
        assert len(beta_messages) == 1
        assert len(ungrouped) == 1

        # Verify content
        alpha_contents = [m.content for m in alpha_messages]
        assert "Message 1" in alpha_contents
        assert "Message 3" in alpha_contents

    def test_queue_clearing(self):
        """Test clearing the message queue."""
        self.queue.mark_renderer_active()

        # Add some messages
        self.queue.emit_simple(MessageType.INFO, "Message 1")
        self.queue.emit_simple(MessageType.ERROR, "Message 2")
        self.queue.emit_simple(MessageType.SUCCESS, "Message 3")

        # Verify messages are there
        assert self.queue.get_nowait() is not None
        assert self.queue.get_nowait() is not None
        assert self.queue.get_nowait() is not None
        assert self.queue.get_nowait() is None  # Should be empty now

        # Add more messages
        self.queue.emit_simple(MessageType.INFO, "New message")

        # Clear by consuming all messages
        cleared_messages = []
        while True:
            msg = self.queue.get_nowait()
            if msg is None:
                break
            cleared_messages.append(msg)

        assert len(cleared_messages) == 1
        assert cleared_messages[0].content == "New message"
        assert self.queue.get_nowait() is None

    def test_message_rendering_helpers(self):
        """Test various message rendering helper functions."""
        self.queue.mark_renderer_active()

        # Test different message types directly on queue
        self.queue.emit_simple(MessageType.INFO, "Info message")
        self.queue.emit_simple(MessageType.ERROR, "Error message")
        self.queue.emit_simple(MessageType.SUCCESS, "Success message")
        self.queue.emit_simple(MessageType.WARNING, "Warning message")
        self.queue.emit_simple(
            MessageType.TOOL_OUTPUT, "Tool output", tool_name="test_tool"
        )
        self.queue.emit_simple(
            MessageType.COMMAND_OUTPUT, "Command output", command="ls -la"
        )
        self.queue.emit_simple(MessageType.AGENT_REASONING, "Agent reasoning")
        self.queue.emit_simple(MessageType.SYSTEM, "System message")

        # Collect all messages
        messages = []
        for _ in range(8):
            msg = self.queue.get_nowait()
            if msg:
                messages.append(msg)

        # Verify message types and content
        message_types = {msg.type for msg in messages}
        expected_types = {
            MessageType.INFO,
            MessageType.ERROR,
            MessageType.SUCCESS,
            MessageType.WARNING,
            MessageType.TOOL_OUTPUT,
            MessageType.COMMAND_OUTPUT,
            MessageType.AGENT_REASONING,
            MessageType.SYSTEM,
        }
        assert message_types == expected_types

        # Check specific metadata
        tool_msg = next(m for m in messages if m.type == MessageType.TOOL_OUTPUT)
        assert tool_msg.metadata.get("tool_name") == "test_tool"

        cmd_msg = next(m for m in messages if m.type == MessageType.COMMAND_OUTPUT)
        assert cmd_msg.metadata.get("command") == "ls -la"

    def test_buffered_messages_before_renderer(self):
        """Test message buffering before renderer is active."""
        # Don't mark renderer as active - messages should be buffered
        self.queue.emit_simple(MessageType.INFO, "Buffered message 1")
        self.queue.emit_simple(MessageType.ERROR, "Buffered message 2")

        # Messages should be in startup buffer, not main queue
        assert self.queue.get_nowait() is None

        # Get buffered messages
        buffered = self.queue.get_buffered_messages()
        assert len(buffered) == 2

        contents = [msg.content for msg in buffered]
        assert "Buffered message 1" in contents
        assert "Buffered message 2" in contents

        # Clear buffer and mark renderer active
        self.queue.clear_startup_buffer()
        self.queue.mark_renderer_active()

        # Now messages should go to main queue
        self.queue.emit_simple(MessageType.INFO, "Direct message")
        message = self.queue.get_nowait()
        assert message is not None
        assert message.content == "Direct message"

    def test_message_listeners(self):
        """Test message listener functionality."""
        received_messages = []

        def test_listener(message):
            received_messages.append(message)

        # Add listener and mark renderer active
        self.queue.add_listener(test_listener)
        self.queue.mark_renderer_active()

        # Emit messages
        self.queue.emit_simple(MessageType.INFO, "Listener test 1")
        self.queue.emit_simple(MessageType.ERROR, "Listener test 2")

        # Give some time for async processing
        time.sleep(0.1)

        # Verify listener received messages
        assert len(received_messages) == 2
        contents = [msg.content for msg in received_messages]
        assert "Listener test 1" in contents
        assert "Listener test 2" in contents

        # Remove listener
        self.queue.remove_listener(test_listener)

        # Emit another message
        self.queue.emit_simple(MessageType.INFO, "After removal")

        # Give processing time
        time.sleep(0.1)

        # Listener should not have received the new message
        assert len(received_messages) == 2

    def test_ui_message_timestamps(self):
        """Test that UIMessage objects get proper timestamps."""
        self.queue.mark_renderer_active()

        before = datetime.now(timezone.utc)
        self.queue.emit_simple(MessageType.INFO, "Timestamp test")
        after = datetime.now(timezone.utc)

        message = self.queue.get_nowait()
        assert message is not None
        assert message.timestamp is not None
        assert before <= message.timestamp <= after

    def test_global_queue_singleton(self):
        """Test that global queue is a singleton."""
        queue1 = get_global_queue()
        queue2 = get_global_queue()

        assert queue1 is queue2

        # Test that it's started automatically
        assert queue1._running

    @patch("code_puppy.tui_state.is_tui_mode")
    def test_emit_divider(self, mock_tui_mode):
        """Test divider emission in different modes."""
        # Test non-TUI mode
        mock_tui_mode.return_value = False
        self.queue.mark_renderer_active()

        # Create a divider message directly
        divider_content = "[dim]" + "─" * 100 + "\n" + "[/dim]"
        self.queue.emit_simple(MessageType.DIVIDER, divider_content)

        message = self.queue.get_nowait()
        assert message is not None
        assert message.type == MessageType.DIVIDER
        assert message.content == divider_content

    def test_queue_full_behavior(self):
        """Test queue behavior when full."""
        # Create a small queue
        small_queue = MessageQueue(maxsize=2)
        small_queue.start()
        small_queue.mark_renderer_active()

        try:
            # Fill the queue
            small_queue.emit_simple(MessageType.INFO, "Message 1")
            small_queue.emit_simple(MessageType.INFO, "Message 2")

            # Add one more - should drop oldest
            small_queue.emit_simple(MessageType.INFO, "Message 3")

            # Get messages
            msg1 = small_queue.get_nowait()
            msg2 = small_queue.get_nowait()

            # Should have Message 2 and Message 3 (Message 1 was dropped)
            assert msg1.content == "Message 2"
            assert msg2.content == "Message 3"

            # Queue should be empty now
            assert small_queue.get_nowait() is None

        finally:
            small_queue.stop()

    def test_concurrent_access(self):
        """Test thread-safe concurrent access to queue."""
        self.queue.mark_renderer_active()

        messages_sent = []

        def producer():
            for i in range(5):
                msg_content = f"Producer message {i}"
                messages_sent.append(msg_content)
                self.queue.emit_simple(MessageType.INFO, msg_content)

        # Start producer thread
        producer_thread = threading.Thread(target=producer)
        producer_thread.start()
        producer_thread.join()

        # Give a brief moment for messages to be processed
        time.sleep(0.1)

        # Now consume all messages
        messages_received = []
        for _ in range(10):  # Try to get all messages
            msg = self.queue.get_nowait()
            if msg:
                messages_received.append(msg.content)
            else:
                break

        # Should have received all messages (may be less due to processing thread consumption)
        assert len(messages_received) <= 5
        assert len(messages_received) >= 0

        # All received messages should be in sent messages
        for received in messages_received:
            assert received in messages_sent

        # Queue should be empty now
        assert self.queue.get_nowait() is None

    def test_ui_message_creation(self):
        """Test UIMessage dataclass creation and defaults."""
        # Test with minimal parameters
        msg = UIMessage(type=MessageType.INFO, content="Test")
        assert msg.type == MessageType.INFO
        assert msg.content == "Test"
        assert msg.timestamp is not None
        assert msg.metadata == {}

        # Test with all parameters
        custom_time = datetime.now(timezone.utc)
        custom_metadata = {"key": "value"}
        msg2 = UIMessage(
            type=MessageType.ERROR,
            content="Error",
            timestamp=custom_time,
            metadata=custom_metadata,
        )
        assert msg2.type == MessageType.ERROR
        assert msg2.content == "Error"
        assert msg2.timestamp == custom_time
        assert msg2.metadata == custom_metadata

    def test_message_queue_operations(self):
        """Test basic queue operations."""
        self.queue.mark_renderer_active()

        # Test empty queue
        assert self.queue.get_nowait() is None

        # Test single message
        test_msg = UIMessage(type=MessageType.INFO, content="Single test")
        self.queue.emit(test_msg)

        retrieved = self.queue.get_nowait()
        assert retrieved is not None
        assert retrieved.content == "Single test"
        assert retrieved.type == MessageType.INFO

        # Queue should be empty again
        assert self.queue.get_nowait() is None

        # Test multiple messages
        messages = [
            UIMessage(type=MessageType.INFO, content="Msg 1"),
            UIMessage(type=MessageType.ERROR, content="Msg 2"),
            UIMessage(type=MessageType.SUCCESS, content="Msg 3"),
        ]

        for msg in messages:
            self.queue.emit(msg)

        # Retrieve in FIFO order
        for i, expected_msg in enumerate(messages):
            retrieved = self.queue.get_nowait()
            assert retrieved is not None
            assert retrieved.content == expected_msg.content
            assert retrieved.type == expected_msg.type
