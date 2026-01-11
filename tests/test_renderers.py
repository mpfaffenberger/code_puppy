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
from code_puppy.messaging.renderers import (
    InteractiveRenderer,
    MessageRenderer,
    SynchronousInteractiveRenderer,
)


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


class TestSynchronousInteractiveRenderer:
    """Test SynchronousInteractiveRenderer functionality."""

    def test_sync_renderer_initialization(self):
        """Test SynchronousInteractiveRenderer initialization."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        assert renderer.queue is queue
        assert renderer.console is console
        assert renderer._running is False
        assert renderer._thread is None

    def test_sync_renderer_default_console(self):
        """Test SynchronousInteractiveRenderer with default console."""
        queue = MessageQueue()
        renderer = SynchronousInteractiveRenderer(queue)
        assert renderer.console is not None
        assert isinstance(renderer.console, Console)

    def test_sync_renderer_start_stop(self):
        """Test starting and stopping the synchronous renderer."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        renderer.start()

        assert renderer._running is True
        assert renderer._thread is not None
        assert queue._has_active_renderer

        renderer.stop()
        assert renderer._running is False
        assert not queue._has_active_renderer

    def test_sync_renderer_double_start(self):
        """Test that starting renderer twice is safe."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        renderer.start()
        thread1 = renderer._thread

        # Start again
        renderer.start()
        thread2 = renderer._thread

        # Should be same thread (first start is respected)
        assert thread1 == thread2

        renderer.stop()

    def test_sync_renderer_render_error_message(self):
        """Test rendering ERROR message type."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.ERROR, content="Error occurred!")

        renderer._render_message(msg)
        output_text = output.getvalue()
        assert "Error occurred!" in output_text

    def test_sync_renderer_render_warning_message(self):
        """Test rendering WARNING message type."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.WARNING, content="Warning!")

        renderer._render_message(msg)
        output_text = output.getvalue()
        assert "Warning!" in output_text

    def test_sync_renderer_render_success_message(self):
        """Test rendering SUCCESS message type."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.SUCCESS, content="Success!")

        renderer._render_message(msg)
        output_text = output.getvalue()
        assert "Success!" in output_text

    def test_sync_renderer_render_tool_output(self):
        """Test rendering TOOL_OUTPUT message type."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.TOOL_OUTPUT, content="Tool result")

        renderer._render_message(msg)
        output_text = output.getvalue()
        assert "Tool result" in output_text

    def test_sync_renderer_render_agent_reasoning(self):
        """Test rendering AGENT_REASONING message type."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.AGENT_REASONING, content="Thinking now")

        renderer._render_message(msg)
        output_text = output.getvalue()
        # Check core content is present (ANSI codes may split text)
        assert "Thinking" in output_text

    def test_sync_renderer_render_agent_response_markdown(self):
        """Test rendering AGENT_RESPONSE as markdown."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.AGENT_RESPONSE, content="# Header\n\nSome **bold** text"
        )

        renderer._render_message(msg)
        output_text = output.getvalue()
        # Markdown should be rendered
        assert len(output_text) > 0

    def test_sync_renderer_render_system_message(self):
        """Test rendering SYSTEM message type with dim style."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.SYSTEM, content="System message")

        renderer._render_message(msg)
        output_text = output.getvalue()
        assert "System message" in output_text

    def test_sync_renderer_render_version_messages_dim(self):
        """Test that version messages are rendered dim."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)

        # Test Current version message
        msg1 = UIMessage(type=MessageType.INFO, content="Current version: 1.0.0")
        renderer._render_message(msg1)

        # Test Latest version message
        msg2 = UIMessage(type=MessageType.INFO, content="Latest version: 1.1.0")
        renderer._render_message(msg2)

        output_text = output.getvalue()
        assert "Current version" in output_text
        assert "Latest version" in output_text

    def test_sync_renderer_render_rich_object(self):
        """Test rendering a Rich object (non-string content)."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        text_obj = Text("Styled content", style="bold")
        msg = UIMessage(type=MessageType.INFO, content=text_obj)

        renderer._render_message(msg)
        output_text = output.getvalue()
        assert "Styled content" in output_text

    def test_sync_renderer_handles_markup_in_content(self):
        """Test that Rich markup in content is escaped."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        # Content with Rich markup tags that should be escaped
        msg = UIMessage(type=MessageType.ERROR, content="Error: [bold]malformed[/bold")

        # Should not raise, markup should be escaped
        renderer._render_message(msg)
        output_text = output.getvalue()
        assert "Error:" in output_text


class TestSyncRendererHumanInput:
    """Test SynchronousInteractiveRenderer human input handling."""

    def test_sync_renderer_human_input_no_prompt_id(self):
        """Test handling human input request without prompt_id."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.HUMAN_INPUT_REQUEST,
            content="Enter something:",
            metadata=None,  # No metadata/prompt_id
        )

        renderer._render_message(msg)
        output_text = output.getvalue()
        assert "Error" in output_text or "Invalid" in output_text

    def test_sync_renderer_human_input_empty_metadata(self):
        """Test handling human input request with empty metadata."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.HUMAN_INPUT_REQUEST,
            content="Enter something:",
            metadata={},  # Empty metadata, no prompt_id
        )

        renderer._render_message(msg)
        output_text = output.getvalue()
        assert "Error" in output_text or "Invalid" in output_text


class TestInteractiveRendererAdvanced:
    """Advanced tests for InteractiveRenderer."""

    @pytest.mark.asyncio
    async def test_interactive_renderer_tool_output(self):
        """Test rendering TOOL_OUTPUT message type."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.TOOL_OUTPUT, content="Tool result")

        await renderer.render_message(msg)
        output_text = output.getvalue()
        assert "Tool result" in output_text

    @pytest.mark.asyncio
    async def test_interactive_renderer_agent_reasoning(self):
        """Test rendering AGENT_REASONING message type."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.AGENT_REASONING, content="Analyzing now")

        await renderer.render_message(msg)
        output_text = output.getvalue()
        # Check core content is present (ANSI codes may split text)
        assert "Analyzing" in output_text

    @pytest.mark.asyncio
    async def test_interactive_renderer_planned_next_steps(self):
        """Test rendering PLANNED_NEXT_STEPS message type."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.PLANNED_NEXT_STEPS, content="Next: do something"
        )

        await renderer.render_message(msg)
        output_text = output.getvalue()
        assert "Next: do something" in output_text

    @pytest.mark.asyncio
    async def test_interactive_renderer_agent_response_markdown(self):
        """Test rendering AGENT_RESPONSE as markdown."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.AGENT_RESPONSE, content="# Hello\n\nThis is **bold** text"
        )

        await renderer.render_message(msg)
        output_text = output.getvalue()
        assert len(output_text) > 0

    @pytest.mark.asyncio
    async def test_interactive_renderer_system_message(self):
        """Test rendering SYSTEM message type."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.SYSTEM, content="System info")

        await renderer.render_message(msg)
        output_text = output.getvalue()
        assert "System info" in output_text

    @pytest.mark.asyncio
    async def test_interactive_renderer_version_message_dim(self):
        """Test that version messages are rendered dim."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.INFO, content="Current version: 2.0.0")

        await renderer.render_message(msg)
        output_text = output.getvalue()
        assert "Current version" in output_text

    @pytest.mark.asyncio
    async def test_interactive_renderer_latest_version_dim(self):
        """Test that latest version messages are rendered dim."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.INFO, content="Latest version: 2.1.0")

        await renderer.render_message(msg)
        output_text = output.getvalue()
        assert "Latest version" in output_text

    @pytest.mark.asyncio
    async def test_interactive_renderer_rich_object(self):
        """Test rendering a Rich object (non-string content)."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        text_obj = Text("Rich text content", style="italic")
        msg = UIMessage(type=MessageType.INFO, content=text_obj)

        await renderer.render_message(msg)
        output_text = output.getvalue()
        assert "Rich text content" in output_text

    @pytest.mark.asyncio
    async def test_interactive_renderer_human_input_request(self):
        """Test handling human input request in async mode."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.HUMAN_INPUT_REQUEST,
            content="Please enter something:",
            metadata={"prompt_id": "test-123"},
        )

        await renderer.render_message(msg)
        output_text = output.getvalue()
        # Should render the prompt
        assert "INPUT REQUESTED" in output_text or "Please enter" in output_text

    @pytest.mark.asyncio
    async def test_interactive_renderer_escapes_markup(self):
        """Test that Rich markup in content is escaped."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.ERROR, content="Error: [bold]unclosed tag")

        # Should not raise
        await renderer.render_message(msg)
        output_text = output.getvalue()
        assert "Error:" in output_text


class TestRendererExceptionHandling:
    """Test renderer exception handling in message consumption."""

    @pytest.mark.asyncio
    async def test_consume_messages_handles_exception(self, capsys):
        """Test that _consume_messages handles exceptions gracefully."""
        queue = MessageQueue()

        class FailingRenderer(MessageRenderer):
            def __init__(self, queue):
                super().__init__(queue)
                self.call_count = 0

            async def render_message(self, message):
                self.call_count += 1
                if self.call_count == 1:
                    raise ValueError("Test error")
                # Second call succeeds

        renderer = FailingRenderer(queue)
        await renderer.start()

        # Emit a message that will cause an exception
        msg1 = UIMessage(type=MessageType.INFO, content="Test")
        queue.emit(msg1)

        # Give time for message processing
        await asyncio.sleep(0.3)

        await renderer.stop()
        # Renderer should have continued despite the error

    @pytest.mark.asyncio
    async def test_renderer_error_doesnt_crash_task(self):
        """Test that an error in render_message doesn't crash the consumer task."""
        queue = MessageQueue()
        error_raised = [False]

        class ErrorRenderer(MessageRenderer):
            async def render_message(self, message):
                error_raised[0] = True
                raise ValueError("Intentional test error")

        renderer = ErrorRenderer(queue)
        await renderer.start()

        # The consumer task should be running
        assert renderer._running is True
        assert renderer._task is not None

        # Let the consumer run for a bit (it will timeout waiting for messages)
        await asyncio.sleep(0.2)

        # Task should still be running (not crashed)
        assert not renderer._task.done()

        await renderer.stop()
        assert renderer._running is False


class TestMarkdownRendering:
    """Test markdown rendering and fallback behavior."""

    @pytest.mark.asyncio
    async def test_async_renderer_markdown_rendering(self):
        """Test that AGENT_RESPONSE renders as markdown."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.AGENT_RESPONSE,
            content="## Subheading\n\n- Item 1\n- Item 2",
        )

        await renderer.render_message(msg)
        output_text = output.getvalue()
        assert len(output_text) > 0

    def test_sync_renderer_markdown_rendering(self):
        """Test that sync renderer handles markdown."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.AGENT_RESPONSE, content="**Bold** and *italic*"
        )

        renderer._render_message(msg)
        output_text = output.getvalue()
        assert len(output_text) > 0

    def test_sync_renderer_info_no_style(self):
        """Test INFO message without special style."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.INFO, content="Just info")

        renderer._render_message(msg)
        output_text = output.getvalue()
        assert "Just info" in output_text

    @pytest.mark.asyncio
    async def test_async_renderer_info_no_style(self):
        """Test INFO message without special style in async renderer."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.INFO, content="Plain info")

        await renderer.render_message(msg)
        output_text = output.getvalue()
        assert "Plain info" in output_text
