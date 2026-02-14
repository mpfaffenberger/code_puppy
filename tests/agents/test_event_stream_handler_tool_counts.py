"""Focused tests for tool-call token counter behavior in event_stream_handler."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai import PartDeltaEvent, PartEndEvent, PartStartEvent, RunContext
from pydantic_ai.messages import ToolCallPart, ToolCallPartDelta
from rich.console import Console

from code_puppy.agents.event_stream_handler import (
    event_stream_handler,
    set_streaming_console,
)


async def _tool_call_stream(args_deltas: list[str]):
    """Yield a tool call start, a sequence of deltas, and an end event."""
    tool_part = ToolCallPart(tool_call_id="tool_1", tool_name="my_tool", args={})
    yield PartStartEvent(index=0, part=tool_part)

    for args_delta in args_deltas:
        yield PartDeltaEvent(
            index=0,
            delta=ToolCallPartDelta(args_delta=args_delta),
        )

    yield PartEndEvent(index=0, part=tool_part, next_part_kind=None)


def _counter_lines(console_mock: MagicMock) -> list[str]:
    """Extract tool counter display lines."""
    lines: list[str] = []
    for call in console_mock.print.call_args_list:
        if call.args:
            rendered = str(call.args[0])
            if "Calling" in rendered:
                lines.append(rendered)
    return lines


@pytest.mark.asyncio
async def test_claude_code_shows_cumulative_char_count():
    """Claude Code models should show cumulative arg character length."""
    mock_ctx = MagicMock(spec=RunContext)
    console = MagicMock(spec=Console)
    set_streaming_console(console)

    # Two deltas: 4 chars + 8 chars = 12 total chars
    stream = _tool_call_stream(args_deltas=["abcd", "abcdefgh"])

    with patch(
        "code_puppy.agents.event_stream_handler.get_global_model_name",
        return_value="claude-code-claude-sonnet-4-5",
    ):
        with patch("code_puppy.agents.event_stream_handler.pause_all_spinners"):
            with patch("code_puppy.agents.event_stream_handler.resume_all_spinners"):
                await event_stream_handler(mock_ctx, stream)

    lines = _counter_lines(console)
    # Should display char(s), not token(s)
    assert any("char(s)" in line for line in lines)
    # Final line should show 12 chars (4 + 8)
    assert any("12 char(s)" in line for line in lines)


@pytest.mark.asyncio
async def test_claude_code_counts_empty_deltas_too():
    """Claude Code should still increment on empty args_delta (len 0 adds 0, counter still updates)."""
    mock_ctx = MagicMock(spec=RunContext)
    console = MagicMock(spec=Console)
    set_streaming_console(console)

    # Mix of empty and non-empty deltas
    stream = _tool_call_stream(args_deltas=["", "abcd", "", "ef"])

    with patch(
        "code_puppy.agents.event_stream_handler.get_global_model_name",
        return_value="claude-code-claude-sonnet-4-5",
    ):
        with patch("code_puppy.agents.event_stream_handler.pause_all_spinners"):
            with patch("code_puppy.agents.event_stream_handler.resume_all_spinners"):
                await event_stream_handler(mock_ctx, stream)

    lines = _counter_lines(console)
    # Should show 6 total chars (0 + 4 + 0 + 2)
    assert any("6 char(s)" in line for line in lines)


@pytest.mark.asyncio
async def test_non_claude_models_keep_additive_token_counting():
    """Non-Claude models keep additive delta token counting."""
    mock_ctx = MagicMock(spec=RunContext)
    console = MagicMock(spec=Console)
    set_streaming_console(console)

    stream = _tool_call_stream(args_deltas=["abcd", "abcdefgh"])

    with patch(
        "code_puppy.agents.event_stream_handler.get_global_model_name",
        return_value="openai:gpt-5",
    ):
        with patch("code_puppy.agents.event_stream_handler.pause_all_spinners"):
            with patch("code_puppy.agents.event_stream_handler.resume_all_spinners"):
                await event_stream_handler(mock_ctx, stream)

    lines = _counter_lines(console)
    # Should display token(s), not char(s)
    assert any("token(s)" in line for line in lines)
    # 4 chars -> 1 token, 8 chars -> 2 tokens, total additive = 3
    assert any("3 token(s)" in line for line in lines)
