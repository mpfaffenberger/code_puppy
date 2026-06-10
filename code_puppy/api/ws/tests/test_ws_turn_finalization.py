from __future__ import annotations

from dataclasses import dataclass

import pytest

from code_puppy.api.ws.chat_turn_state import WebSocketTurnState
from code_puppy.api.ws.ws_turn_finalization import (
    emit_pre_stream_end_tool_results,
    finalize_turn_history,
)


class _Logger:
    def __init__(self):
        self.debug_messages = []
        self.info_messages = []
        self.warning_messages = []

    def debug(self, message, *args):
        self.debug_messages.append(message % args if args else message)

    def info(self, message, *args):
        self.info_messages.append(message % args if args else message)

    def warning(self, message, *args):
        self.warning_messages.append(message % args if args else message)


class _Agent:
    def __init__(self):
        self._history = []

    def set_message_history(self, history):
        self._history = list(history)

    def get_message_history(self):
        return list(self._history)


@dataclass
class _ToolReturnLike:
    tool_name: str
    tool_call_id: str | None
    content: object


@dataclass
class _Message:
    parts: list[object]


class _Result:
    def __init__(self, messages):
        self._messages = list(messages)

    def all_messages(self):
        return list(self._messages)


@pytest.fixture(autouse=True)
def _patch_tool_return_types(monkeypatch):
    import code_puppy.api.ws.ws_turn_finalization as module

    monkeypatch.setitem(
        __import__("sys").modules,
        "pydantic_ai.messages",
        type(
            "M",
            (),
            {
                "ToolReturn": _ToolReturnLike,
                "ToolReturnPart": _ToolReturnLike,
            },
        )(),
    )
    return module


@pytest.mark.asyncio
async def test_emit_pre_stream_end_tool_results_uses_alias_and_group_id():
    turn_state = WebSocketTurnState(
        tool_id_aliases={"raw-1": "tool-1"},
        tool_group_ids={"tool-1": "tg-1"},
    )
    sent = []

    async def _send(model):
        sent.append(model)

    result = _Result([_Message(parts=[_ToolReturnLike("calc", "raw-1", {"x": 1})])])

    pre_sent = await emit_pre_stream_end_tool_results(
        result=result,
        turn_state=turn_state,
        session_id="s1",
        agent_name="agent",
        model_name="model",
        send_typed_tool_lifecycle=_send,
        logger=_Logger(),
    )

    assert pre_sent == {"tool-1"}
    assert len(sent) == 1
    assert sent[0].tool_id == "tool-1"
    assert sent[0].tool_group_id == "tg-1"
    assert sent[0].result == {"x": 1}


@pytest.mark.asyncio
async def test_finalize_turn_history_snapshots_history_before_awaits():
    turn_state = WebSocketTurnState(tool_group_ids={})
    agent = _Agent()
    sent = []

    async def _send(model):
        sent.append(model)

    messages = [_Message(parts=[]), _Message(parts=[])]
    finalized = await finalize_turn_history(
        result=_Result(messages),
        agent=agent,
        turn_state=turn_state,
        session_id="s2",
        agent_name="agent",
        model_name="model",
        send_typed=_send,
        pre_sent_tool_ids=set(),
        logger=_Logger(),
    )

    assert finalized.history_snapshot == messages
    assert agent.get_message_history() == messages
    assert sent == []


@pytest.mark.asyncio
async def test_finalize_turn_history_skips_pre_sent_duplicates():
    turn_state = WebSocketTurnState(tool_group_ids={"tool-9": "tg-9"})
    agent = _Agent()
    sent = []

    async def _send(model):
        sent.append(model)

    result = _Result(
        [_Message(parts=[_ToolReturnLike("shell", "tool-9", {"ok": True})])]
    )
    finalized = await finalize_turn_history(
        result=result,
        agent=agent,
        turn_state=turn_state,
        session_id="s3",
        agent_name="agent",
        model_name="model",
        send_typed=_send,
        pre_sent_tool_ids={"tool-9"},
        logger=_Logger(),
    )

    assert finalized.pre_sent_tool_ids == {"tool-9"}
    assert sent == []


@pytest.mark.asyncio
async def test_finalize_turn_history_emits_remaining_tool_results_and_serializes():
    class _Complex:
        def __init__(self):
            self.answer = 42

    turn_state = WebSocketTurnState(tool_group_ids={"tool-2": "tg-2"})
    agent = _Agent()
    sent = []

    async def _send(model):
        sent.append(model)

    result = _Result([_Message(parts=[_ToolReturnLike("calc", "tool-2", _Complex())])])
    finalized = await finalize_turn_history(
        result=result,
        agent=agent,
        turn_state=turn_state,
        session_id="s4",
        agent_name="agent",
        model_name="model",
        send_typed=_send,
        pre_sent_tool_ids=set(),
        logger=_Logger(),
    )

    assert finalized.history_snapshot
    assert len(sent) == 1
    assert sent[0].tool_id == "tool-2"
    assert sent[0].tool_group_id == "tg-2"
    assert sent[0].result == {"answer": 42}
