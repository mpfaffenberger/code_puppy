from __future__ import annotations

from types import SimpleNamespace

import pytest

from code_puppy.api.ws.chat_tool_lifecycle import (
    accumulate_tool_call_part_delta,
    finish_tool_call_part,
    handle_tool_call_complete_event,
    handle_tool_call_start_event,
    resolve_pending_tool_id,
    resolve_tool_group_id,
    send_status_only_pending_tool_results,
    start_tool_call_part,
    start_tool_return_part,
)
from code_puppy.api.ws.chat_turn_state import WebSocketTurnState


class _Logger:
    def __init__(self):
        self.debug_messages = []
        self.info_messages = []
        self.warning_messages = []

    def debug(self, message, *args):
        self.debug_messages.append((message, args))

    def info(self, message, *args):
        self.info_messages.append((message, args))

    def warning(self, message, *args):
        self.warning_messages.append((message, args))


@pytest.mark.asyncio
async def test_handle_tool_call_start_event_tracks_pending_and_emits_call():
    turn_state = WebSocketTurnState()
    sent = []

    async def _send(model):
        sent.append(model)

    await handle_tool_call_start_event(
        turn_state=turn_state,
        event_data={"tool_name": "shell", "tool_args": {"cmd": "pwd"}},
        session_id="session-1",
        agent_name="agent-1",
        model_name="model-1",
        send_typed_tool_lifecycle=_send,
        logger=_Logger(),
    )

    assert len(sent) == 1
    assert sent[0].tool_name == "shell"
    assert sent[0].tool_group_id.startswith("tg-")
    assert turn_state.current_tool_name == "shell"
    assert list(turn_state.pending_tool_calls.values())[0]["tool_name"] == "shell"


@pytest.mark.asyncio
async def test_handle_tool_call_complete_event_reuses_pending_group_id():
    turn_state = WebSocketTurnState(
        pending_tool_calls={
            "tool-1": {"tool_name": "shell", "tool_group_id": "tg-abc"}
        },
        current_tool_name="shell",
        current_tool_group_id="tg-abc",
    )
    sent = []

    async def _send(model):
        sent.append(model)

    await handle_tool_call_complete_event(
        turn_state=turn_state,
        event_data={"tool_name": "shell", "result": {"ok": True}, "duration_ms": 12},
        session_id="session-2",
        agent_name="agent-2",
        model_name="model-2",
        send_typed_tool_lifecycle=_send,
        logger=_Logger(),
    )

    assert len(sent) == 1
    assert sent[0].tool_id == "tool-1"
    assert sent[0].tool_group_id == "tg-abc"
    assert turn_state.pending_tool_calls == {}
    assert turn_state.current_tool_name is None


@pytest.mark.asyncio
async def test_tool_call_part_start_delta_end_round_trip_emits_tool_call():
    turn_state = WebSocketTurnState()
    sent = []
    logger = _Logger()

    async def _send(model):
        sent.append(model)

    handled = start_tool_call_part(
        turn_state=turn_state,
        part_index=3,
        part_obj=SimpleNamespace(tool_name="calc", tool_call_id="raw-1", args='{"a":'),
        logger=logger,
    )
    assert handled is True

    assert (
        accumulate_tool_call_part_delta(
            turn_state=turn_state,
            part_index=3,
            delta_obj={"args_delta": "1}"},
        )
        is True
    )

    await finish_tool_call_part(
        turn_state=turn_state,
        part_index=3,
        part_info=turn_state.active_parts[3],
        session_id="session-3",
        agent_name="agent-3",
        model_name="model-3",
        send_typed_tool_lifecycle=_send,
        logger=logger,
    )

    assert len(sent) == 1
    assert sent[0].tool_name == "calc"
    assert sent[0].args == {"a": 1}
    assert turn_state.pending_tool_calls[sent[0].tool_id]["raw_tool_call_id"] == "raw-1"
    assert turn_state.tool_group_ids[sent[0].tool_id] == sent[0].tool_group_id
    assert 3 not in turn_state.active_parts


@pytest.mark.asyncio
async def test_start_tool_return_part_matches_pending_by_raw_tool_call_id():
    turn_state = WebSocketTurnState(
        pending_tool_calls={
            "tool-1": {
                "tool_name": "calc",
                "start_time": 0.0,
                "part_index": 5,
                "raw_tool_call_id": "raw-1",
                "tool_group_id": "tg-xyz",
            }
        },
        current_tool_group_id="tg-xyz",
    )
    sent = []

    async def _send(model):
        sent.append(model)

    await start_tool_return_part(
        turn_state=turn_state,
        part_index=6,
        part_obj={"tool_call_id": "raw-1", "content": {"answer": 42}},
        session_id="session-4",
        agent_name="agent-4",
        model_name="model-4",
        send_typed_tool_lifecycle=_send,
        logger=_Logger(),
    )

    assert len(sent) == 1
    assert sent[0].tool_id == "tool-1"
    assert sent[0].tool_group_id == "tg-xyz"
    assert turn_state.pending_tool_calls["tool-1"]["result"] == {"answer": 42}


@pytest.mark.asyncio
async def test_send_status_only_pending_tool_results_marks_sent():
    turn_state = WebSocketTurnState(
        pending_tool_calls={
            "tool-1": {
                "tool_name": "shell",
                "start_time": 0.0,
                "tool_group_id": "tg-shell",
                "status_only_sent": False,
            }
        },
        current_tool_group_id="tg-shell",
    )
    sent = []

    async def _send(model):
        sent.append(model)

    await send_status_only_pending_tool_results(
        turn_state=turn_state,
        session_id="session-5",
        agent_name="agent-5",
        model_name="model-5",
        send_typed=_send,
        logger=_Logger(),
    )

    assert len(sent) == 1
    assert sent[0].tool_group_id == "tg-shell"
    assert sent[0].result["_pending_full_result"] is True
    assert turn_state.pending_tool_calls["tool-1"]["status_only_sent"] is True


def test_resolve_pending_tool_id_and_group_id_fallbacks():
    logger = _Logger()
    turn_state = WebSocketTurnState(
        pending_tool_calls={
            "tool-1": {"tool_name": "shell", "raw_tool_call_id": "raw-1"}
        }
    )

    assert (
        resolve_pending_tool_id(turn_state=turn_state, tool_call_id="raw-1") == "tool-1"
    )
    assert resolve_pending_tool_id(turn_state=turn_state, tool_name="shell") == "tool-1"

    group_id = resolve_tool_group_id(
        turn_state=turn_state,
        logger=logger,
        tool_id="tool-1",
        pending_info=turn_state.pending_tool_calls["tool-1"],
        tool_name="shell",
        source="test",
    )

    assert group_id.startswith("tg-")
    assert turn_state.tool_group_ids["tool-1"] == group_id
    assert turn_state.pending_tool_calls["tool-1"]["tool_group_id"] == group_id
