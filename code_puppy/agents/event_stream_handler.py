"""Event stream handler for processing streaming events from agent runs."""

import asyncio
import logging
from collections.abc import AsyncIterable
from typing import Any, Optional

from pydantic_ai import PartDeltaEvent, PartEndEvent, PartStartEvent, RunContext
from pydantic_ai.messages import (
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    ToolCallPartDelta,
)
from rich.console import Console
from rich.markup import escape
from rich.text import Text

from code_puppy.config import get_banner_color, get_subagent_verbose
from code_puppy.messaging.spinner import pause_all_spinners, resume_all_spinners
from code_puppy.tools.subagent_context import is_subagent

logger = logging.getLogger(__name__)


def _fire_stream_event(event_type: str, event_data: Any) -> None:
    """Fire a stream event callback asynchronously (non-blocking).

    Args:
        event_type: Type of the event (e.g., 'part_start', 'part_delta', 'part_end')
        event_data: Data associated with the event
    """
    try:
        from code_puppy import callbacks
        from code_puppy.messaging import get_session_context

        agent_session_id = get_session_context()

        # Use create_task to fire callback without blocking
        asyncio.create_task(
            callbacks.on_stream_event(event_type, event_data, agent_session_id)
        )
    except ImportError:
        logger.debug("callbacks or messaging module not available for stream event")
    except Exception as e:
        logger.debug(f"Error firing stream event callback: {e}")


# Module-level console for streaming output
# Set via set_streaming_console() to share console with spinner
_streaming_console: Optional[Console] = None


def set_streaming_console(console: Optional[Console]) -> None:
    """Set the console used for streaming output.

    This should be called with the same console used by the spinner
    to avoid Live display conflicts that cause line duplication.

    Args:
        console: The Rich console to use, or None to use a fallback.
    """
    global _streaming_console
    _streaming_console = console


def get_streaming_console() -> Console:
    """Get the console for streaming output.

    Returns the configured console or creates a fallback Console.
    """
    if _streaming_console is not None:
        return _streaming_console
    return Console()


def _should_suppress_output() -> bool:
    """Check if sub-agent output should be suppressed.

    Returns:
        True if we're in a sub-agent context and verbose mode is disabled.
    """
    return is_subagent() and not get_subagent_verbose()


def _has_active_prompt_surface() -> bool:
    """Return True when the always-on prompt surface is mounted."""
    try:
        from code_puppy.command_line.interactive_runtime import (
            get_active_interactive_runtime,
        )

        runtime = get_active_interactive_runtime()
        return runtime.has_prompt_surface() if runtime is not None else False
    except Exception:
        return False


async def _consume_events_without_console(events: AsyncIterable[Any]) -> None:
    """Consume stream events without terminal rendering, but keep callbacks alive."""
    async for event in events:
        if isinstance(event, PartStartEvent):
            _fire_stream_event(
                "part_start",
                {
                    "index": event.index,
                    "part_type": type(event.part).__name__,
                    "part": event.part,
                },
            )
        elif isinstance(event, PartDeltaEvent):
            _fire_stream_event(
                "part_delta",
                {
                    "index": event.index,
                    "delta_type": type(event.delta).__name__,
                    "delta": event.delta,
                },
            )
        elif isinstance(event, PartEndEvent):
            _fire_stream_event(
                "part_end",
                {
                    "index": event.index,
                    "next_part_kind": getattr(event, "next_part_kind", None),
                },
            )


async def event_stream_handler(
    ctx: RunContext,
    events: AsyncIterable[Any],
) -> None:
    """Handle streaming events from the agent run.

    This function processes streaming events and emits TextPart, ThinkingPart,
    and ToolCallPart content with styled banners/tokens as they stream in.

    Args:
        ctx: The run context.
        events: Async iterable of streaming events (PartStartEvent, PartDeltaEvent, etc.).
    """
    # If we're in a sub-agent and verbose mode is disabled, silently consume events
    if _should_suppress_output():
        async for _ in events:
            pass  # Just consume events without rendering
        return

    # The always-on prompt surface cannot safely coexist with live terminal streaming.
    # In that mode, we keep callbacks/events flowing and render the final response
    # through the normal AgentResponseMessage banner path instead.
    if _has_active_prompt_surface():
        await _consume_events_without_console(events)
        return

    from termflow import Parser as TermflowParser
    from termflow import Renderer as TermflowRenderer

    # Use the module-level console (set via set_streaming_console)
    console = get_streaming_console()

    # Track which part indices we're currently streaming (for Text/Thinking/Tool parts)
    streaming_parts: set[int] = set()
    thinking_parts: set[int] = set()  # Track which parts are thinking (for dim style)
    text_parts: set[int] = set()  # Track which parts are text
    tool_parts: set[int] = set()  # Track which parts are tool calls
    banner_printed: set[int] = set()  # Track if banner was already printed
    token_count: dict[int, int] = {}  # Track token count per text/tool part
    tool_names: dict[int, str] = {}  # Track tool name per tool part index
    tool_progress_announced: set[int] = set()
    did_stream_anything = False  # Track if we streamed any content
    spinner_paused = False

    # Termflow streaming state for text parts
    termflow_parsers: dict[int, TermflowParser] = {}
    termflow_renderers: dict[int, TermflowRenderer] = {}
    termflow_line_buffers: dict[int, str] = {}  # Buffer incomplete lines

    async def _print_thinking_banner() -> None:
        """Print the THINKING banner with spinner pause and line clear."""
        nonlocal did_stream_anything, spinner_paused

        if not spinner_paused:
            pause_all_spinners()
            spinner_paused = True
            await asyncio.sleep(0.02)
        console.print(" " * 50, end="\r")
        console.print()  # Newline before banner
        # Bold banner with configurable color and lightning bolt
        thinking_color = get_banner_color("thinking")
        console.print(
            Text.from_markup(
                f"[bold white on {thinking_color}] THINKING [/bold white on {thinking_color}] [dim]\u26a1 "
            ),
            end="",
        )
        did_stream_anything = True

    async def _print_response_banner() -> None:
        """Print the AGENT RESPONSE banner with spinner pause and line clear."""
        nonlocal did_stream_anything, spinner_paused

        if not spinner_paused:
            pause_all_spinners()
            spinner_paused = True
            await asyncio.sleep(0.02)
        console.print(" " * 50, end="\r")
        console.print()  # Newline before banner
        response_color = get_banner_color("agent_response")
        console.print(
            Text.from_markup(
                f"[bold white on {response_color}] AGENT RESPONSE [/bold white on {response_color}]"
            )
        )
        did_stream_anything = True

    async for event in events:
        # PartStartEvent - register the part but defer banner until content arrives
        if isinstance(event, PartStartEvent):
            # Fire stream event callback for part_start
            _fire_stream_event(
                "part_start",
                {
                    "index": event.index,
                    "part_type": type(event.part).__name__,
                    "part": event.part,
                },
            )

            part = event.part
            if isinstance(part, ThinkingPart):
                streaming_parts.add(event.index)
                thinking_parts.add(event.index)
                # If there's initial content, print banner + content now
                if part.content and part.content.strip():
                    await _print_thinking_banner()
                    escaped = escape(part.content)
                    console.print(f"[dim]{escaped}[/dim]", end="")
                    banner_printed.add(event.index)
            elif isinstance(part, TextPart):
                streaming_parts.add(event.index)
                text_parts.add(event.index)
                # Initialize termflow streaming for this text part
                termflow_parsers[event.index] = TermflowParser()
                termflow_renderers[event.index] = TermflowRenderer(
                    output=console.file, width=console.width
                )
                termflow_line_buffers[event.index] = ""
                # Handle initial content if present
                if part.content and part.content.strip():
                    await _print_response_banner()
                    banner_printed.add(event.index)
                    termflow_line_buffers[event.index] = part.content
            elif isinstance(part, ToolCallPart):
                streaming_parts.add(event.index)
                tool_parts.add(event.index)
                token_count[event.index] = 0  # Initialize token counter
                # Capture tool name from the start event
                tool_names[event.index] = part.tool_name or ""
                # Track tool name for display
                banner_printed.add(
                    event.index
                )  # Use banner_printed to track if we've shown tool info

        # PartDeltaEvent - stream the content as it arrives
        elif isinstance(event, PartDeltaEvent):
            # Fire stream event callback for part_delta
            _fire_stream_event(
                "part_delta",
                {
                    "index": event.index,
                    "delta_type": type(event.delta).__name__,
                    "delta": event.delta,
                },
            )

            if event.index in streaming_parts:
                delta = event.delta
                if isinstance(delta, (TextPartDelta, ThinkingPartDelta)):
                    if delta.content_delta:
                        # For text parts, stream markdown with termflow
                        if event.index in text_parts:
                            # Print banner on first content
                            if event.index not in banner_printed:
                                await _print_response_banner()
                                banner_printed.add(event.index)

                            # Add content to line buffer
                            termflow_line_buffers[event.index] += delta.content_delta

                            # Process complete lines
                            parser = termflow_parsers[event.index]
                            renderer = termflow_renderers[event.index]
                            buffer = termflow_line_buffers[event.index]

                            while "\n" in buffer:
                                line, buffer = buffer.split("\n", 1)
                                events_to_render = parser.parse_line(line)
                                renderer.render_all(events_to_render)

                            termflow_line_buffers[event.index] = buffer
                        else:
                            # For thinking parts, stream immediately (dim)
                            if event.index not in banner_printed:
                                await _print_thinking_banner()
                                banner_printed.add(event.index)
                            escaped = escape(delta.content_delta)
                            console.print(f"[dim]{escaped}[/dim]", end="")
                elif isinstance(delta, ToolCallPartDelta):
                    prompt_surface_active = _has_active_prompt_surface()
                    # For tool calls, estimate tokens from args_delta content
                    # args_delta contains the streaming JSON arguments
                    args_delta = getattr(delta, "args_delta", "") or ""
                    if args_delta:
                        # Rough estimate: 4 chars ≈ 1 token (same heuristic as subagent_stream_handler)
                        estimated_tokens = max(1, len(args_delta) // 4)
                        token_count[event.index] += estimated_tokens
                    else:
                        # Even empty deltas count as activity
                        token_count[event.index] += 1

                    # Update tool name if delta provides more of it
                    tool_name_delta = getattr(delta, "tool_name_delta", "") or ""
                    if tool_name_delta:
                        tool_names[event.index] = (
                            tool_names.get(event.index, "") + tool_name_delta
                        )

                    # Use stored tool name for display
                    tool_name = tool_names.get(event.index, "")
                    count = token_count[event.index]
                    if prompt_surface_active:
                        if event.index not in tool_progress_announced:
                            label = tool_name or "tool"
                            console.print(f"  \U0001f527 Calling {label}...")
                            tool_progress_announced.add(event.index)
                    else:
                        # Display with tool wrench icon and tool name
                        if tool_name:
                            console.print(
                                f"  \U0001f527 Calling {tool_name}... {count} token(s)   ",
                                end="\r",
                            )
                        else:
                            console.print(
                                f"  \U0001f527 Calling tool... {count} token(s)   ",
                                end="\r",
                            )

        # PartEndEvent - finish the streaming with a newline
        elif isinstance(event, PartEndEvent):
            # Fire stream event callback for part_end
            _fire_stream_event(
                "part_end",
                {
                    "index": event.index,
                    "next_part_kind": getattr(event, "next_part_kind", None),
                },
            )

            if event.index in streaming_parts:
                # For text parts, finalize termflow rendering
                if event.index in text_parts:
                    # Render any remaining buffered content
                    if event.index in termflow_parsers:
                        parser = termflow_parsers[event.index]
                        renderer = termflow_renderers[event.index]
                        remaining = termflow_line_buffers.get(event.index, "")

                        # Parse and render any remaining partial line
                        if remaining.strip():
                            events_to_render = parser.parse_line(remaining)
                            renderer.render_all(events_to_render)

                        # Finalize the parser to close any open blocks
                        final_events = parser.finalize()
                        renderer.render_all(final_events)

                        # Clean up termflow state
                        del termflow_parsers[event.index]
                        del termflow_renderers[event.index]
                        del termflow_line_buffers[event.index]
                # For tool parts, clear the chunk counter line
                elif event.index in tool_parts:
                    if not _has_active_prompt_surface():
                        # Clear the chunk counter line by printing spaces and returning
                        console.print(" " * 50, end="\r")
                # For thinking parts, just print newline
                elif event.index in banner_printed:
                    console.print()  # Final newline after streaming

                # Clean up token count and tool names
                token_count.pop(event.index, None)
                tool_names.pop(event.index, None)
                tool_progress_announced.discard(event.index)
                # Clean up all tracking sets
                streaming_parts.discard(event.index)
                thinking_parts.discard(event.index)
                text_parts.discard(event.index)
                tool_parts.discard(event.index)
                banner_printed.discard(event.index)

                # Resume spinner if next part is NOT text/thinking/tool (avoid race condition)
                # If next part is None or handled differently, it's safe to resume
                # Note: spinner itself handles blank line before appearing
                next_kind = getattr(event, "next_part_kind", None)
                if next_kind not in ("text", "thinking", "tool-call"):
                    resume_all_spinners()
                    spinner_paused = False

    # Spinner is resumed in PartEndEvent when appropriate (based on next_part_kind)
    if spinner_paused:
        resume_all_spinners()
