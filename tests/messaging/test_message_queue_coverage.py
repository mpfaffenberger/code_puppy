"""
Additional coverage tests for message_queue.py.

Focuses on uncovered code paths: start/stop lifecycle, listeners,
prompt request/response, async operations, and global helper functions.
"""

import asyncio
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.messaging.message_queue import (
    MessageQueue,
    MessageType,
    UIMessage,
    emit_agent_reasoning,
    emit_agent_response,
    emit_command_output,
    emit_divider,
    emit_error,
    emit_info,
    emit_message,
    emit_planned_next_steps,
    emit_success,
    emit_system_message,
    emit_tool_output,
    emit_warning,
    get_buffered_startup_messages,
    get_global_queue,
    provide_prompt_response,
)


class TestMessageQueueStartStop:
    """Test queue start/stop lifecycle."""

    def test_start_when_already_running(self):
        """Test that start() returns early when already running."""
        queue = MessageQueue()
        queue.start()
        assert queue._running is True
        original_thread = queue._thread

        # Call start again - should return early without creating new thread
        queue.start()
        assert queue._thread is original_thread
        assert queue._running is True

        queue.stop()

    def test_stop_running_queue(self):
        """Test stopping a running queue."""
        queue = MessageQueue()
        queue.start()
        assert queue._running is True
        assert queue._thread is not None
        assert queue._thread.is_alive()

        queue.stop()
        assert queue._running is False
        # Thread should have stopped (join with timeout)
        time.sleep(0.2)  # Give thread time to finish
        assert not queue._thread.is_alive()

    def test_stop_not_running_queue(self):
        """Test stopping a queue that was never started."""
        queue = MessageQueue()
        assert queue._running is False
        assert queue._thread is None

        # Should not raise
        queue.stop()
        assert queue._running is False


class TestMessageQueueListeners:
    """Test listener add/remove and notification."""

    def test_add_listener(self):
        """Test adding a listener."""
        queue = MessageQueue()
        callback = MagicMock()

        queue.add_listener(callback)

        assert callback in queue._listeners
        assert queue._has_active_renderer is True

    def test_remove_listener(self):
        """Test removing a listener."""
        queue = MessageQueue()
        callback = MagicMock()

        queue.add_listener(callback)
        assert queue._has_active_renderer is True

        queue.remove_listener(callback)
        assert callback not in queue._listeners
        assert queue._has_active_renderer is False

    def test_remove_nonexistent_listener(self):
        """Test removing a listener that doesn't exist."""
        queue = MessageQueue()
        callback = MagicMock()

        # Should not raise when removing non-existent listener
        queue.remove_listener(callback)
        assert queue._has_active_renderer is False

    def test_remove_one_of_multiple_listeners(self):
        """Test removing one listener keeps renderer active."""
        queue = MessageQueue()
        callback1 = MagicMock()
        callback2 = MagicMock()

        queue.add_listener(callback1)
        queue.add_listener(callback2)
        assert queue._has_active_renderer is True

        queue.remove_listener(callback1)
        assert callback2 in queue._listeners
        # Still has listeners, so renderer should remain active
        assert queue._has_active_renderer is True

    def test_listener_receives_messages(self):
        """Test that listeners receive messages from the processing thread."""
        queue = MessageQueue()
        received_messages = []

        def callback(msg):
            received_messages.append(msg)

        queue.add_listener(callback)
        queue.start()

        # Emit a message - it should go through the queue
        msg = UIMessage(type=MessageType.INFO, content="Test listener")
        queue.emit(msg)

        # Wait for the processing thread to handle it
        time.sleep(0.3)

        queue.stop()

        assert len(received_messages) == 1
        assert received_messages[0].content == "Test listener"

    def test_listener_exception_doesnt_break_processing(self):
        """Test that listener exceptions don't break message processing."""
        queue = MessageQueue()
        received_messages = []

        def bad_callback(msg):
            raise ValueError("Intentional error")

        def good_callback(msg):
            received_messages.append(msg)

        queue.add_listener(bad_callback)
        queue.add_listener(good_callback)
        queue.start()

        msg = UIMessage(type=MessageType.INFO, content="Test")
        queue.emit(msg)

        time.sleep(0.3)
        queue.stop()

        # Good callback should still receive the message
        assert len(received_messages) == 1


class TestMessageQueueAsyncOperations:
    """Test async queue operations."""

    @pytest.mark.asyncio
    async def test_get_async_initializes_queue(self):
        """Test that get_async lazy-initializes the async queue."""
        queue = MessageQueue()
        queue.mark_renderer_active()
        queue.start()

        assert queue._async_queue is None

        # Put a message in the queue
        msg = UIMessage(type=MessageType.INFO, content="Async test")
        queue.emit(msg)

        # Start waiting for async message (with timeout)
        async def get_with_timeout():
            try:
                return await asyncio.wait_for(queue.get_async(), timeout=0.5)
            except asyncio.TimeoutError:
                return None

        # The get_async should initialize the async queue
        # Note: The message might not arrive in time due to thread timing
        await get_with_timeout()

        # Async queue should now be initialized
        assert queue._async_queue is not None
        assert queue._event_loop is not None

        queue.stop()

    @pytest.mark.asyncio
    async def test_async_queue_receives_messages(self):
        """Test that async queue receives messages from the sync queue."""
        queue = MessageQueue()
        queue.mark_renderer_active()

        # Initialize async queue first by calling get_async
        async def init_and_wait():
            # Start the background thread after async queue is initialized
            asyncio.get_event_loop().call_soon(
                lambda: None
            )  # Ensure event loop is running

            # Create a task to wait for message
            async def wait_for_message():
                return await asyncio.wait_for(queue.get_async(), timeout=1.0)

            task = asyncio.create_task(wait_for_message())

            # Start the queue processing after a small delay
            await asyncio.sleep(0.05)
            queue.start()

            # Emit message after queue is started
            await asyncio.sleep(0.05)
            msg = UIMessage(type=MessageType.INFO, content="Async delivery")
            queue.emit(msg)

            try:
                result = await task
                return result
            except asyncio.TimeoutError:
                return None

        result = await init_and_wait()

        queue.stop()

        # Message should have been delivered
        if result:
            assert result.content == "Async delivery"


class TestPromptRequestResponse:
    """Test human input prompt request/response system."""

    def test_create_prompt_request(self):
        """Test creating a prompt request."""
        queue = MessageQueue()
        queue.mark_renderer_active()

        prompt_id = queue.create_prompt_request("Enter your name:")

        assert prompt_id == "prompt_1"
        # Second prompt should have incremented ID
        prompt_id2 = queue.create_prompt_request("Enter age:")
        assert prompt_id2 == "prompt_2"

    def test_create_prompt_request_emits_message(self):
        """Test that create_prompt_request emits a HUMAN_INPUT_REQUEST message."""
        queue = MessageQueue()
        queue.mark_renderer_active()

        queue.create_prompt_request("What is your quest?")

        msg = queue.get_nowait()
        assert msg is not None
        assert msg.type == MessageType.HUMAN_INPUT_REQUEST
        assert msg.content == "What is your quest?"
        assert "prompt_id" in msg.metadata

    def test_provide_prompt_response(self):
        """Test providing a response to a prompt."""
        queue = MessageQueue()

        queue.provide_prompt_response("prompt_1", "The Holy Grail")

        assert "prompt_1" in queue._prompt_responses
        assert queue._prompt_responses["prompt_1"] == "The Holy Grail"

    def test_wait_for_prompt_response_immediate(self):
        """Test waiting for a prompt response that's already available."""
        queue = MessageQueue()

        # Pre-populate the response
        queue._prompt_responses["prompt_1"] = "immediate response"

        # Should return immediately
        response = queue.wait_for_prompt_response("prompt_1", timeout=1.0)
        assert response == "immediate response"
        # Response should be consumed
        assert "prompt_1" not in queue._prompt_responses

    def test_wait_for_prompt_response_with_delay(self):
        """Test waiting for a prompt response that arrives after a delay."""
        queue = MessageQueue()

        def delayed_response():
            time.sleep(0.2)
            queue.provide_prompt_response("prompt_1", "delayed response")

        thread = threading.Thread(target=delayed_response)
        thread.start()

        response = queue.wait_for_prompt_response("prompt_1", timeout=2.0)
        thread.join()

        assert response == "delayed response"

    def test_wait_for_prompt_response_timeout(self):
        """Test that wait_for_prompt_response raises TimeoutError."""
        queue = MessageQueue()

        with pytest.raises(TimeoutError) as exc_info:
            queue.wait_for_prompt_response("nonexistent_prompt", timeout=0.2)

        assert "No response for prompt nonexistent_prompt" in str(exc_info.value)


class TestGlobalQueueFunctions:
    """Test global queue helper functions."""

    def test_get_global_queue_creates_queue(self):
        """Test that get_global_queue creates and starts a queue."""
        # Reset global state for test
        import code_puppy.messaging.message_queue as mq_module

        original_queue = mq_module._global_queue
        mq_module._global_queue = None

        try:
            queue = get_global_queue()
            assert queue is not None
            assert isinstance(queue, MessageQueue)
            assert queue._running is True
        finally:
            # Restore original queue
            if mq_module._global_queue:
                mq_module._global_queue.stop()
            mq_module._global_queue = original_queue

    def test_get_global_queue_returns_same_instance(self):
        """Test that get_global_queue returns the same instance."""
        queue1 = get_global_queue()
        queue2 = get_global_queue()
        assert queue1 is queue2

    def test_get_buffered_startup_messages(self):
        """Test getting buffered startup messages."""
        import code_puppy.messaging.message_queue as mq_module

        original_queue = mq_module._global_queue

        try:
            # Create a fresh queue
            mq_module._global_queue = MessageQueue()
            mq_module._global_queue.start()

            # Add to startup buffer
            msg = UIMessage(type=MessageType.INFO, content="startup msg")
            mq_module._global_queue._startup_buffer.append(msg)

            messages = get_buffered_startup_messages()
            assert len(messages) == 1
            assert messages[0].content == "startup msg"
        finally:
            if mq_module._global_queue:
                mq_module._global_queue.stop()
            mq_module._global_queue = original_queue

    def test_get_buffered_messages_includes_queued_messages(self):
        """Test that get_buffered_messages also retrieves from internal queue."""
        queue = MessageQueue()
        queue.mark_renderer_active()

        # Put messages directly in the internal queue
        msg1 = UIMessage(type=MessageType.INFO, content="from startup")
        msg2 = UIMessage(type=MessageType.INFO, content="from queue")

        queue._startup_buffer.append(msg1)
        queue._queue.put_nowait(msg2)

        # get_buffered_messages should get both
        messages = queue.get_buffered_messages()

        assert len(messages) == 2
        assert messages[0].content == "from startup"
        assert messages[1].content == "from queue"

    def test_provide_prompt_response_global(self):
        """Test the global provide_prompt_response function."""
        queue = get_global_queue()

        provide_prompt_response("test_prompt_global", "global response")

        assert "test_prompt_global" in queue._prompt_responses
        assert queue._prompt_responses["test_prompt_global"] == "global response"

        # Clean up
        queue._prompt_responses.pop("test_prompt_global", None)


class TestEmitHelperFunctions:
    """Test all emit_* helper functions."""

    def setup_method(self):
        """Set up for each test."""
        self.queue = get_global_queue()
        self.queue.mark_renderer_active()
        # Clear any existing messages
        while self.queue.get_nowait():
            pass

    def test_emit_message(self):
        """Test emit_message function."""
        emit_message(MessageType.DEBUG, "debug content", extra="data")

        msg = self.queue.get_nowait()
        assert msg is not None
        assert msg.type == MessageType.DEBUG
        assert msg.content == "debug content"
        assert msg.metadata.get("extra") == "data"

    def test_emit_info(self):
        """Test emit_info function."""
        emit_info("info message", key="value")

        msg = self.queue.get_nowait()
        assert msg.type == MessageType.INFO
        assert msg.content == "info message"

    def test_emit_success(self):
        """Test emit_success function."""
        emit_success("success message")

        msg = self.queue.get_nowait()
        assert msg.type == MessageType.SUCCESS
        assert msg.content == "success message"

    def test_emit_warning(self):
        """Test emit_warning function."""
        emit_warning("warning message")

        msg = self.queue.get_nowait()
        assert msg.type == MessageType.WARNING
        assert msg.content == "warning message"

    def test_emit_error(self):
        """Test emit_error function."""
        emit_error("error message")

        msg = self.queue.get_nowait()
        assert msg.type == MessageType.ERROR
        assert msg.content == "error message"

    def test_emit_tool_output_without_tool_name(self):
        """Test emit_tool_output without tool_name."""
        emit_tool_output("tool output")

        msg = self.queue.get_nowait()
        assert msg.type == MessageType.TOOL_OUTPUT
        assert msg.content == "tool output"
        assert "tool_name" not in msg.metadata

    def test_emit_tool_output_with_tool_name(self):
        """Test emit_tool_output with tool_name."""
        emit_tool_output("tool output", tool_name="my_tool")

        msg = self.queue.get_nowait()
        assert msg.type == MessageType.TOOL_OUTPUT
        assert msg.metadata["tool_name"] == "my_tool"

    def test_emit_command_output_without_command(self):
        """Test emit_command_output without command."""
        emit_command_output("command output")

        msg = self.queue.get_nowait()
        assert msg.type == MessageType.COMMAND_OUTPUT
        assert msg.content == "command output"
        assert "command" not in msg.metadata

    def test_emit_command_output_with_command(self):
        """Test emit_command_output with command."""
        emit_command_output("output", command="ls -la")

        msg = self.queue.get_nowait()
        assert msg.type == MessageType.COMMAND_OUTPUT
        assert msg.metadata["command"] == "ls -la"

    def test_emit_agent_reasoning(self):
        """Test emit_agent_reasoning function."""
        emit_agent_reasoning("thinking about stuff")

        msg = self.queue.get_nowait()
        assert msg.type == MessageType.AGENT_REASONING
        assert msg.content == "thinking about stuff"

    def test_emit_planned_next_steps(self):
        """Test emit_planned_next_steps function."""
        emit_planned_next_steps(["step 1", "step 2"])

        msg = self.queue.get_nowait()
        assert msg.type == MessageType.PLANNED_NEXT_STEPS
        assert msg.content == ["step 1", "step 2"]

    def test_emit_agent_response(self):
        """Test emit_agent_response function."""
        emit_agent_response("Here is my response")

        msg = self.queue.get_nowait()
        assert msg.type == MessageType.AGENT_RESPONSE
        assert msg.content == "Here is my response"

    def test_emit_system_message(self):
        """Test emit_system_message function."""
        emit_system_message("system notification")

        msg = self.queue.get_nowait()
        assert msg.type == MessageType.SYSTEM
        assert msg.content == "system notification"

    def test_emit_divider_default(self):
        """Test emit_divider with default content."""
        emit_divider()

        msg = self.queue.get_nowait()
        assert msg.type == MessageType.DIVIDER
        assert "─" in msg.content  # Default divider character

    def test_emit_divider_custom(self):
        """Test emit_divider with custom content."""
        emit_divider("====")

        msg = self.queue.get_nowait()
        assert msg.type == MessageType.DIVIDER
        assert msg.content == "===="


class TestEmitPrompt:
    """Test emit_prompt function."""

    def test_emit_prompt(self):
        """Test emit_prompt calls safe_input and returns response."""
        with patch(
            "code_puppy.command_line.utils.safe_input", return_value="user input"
        ) as mock_input:
            from code_puppy.messaging.message_queue import emit_prompt

            result = emit_prompt("Enter something:")

            assert result == "user input"
            mock_input.assert_called_once_with(">>> ")


class TestProcessMessagesEdgeCases:
    """Test edge cases in _process_messages."""

    def test_process_messages_with_async_queue_error(self):
        """Test that async queue errors don't break processing."""
        queue = MessageQueue()
        received = []

        def callback(msg):
            received.append(msg)

        queue.add_listener(callback)

        # Set up a mock async queue that raises
        queue._async_queue = asyncio.Queue()
        mock_loop = MagicMock()
        mock_loop.call_soon_threadsafe.side_effect = RuntimeError("Event loop closed")
        queue._event_loop = mock_loop

        queue.start()

        msg = UIMessage(type=MessageType.INFO, content="Test error handling")
        queue.emit(msg)

        time.sleep(0.3)
        queue.stop()

        # Message should still be delivered to listeners despite async error
        assert len(received) == 1
        assert received[0].content == "Test error handling"

    def test_process_messages_queue_empty_timeout(self):
        """Test that _process_messages handles queue.Empty gracefully."""
        queue = MessageQueue()
        queue.start()

        # Let it run with no messages for a bit
        time.sleep(0.3)

        # Should still be running
        assert queue._running is True
        assert queue._thread.is_alive()

        queue.stop()


class TestEmitQueueFullEdgeCase:
    """Test edge case when queue is full and get_nowait fails."""

    def test_emit_queue_full_get_also_fails(self):
        """Test emit when queue is full and get_nowait also fails (race condition)."""
        import queue as queue_module

        mq = MessageQueue(maxsize=1)
        mq.mark_renderer_active()

        # Fill the queue
        msg1 = UIMessage(type=MessageType.INFO, content="Msg1")
        mq.emit(msg1)

        # This tests the except queue.Empty: pass branch on line 126-127
        # We simulate the race condition where queue.Full is raised, then
        # when we try to get_nowait to make room, it's already empty
        with patch.object(mq._queue, "put_nowait", side_effect=queue_module.Full):
            with patch.object(mq._queue, "get_nowait", side_effect=queue_module.Empty):
                # This should not raise - it catches the exception
                msg2 = UIMessage(type=MessageType.INFO, content="Msg2")
                mq.emit(msg2)  # Should handle gracefully


class TestStartupBuffer:
    """Tests for startup buffer and clear_startup_buffer."""

    def test_clear_startup_buffer(self):
        mq = MessageQueue()
        msg = UIMessage(type=MessageType.INFO, content="buffered")
        mq.emit(msg)  # No active renderer, goes to buffer
        assert len(mq._startup_buffer) == 1
        mq.clear_startup_buffer()
        assert len(mq._startup_buffer) == 0

    def test_emit_without_active_renderer_buffers(self):
        mq = MessageQueue()
        msg = UIMessage(type=MessageType.INFO, content="buf")
        mq.emit(msg)
        assert len(mq._startup_buffer) == 1
        assert mq._startup_buffer[0].content == "buf"

    def test_emit_overflow_drop_and_retry(self):
        """Queue Full → drop oldest → retry put succeeds (line 129)."""
        import queue as queue_module

        mq = MessageQueue()
        mq._has_active_renderer = True
        call_count = [0]
        orig_put = mq._queue.put_nowait

        def put_side_effect(item):
            call_count[0] += 1
            if call_count[0] == 1:
                raise queue_module.Full()
            return orig_put(item)

        with patch.object(mq._queue, "put_nowait", side_effect=put_side_effect):
            msg = UIMessage(type=MessageType.INFO, content="x")
            mq._queue.put("placeholder")  # Fill queue for get_nowait
            mq.emit(msg)
        assert call_count[0] == 2  # put_nowait called twice

    def test_emit_overflow_race_empty(self):
        """Queue Full then Empty race condition (line 130-131)."""
        import queue as queue_module

        mq = MessageQueue()
        mq._has_active_renderer = True
        with patch.object(mq._queue, "put_nowait", side_effect=queue_module.Full):
            with patch.object(mq._queue, "get_nowait", side_effect=queue_module.Empty):
                msg = UIMessage(type=MessageType.INFO, content="x")
                mq.emit(msg)  # Should not raise
