"""Tests for pause-aware buffering in the synchronous renderer.

The renderer must:
- buffer all non-``HUMAN_INPUT_REQUEST`` messages while the
  ``PauseController`` is paused,
- preserve order on flush,
- never buffer ``HUMAN_INPUT_REQUEST`` (those are blocking prompts),
- flush both lazily (next render after resume) AND actively (via the
  resume listener) so output is never silently swallowed.
"""

from __future__ import annotations

import io
import time

import pytest
from rich.console import Console

from code_puppy.messaging.message_queue import (
    MessageQueue,
    MessageType,
    UIMessage,
)
from code_puppy.messaging.pause_controller import (
    get_pause_controller,
    reset_pause_controller,
)
from code_puppy.messaging.renderers import (
    _BUFFER_FLUSH_INDICATOR_THRESHOLD,
    SynchronousInteractiveRenderer,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_pause_controller()
    yield
    reset_pause_controller()


@pytest.fixture
def buffer_io() -> io.StringIO:
    return io.StringIO()


@pytest.fixture
def renderer(buffer_io):
    """A renderer wired up to an in-memory console."""
    console = Console(file=buffer_io, force_terminal=False, width=200)
    r = SynchronousInteractiveRenderer(MessageQueue(), console=console)
    r.start()
    try:
        yield r
    finally:
        r.stop()


def _msg(text: str, kind: MessageType = MessageType.INFO) -> UIMessage:
    return UIMessage(type=kind, content=text)


# =============================================================================
# Pause buffers; resume drains in order
# =============================================================================


def test_messages_are_buffered_while_paused(renderer, buffer_io):
    pc = get_pause_controller()
    pc.pause()

    renderer._render_message(_msg("one"))
    renderer._render_message(_msg("two"))
    renderer._render_message(_msg("three"))

    # Nothing should have been written to the console while paused.
    assert buffer_io.getvalue() == ""
    # Buffer contains all three in order.
    assert [m.content for m in renderer._paused_buffer] == ["one", "two", "three"]


def test_resume_flushes_buffer_via_listener(renderer, buffer_io):
    pc = get_pause_controller()
    pc.pause()
    renderer._render_message(_msg("alpha"))
    renderer._render_message(_msg("beta"))
    renderer._render_message(_msg("gamma"))

    assert buffer_io.getvalue() == ""

    pc.resume()
    # The listener runs synchronously inside ``resume()``, so output is
    # already flushed by the time resume() returns.
    output = buffer_io.getvalue()
    assert "alpha" in output
    assert "beta" in output
    assert "gamma" in output
    assert output.index("alpha") < output.index("beta") < output.index("gamma")
    # Buffer is empty after flush.
    assert renderer._paused_buffer == []


def test_lazy_flush_drains_before_next_message(buffer_io):
    """If we manage to render() before the resume listener fires (e.g. the
    listener was de-registered), the next render must still drain the
    buffer first to keep ordering correct.
    """
    console = Console(file=buffer_io, force_terminal=False, width=200)
    renderer = SynchronousInteractiveRenderer(MessageQueue(), console=console)
    renderer.start()
    try:
        pc = get_pause_controller()
        # Remove the active-flush listener to force the lazy-flush path.
        pc.remove_resume_listener(renderer._flush_paused_buffer)

        pc.pause()
        renderer._render_message(_msg("buffered-1"))
        renderer._render_message(_msg("buffered-2"))
        assert buffer_io.getvalue() == ""

        pc.resume()
        # Listener was removed — buffer is still pending.
        assert [m.content for m in renderer._paused_buffer] == [
            "buffered-1",
            "buffered-2",
        ]

        # Next render after resume drains in order, then renders the new msg.
        renderer._render_message(_msg("live"))
        output = buffer_io.getvalue()
        assert output.index("buffered-1") < output.index("buffered-2")
        assert output.index("buffered-2") < output.index("live")
        assert renderer._paused_buffer == []
    finally:
        renderer.stop()


def test_messages_pass_through_when_not_paused(renderer, buffer_io):
    renderer._render_message(_msg("immediate"))

    assert "immediate" in buffer_io.getvalue()
    assert renderer._paused_buffer == []


# =============================================================================
# HUMAN_INPUT_REQUEST bypasses the buffer
# =============================================================================


def test_human_input_request_bypasses_buffer_while_paused(
    monkeypatch, renderer, buffer_io
):
    """Buffering a HUMAN_INPUT_REQUEST would deadlock the runtime — those
    messages MUST render immediately regardless of pause state.
    """
    # The handler shells out to ``input()``; stub it.
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")

    pc = get_pause_controller()
    pc.pause()

    prompt_msg = UIMessage(
        type=MessageType.HUMAN_INPUT_REQUEST,
        content="Need answer please",
        metadata={"prompt_id": "test-prompt-1"},
    )
    renderer._render_message(prompt_msg)

    # Rendered immediately, despite being paused.
    assert "Need answer please" in buffer_io.getvalue()
    # The HIR did NOT enter the pause buffer.
    assert renderer._paused_buffer == []


# =============================================================================
# Flush indicator on large buffers
# =============================================================================


def test_flush_indicator_emitted_for_large_buffers(renderer, buffer_io):
    pc = get_pause_controller()
    pc.pause()

    count = _BUFFER_FLUSH_INDICATOR_THRESHOLD + 5
    for i in range(count):
        renderer._render_message(_msg(f"msg-{i:03d}"))

    pc.resume()
    output = buffer_io.getvalue()

    assert f"buffered {count} messages during pause" in output
    # Order is preserved despite the indicator.
    assert output.index(f"buffered {count}") < output.index("msg-000")
    assert output.index("msg-000") < output.index(f"msg-{count - 1:03d}")


def test_flush_indicator_not_emitted_for_small_buffers(renderer, buffer_io):
    pc = get_pause_controller()
    pc.pause()

    for i in range(3):
        renderer._render_message(_msg(f"msg-{i}"))

    pc.resume()
    output = buffer_io.getvalue()

    assert "buffered" not in output
    assert "msg-0" in output and "msg-1" in output and "msg-2" in output


# =============================================================================
# Shutdown drains anything left over
# =============================================================================


def test_stop_drains_remaining_buffer(buffer_io):
    console = Console(file=buffer_io, force_terminal=False, width=200)
    renderer = SynchronousInteractiveRenderer(MessageQueue(), console=console)
    renderer.start()

    pc = get_pause_controller()
    pc.pause()
    renderer._render_message(_msg("straggler-1"))
    renderer._render_message(_msg("straggler-2"))

    # Stop the renderer while still paused — it should drain anyway since
    # we're shutting down (don't silently lose messages).
    renderer.stop()

    output = buffer_io.getvalue()
    assert "straggler-1" in output
    assert "straggler-2" in output


# =============================================================================
# Renderer-level: end-to-end via the bus listener path
# =============================================================================


def test_bus_listener_path_respects_pause(buffer_io):
    """The bus listener path is what production uses — emit_info() and
    friends call ``MessageQueue.emit`` which fires registered listeners
    (i.e. our ``_render_message``). Verify buffering works end-to-end.
    """
    console = Console(file=buffer_io, force_terminal=False, width=200)
    q = MessageQueue()
    renderer = SynchronousInteractiveRenderer(q, console=console)
    renderer.start()
    try:
        pc = get_pause_controller()
        pc.pause()
        # Emit through the queue; the renderer is a registered listener.
        q.emit(_msg("bus-1"))
        q.emit(_msg("bus-2"))
        # Give the consume thread a chance to drain (it shouldn't matter:
        # listeners fire synchronously on emit, but let's be paranoid).
        time.sleep(0.05)
        assert buffer_io.getvalue() == ""

        pc.resume()
        output = buffer_io.getvalue()
        assert "bus-1" in output
        assert "bus-2" in output
        assert output.index("bus-1") < output.index("bus-2")
    finally:
        renderer.stop()
