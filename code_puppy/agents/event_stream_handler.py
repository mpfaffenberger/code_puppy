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

from code_puppy.agents.smooth_stream import (
    SmoothTermflowWriter,
    make_smooth_termflow_writer,
)
from code_puppy.agents.stream_status import get_stream_status
from code_puppy.agents.thinking_output import DimWriter
from code_puppy.config import (
    get_headless_mode,
    get_output_level,
    get_subagent_verbose,
    get_suppress_thinking_messages,
)
from code_puppy.tools.display import erase_progress_line
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
        coroutine = callbacks.on_stream_event(event_type, event_data, agent_session_id)
        try:
            asyncio.create_task(coroutine)
        except BaseException:
            # Submission failed: no task owns this coroutine. Preserve cancellation.
            coroutine.close()
            raise
    except ImportError:
        logger.debug("callbacks or messaging module not available for stream event")
    except Exception as e:
        logger.debug(f"Error firing stream event callback: {e}")


# Module-level console for streaming output
# Set via set_streaming_console() so every stream shares one console
_streaming_console: Optional[Console] = None


def set_streaming_console(console: Optional[Console]) -> None:
    """Set the console used for streaming output.

    All streams (markdown, thinking, tool token lines) should share one
    console; output scrolls inside the bottom bar's scroll region.

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

    Headless runs (``-p``) always suppress it as well. The counter repaints
    itself with a bare ``\\r``, which only overwrites on a real terminal --
    redirected into a file or CI log every repaint becomes its own line, so
    a single tool call emits a wall of ``Calling <tool>... N token(s)`` rows.
    """
    if get_headless_mode():
        return True
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

    # NOTE: TTFT/gen-speed timing lives in callback hooks (agent_run_start +
    # stream_event + agent_run_end); this handler only renders.

    from termflow import Parser as TermflowParser
    from termflow import Renderer as TermflowRenderer
    from termflow.render.style import RenderFeatures, RenderStyle
    from termflow.syntax import Highlighter

    from code_puppy.callbacks import (
        on_prompt_text_color,
        on_termflow_highlighter,
        on_termflow_style,
    )

    # Use the module-level console (set via set_streaming_console)
    console = get_streaming_console()
    from code_puppy.i18n import t
    from code_puppy.messaging.bottom_bar import get_bottom_bar

    progress_bar = None if is_subagent() else get_bottom_bar()
    stream_status = get_stream_status(progress_bar)

    # Live panel for speculative CodeMode runs (harness#699): renders the
    # streaming run_code snippet with per-launch clocks from the typed
    # code_mode.* capability events, then the hit/miss reveal at finalize.
    from code_puppy.messaging.speculation_panel import get_speculation_panel

    spec_panel = get_speculation_panel()

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

    # Termflow streaming state for text parts
    termflow_parsers: dict[int, TermflowParser] = {}
    termflow_renderers: dict[int, TermflowRenderer] = {}
    termflow_line_buffers: dict[int, str] = {}  # Buffer incomplete lines
    # Optional smooth (typewriter) writers wrapping the console for text parts.
    termflow_writers: dict[int, SmoothTermflowWriter] = {}

    class _ThemedBoldWriter:
        """Keep terminal bold from brightening default text to profile white."""

        def __init__(self, target, color: str) -> None:
            self._target = target
            self._color_sgr = f"\x1b[38;2;{int(color[1:3], 16)};{int(color[3:5], 16)};{int(color[5:7], 16)}m"

        def write(self, text):
            return self._target.write(
                text.replace("\x1b[1m", f"\x1b[1m{self._color_sgr}")
            )

        def flush(self):
            return self._target.flush()

    def _make_text_renderer(index: int) -> TermflowRenderer:
        """Build a termflow renderer, optionally typed out smoothly."""
        thinking = index in thinking_parts
        writer = (
            make_smooth_termflow_writer(console.file, thinking=True)
            if thinking
            else make_smooth_termflow_writer(console.file)
        )
        if writer is not None:
            writer.start()
            termflow_writers[index] = writer
            output = writer
        else:
            output = console.file
        prompt_color = on_prompt_text_color()
        if prompt_color and len(prompt_color) == 7 and prompt_color.startswith("#"):
            output = _ThemedBoldWriter(output, prompt_color)
        width = console.width
        if thinking:
            from code_puppy.messaging.tool_output import format_activity_heading

            heading = format_activity_heading(
                t("stream.activity.thinking"), secondary=True
            )
            width = max(1, width - heading.cell_len - 2)
            output = DimWriter(output)
        return TermflowRenderer(
            output=output,
            width=width,
            style=on_termflow_style(RenderStyle.default()),
            features=RenderFeatures(clipboard=False),
            highlighter=on_termflow_highlighter(Highlighter()),
        )

    def _render_text_content(index: int, content: str) -> None:
        """Feed text through Termflow one complete line at a time."""
        buffer = termflow_line_buffers[index] + content
        parser = termflow_parsers[index]
        renderer = termflow_renderers[index]

        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            renderer.render_all(parser.parse_line(line))

        termflow_line_buffers[index] = buffer

    thinking_stream_id = object()

    def _filter_thinking(index: int, text: str, *, final: bool = False) -> str:
        """Apply synchronous display-only filters before rendering thinking."""
        from code_puppy.callbacks import on_thinking_display_filter

        return on_thinking_display_filter(
            text,
            stream_id=thinking_stream_id,
            part_index=index,
            final=final,
        )

    def _emit_thinking(index: int, text: str, *, final: bool = False) -> None:
        """Filter thinking before sending it through dim Termflow Markdown."""
        text = _filter_thinking(index, text, final=final)
        if not text or _suppress_thinking_stream():
            return
        if index not in termflow_parsers:
            from code_puppy.messaging.tool_output import format_activity_heading

            console.print(
                format_activity_heading(t("stream.activity.thinking"), secondary=True),
                end="  ",
            )
            termflow_parsers[index] = TermflowParser()
            termflow_renderers[index] = _make_text_renderer(index)
            termflow_line_buffers[index] = ""
        _render_text_content(index, text)

    async def _finish_text_part(index: int) -> None:
        """Flush one text part, including streams missing ``PartEndEvent``."""
        parser = termflow_parsers.pop(index, None)
        renderer = termflow_renderers.pop(index, None)
        if parser is not None and renderer is not None:
            remaining = termflow_line_buffers.pop(index, "")
            if remaining.strip():
                renderer.render_all(parser.parse_line(remaining))
            renderer.render_all(parser.finalize())

        writer = termflow_writers.pop(index, None)
        if writer is not None:
            await writer.close()
        console.print()  # Blank line separating the response from what follows

    async def _start_fresh_block(*, thinking: bool = False) -> None:
        """Open a thinking/response block on a clean line (banners are gone)."""
        nonlocal did_stream_anything

        # Thinking follows the previous block's existing trailing spacing.
        erase_progress_line(console)
        if not thinking:
            console.print()
        did_stream_anything = True

    def _abort_all_drainers() -> None:
        """Kill every drain task and drop buffers — the user said STOP."""
        for index in thinking_parts:
            # Finalize callback state but discard any withheld display text:
            # abort means the user explicitly asked output to stop.
            _filter_thinking(index, "", final=True)
        for writer in termflow_writers.values():
            writer.abort()
        termflow_writers.clear()

    try:
        async for event in events:
            # ---- Pause gate ------------------------------------------------
            # Paused: suppress rendering and block at this safe boundary until
            # resume (or the safety timeout, to avoid SSE upstream timeouts).
            from code_puppy.messaging.pause_controller import get_pause_controller

            _pc = get_pause_controller()
            while _pc.is_paused():
                # Read max pause from config lazily (avoid module-load coupling).
                from code_puppy.config import get_value

                try:
                    max_pause = float(get_value("max_pause_seconds") or 180.0)
                except (TypeError, ValueError):
                    max_pause = 180.0
                resumed = await _pc.wait_if_paused(timeout=max_pause)
                if resumed:
                    break
                # Timed out (controller force-resumed). If a /command window
                # still owns the pause lease, re-arm and keep waiting: streaming
                # must not interleave under it; the drain's ``finally``
                # guarantees the ultimate resume.
                from code_puppy.messaging.run_ui import is_draining

                if is_draining():
                    _pc.pause()
                    continue
                from code_puppy.messaging import emit_warning

                emit_warning(
                    f"⏸  Pause exceeded {max_pause:.0f}s; auto-resuming to "
                    "avoid upstream timeout."
                )
                break

            stream_status.update(event)
            # ---- Speculative CodeMode panel (harness#699) -------------------
            # The typed code_mode.* capability events own their own terminal
            # region; everything else falls through to the normal renderer.
            if spec_panel.handle_event(event, console):
                did_stream_anything = True
                continue

            # PartStartEvent - register the part but defer banner until content arrives
            if isinstance(event, PartStartEvent):
                # A new part closes out any speculation cycle whose outcome
                # events have already flushed.
                spec_panel.finalize()
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
                            await _start_fresh_block(thinking=True)
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
                        await _start_fresh_block()
                        banner_printed.add(event.index)
                        _render_text_content(event.index, part.content)
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
                                    await _start_fresh_block()
                                    banner_printed.add(event.index)

                                _render_text_content(event.index, delta.content_delta)
                            else:
                                # Stream thinking parts smoothly (dim) via a
                                # rate-limited buffer; gate on output level /
                                # suppress_thinking toggle.
                                if not _suppress_thinking_stream():
                                    if event.index not in banner_printed:
                                        await _start_fresh_block(thinking=True)
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

            # PartEndEvent - finish the streaming with a newline
            elif isinstance(event, PartEndEvent):
                # Speculation cycle: args finished streaming, execution begins;
                # the live region yields the console until the final reveal.
                spec_panel.on_part_end()
                # Fire stream event callback for part_end
                _fire_stream_event(
                    "part_end",
                    {
                        "index": event.index,
                        "next_part_kind": getattr(event, "next_part_kind", None),
                    },
                )

                if event.index in streaming_parts:
                    if event.index in text_parts:
                        await _finish_text_part(event.index)
                    # Finish Markdown and drain before the next tool/response.
                    elif event.index in thinking_parts:
                        _emit_thinking(event.index, "", final=True)
                        if event.index in termflow_parsers:
                            await _finish_text_part(event.index)

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

    except BaseException:
        # Cancelled/crashed mid-stream: the graceful drain never runs, orphaning
        # background drain tasks that keep typing into the terminal. Abort them.
        # The speculation panel's live region would keep repainting too.
        spec_panel.finalize()
        _abort_all_drainers()
        raise

    # Providers can end without PartEndEvent. Finalize those parsers too;
    # otherwise an unterminated fence or partial line disappears.
    for index in list(text_parts):
        await _finish_text_part(index)

    # Drain any smoothers/writers that didn't see a PartEndEvent (e.g. the
    # stream ended abruptly) so we never lose buffered text or orphan tasks.
    for index in list(thinking_parts):
        _emit_thinking(index, "", final=True)
        if index in termflow_parsers:
            await _finish_text_part(index)
    for writer in list(termflow_writers.values()):
        await writer.close()
    termflow_writers.clear()
    # Outcome events arrive in a later handler invocation (tool execution runs
    # between streams), so stream end only closes cycles cut mid-part; an
    # executing cycle survives the gap and reveals on the next part start.
    spec_panel.on_stream_end()
    stream_status.working()
