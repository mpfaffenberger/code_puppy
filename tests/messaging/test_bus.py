"""Tests for code_puppy.messaging.bus - MessageBus and global functions."""

import asyncio
import queue
from unittest.mock import patch

import pytest

from code_puppy.messaging.bus import (
    MessageBus,
    emit,
    emit_debug,
    emit_error,
    emit_info,
    emit_shell_line,
    emit_success,
    emit_warning,
    get_message_bus,
    get_session_context,
    reset_message_bus,
    set_session_context,
)
from code_puppy.messaging.commands import (
    CancelAgentCommand,
    ConfirmationResponse,
    SelectionResponse,
    UserInputResponse,
)
from code_puppy.messaging.messages import (
    MessageCategory,
    MessageLevel,
    ShellLineMessage,
    TextMessage,
)


@pytest.fixture
def bus():
    return MessageBus(maxsize=10)


# =========================================================================
# Basic emit / buffering
# =========================================================================


def test_emit_buffers_when_no_renderer(bus):
    msg = TextMessage(level=MessageLevel.INFO, text="hello")
    bus.emit(msg)
    assert len(bus._startup_buffer) == 1
    assert bus.outgoing_qsize == 0


def test_emit_goes_to_queue_when_renderer_active(bus):
    bus.mark_renderer_active()
    msg = TextMessage(level=MessageLevel.INFO, text="hello")
    bus.emit(msg)
    assert bus.outgoing_qsize == 1
    assert len(bus._startup_buffer) == 0


def test_emit_drops_oldest_when_full(bus):
    bus.mark_renderer_active()
    # Fill the queue
    for i in range(10):
        bus.emit(TextMessage(level=MessageLevel.INFO, text=f"msg-{i}"))
    assert bus.outgoing_qsize == 10
    # Next emit should drop oldest
    bus.emit(TextMessage(level=MessageLevel.INFO, text="overflow"))
    assert bus.outgoing_qsize == 10


def test_emit_buffer_truncates_when_full(bus):
    # No active renderer, buffer fills
    for i in range(15):
        bus.emit(TextMessage(level=MessageLevel.INFO, text=f"msg-{i}"))
    assert len(bus._startup_buffer) == 10  # maxsize


def test_emit_auto_tags_session(bus):
    bus.set_session_context("sess-1")
    bus.mark_renderer_active()
    msg = TextMessage(level=MessageLevel.INFO, text="hello")
    bus.emit(msg)
    assert msg.session_id == "sess-1"


def test_emit_does_not_overwrite_existing_session(bus):
    bus.set_session_context("sess-1")
    bus.mark_renderer_active()
    msg = TextMessage(level=MessageLevel.INFO, text="hello", session_id="other")
    bus.emit(msg)
    assert msg.session_id == "other"


# =========================================================================
# Convenience emit methods
# =========================================================================


def test_emit_text(bus):
    bus.mark_renderer_active()
    bus.emit_text(MessageLevel.WARNING, "warn!", MessageCategory.TOOL_OUTPUT)
    got = bus.get_message_nowait()
    assert isinstance(got, TextMessage)
    assert got.level == MessageLevel.WARNING
    assert got.text == "warn!"
    assert got.category == MessageCategory.TOOL_OUTPUT


def test_emit_info_warning_error_success_debug(bus):
    bus.mark_renderer_active()
    bus.emit_info("i")
    bus.emit_warning("w")
    bus.emit_error("e")
    bus.emit_success("s")
    bus.emit_debug("d")
    levels = []
    while True:
        m = bus.get_message_nowait()
        if m is None:
            break
        levels.append(m.level)
    assert levels == [
        MessageLevel.INFO,
        MessageLevel.WARNING,
        MessageLevel.ERROR,
        MessageLevel.SUCCESS,
        MessageLevel.DEBUG,
    ]


def test_emit_shell_line(bus):
    bus.mark_renderer_active()
    bus.emit_shell_line("output", "stderr")
    msg = bus.get_message_nowait()
    assert isinstance(msg, ShellLineMessage)
    assert msg.line == "output"
    assert msg.stream == "stderr"


# =========================================================================
# Session context
# =========================================================================


def test_session_context(bus):
    assert bus.get_session_context() is None
    bus.set_session_context("abc")
    assert bus.get_session_context() == "abc"
    bus.set_session_context(None)
    assert bus.get_session_context() is None


# =========================================================================
# Request/response
# =========================================================================


@pytest.mark.asyncio
async def test_request_input(bus):
    async def respond():
        await asyncio.sleep(0.05)
        # Find the pending request
        with bus._lock:
            prompt_id = list(bus._pending_requests.keys())[0]
        bus.provide_response(UserInputResponse(prompt_id=prompt_id, value="hello"))

    asyncio.get_event_loop().create_task(respond())
    result = await bus.request_input("Enter:", default="def")
    assert result == "hello"


@pytest.mark.asyncio
async def test_request_input_empty_uses_default(bus):
    async def respond():
        await asyncio.sleep(0.05)
        with bus._lock:
            prompt_id = list(bus._pending_requests.keys())[0]
        bus.provide_response(UserInputResponse(prompt_id=prompt_id, value=""))

    asyncio.get_event_loop().create_task(respond())
    result = await bus.request_input("Enter:", default="fallback")
    assert result == "fallback"


@pytest.mark.asyncio
async def test_request_input_no_default(bus):
    async def respond():
        await asyncio.sleep(0.05)
        with bus._lock:
            prompt_id = list(bus._pending_requests.keys())[0]
        bus.provide_response(UserInputResponse(prompt_id=prompt_id, value=""))

    asyncio.get_event_loop().create_task(respond())
    result = await bus.request_input("Enter:")
    assert result == ""


@pytest.mark.asyncio
async def test_request_confirmation(bus):
    async def respond():
        await asyncio.sleep(0.05)
        with bus._lock:
            prompt_id = list(bus._pending_requests.keys())[0]
        bus.provide_response(
            ConfirmationResponse(prompt_id=prompt_id, confirmed=True, feedback="ok")
        )

    asyncio.get_event_loop().create_task(respond())
    confirmed, feedback = await bus.request_confirmation("Title", "Desc")
    assert confirmed is True
    assert feedback == "ok"


@pytest.mark.asyncio
async def test_request_selection(bus):
    async def respond():
        await asyncio.sleep(0.05)
        with bus._lock:
            prompt_id = list(bus._pending_requests.keys())[0]
        bus.provide_response(
            SelectionResponse(
                prompt_id=prompt_id, selected_index=1, selected_value="opt2"
            )
        )

    asyncio.get_event_loop().create_task(respond())
    idx, val = await bus.request_selection("Pick:", ["opt1", "opt2"])
    assert idx == 1
    assert val == "opt2"


# =========================================================================
# provide_response for non-response commands
# =========================================================================


def test_provide_response_non_response_command(bus):
    cmd = CancelAgentCommand()
    bus.provide_response(cmd)
    assert bus.incoming_qsize == 1


def test_provide_response_incoming_full(bus):
    """When incoming queue is full, oldest is dropped."""
    # Fill incoming queue
    for _ in range(10):
        bus.provide_response(CancelAgentCommand())
    assert bus.incoming_qsize == 10
    # One more should drop oldest
    bus.provide_response(CancelAgentCommand())
    assert bus.incoming_qsize == 10


# =========================================================================
# _complete_request edge cases
# =========================================================================


def test_complete_request_unknown_prompt_id(bus):
    """Should not raise on unknown prompt_id."""
    bus._complete_request("nonexistent", "value")


def test_complete_request_with_event_loop(bus):
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    bus._event_loop = loop
    with bus._lock:
        bus._pending_requests["test-id"] = future
    bus._complete_request("test-id", "result")
    loop.run_until_complete(asyncio.sleep(0.01))
    assert future.result() == "result"
    loop.close()


def test_complete_request_event_loop_closed(bus):
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    bus._event_loop = loop
    loop.close()  # Close loop so call_soon_threadsafe raises RuntimeError
    with bus._lock:
        bus._pending_requests["test-id"] = future
    # Should not raise
    bus._complete_request("test-id", "result")


def test_set_future_result_already_done(bus):
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    future.set_result("first")
    bus._set_future_result(future, "second")
    assert future.result() == "first"
    loop.close()


def test_complete_request_no_event_loop(bus):
    """With no event loop, falls back to direct set."""
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    bus._event_loop = None
    with bus._lock:
        bus._pending_requests["test-id"] = future
    bus._complete_request("test-id", "val")
    # future.result() needs the loop
    loop.run_until_complete(asyncio.sleep(0))
    assert future.result() == "val"
    loop.close()


def test_complete_request_future_already_done(bus):
    """Should not raise when future already done."""
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    future.set_result("done")
    with bus._lock:
        bus._pending_requests["test-id"] = future
    bus._complete_request("test-id", "ignored")
    loop.close()


# =========================================================================
# Queue access
# =========================================================================


@pytest.mark.asyncio
async def test_get_message_async(bus):
    bus.mark_renderer_active()
    bus.emit(TextMessage(level=MessageLevel.INFO, text="async"))
    msg = await bus.get_message()
    assert msg.text == "async"


def test_get_message_nowait_empty(bus):
    assert bus.get_message_nowait() is None


def test_get_message_nowait(bus):
    bus.mark_renderer_active()
    bus.emit(TextMessage(level=MessageLevel.INFO, text="hi"))
    msg = bus.get_message_nowait()
    assert msg is not None


@pytest.mark.asyncio
async def test_get_command_async(bus):
    bus.provide_response(CancelAgentCommand())
    cmd = await bus.get_command()
    assert isinstance(cmd, CancelAgentCommand)


# =========================================================================
# Buffering
# =========================================================================


def test_get_buffered_messages(bus):
    msg = TextMessage(level=MessageLevel.INFO, text="buf")
    bus.emit(msg)
    buffered = bus.get_buffered_messages()
    assert len(buffered) == 1
    # Original buffer unchanged
    assert len(bus._startup_buffer) == 1


def test_clear_buffer(bus):
    bus.emit(TextMessage(level=MessageLevel.INFO, text="buf"))
    bus.clear_buffer()
    assert len(bus._startup_buffer) == 0


def test_mark_renderer_active_inactive(bus):
    assert not bus.has_active_renderer
    bus.mark_renderer_active()
    assert bus.has_active_renderer
    bus.mark_renderer_inactive()
    assert not bus.has_active_renderer


# =========================================================================
# Queue status
# =========================================================================


def test_queue_sizes(bus):
    assert bus.outgoing_qsize == 0
    assert bus.incoming_qsize == 0
    assert bus.pending_requests_count == 0


# =========================================================================
# Global singleton
# =========================================================================


def test_global_bus_singleton():
    reset_message_bus()
    b1 = get_message_bus()
    b2 = get_message_bus()
    assert b1 is b2
    reset_message_bus()


def test_reset_message_bus():
    reset_message_bus()
    b1 = get_message_bus()
    reset_message_bus()
    b2 = get_message_bus()
    assert b1 is not b2
    reset_message_bus()


# =========================================================================
# Convenience functions
# =========================================================================


def test_global_emit_functions():
    reset_message_bus()
    bus = get_message_bus()
    bus.mark_renderer_active()

    emit(TextMessage(level=MessageLevel.INFO, text="e"))
    emit_info("i")
    emit_warning("w")
    emit_error("e")
    emit_success("s")
    emit_debug("d")
    emit_shell_line("line", "stdout")

    count = 0
    while bus.get_message_nowait() is not None:
        count += 1
    assert count == 7
    reset_message_bus()


def test_outgoing_queue_overflow():
    """When outgoing queue is full, drop oldest and put new."""
    bus = MessageBus(maxsize=1)
    bus.mark_renderer_active()
    bus.emit(TextMessage(level=MessageLevel.INFO, text="first"))
    bus.emit(TextMessage(level=MessageLevel.INFO, text="second"))
    msg = bus.get_message_nowait()
    assert msg.text == "second"  # first was dropped


def test_outgoing_queue_overflow_race_empty():
    """Outgoing queue: Full then Empty (race condition)."""
    bus = MessageBus(maxsize=1)
    bus.mark_renderer_active()
    # Patch put_nowait to always raise Full, and get_nowait to raise Empty
    with patch.object(bus._outgoing, "put_nowait", side_effect=queue.Full):
        with patch.object(bus._outgoing, "get_nowait", side_effect=queue.Empty):
            bus.emit(TextMessage(level=MessageLevel.INFO, text="x"))
            # Should not raise - catches Empty


def test_incoming_queue_overflow():
    """When incoming queue is full, drop oldest and put new."""
    bus = MessageBus(maxsize=1)
    bus.provide_response(CancelAgentCommand())
    bus.provide_response(CancelAgentCommand())  # triggers overflow handling
    assert not bus._incoming.empty()


def test_incoming_queue_overflow_race_empty():
    """Incoming queue: Full then Empty (race condition)."""
    bus = MessageBus(maxsize=1)
    with patch.object(bus._incoming, "put_nowait", side_effect=queue.Full):
        with patch.object(bus._incoming, "get_nowait", side_effect=queue.Empty):
            bus.provide_response(CancelAgentCommand())
            # Should not raise - catches Empty


@pytest.mark.asyncio
async def test_get_message_async_empty():
    """get_message waits when queue is empty then returns."""
    bus = MessageBus()
    bus.mark_renderer_active()
    # Put a message after a short delay
    import threading

    def delayed_put():
        import time

        time.sleep(0.05)
        bus.emit(TextMessage(level=MessageLevel.INFO, text="delayed"))

    t = threading.Thread(target=delayed_put)
    t.start()
    msg = await bus.get_message()
    assert msg.text == "delayed"
    t.join()


@pytest.mark.asyncio
async def test_get_command_async_empty():
    """get_command waits when queue is empty then returns."""
    bus = MessageBus()
    import threading

    def delayed_put():
        import time

        time.sleep(0.05)
        bus.provide_response(CancelAgentCommand())

    t = threading.Thread(target=delayed_put)
    t.start()
    cmd = await bus.get_command()
    assert isinstance(cmd, CancelAgentCommand)
    t.join()


def test_global_session_context():
    reset_message_bus()
    assert get_session_context() is None
    set_session_context("s1")
    assert get_session_context() == "s1"
    set_session_context(None)
    reset_message_bus()
