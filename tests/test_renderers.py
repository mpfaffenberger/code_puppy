"""
Comprehensive tests for message renderer implementations.

Tests cover async message rendering, queue consumption, error handling,
and renderer lifecycle management.
"""

import asyncio
from io import StringIO

import pytest
from rich.console import Console
from rich.text import Text

from code_puppy.messaging.message_queue import MessageQueue, MessageType, UIMessage
from code_puppy.messaging.renderers import InteractiveRenderer, MessageRenderer


class TestMessageRenderer:
    """Test MessageRenderer base class functionality."""

    @pytest.mark.asyncio
    async def test_renderer_initialization(self):
        """Test MessageRenderer initialization."""
        queue = MessageQueue()

        class TestRenderer(MessageRenderer):
            async def render_message(self, message):
                pass

        renderer = TestRenderer(queue)
        assert renderer.queue is queue
        assert renderer._running is False
        assert renderer._task is None

    @pytest.mark.asyncio
    async def test_renderer_start(self):
        """Test starting a renderer."""
        queue = MessageQueue()

        class TestRenderer(MessageRenderer):
            async def render_message(self, message):
                pass

        renderer = TestRenderer(queue)
        await renderer.start()

        assert renderer._running is True
        assert renderer._task is not None

        await renderer.stop()

    @pytest.mark.asyncio
    async def test_renderer_stop(self):
        """Test stopping a renderer."""
        queue = MessageQueue()

        class TestRenderer(MessageRenderer):
            async def render_message(self, message):
                pass

        renderer = TestRenderer(queue)
        await renderer.start()
        assert renderer._running is True

        await renderer.stop()
        assert renderer._running is False
        # Give task time to cancel
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_renderer_marks_queue_state(self):
        """Test that renderer activation marks queue state."""
        queue = MessageQueue()
        assert not queue._has_active_renderer

        class TestRenderer(MessageRenderer):
            async def render_message(self, message):
                pass

        renderer = TestRenderer(queue)
        await renderer.start()
        assert queue._has_active_renderer

        await renderer.stop()
        assert not queue._has_active_renderer

    @pytest.mark.asyncio
    async def test_renderer_double_start(self):
        """Test that starting renderer twice is safe."""
        queue = MessageQueue()

        class TestRenderer(MessageRenderer):
            async def render_message(self, message):
                pass

        renderer = TestRenderer(queue)
        await renderer.start()
        task1 = renderer._task

        # Start again
        await renderer.start()
        task2 = renderer._task

        # Should be same task
        assert task1 == task2

        await renderer.stop()

    @pytest.mark.asyncio
    async def test_renderer_lifecycle_basic(self):
        """Test basic renderer lifecycle."""
        queue = MessageQueue()

        class TestRenderer(MessageRenderer):
            async def render_message(self, message):
                pass

        renderer = TestRenderer(queue)
        assert not renderer._running

        await renderer.start()
        assert renderer._running

        await renderer.stop()
        assert not renderer._running


class TestInteractiveRenderer:
    """Test InteractiveRenderer functionality."""

    def test_interactive_renderer_init(self):
        """Test InteractiveRenderer initialization."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output)

        renderer = InteractiveRenderer(queue, console)
        assert renderer.queue is queue
        assert renderer.console is console

    def test_interactive_renderer_default_console(self):
        """Test InteractiveRenderer with default console."""
        queue = MessageQueue()
        renderer = InteractiveRenderer(queue)
        assert renderer.console is not None
        assert isinstance(renderer.console, Console)

    @pytest.mark.asyncio
    async def test_interactive_renderer_render_info(self):
        """Test rendering INFO message."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.INFO, content="Info message")

        await renderer.render_message(msg)

        output_text = output.getvalue()
        # Should have rendered something
        assert len(output_text) > 0

    @pytest.mark.asyncio
    async def test_interactive_renderer_render_error(self):
        """Test rendering ERROR message."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.ERROR, content="Error message")

        await renderer.render_message(msg)

        output_text = output.getvalue()
        assert len(output_text) > 0

    @pytest.mark.asyncio
    async def test_interactive_renderer_render_success(self):
        """Test rendering SUCCESS message."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.SUCCESS, content="Success!")

        await renderer.render_message(msg)

        output_text = output.getvalue()
        assert len(output_text) > 0

    @pytest.mark.asyncio
    async def test_interactive_renderer_render_warning(self):
        """Test rendering WARNING message."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.WARNING, content="Warning!")

        await renderer.render_message(msg)

        output_text = output.getvalue()
        assert len(output_text) > 0


class TestRendererMessageHandling:
    """Test renderer handling of various message types."""

    @pytest.mark.asyncio
    async def test_renderer_handles_text_content(self):
        """Test renderer handling plain text content."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.INFO, content="Plain text")

        await renderer.render_message(msg)
        output_text = output.getvalue()
        assert "Plain text" in output_text

    @pytest.mark.asyncio
    async def test_renderer_handles_rich_text(self):
        """Test renderer handling Rich Text objects."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output)

        renderer = InteractiveRenderer(queue, console)
        text = Text("Styled text", style="bold red")
        msg = UIMessage(type=MessageType.ERROR, content=text)

        await renderer.render_message(msg)
        output_text = output.getvalue()
        assert "Styled text" in output_text

    @pytest.mark.asyncio
    async def test_renderer_handles_none_content(self):
        """Test renderer handling message with None content."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.INFO, content=None)

        # Should not raise
        await renderer.render_message(msg)

    @pytest.mark.asyncio
    async def test_renderer_handles_divider(self):
        """Test renderer handling DIVIDER message."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.DIVIDER, content="")

        await renderer.render_message(msg)
        # Should render a divider


class TestRendererErrorHandling:
    """Test renderer error handling and resilience."""

    @pytest.mark.asyncio
    async def test_renderer_render_method_called(self):
        """Test that render_message method is defined."""
        queue = MessageQueue()

        class TestRenderer(MessageRenderer):
            async def render_message(self, message):
                pass

        renderer = TestRenderer(queue)
        msg = UIMessage(type=MessageType.INFO, content="Test")

        # Should not raise
        await renderer.render_message(msg)

    @pytest.mark.asyncio
    async def test_renderer_timeout_on_message_retrieval(self):
        """Test that renderer handles timeout gracefully."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output)

        renderer = InteractiveRenderer(queue, console)
        await renderer.start()

        # Let it run briefly with no messages
        await asyncio.sleep(0.2)

        await renderer.stop()
        # Should complete without error


class TestRendererLifecycle:
    """Test renderer lifecycle management."""

    @pytest.mark.asyncio
    async def test_renderer_start_stop_cycle(self):
        """Test multiple start/stop cycles."""
        queue = MessageQueue()

        class TestRenderer(MessageRenderer):
            async def render_message(self, message):
                pass

        renderer = TestRenderer(queue)

        for _ in range(3):
            await renderer.start()
            assert renderer._running is True
            await asyncio.sleep(0.05)
            await renderer.stop()
            assert renderer._running is False
            await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_renderer_cancellation(self):
        """Test renderer task cancellation."""
        queue = MessageQueue()

        class SlowRenderer(MessageRenderer):
            async def render_message(self, message):
                await asyncio.sleep(1.0)

        renderer = SlowRenderer(queue)
        await renderer.start()

        assert renderer._task is not None
        assert not renderer._task.cancelled()

        await renderer.stop()

        # Task should be cancelled or done
        await asyncio.sleep(0.1)
        assert renderer._task.cancelled() or renderer._task.done()

    @pytest.mark.asyncio
    async def test_renderer_with_buffered_messages(self):
        """Test renderer with buffered messages."""
        queue = MessageQueue()

        # Buffer messages before renderer starts
        msg1 = UIMessage(type=MessageType.INFO, content="Buffered1")
        msg2 = UIMessage(type=MessageType.INFO, content="Buffered2")
        queue.emit(msg1)
        queue.emit(msg2)

        # Should be in buffer
        buffered = queue.get_buffered_messages()
        assert len(buffered) == 2

        class TestRenderer(MessageRenderer):
            async def render_message(self, message):
                pass

        renderer = TestRenderer(queue)
        await renderer.start()
        assert queue._has_active_renderer
        await renderer.stop()


class TestMultipleRenderers:
    """Test behavior with multiple renderers."""

    @pytest.mark.asyncio
    async def test_multiple_renderers_same_queue(self):
        """Test multiple renderers on same queue."""
        queue = MessageQueue()

        class RendererA(MessageRenderer):
            async def render_message(self, message):
                pass

        class RendererB(MessageRenderer):
            async def render_message(self, message):
                pass

        renderer_a = RendererA(queue)
        renderer_b = RendererB(queue)

        await renderer_a.start()
        assert queue._has_active_renderer

        await renderer_b.start()
        assert queue._has_active_renderer

        await renderer_a.stop()
        assert not queue._has_active_renderer

        await renderer_b.stop()
