"""Live counts cover all output parts and do not depend on chunk boundaries."""

import importlib
import io
from unittest.mock import Mock

import pytest
from rich.console import Console

from pydantic_ai import PartDeltaEvent, PartEndEvent, PartStartEvent
from pydantic_ai.messages import (
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ToolCallPart,
    ToolCallPartDelta,
)

from code_puppy.agents.stream_status import (
    StreamStatus,
    finish_stream_status,
    get_stream_status,
)


def test_counts_accumulate_across_parts_and_activity_changes():
    bar = Mock()
    status = StreamStatus(bar)
    thought = ThinkingPart(content="12345")
    status.update(PartStartEvent(index=0, part=thought))
    bar.set_tool_progress.assert_called_with("Streamed ~2 tokens | Thinking")
    status.update(PartEndEvent(index=0, part=thought))
    status.update(PartStartEvent(index=1, part=TextPart(content="12345")))
    bar.set_tool_progress.assert_called_with("Streamed ~4 tokens | Writing Response")
    status.update(
        PartStartEvent(index=2, part=ToolCallPart(tool_name="read_", args=""))
    )
    status.update(
        PartDeltaEvent(
            index=2, delta=ToolCallPartDelta(tool_name_delta="file", args_delta="12345")
        )
    )
    bar.set_tool_progress.assert_called_with("Streamed ~6 tokens | Calling read_file")
    assert StreamStatus(bar).characters == 0


def test_small_chunks_do_not_inflate_estimate():
    bar = Mock()
    status = StreamStatus(bar)
    status.update(PartStartEvent(index=0, part=TextPart(content="")))
    for char in "1234567890":
        status.update(PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=char)))
    bar.set_tool_progress.assert_called_with("Streamed ~4 tokens | Writing Response")


def test_total_persists_across_requests_and_resets_only_for_new_run():
    bar = Mock()
    first = get_stream_status(bar, reset=True)
    bar.set_tool_progress.assert_called_with("Streamed ~0 tokens | Working")
    first.update(PartStartEvent(index=0, part=ThinkingPart(content="12345")))
    second = get_stream_status(bar)
    assert second is first
    second.update(PartStartEvent(index=0, part=TextPart(content="12345")))
    bar.set_tool_progress.assert_called_with("Streamed ~4 tokens | Writing Response")
    finish_stream_status(bar)
    bar.set_tool_progress.assert_called_with("Streamed ~4 tokens | Idle")
    fresh = get_stream_status(bar, reset=True)
    assert fresh.characters == 0
    bar.set_tool_progress.assert_called_with("Streamed ~0 tokens | Working")


@pytest.mark.asyncio
async def test_handler_keeps_total_during_thinking_and_response(monkeypatch):
    handler = importlib.import_module("code_puppy.agents.event_stream_handler")
    bar = Mock()
    monkeypatch.setattr("code_puppy.messaging.bottom_bar.get_bottom_bar", lambda: bar)
    monkeypatch.setattr(
        handler, "get_streaming_console", lambda: Console(file=io.StringIO())
    )
    monkeypatch.setattr(handler, "_should_suppress_output", lambda: False)
    monkeypatch.setattr(handler, "_suppress_thinking_stream", lambda: True)
    monkeypatch.setattr(handler, "is_subagent", lambda: False)
    monkeypatch.setattr(handler, "_fire_stream_event", lambda *args: None)

    async def events(part):
        yield PartStartEvent(index=0, part=part)
        yield PartEndEvent(index=0, part=part)

    await handler.event_stream_handler(None, events(ThinkingPart(content="12345")))
    bar.set_tool_progress.assert_any_call("Streamed ~2 tokens | Thinking")
    bar.set_tool_progress.assert_called_with("Streamed ~2 tokens | Working")
    await handler.event_stream_handler(None, events(TextPart(content="12345")))
    bar.set_tool_progress.assert_any_call("Streamed ~4 tokens | Writing Response")
    bar.set_tool_progress.assert_called_with("Streamed ~4 tokens | Working")
    assert all(call.args[0] for call in bar.set_tool_progress.call_args_list)


def test_tool_end_switches_to_working_without_changing_total():
    bar = Mock()
    status = StreamStatus(bar)
    part = ToolCallPart(tool_name="grep", args="12345")
    status.update(PartStartEvent(index=0, part=part))
    bar.set_tool_progress.assert_called_with("Streamed ~2 tokens | Calling grep")
    status.update(PartEndEvent(index=0, part=part))
    bar.set_tool_progress.assert_called_with("Streamed ~2 tokens | Working")
    assert status.characters == 5


def test_no_bar_is_noop():
    status = StreamStatus(None)
    status.update(PartStartEvent(index=0, part=TextPart(content="ignored")))
    assert status.characters == 0
