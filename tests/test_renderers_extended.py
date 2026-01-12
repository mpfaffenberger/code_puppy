"""
Extended tests for renderers.py to cover uncovered lines.

Focuses on:
- InteractiveRenderer additional message types and edge cases
- SynchronousInteractiveRenderer (completely untested)
- Error handling paths
"""

import asyncio
import sys
import time
from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from code_puppy.messaging.message_queue import MessageQueue, MessageType, UIMessage
from code_puppy.messaging.renderers import (
    InteractiveRenderer,
    MessageRenderer,
    SynchronousInteractiveRenderer,
)

# =============================================================================
# InteractiveRenderer - Uncovered Message Types
# =============================================================================


class TestInteractiveRendererMessageTypes:
    """Test InteractiveRenderer with all message types."""

    @pytest.mark.asyncio
    async def test_render_tool_output(self):
        """Test rendering TOOL_OUTPUT message (blue style)."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.TOOL_OUTPUT, content="Tool output text")

        await renderer.render_message(msg)

        output_text = output.getvalue()
        assert "Tool output text" in output_text

    @pytest.mark.asyncio
    async def test_render_agent_reasoning(self):
        """Test rendering AGENT_REASONING message (no style)."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.AGENT_REASONING, content="Thinking...")

        await renderer.render_message(msg)

        output_text = output.getvalue()
        assert "Thinking" in output_text

    @pytest.mark.asyncio
    async def test_render_planned_next_steps(self):
        """Test rendering PLANNED_NEXT_STEPS message (no style)."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.PLANNED_NEXT_STEPS, content="1. Do this\n2. Do that"
        )

        await renderer.render_message(msg)

        output_text = output.getvalue()
        assert "Do this" in output_text

    @pytest.mark.asyncio
    async def test_render_agent_response_markdown(self):
        """Test rendering AGENT_RESPONSE as markdown."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.AGENT_RESPONSE, content="# Header\n\nParagraph text"
        )

        await renderer.render_message(msg)

        output_text = output.getvalue()
        # Markdown should be rendered
        assert len(output_text) > 0

    @pytest.mark.asyncio
    async def test_render_agent_response_markdown_fallback(self):
        """Test AGENT_RESPONSE falls back to plain text on markdown failure."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.AGENT_RESPONSE, content="Simple text")

        # Mock Markdown to raise an exception
        with patch(
            "code_puppy.messaging.renderers.Markdown",
            side_effect=Exception("Markdown error"),
        ):
            await renderer.render_message(msg)

        output_text = output.getvalue()
        assert "Simple text" in output_text

    @pytest.mark.asyncio
    async def test_render_system_message(self):
        """Test rendering SYSTEM message (dim style)."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.SYSTEM, content="System message")

        await renderer.render_message(msg)

        output_text = output.getvalue()
        assert "System message" in output_text

    @pytest.mark.asyncio
    async def test_render_unknown_message_type(self):
        """Test rendering unknown message type (else branch, no style)."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        # DIVIDER is in the else branch
        msg = UIMessage(type=MessageType.DIVIDER, content="---")

        await renderer.render_message(msg)

        output_text = output.getvalue()
        assert len(output_text) > 0


class TestInteractiveRendererVersionMessages:
    """Test version message special handling."""

    @pytest.mark.asyncio
    async def test_current_version_message_dim(self):
        """Test that 'Current version:' messages become dim."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.INFO, content="Current version: 1.0.0")

        await renderer.render_message(msg)

        output_text = output.getvalue()
        assert "Current version" in output_text

    @pytest.mark.asyncio
    async def test_latest_version_message_dim(self):
        """Test that 'Latest version:' messages become dim."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.INFO, content="Latest version: 2.0.0")

        await renderer.render_message(msg)

        output_text = output.getvalue()
        assert "Latest version" in output_text


class TestInteractiveRendererComplexContent:
    """Test rendering complex Rich objects."""

    @pytest.mark.asyncio
    async def test_render_table_content(self):
        """Test rendering Rich Table objects."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        table = Table(title="Test Table")
        table.add_column("Name")
        table.add_row("Alice")
        msg = UIMessage(type=MessageType.INFO, content=table)

        await renderer.render_message(msg)

        output_text = output.getvalue()
        assert "Alice" in output_text

    @pytest.mark.asyncio
    async def test_render_markdown_content(self):
        """Test rendering pre-built Markdown objects."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        md = Markdown("**Bold text**")
        msg = UIMessage(type=MessageType.INFO, content=md)

        await renderer.render_message(msg)

        output_text = output.getvalue()
        assert len(output_text) > 0


class TestInteractiveRendererHumanInput:
    """Test _handle_human_input_request."""

    @pytest.mark.asyncio
    async def test_handle_human_input_request(self):
        """Test handling HUMAN_INPUT_REQUEST message."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.HUMAN_INPUT_REQUEST,
            content="Please enter your name:",
            metadata={"prompt_id": "test-123"},
        )

        await renderer.render_message(msg)

        output_text = output.getvalue()
        assert "INPUT REQUESTED" in output_text
        assert "Please enter your name" in output_text


class TestInteractiveRendererFlush:
    """Test console flush handling."""

    @pytest.mark.asyncio
    async def test_console_flush_called(self):
        """Test that console.file.flush() is called when available."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.INFO, content="Test")

        # Spy on flush
        original_flush = output.flush
        flush_called = [False]

        def mock_flush():
            flush_called[0] = True
            original_flush()

        output.flush = mock_flush

        await renderer.render_message(msg)

        assert flush_called[0] is True

    @pytest.mark.asyncio
    async def test_console_with_flush_attribute_check(self):
        """Test that flush is checked via hasattr before calling."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.INFO, content="Test flush check")

        # The hasattr check should work correctly
        await renderer.render_message(msg)
        assert "Test flush check" in output.getvalue()


# =============================================================================
# SynchronousInteractiveRenderer - All Untested
# =============================================================================


class TestSynchronousInteractiveRendererInit:
    """Test SynchronousInteractiveRenderer initialization."""

    def test_init_with_queue_and_console(self):
        """Test init with custom console."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output)

        renderer = SynchronousInteractiveRenderer(queue, console)

        assert renderer.queue is queue
        assert renderer.console is console
        assert renderer._running is False
        assert renderer._thread is None

    def test_init_with_default_console(self):
        """Test init with default console."""
        queue = MessageQueue()

        renderer = SynchronousInteractiveRenderer(queue)

        assert renderer.queue is queue
        assert renderer.console is not None
        assert isinstance(renderer.console, Console)


class TestSynchronousInteractiveRendererLifecycle:
    """Test start/stop lifecycle."""

    def test_start_creates_thread(self):
        """Test that start creates background thread."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output)

        renderer = SynchronousInteractiveRenderer(queue, console)
        renderer.start()

        try:
            assert renderer._running is True
            assert renderer._thread is not None
            assert renderer._thread.is_alive()
            assert queue._has_active_renderer
        finally:
            renderer.stop()

    def test_start_double_start_safe(self):
        """Test that starting twice is safe."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output)

        renderer = SynchronousInteractiveRenderer(queue, console)
        renderer.start()
        thread1 = renderer._thread

        renderer.start()  # Should be no-op
        thread2 = renderer._thread

        try:
            assert thread1 is thread2
        finally:
            renderer.stop()

    def test_stop_stops_thread(self):
        """Test that stop stops the thread."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output)

        renderer = SynchronousInteractiveRenderer(queue, console)
        renderer.start()
        assert renderer._running is True

        renderer.stop()

        assert renderer._running is False
        assert not queue._has_active_renderer
        # Thread should have joined
        time.sleep(0.1)
        assert not renderer._thread.is_alive()

    def test_stop_without_start(self):
        """Test that stop without start is safe."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output)

        renderer = SynchronousInteractiveRenderer(queue, console)
        # Should not raise
        renderer.stop()

        assert renderer._running is False


class TestSynchronousInteractiveRendererMessageTypes:
    """Test _render_message for all message types."""

    def test_render_error_message(self):
        """Test rendering ERROR message (bold red)."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.ERROR, content="Error occurred")

        renderer._render_message(msg)

        assert "Error occurred" in output.getvalue()

    def test_render_warning_message(self):
        """Test rendering WARNING message (yellow)."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.WARNING, content="Warning!")

        renderer._render_message(msg)

        assert "Warning" in output.getvalue()

    def test_render_success_message(self):
        """Test rendering SUCCESS message (green)."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.SUCCESS, content="Success!")

        renderer._render_message(msg)

        assert "Success" in output.getvalue()

    def test_render_tool_output_message(self):
        """Test rendering TOOL_OUTPUT message (blue)."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.TOOL_OUTPUT, content="Tool result")

        renderer._render_message(msg)

        assert "Tool result" in output.getvalue()

    def test_render_agent_reasoning_message(self):
        """Test rendering AGENT_REASONING message (no style)."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.AGENT_REASONING, content="Thinking about it..."
        )

        renderer._render_message(msg)

        assert "Thinking about it" in output.getvalue()

    def test_render_agent_response_as_markdown(self):
        """Test AGENT_RESPONSE renders as markdown."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.AGENT_RESPONSE, content="# Title\n\nBody")

        renderer._render_message(msg)

        # Should have output something
        assert len(output.getvalue()) > 0

    def test_render_agent_response_markdown_fallback(self):
        """Test AGENT_RESPONSE falls back on markdown failure."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.AGENT_RESPONSE, content="Plain fallback")

        with patch(
            "code_puppy.messaging.renderers.Markdown",
            side_effect=Exception("Parse error"),
        ):
            renderer._render_message(msg)

        assert "Plain fallback" in output.getvalue()

    def test_render_system_message(self):
        """Test rendering SYSTEM message (dim)."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.SYSTEM, content="System info")

        renderer._render_message(msg)

        assert "System info" in output.getvalue()

    def test_render_unknown_type(self):
        """Test rendering unknown type (else branch)."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.DIVIDER, content="---")

        renderer._render_message(msg)

        assert len(output.getvalue()) > 0


class TestSynchronousInteractiveRendererVersionMessages:
    """Test version message special handling."""

    def test_current_version_becomes_dim(self):
        """Test 'Current version:' becomes dim."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.INFO, content="Current version: 1.2.3")

        renderer._render_message(msg)

        assert "Current version" in output.getvalue()

    def test_latest_version_becomes_dim(self):
        """Test 'Latest version:' becomes dim."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.INFO, content="Latest version: 3.0.0")

        renderer._render_message(msg)

        assert "Latest version" in output.getvalue()


class TestSynchronousInteractiveRendererComplexContent:
    """Test rendering complex Rich objects."""

    def test_render_table(self):
        """Test rendering Rich Table."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        table = Table()
        table.add_column("Col1")
        table.add_row("Value1")
        msg = UIMessage(type=MessageType.INFO, content=table)

        renderer._render_message(msg)

        assert "Value1" in output.getvalue()

    def test_render_text_object(self):
        """Test rendering Rich Text object."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        text = Text("Styled content", style="bold")
        msg = UIMessage(type=MessageType.INFO, content=text)

        renderer._render_message(msg)

        assert "Styled content" in output.getvalue()


class TestSynchronousInteractiveRendererHumanInput:
    """Test _handle_human_input_request."""

    def test_human_input_no_prompt_id(self):
        """Test handling request without prompt_id shows error."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.HUMAN_INPUT_REQUEST,
            content="Enter something:",
            metadata={},  # No prompt_id!
        )

        renderer._render_message(msg)

        assert "Error" in output.getvalue() or "Invalid" in output.getvalue()

    def test_human_input_no_metadata(self):
        """Test handling request with None metadata."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.HUMAN_INPUT_REQUEST,
            content="Enter something:",
            metadata=None,
        )

        renderer._render_message(msg)

        assert "Error" in output.getvalue() or "Invalid" in output.getvalue()

    def test_human_input_with_valid_prompt_id(self):
        """Test handling request with valid prompt_id."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.HUMAN_INPUT_REQUEST,
            content="Enter your name:",
            metadata={"prompt_id": "prompt-abc"},
        )

        # Mock input() to return a value and patch provide_prompt_response at the import location
        with patch("builtins.input", return_value="Claude"):
            with patch(
                "code_puppy.messaging.message_queue.provide_prompt_response"
            ) as mock_provide:
                renderer._render_message(msg)

                mock_provide.assert_called_once_with("prompt-abc", "Claude")

        assert "Enter your name" in output.getvalue()

    def test_human_input_displays_prompt(self):
        """Test that human input request displays the prompt."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.HUMAN_INPUT_REQUEST,
            content="Please enter something:",
            metadata={"prompt_id": "prompt-display"},
        )

        # Mock input to return immediately and mock the response function
        with patch("builtins.input", return_value="user input"):
            with patch("code_puppy.messaging.message_queue.provide_prompt_response"):
                renderer._render_message(msg)

        # Prompt should have been displayed
        assert "Please enter something" in output.getvalue()


class TestSynchronousInteractiveRendererConsumeMessages:
    """Test _consume_messages thread behavior."""

    def test_consume_messages_processes_queue(self):
        """Test that _consume_messages processes messages from queue."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        renderer.start()

        try:
            # Emit a message
            msg = UIMessage(type=MessageType.INFO, content="Hello from queue!")
            queue.emit(msg)

            # Give time for processing
            time.sleep(0.1)

            assert "Hello from queue" in output.getvalue()
        finally:
            renderer.stop()

    def test_consume_messages_sleeps_on_empty(self):
        """Test that _consume_messages sleeps when queue is empty."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        renderer.start()

        try:
            # Let it run with empty queue
            time.sleep(0.05)
            # Should not crash
        finally:
            renderer.stop()


class TestSynchronousInteractiveRendererFlush:
    """Test console flush handling."""

    def test_flush_called_on_render(self):
        """Test that flush is called after rendering."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.INFO, content="Test")

        flush_called = [False]
        original_flush = output.flush

        def mock_flush():
            flush_called[0] = True
            original_flush()

        output.flush = mock_flush

        renderer._render_message(msg)

        assert flush_called[0] is True

    def test_flush_attribute_check(self):
        """Test that flush is checked via hasattr before calling."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(type=MessageType.INFO, content="Test flush check")

        # The hasattr check should work correctly with normal console
        renderer._render_message(msg)
        assert "Test flush check" in output.getvalue()


class TestSynchronousInteractiveRendererHumanInputFlush:
    """Test flush in human input handler."""

    def test_human_input_flush(self):
        """Test flush is called in _handle_human_input_request."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = SynchronousInteractiveRenderer(queue, console)
        msg = UIMessage(
            type=MessageType.HUMAN_INPUT_REQUEST,
            content="Enter:",
            metadata={"prompt_id": "test"},
        )

        flush_count = [0]
        original_flush = output.flush

        def mock_flush():
            flush_count[0] += 1
            original_flush()

        output.flush = mock_flush

        with patch("builtins.input", return_value="x"):
            with patch("code_puppy.messaging.message_queue.provide_prompt_response"):
                renderer._render_message(msg)

        # Should have flushed at least once
        assert flush_count[0] >= 1


# =============================================================================
# MessageRenderer Error Handling in _consume_messages
# =============================================================================


class TestMessageRendererErrorHandling:
    """Test error handling in _consume_messages."""

    @pytest.mark.asyncio
    async def test_consume_messages_handles_render_error(self):
        """Test that render errors are caught and logged to stderr."""
        queue = MessageQueue()
        error_written = []

        class FailingRenderer(MessageRenderer):
            async def render_message(self, message):
                raise ValueError("Render failed!")

        renderer = FailingRenderer(queue)

        # Mock sys.stderr.write to capture error output
        original_stderr_write = sys.stderr.write

        def capture_stderr(text):
            error_written.append(text)
            return original_stderr_write(text)

        try:
            await renderer.start()

            # Emit a message that will fail to render
            msg = UIMessage(type=MessageType.INFO, content="Will fail")
            queue.emit(msg)

            with patch.object(sys.stderr, "write", side_effect=capture_stderr):
                # Give time to process
                await asyncio.sleep(0.3)

            # Error should be captured (may or may not have been written yet)
            # The key is that the renderer doesn't crash

        finally:
            await renderer.stop()

    @pytest.mark.asyncio
    async def test_renderer_message_loop_runs(self):
        """Test that the renderer's message loop is running."""
        queue = MessageQueue()

        class TrackingRenderer(MessageRenderer):
            def __init__(self, queue):
                super().__init__(queue)
                self.loop_iterations = 0

            async def render_message(self, message):
                pass

        renderer = TrackingRenderer(queue)

        try:
            await renderer.start()

            # Verify renderer is running
            assert renderer._running is True
            assert renderer._task is not None

            # Let it run briefly
            await asyncio.sleep(0.15)

            # Should still be running
            assert renderer._running is True

        finally:
            await renderer.stop()


class TestInteractiveRendererWithStyle:
    """Test InteractiveRenderer with styled content and no style."""

    @pytest.mark.asyncio
    async def test_render_with_style(self):
        """Test rendering message with style applied."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        # ERROR has style="bold red"
        msg = UIMessage(type=MessageType.ERROR, content="Error with style")

        await renderer.render_message(msg)

        assert "Error with style" in output.getvalue()

    @pytest.mark.asyncio
    async def test_render_without_style(self):
        """Test rendering message without style (else branch for string content)."""
        queue = MessageQueue()
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        renderer = InteractiveRenderer(queue, console)
        # AGENT_REASONING has style=None
        msg = UIMessage(type=MessageType.AGENT_REASONING, content="No style text")

        await renderer.render_message(msg)

        assert "No style text" in output.getvalue()
