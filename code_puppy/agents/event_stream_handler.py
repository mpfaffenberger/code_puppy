"""Event stream handler for processing streaming events from agent runs."""

import asyncio
import logging
import sys
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


def _get_active_prompt_runtime() -> Any | None:
    """Return the active interactive runtime, if available."""
    try:
        from code_puppy.command_line.interactive_runtime import (
            get_active_interactive_runtime,
        )

        return get_active_interactive_runtime()
    except Exception:
        return None


def _has_active_prompt_surface() -> bool:
    """Return True when the always-on prompt surface is mounted."""
    runtime = _get_active_prompt_runtime()
    return runtime.has_prompt_surface() if runtime is not None else False


def _set_prompt_ephemeral_status(text: str | None) -> None:
    """Update transient prompt-local status for mutable stream output."""
    runtime = _get_active_prompt_runtime()
    if runtime is None:
        return
    try:
        runtime.set_prompt_ephemeral_status(text)
    except Exception:
        pass


def _clear_prompt_ephemeral_status() -> None:
    """Clear transient prompt-local status."""
    runtime = _get_active_prompt_runtime()
    if runtime is None:
        return
    try:
        runtime.clear_prompt_ephemeral_status()
    except Exception:
        pass


def _set_prompt_ephemeral_preview(text: str | None) -> None:
    """Update transient prompt-local preview for live response text."""
    runtime = _get_active_prompt_runtime()
    if runtime is None:
        return
    try:
        runtime.set_prompt_ephemeral_preview(text)
    except Exception:
        pass


def _merge_tool_name(current_name: str, tool_name_delta: str) -> str:
    """Merge a streamed tool name delta without duplicating already-known names."""
    if not tool_name_delta:
        return current_name
    if not current_name:
        return tool_name_delta
    if tool_name_delta.startswith(current_name):
        return tool_name_delta
    if tool_name_delta in current_name:
        return current_name
    for overlap in range(min(len(current_name), len(tool_name_delta)), 0, -1):
        if current_name.endswith(tool_name_delta[:overlap]):
            return current_name + tool_name_delta[overlap:]
    return current_name + tool_name_delta


def _is_reasoning_tool_name(tool_name: str) -> bool:
    """Return True for the reasoning tool, including streamed prefixes."""
    reasoning_tool = "agent_share_your_reasoning"
    return bool(tool_name) and (
        reasoning_tool.startswith(tool_name) or tool_name.startswith(reasoning_tool)
    )


def _build_prompt_safe_console(source_console: Console) -> Console:
    """Create a console that writes to the real terminal above the prompt."""
    return Console(
        file=sys.__stdout__,
        force_terminal=source_console.is_terminal,
        width=source_console.width,
        color_system=source_console.color_system,
        soft_wrap=source_console.soft_wrap,
        legacy_windows=source_console.legacy_windows,
    )


async def _print_stream_output(
    console: Console, *args: Any, **kwargs: Any
) -> None:
    """Render stream output above the prompt when the prompt surface is mounted."""
    runtime = _get_active_prompt_runtime()
    if runtime is not None and runtime.has_prompt_surface():
        prompt_safe_console = _build_prompt_safe_console(console)
        rendered = await runtime.run_above_prompt_async(
            lambda: prompt_safe_console.print(*args, **kwargs)
        )
        if rendered:
            return
    console.print(*args, **kwargs)


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
    did_stream_anything = False  # Track if we streamed any content
    spinner_paused = False
    prompt_surface_response_preview = ""

    # Termflow streaming state for text parts
    termflow_parsers: dict[int, TermflowParser] = {}
    termflow_renderers: dict[int, TermflowRenderer] = {}
    termflow_line_buffers: dict[int, str] = {}  # Buffer incomplete lines

    async def _print_thinking_banner() -> None:
        """Print the THINKING banner with spinner pause and line clear."""
        nonlocal did_stream_anything, spinner_paused

        prompt_surface_active = _has_active_prompt_surface()
        if not spinner_paused:
            pause_all_spinners()
            spinner_paused = True
            await asyncio.sleep(0.02)
        if prompt_surface_active:
            await _print_stream_output(console)
        else:
            await _print_stream_output(console, " " * 50, end="\r")
            await _print_stream_output(console)  # Newline before banner
        # Bold banner with configurable color and lightning bolt
        thinking_color = get_banner_color("thinking")
        await _print_stream_output(
            console,
            Text.from_markup(
                f"[bold white on {thinking_color}] THINKING [/bold white on {thinking_color}] [dim]\u26a1 "
            ),
            end="",
        )
        did_stream_anything = True

    async def _print_response_banner() -> None:
        """Print the AGENT RESPONSE banner with spinner pause and line clear."""
        nonlocal did_stream_anything, spinner_paused

        prompt_surface_active = _has_active_prompt_surface()
        if not spinner_paused:
            pause_all_spinners()
            spinner_paused = True
            await asyncio.sleep(0.02)
        if prompt_surface_active:
            await _print_stream_output(console)
        else:
            await _print_stream_output(console, " " * 50, end="\r")
            await _print_stream_output(console)  # Newline before banner
        response_color = get_banner_color("agent_response")
        await _print_stream_output(
            console,
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
                    await _print_stream_output(console, f"[dim]{escaped}[/dim]", end="")
                    banner_printed.add(event.index)
            elif isinstance(part, TextPart):
                streaming_parts.add(event.index)
                text_parts.add(event.index)
                if _has_active_prompt_surface():
                    if part.content:
                        prompt_surface_response_preview += part.content
                        _set_prompt_ephemeral_preview(prompt_surface_response_preview)
                else:
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
                            if _has_active_prompt_surface():
                                prompt_surface_response_preview += delta.content_delta
                                _set_prompt_ephemeral_preview(
                                    prompt_surface_response_preview
                                )
                                continue
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
                            await _print_stream_output(
                                console, f"[dim]{escaped}[/dim]", end=""
                            )
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
                        tool_names[event.index] = _merge_tool_name(
                            tool_names.get(event.index, ""), tool_name_delta
                        )

                    # Use stored tool name for display
                    tool_name = tool_names.get(event.index, "")
                    if prompt_surface_active:
                        if not _is_reasoning_tool_name(tool_name):
                            count = token_count[event.index]
                            if tool_name:
                                _set_prompt_ephemeral_status(
                                    f"\U0001f527 Calling {tool_name}... {count} token(s)"
                                )
                            else:
                                _set_prompt_ephemeral_status(
                                    f"\U0001f527 Calling tool... {count} token(s)"
                                )
                        continue
                    count = token_count[event.index]
                    # Display with tool wrench icon and tool name
                    if tool_name:
                        await _print_stream_output(
                            console,
                            f"  \U0001f527 Calling {tool_name}... {count} token(s)   ",
                            end="\r",
                        )
                    else:
                        await _print_stream_output(
                            console,
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
                    if _has_active_prompt_surface():
                        _clear_prompt_ephemeral_status()
                    else:
                        # Clear the chunk counter line by printing spaces and returning
                        await _print_stream_output(console, " " * 50, end="\r")
                # For thinking parts, just print newline
                elif event.index in banner_printed:
                    await _print_stream_output(console)  # Final newline after streaming

                # Clean up token count and tool names
                token_count.pop(event.index, None)
                tool_names.pop(event.index, None)
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
