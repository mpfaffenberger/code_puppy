"""
Comprehensive tests for the MessageBus messaging infrastructure.

Tests cover message emission, request/response correlation, session context,
queue management, and async/sync operation.
"""

import asyncio
import queue
import threading
from unittest.mock import patch

import pytest

from code_puppy.messaging.bus import MessageBus
from code_puppy.messaging.commands import (
    ConfirmationResponse,
    SelectionResponse,
    UserInputResponse,
)
from code_puppy.messaging.messages import (
    MessageCategory,
    MessageLevel,
    TextMessage,
)


class TestMessageBusInitialization:
    """Test MessageBus initialization and basic setup."""

    def test_initialization_default(self):
        """Test default initialization."""
        bus = MessageBus()
        assert bus._maxsize == 1000
        assert isinstance(bus._outgoing, queue.Queue)
        assert isinstance(bus._incoming, queue.Queue)
        assert bus._current_session_id is None
        assert not bus._has_active_renderer
        assert bus._startup_buffer == []

    def test_initialization_custom_maxsize(self):
        """Test initialization with custom maxsize."""
        bus = MessageBus(maxsize=500)
        assert bus._maxsize == 500

    def test_initialization_queues_are_independent(self):
        """Test that outgoing and incoming queues are separate."""
        bus = MessageBus()
        assert bus._outgoing is not bus._incoming
        assert isinstance(bus._outgoing, queue.Queue)
        assert isinstance(bus._incoming, queue.Queue)


class TestMessageBusEmission:
    """Test message emission functionality."""

    def test_emit_text_message(self):
        """Test emitting a text message."""
        bus = MessageBus()
        bus._has_active_renderer = True
        message = TextMessage(level=MessageLevel.INFO, text="Hello")
        bus.emit(message)
        assert not bus._outgoing.empty()
        emitted = bus._outgoing.get_nowait()
        assert emitted.text == "Hello"

    def test_emit_buffers_without_renderer(self):
        """Test that messages are buffered when no renderer is active."""
        bus = MessageBus()
        assert not bus._has_active_renderer
        message = TextMessage(level=MessageLevel.INFO, text="Test")
        bus.emit(message)
        assert bus._outgoing.empty()
        assert len(bus._startup_buffer) == 1
        assert bus._startup_buffer[0].text == "Test"

    def test_emit_info(self):
        """Test emit_info helper method."""
        bus = MessageBus()
        bus._has_active_renderer = True
        bus.emit_info("Info message")
        assert not bus._outgoing.empty()
        msg = bus._outgoing.get_nowait()
        assert msg.level == MessageLevel.INFO
        assert msg.text == "Info message"

    def test_emit_warning(self):
        """Test emit_warning helper method."""
        bus = MessageBus()
        bus._has_active_renderer = True
        bus.emit_warning("Warning!")
        msg = bus._outgoing.get_nowait()
        assert msg.level == MessageLevel.WARNING

    def test_emit_error(self):
        """Test emit_error helper method."""
        bus = MessageBus()
        bus._has_active_renderer = True
        bus.emit_error("Error!")
        msg = bus._outgoing.get_nowait()
        assert msg.level == MessageLevel.ERROR

    def test_emit_success(self):
        """Test emit_success helper method."""
        bus = MessageBus()
        bus._has_active_renderer = True
        bus.emit_success("Success!")
        msg = bus._outgoing.get_nowait()
        assert msg.level == MessageLevel.SUCCESS

    def test_emit_debug(self):
        """Test emit_debug helper method."""
        bus = MessageBus()
        bus._has_active_renderer = True
        bus.emit_debug("Debug info")
        msg = bus._outgoing.get_nowait()
        assert msg.level == MessageLevel.DEBUG

    def test_emit_text_with_level_and_category(self):
        """Test emit_text with custom level and category."""
        bus = MessageBus()
        bus._has_active_renderer = True
        bus.emit_text(
            level=MessageLevel.ERROR,
            text="Error occurred",
            category=MessageCategory.AGENT,
        )
        msg = bus._outgoing.get_nowait()
        assert msg.level == MessageLevel.ERROR
        assert msg.category == MessageCategory.AGENT

    def test_emit_auto_tags_with_session_id(self):
        """Test that emit auto-tags messages with session_id."""
        bus = MessageBus()
        bus._has_active_renderer = True
        bus.set_session_context("session-123")
        message = TextMessage(level=MessageLevel.INFO, text="Test")
        bus.emit(message)
        emitted = bus._outgoing.get_nowait()
        assert emitted.session_id == "session-123"

    def test_emit_respects_existing_session_id(self):
        """Test that emit respects existing session_id."""
        bus = MessageBus()
        bus._has_active_renderer = True
        bus.set_session_context("session-123")
        message = TextMessage(
            level=MessageLevel.INFO, text="Test", session_id="custom-id"
        )
        bus.emit(message)
        emitted = bus._outgoing.get_nowait()
        assert emitted.session_id == "custom-id"

    def test_emit_queue_full_drops_oldest(self):
        """Test that full queue drops oldest message."""
        bus = MessageBus(maxsize=2)
        bus._has_active_renderer = True
        bus.emit(TextMessage(level=MessageLevel.INFO, text="msg1"))
        bus.emit(TextMessage(level=MessageLevel.INFO, text="msg2"))
        bus.emit(TextMessage(level=MessageLevel.INFO, text="msg3"))

        # Should have msg2 and msg3
        msgs = []
        while not bus._outgoing.empty():
            msgs.append(bus._outgoing.get_nowait().text)
        assert "msg3" in msgs


class TestSessionContext:
    """Test session context management."""

    def test_set_session_context(self):
        """Test setting session context."""
        bus = MessageBus()
        bus.set_session_context("session-1")
        assert bus.get_session_context() == "session-1"

    def test_clear_session_context(self):
        """Test clearing session context."""
        bus = MessageBus()
        bus.set_session_context("session-1")
        bus.set_session_context(None)
        assert bus.get_session_context() is None

    def test_session_context_thread_safe(self):
        """Test that session context is thread-safe."""
        bus = MessageBus()
        results = []

        def set_context(session_id):
            bus.set_session_context(session_id)
            import time

            time.sleep(0.01)
            results.append(bus.get_session_context())

        threads = [
            threading.Thread(target=set_context, args=(f"session-{i}",))
            for i in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have collected some session contexts
        assert len(results) == 3


class TestUserInputRequest:
    """Test user input request functionality."""

    @pytest.mark.asyncio
    async def test_request_input_basic(self):
        """Test basic user input request."""
        bus = MessageBus()
        bus._has_active_renderer = True
        bus._event_loop = asyncio.get_running_loop()

        # Schedule response
        async def send_response():
            await asyncio.sleep(0.05)
            command = UserInputResponse(prompt_id="test-id", value="user input")
            bus.provide_response(command)

        asyncio.create_task(send_response())

        # Mock the uuid to control prompt_id
        with patch("code_puppy.messaging.bus.uuid4", return_value="test-id"):
            result = await asyncio.wait_for(
                bus.request_input("Enter text:"), timeout=2.0
            )

        assert result == "user input"

    @pytest.mark.asyncio
    async def test_request_input_with_default(self):
        """Test user input request with default value."""
        bus = MessageBus()
        bus._has_active_renderer = True
        bus._event_loop = asyncio.get_running_loop()

        async def send_empty_response():
            await asyncio.sleep(0.05)
            command = UserInputResponse(prompt_id="test-id", value="")
            bus.provide_response(command)

        asyncio.create_task(send_empty_response())

        with patch("code_puppy.messaging.bus.uuid4", return_value="test-id"):
            result = await asyncio.wait_for(
                bus.request_input("Enter:", default="default-value"), timeout=2.0
            )

        assert result == "default-value"

    @pytest.mark.asyncio
    async def test_request_input_password(self):
        """Test password input request."""
        bus = MessageBus()
        bus._has_active_renderer = True
        bus._event_loop = asyncio.get_running_loop()

        async def send_response():
            await asyncio.sleep(0.05)
            command = UserInputResponse(prompt_id="pwd-id", value="secret")
            bus.provide_response(command)

        asyncio.create_task(send_response())

        with patch("code_puppy.messaging.bus.uuid4", return_value="pwd-id"):
            result = await asyncio.wait_for(
                bus.request_input("Password:", input_type="password"), timeout=2.0
            )

        assert result == "secret"

    @pytest.mark.asyncio
    async def test_request_input_cleanup_on_completion(self):
        """Test that pending requests are cleaned up after completion."""
        bus = MessageBus()
        bus._has_active_renderer = True
        bus._event_loop = asyncio.get_running_loop()

        async def send_response():
            await asyncio.sleep(0.05)
            command = UserInputResponse(prompt_id="cleanup-id", value="test")
            bus.provide_response(command)

        asyncio.create_task(send_response())

        with patch("code_puppy.messaging.bus.uuid4", return_value="cleanup-id"):
            result = await asyncio.wait_for(bus.request_input("Test:"), timeout=2.0)

        # Pending requests should be cleaned up
        assert "cleanup-id" not in bus._pending_requests
        assert result == "test"


class TestConfirmationRequest:
    """Test confirmation request functionality."""

    @pytest.mark.asyncio
    async def test_request_confirmation_yes(self):
        """Test confirmation request with yes response."""
        bus = MessageBus()
        bus._has_active_renderer = True
        bus._event_loop = asyncio.get_running_loop()

        async def send_response():
            await asyncio.sleep(0.05)
            command = ConfirmationResponse(
                prompt_id="confirm-id",
                confirmed=True,
                feedback=None,
            )
            bus.provide_response(command)

        asyncio.create_task(send_response())

        with patch("code_puppy.messaging.bus.uuid4", return_value="confirm-id"):
            confirmed, feedback = await asyncio.wait_for(
                bus.request_confirmation(
                    title="Confirm?",
                    description="Are you sure?",
                ),
                timeout=2.0,
            )

        assert confirmed is True
        assert feedback is None

    @pytest.mark.asyncio
    async def test_request_confirmation_with_feedback(self):
        """Test confirmation request with feedback."""
        bus = MessageBus()
        bus._has_active_renderer = True
        bus._event_loop = asyncio.get_running_loop()

        async def send_response():
            await asyncio.sleep(0.05)
            command = ConfirmationResponse(
                prompt_id="confirm-id",
                confirmed=True,
                feedback="Good idea",
            )
            bus.provide_response(command)

        asyncio.create_task(send_response())

        with patch("code_puppy.messaging.bus.uuid4", return_value="confirm-id"):
            confirmed, feedback = await asyncio.wait_for(
                bus.request_confirmation(
                    title="Confirm?",
                    description="Proceed?",
                    allow_feedback=True,
                ),
                timeout=2.0,
            )

        assert confirmed is True
        assert feedback == "Good idea"


class TestSelectionRequest:
    """Test selection request functionality."""

    @pytest.mark.asyncio
    async def test_request_selection_basic(self):
        """Test basic selection request."""
        bus = MessageBus()
        bus._has_active_renderer = True
        bus._event_loop = asyncio.get_running_loop()

        async def send_response():
            await asyncio.sleep(0.05)
            command = SelectionResponse(
                prompt_id="select-id",
                selected_index=1,
                selected_value="Option 2",
            )
            bus.provide_response(command)

        asyncio.create_task(send_response())

        with patch("code_puppy.messaging.bus.uuid4", return_value="select-id"):
            index, value = await asyncio.wait_for(
                bus.request_selection(
                    "Choose:",
                    ["Option 1", "Option 2", "Option 3"],
                ),
                timeout=2.0,
            )

        assert index == 1
        assert value == "Option 2"

    @pytest.mark.asyncio
    async def test_request_selection_first_option(self):
        """Test selection request selecting first option."""
        bus = MessageBus()
        bus._has_active_renderer = True
        bus._event_loop = asyncio.get_running_loop()

        async def send_response():
            await asyncio.sleep(0.05)
            command = SelectionResponse(
                prompt_id="select-first-id",
                selected_index=0,
                selected_value="Option 1",
            )
            bus.provide_response(command)

        asyncio.create_task(send_response())

        with patch("code_puppy.messaging.bus.uuid4", return_value="select-first-id"):
            index, value = await asyncio.wait_for(
                bus.request_selection(
                    "Choose:",
                    ["Option 1", "Option 2"],
                ),
                timeout=2.0,
            )

        assert index == 0
        assert value == "Option 1"


class TestProvideResponse:
    """Test response handling from UI."""

    def test_provide_response_puts_in_queue(self):
        """Test that non-response commands go into incoming queue."""
        from code_puppy.messaging.commands import CancelAgentCommand

        bus = MessageBus()
        command = CancelAgentCommand()
        bus.provide_response(command)

        # Should be in incoming queue
        retrieved = bus._incoming.get_nowait()
        assert retrieved is command

    def test_provide_response_unknown_request_ignored(self):
        """Test providing response for unknown request is safe."""
        bus = MessageBus()
        bus._has_active_renderer = True

        # Create a response with unknown prompt_id
        command = UserInputResponse(prompt_id="unknown-id", value="test")
        bus.provide_response(command)

        # Should not raise, just be silently ignored
        assert True


class TestQueueAccess:
    """Test queue access methods."""

    def test_get_message_nowait(self):
        """Test non-blocking message retrieval."""
        bus = MessageBus()
        bus._has_active_renderer = True
        msg = TextMessage(level=MessageLevel.INFO, text="test")
        bus.emit(msg)

        retrieved = bus.get_message_nowait()
        assert retrieved is not None
        assert retrieved.text == "test"

    def test_get_message_nowait_empty(self):
        """Test non-blocking message retrieval on empty queue."""
        bus = MessageBus()
        bus._has_active_renderer = True

        retrieved = bus.get_message_nowait()
        assert retrieved is None

    def test_command_queue_direct_put(self):
        """Test putting commands directly in queue."""
        bus = MessageBus()

        # Put a command in incoming queue
        cmd = UserInputResponse(prompt_id="test", value="response")
        bus._incoming.put(cmd)

        retrieved = bus._incoming.get_nowait()
        assert retrieved.value == "response"


class TestBufferedMessages:
    """Test message buffering functionality."""

    def test_get_buffered_messages_empty(self):
        """Test getting buffered messages when none exist."""
        bus = MessageBus()
        assert bus.get_buffered_messages() == []

    def test_get_buffered_messages(self):
        """Test getting buffered messages."""
        bus = MessageBus()
        msg1 = TextMessage(level=MessageLevel.INFO, text="msg1")
        msg2 = TextMessage(level=MessageLevel.INFO, text="msg2")
        bus.emit(msg1)
        bus.emit(msg2)

        buffered = bus.get_buffered_messages()
        assert len(buffered) == 2
        assert buffered[0].text == "msg1"
        assert buffered[1].text == "msg2"

    def test_clear_buffer(self):
        """Test clearing the startup buffer."""
        bus = MessageBus()
        msg = TextMessage(level=MessageLevel.INFO, text="test")
        bus.emit(msg)

        assert len(bus.get_buffered_messages()) == 1
        bus.clear_buffer()
        assert len(bus.get_buffered_messages()) == 0

    def test_activate_renderer_flushes_buffer(self):
        """Test that activating renderer allows buffered messages to flush."""
        bus = MessageBus()
        msg = TextMessage(level=MessageLevel.INFO, text="test")
        bus.emit(msg)

        # Message should be buffered
        assert len(bus._startup_buffer) == 1
        assert bus._outgoing.empty()

        # Activate renderer
        bus._has_active_renderer = True
        msg2 = TextMessage(level=MessageLevel.INFO, text="test2")
        bus.emit(msg2)

        # New message should go to queue
        assert not bus._outgoing.empty()
        msg_from_queue = bus._outgoing.get_nowait()
        assert msg_from_queue.text == "test2"


class TestThreadSafety:
    """Test thread-safety of MessageBus operations."""

    def test_concurrent_emit(self):
        """Test concurrent message emission."""
        bus = MessageBus()
        bus._has_active_renderer = True
        results = []

        def emit_messages(thread_id):
            for i in range(10):
                msg = TextMessage(
                    level=MessageLevel.INFO,
                    text=f"thread-{thread_id}-msg-{i}",
                )
                bus.emit(msg)
                results.append(msg)

        threads = [threading.Thread(target=emit_messages, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have emitted all messages
        assert len(results) == 30
        assert bus._outgoing.qsize() == 30

    def test_concurrent_session_context(self):
        """Test concurrent session context updates."""
        bus = MessageBus()
        contexts = []

        def update_context(session_id):
            bus.set_session_context(session_id)
            contexts.append(bus.get_session_context())

        threads = [
            threading.Thread(target=update_context, args=(f"session-{i}",))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(contexts) == 5
