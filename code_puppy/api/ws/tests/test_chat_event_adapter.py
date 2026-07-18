from __future__ import annotations

from types import SimpleNamespace

import pytest

from code_puppy.api.ws.chat_event_adapter import (
    collect_final_stream_text_delta,
    handle_assistant_part_delta,
    handle_assistant_part_end,
    handle_assistant_part_start,
)
from code_puppy.api.ws.chat_turn_state import WebSocketTurnState


class _Logger:
    def __init__(self):
        self.debug_messages: list[tuple[str, tuple[object, ...]]] = []

    def debug(self, message, *args):
        self.debug_messages.append((message, args))


@pytest.mark.asyncio
async def test_handle_assistant_part_start_sends_start_and_initial_delta():
    turn_state = WebSocketTurnState(current_tool_name="shell")
    payloads = []
    status_calls = []

    async def _safe_send_json(payload):
        payloads.append(payload)

    async def _status_only():
        status_calls.append("called")

    handled = await handle_assistant_part_start(
        turn_state=turn_state,
        part_index=0,
        part_type="TextPart",
        part_obj={"content": "hello"},
        session_id="session-1",
        agent_name="agent-1",
        model_name="model-1",
        safe_send_json=_safe_send_json,
        logger=_Logger(),
        send_status_only_pending_tool_results=_status_only,
    )

    assert handled is True
    assert status_calls == []
    assert len(payloads) == 2
    assert payloads[0]["type"] == "assistant_message_start"
    assert payloads[0]["part_type"] == "text"
    assert payloads[1]["type"] == "assistant_message_delta"
    assert payloads[1]["content"] == "hello"
    assert turn_state.current_tool_group_id is None
    assert turn_state.collected_text == ["hello"]
    assert turn_state.b1_streaming_used is True


@pytest.mark.asyncio
async def test_handle_assistant_part_start_reuses_existing_early_delta_part():
    turn_state = WebSocketTurnState(
        active_parts={2: {"id": "msg-existing", "type": "text", "content": "world"}},
        collected_text=["world"],
    )
    payloads = []

    async def _safe_send_json(payload):
        payloads.append(payload)

    handled = await handle_assistant_part_start(
        turn_state=turn_state,
        part_index=2,
        part_type="ThinkingPart",
        part_obj=SimpleNamespace(content="hello "),
        session_id="session-2",
        agent_name="agent-2",
        model_name="model-2",
        safe_send_json=_safe_send_json,
        logger=_Logger(),
    )

    assert handled is True
    assert payloads == []
    assert turn_state.active_parts[2]["id"] == "msg-existing"
    assert turn_state.active_parts[2]["type"] == "thinking"
    assert turn_state.active_parts[2]["content"] == "hello world"
    assert turn_state.collected_text[0] == "hello "


@pytest.mark.asyncio
async def test_handle_assistant_part_delta_creates_missing_part_then_sends_delta():
    turn_state = WebSocketTurnState(current_tool_name="calculator")
    payloads = []

    async def _safe_send_json(payload):
        payloads.append(payload)

    handled = await handle_assistant_part_delta(
        turn_state=turn_state,
        part_index=0,
        inner_data={"content_delta": "abc"},
        delta_obj={},
        session_id="session-3",
        agent_name="agent-3",
        model_name="model-3",
        safe_send_json=_safe_send_json,
        logger=_Logger(),
    )

    assert handled is True
    assert [p["type"] for p in payloads] == [
        "assistant_message_start",
        "assistant_message_delta",
    ]
    assert payloads[1]["content"] == "abc"
    assert turn_state.active_parts[0]["content"] == "abc"
    assert turn_state.collected_text == ["abc"]
    assert turn_state.b1_streaming_used is True
    assert turn_state.current_tool_group_id is None


@pytest.mark.asyncio
async def test_handle_assistant_part_end_sends_end_and_cleans_up():
    turn_state = WebSocketTurnState(
        active_parts={1: {"id": "msg-1", "type": "text", "content": "done"}}
    )
    payloads = []

    async def _safe_send_json(payload):
        payloads.append(payload)

    handled = await handle_assistant_part_end(
        turn_state=turn_state,
        part_index=1,
        session_id="session-4",
        agent_name="agent-4",
        model_name="model-4",
        safe_send_json=_safe_send_json,
    )

    assert handled is True
    assert payloads[0]["type"] == "assistant_message_end"
    assert payloads[0]["full_content"] == "done"
    assert 1 not in turn_state.active_parts


def test_collect_final_stream_text_delta_appends_nested_content_delta():
    turn_state = WebSocketTurnState()

    handled = collect_final_stream_text_delta(
        turn_state=turn_state,
        event={
            "type": "stream_event",
            "data": {
                "event_type": "part_delta",
                "event_data": {"delta": {"content_delta": "tail"}},
            },
        },
    )

    assert handled is True
    assert turn_state.collected_text == ["tail"]
