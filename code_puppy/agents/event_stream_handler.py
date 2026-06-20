"""Event stream handler for processing streaming events from agent runs."""

import asyncio
import logging
import math
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

from code_puppy.agents.smooth_stream import (
    SmoothTermflowWriter,
    ThinkingStreamSmoother,
    make_smooth_termflow_writer,
    make_thinking_smoother,
)
from code_puppy.config import (
    get_banner_color,
    get_output_level,
    get_subagent_verbose,
    get_suppress_thinking_messages,
)
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

    In ``high`` output mode, sub-agent output is never suppressed.

    Returns:
        True if we're in a sub-agent context and verbose mode is disabled.
    """
    if get_output_level() == "high":
        return False
    return is_subagent() and not get_subagent_verbose()


def _suppress_thinking_stream() -> bool:
    """Return True if thinking banners/content should be hidden.

    Thinking is suppressed in ``low`` output mode (collapsed to a peek
    by the RichConsoleRenderer) or when the user has explicitly set
    ``suppress_thinking_messages``.

    In ``high`` output mode, thinking is *never* suppressed -- the user
    explicitly asked for maximum visibility.
    """
    level = get_output_level()
    if level == "high":
        return False
    return level == "low" or get_suppress_thinking_messages()


def _suppress_tool_progress() -> bool:
    """Return True if tool-call progress counters should be hidden.

    In ``low`` mode, the shell-start peek in the RichConsoleRenderer is
    sufficient; the streaming token counter is noise.
    """
    return get_output_level() == "low"


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

    # Server/SDK/RPC runs must never write Rich output into the transport's
    # stdout. Their final response and tool events use the versioned bus
    # envelope; raw model deltas remain available through stream callbacks.
    from code_puppy.server.context import is_headless_transport

    if is_headless_transport():
        async for event in events:
            if isinstance(event, PartStartEvent):
                event_type = "part_start"
            elif isinstance(event, PartDeltaEvent):
                event_type = "part_delta"
            elif isinstance(event, PartEndEvent):
                event_type = "part_end"
            else:
                event_type = type(event).__name__
            _fire_stream_event(event_type, event)
        return

    # NOTE: TTFT / gen-speed timing is now handled by callback hooks
    # registered in ``messaging.spinner._stream_stats_hooks`` (agent_run_start +
    # stream_event + agent_run_end). This handler stays focused on rendering.

    from termflow import Parser as TermflowParser
    from termflow import Renderer as TermflowRenderer
    from termflow.render.style import RenderFeatures

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
    tool_args_buffer: dict[int, str] = {}  # Accumulate raw tool-call args JSON
    did_stream_anything = False  # Track if we streamed any content
    is_high_mode = get_output_level() == "high"

    # Termflow streaming state for text parts
    termflow_parsers: dict[int, TermflowParser] = {}
    termflow_renderers: dict[int, TermflowRenderer] = {}
    termflow_line_buffers: dict[int, str] = {}  # Buffer incomplete lines
    # Optional smooth (typewriter) writers wrapping the console for text parts.
    termflow_writers: dict[int, SmoothTermflowWriter] = {}

    def _make_text_renderer(index: int) -> TermflowRenderer:
        """Build a termflow renderer, optionally typed out smoothly."""
        writer = make_smooth_termflow_writer(console.file)
        if writer is not None:
            writer.start()
            termflow_writers[index] = writer
            output = writer
        else:
            output = console.file
        return TermflowRenderer(
            output=output,
            width=console.width,
            features=RenderFeatures(clipboard=False),
        )

    # Smooth-stream state for thinking parts. Each index maps to a smoother
    # (steady-rate drain) or lands in ``thinking_direct`` when smoothing is
    # disabled and we should print deltas immediately.
    thinking_smoothers: dict[int, ThinkingStreamSmoother] = {}
    thinking_direct: set[int] = set()

    def _emit_thinking(index: int, text: str) -> None:
        """Render thinking text, smoothed via a per-part buffer when enabled."""
        if not text:
            return
        smoother = thinking_smoothers.get(index)
        if smoother is None and index not in thinking_direct:
            smoother = make_thinking_smoother(console)
            if smoother is not None:
                smoother.start()
                thinking_smoothers[index] = smoother
            else:
                thinking_direct.add(index)
        if smoother is not None:
            smoother.feed(text)
        else:
            console.print(f"[dim]{escape(text)}[/dim]", end="")

    async def _print_thinking_banner() -> None:
        """Print the THINKING banner with spinner pause and line clear."""
        nonlocal did_stream_anything

        pause_all_spinners()
        await asyncio.sleep(0.1)  # Delay to let spinner fully clear
        # Clear line and print newline before banner
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
        nonlocal did_stream_anything

        pause_all_spinners()
        await asyncio.sleep(0.1)  # Delay to let spinner fully clear
        # Clear line and print newline before banner
        console.print(" " * 50, end="\r")
        console.print()  # Newline before banner
        response_color = get_banner_color("agent_response")
        console.print(
            Text.from_markup(
                f"[bold white on {response_color}] AGENT RESPONSE [/bold white on {response_color}]"
            )
        )
        did_stream_anything = True

    def _abort_all_drainers() -> None:
        """Kill every drain task and drop buffers — the user said STOP."""
        for smoother in thinking_smoothers.values():
            smoother.abort()
        thinking_smoothers.clear()
        for writer in termflow_writers.values():
            writer.abort()
        termflow_writers.clear()

    try:
        async for event in events:
            # ---- Pause gate ------------------------------------------------
            # If the user has paused the agent, suppress rendering and block
            # at this safe boundary until resume (or until the safety timeout
            # expires, to avoid SSE upstream timeouts).
            from code_puppy.messaging.pause_controller import get_pause_controller

            _pc = get_pause_controller()
            if _pc.is_paused():
                # Hide the spinner while paused so nothing animates.
                pause_all_spinners()
                # Read max pause from config lazily (avoid module-load coupling).
                from code_puppy.config import get_value

                try:
                    max_pause = float(get_value("max_pause_seconds") or 180.0)
                except (TypeError, ValueError):
                    max_pause = 180.0
                resumed = await _pc.wait_if_paused(timeout=max_pause)
                if not resumed:
                    from code_puppy.messaging import emit_warning

                    emit_warning(
                        f"⏸️  Pause exceeded {max_pause:.0f}s; auto-resuming to "
                        "avoid upstream timeout."
                    )

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
                    # (unless thinking is suppressed by output level or toggle).
                    if part.content and part.content.strip():
                        if not _suppress_thinking_stream():
                            await _print_thinking_banner()
                            _emit_thinking(event.index, part.content)
                        banner_printed.add(event.index)
                elif isinstance(part, TextPart):
                    streaming_parts.add(event.index)
                    text_parts.add(event.index)
                    # Initialize termflow streaming for this text part
                    termflow_parsers[event.index] = TermflowParser()
                    termflow_renderers[event.index] = _make_text_renderer(event.index)
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
                    tool_args_buffer[event.index] = ""  # Accumulate JSON args
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
                                termflow_line_buffers[event.index] += (
                                    delta.content_delta
                                )

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
                                # For thinking parts, stream smoothly (dim) via a
                                # rate-limited buffer so bursty deltas don't stutter.
                                # Gate on output level / suppress_thinking toggle.
                                if not _suppress_thinking_stream():
                                    if event.index not in banner_printed:
                                        await _print_thinking_banner()
                                        banner_printed.add(event.index)
                                    _emit_thinking(event.index, delta.content_delta)
                    elif isinstance(delta, ToolCallPartDelta):
                        # For tool calls, estimate tokens from args_delta content
                        # args_delta contains the streaming JSON arguments
                        args_delta = getattr(delta, "args_delta", "") or ""
                        if args_delta:
                            # Same 2.5 chars/token heuristic as BaseAgent and file_operations
                            estimated_tokens = max(1, math.floor(len(args_delta) / 2.5))
                            token_count[event.index] += estimated_tokens
                            # Accumulate raw args JSON for high-mode display.
                            tool_args_buffer[event.index] = (
                                tool_args_buffer.get(event.index, "") + args_delta
                            )
                        else:
                            # Even empty deltas count as activity
                            token_count[event.index] += 1

                        # Update tool name if delta provides more of it
                        tool_name_delta = getattr(delta, "tool_name_delta", "") or ""
                        if tool_name_delta:
                            tool_names[event.index] = (
                                tool_names.get(event.index, "") + tool_name_delta
                            )

                        # Use stored tool name for display.
                        # In low mode, skip the progress counter — the
                        # RichConsoleRenderer peek is sufficient.
                        if not _suppress_tool_progress():
                            tool_name = tool_names.get(event.index, "")
                            count = token_count[event.index]
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

                        # Drain any smooth typewriter writer to completion so the
                        # full response has finished printing before we move on.
                        writer = termflow_writers.pop(event.index, None)
                        if writer is not None:
                            await writer.close()
                    # For tool parts, clear the chunk counter line
                    elif event.index in tool_parts:
                        # Clear the chunk counter line by printing spaces and returning
                        console.print(" " * 50, end="\r")
                        # In high mode, dump the full tool call arguments so the
                        # user can see exactly what the model sent to the tool.
                        if is_high_mode:
                            tool_name = tool_names.get(event.index, "tool")
                            raw_args = tool_args_buffer.get(event.index, "")
                            if raw_args:
                                # Pretty-print the JSON if possible.
                                import json as _json

                                try:
                                    parsed = _json.loads(raw_args)
                                    formatted = _json.dumps(
                                        parsed, indent=2, ensure_ascii=False
                                    )
                                except (ValueError, TypeError):
                                    formatted = raw_args
                                console.print(
                                    f"[dim]  tool_call {escape(tool_name)} args:[/dim]"
                                )
                                for arg_line in formatted.splitlines():
                                    console.print(f"[dim]    {escape(arg_line)}[/dim]")
                    # For thinking parts, drain the smoother then print newline
                    elif event.index in thinking_parts:
                        smoother = thinking_smoothers.pop(event.index, None)
                        if smoother is not None:
                            await smoother.close()
                        thinking_direct.discard(event.index)
                        if event.index in banner_printed:
                            console.print()  # Final newline after streaming

                    # Clean up token count and tool names
                    token_count.pop(event.index, None)
                    tool_names.pop(event.index, None)
                    tool_args_buffer.pop(event.index, None)
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
    except BaseException:
        # Cancelled (Ctrl+C / steer) or crashed mid-stream: the graceful
        # drain below would never run, orphaning the background drain
        # tasks — which then keep typing into the terminal. Abort them.
        _abort_all_drainers()
        raise

    # Spinner is resumed in PartEndEvent when appropriate (based on next_part_kind)

    # Drain any smoothers/writers that didn't see a PartEndEvent (e.g. the
    # stream ended abruptly) so we never lose buffered text or orphan tasks.
    for smoother in list(thinking_smoothers.values()):
        await smoother.close()
    thinking_smoothers.clear()
    for writer in list(termflow_writers.values()):
        await writer.close()
    termflow_writers.clear()
