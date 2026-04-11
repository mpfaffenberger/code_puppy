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
    try:
        from code_puppy import callbacks
        from code_puppy.messaging import get_session_context

        agent_session_id = get_session_context()
        asyncio.create_task(
            callbacks.on_stream_event(event_type, event_data, agent_session_id)
        )
    except ImportError:
        logger.debug("callbacks or messaging module not available for stream event")
    except Exception as e:
        logger.debug(f"Error firing stream event callback: {e}")


_streaming_console: Optional[Console] = None
_active_foreground_stream_token: Optional[int] = None
_next_foreground_stream_token = 0


def set_streaming_console(console: Optional[Console]) -> None:
    global _streaming_console
    _streaming_console = console


def get_streaming_console() -> Console:
    if _streaming_console is not None:
        return _streaming_console
    return Console()


def start_foreground_stream() -> int:
    global _active_foreground_stream_token, _next_foreground_stream_token
    _next_foreground_stream_token += 1
    _active_foreground_stream_token = _next_foreground_stream_token
    return _active_foreground_stream_token


def clear_foreground_stream(token: Optional[int] = None) -> None:
    global _active_foreground_stream_token
    if token is None or _active_foreground_stream_token == token:
        _active_foreground_stream_token = None


def is_foreground_stream_active(token: Optional[int]) -> bool:
    if _active_foreground_stream_token is None:
        return True
    return token is not None and token == _active_foreground_stream_token


def _should_suppress_output() -> bool:
    return is_subagent() and not get_subagent_verbose()


async def event_stream_handler(ctx: RunContext, events: AsyncIterable[Any]) -> None:
    if _should_suppress_output():
        async for _ in events:
            pass
        return

    from termflow import Parser as TermflowParser
    from termflow import Renderer as TermflowRenderer

    console = get_streaming_console()
    foreground_token = _active_foreground_stream_token

    def _is_active() -> bool:
        return is_foreground_stream_active(foreground_token)

    streaming_parts: set[int] = set()
    thinking_parts: set[int] = set()
    text_parts: set[int] = set()
    tool_parts: set[int] = set()
    banner_printed: set[int] = set()
    token_count: dict[int, int] = {}
    tool_names: dict[int, str] = {}
    termflow_parsers: dict[int, TermflowParser] = {}
    termflow_renderers: dict[int, TermflowRenderer] = {}
    termflow_line_buffers: dict[int, str] = {}

    async def _print_thinking_banner() -> None:
        if not _is_active():
            return
        pause_all_spinners()
        await asyncio.sleep(0.1)
        if not _is_active():
            return
        console.print(" " * 50, end="\r")
        console.print()
        thinking_color = get_banner_color("thinking")
        console.print(
            Text.from_markup(
                f"[bold white on {thinking_color}] THINKING [/bold white on {thinking_color}] [dim]⚡ "
            ),
            end="",
        )

    async def _print_response_banner() -> None:
        if not _is_active():
            return
        pause_all_spinners()
        await asyncio.sleep(0.1)
        if not _is_active():
            return
        console.print(" " * 50, end="\r")
        console.print()
        response_color = get_banner_color("agent_response")
        console.print(
            Text.from_markup(
                f"[bold white on {response_color}] AGENT RESPONSE [/bold white on {response_color}]"
            )
        )

    async for event in events:
        if not _is_active():
            continue

        if isinstance(event, PartStartEvent):
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
                if part.content and part.content.strip():
                    await _print_thinking_banner()
                    console.print(f"[dim]{escape(part.content)}[/dim]", end="")
                    banner_printed.add(event.index)
            elif isinstance(part, TextPart):
                streaming_parts.add(event.index)
                text_parts.add(event.index)
                termflow_parsers[event.index] = TermflowParser()
                termflow_renderers[event.index] = TermflowRenderer(
                    output=console.file, width=console.width
                )
                termflow_line_buffers[event.index] = ""
                if part.content and part.content.strip():
                    await _print_response_banner()
                    banner_printed.add(event.index)
                    termflow_line_buffers[event.index] = part.content
            elif isinstance(part, ToolCallPart):
                streaming_parts.add(event.index)
                tool_parts.add(event.index)
                token_count[event.index] = 0
                tool_names[event.index] = part.tool_name or ""
                banner_printed.add(event.index)

        elif isinstance(event, PartDeltaEvent):
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
                        if event.index in text_parts:
                            if event.index not in banner_printed:
                                await _print_response_banner()
                                banner_printed.add(event.index)
                            termflow_line_buffers[event.index] += delta.content_delta
                            parser = termflow_parsers[event.index]
                            renderer = termflow_renderers[event.index]
                            buffer = termflow_line_buffers[event.index]
                            while "\n" in buffer:
                                line, buffer = buffer.split("\n", 1)
                                renderer.render_all(parser.parse_line(line))
                            termflow_line_buffers[event.index] = buffer
                        else:
                            if event.index not in banner_printed:
                                await _print_thinking_banner()
                                banner_printed.add(event.index)
                            console.print(
                                f"[dim]{escape(delta.content_delta)}[/dim]", end=""
                            )
                elif isinstance(delta, ToolCallPartDelta):
                    args_delta = getattr(delta, "args_delta", "") or ""
                    if args_delta:
                        token_count[event.index] += max(1, len(args_delta) // 4)
                    else:
                        token_count[event.index] += 1
                    tool_name_delta = getattr(delta, "tool_name_delta", "") or ""
                    if tool_name_delta:
                        tool_names[event.index] = (
                            tool_names.get(event.index, "") + tool_name_delta
                        )
                    tool_name = tool_names.get(event.index, "")
                    count = token_count[event.index]
                    if tool_name:
                        console.print(
                            f"  🔧 Calling {tool_name}... {count} token(s)   ", end="\r"
                        )
                    else:
                        console.print(
                            f"  🔧 Calling tool... {count} token(s)   ", end="\r"
                        )

        elif isinstance(event, PartEndEvent):
            _fire_stream_event(
                "part_end",
                {
                    "index": event.index,
                    "next_part_kind": getattr(event, "next_part_kind", None),
                },
            )
            if event.index in streaming_parts:
                if event.index in text_parts:
                    if event.index in termflow_parsers:
                        parser = termflow_parsers[event.index]
                        renderer = termflow_renderers[event.index]
                        remaining = termflow_line_buffers.get(event.index, "")
                        if remaining.strip():
                            renderer.render_all(parser.parse_line(remaining))
                        renderer.render_all(parser.finalize())
                        del termflow_parsers[event.index]
                        del termflow_renderers[event.index]
                        del termflow_line_buffers[event.index]
                elif event.index in tool_parts:
                    console.print(" " * 50, end="\r")
                elif event.index in banner_printed:
                    console.print()

                token_count.pop(event.index, None)
                tool_names.pop(event.index, None)
                streaming_parts.discard(event.index)
                thinking_parts.discard(event.index)
                text_parts.discard(event.index)
                tool_parts.discard(event.index)
                banner_printed.discard(event.index)

                next_kind = getattr(event, "next_part_kind", None)
                if next_kind not in ("text", "thinking", "tool-call"):
                    resume_all_spinners()
