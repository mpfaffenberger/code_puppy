from __future__ import annotations

import asyncio
from contextlib import suppress
from types import SimpleNamespace

import pytest
from fastapi import WebSocketDisconnect

from code_puppy.api.ws.chat_turn_runner import execute_turn_runner
from code_puppy.api.ws.chat_turn_state import WebSocketTurnState


class _FakeWebSocket:
    def __init__(self, messages):
        self._messages = list(messages)

    async def receive_json(self):
        if not self._messages:
            await asyncio.Future()
        next_item = self._messages.pop(0)
        if isinstance(next_item, BaseException):
            raise next_item
        return next_item


class _BlockingAgent:
    def __init__(self, *, on_cancel=None, complete_event=None, result=None):
        self.on_cancel = on_cancel
        self.complete_event = complete_event or asyncio.Event()
        self.result = result

    async def run_with_mcp(self, message_to_send, **run_kwargs):
        try:
            await self.complete_event.wait()
            return self.result
        except asyncio.CancelledError:
            if self.on_cancel is not None:
                self.on_cancel()
            raise


@pytest.mark.asyncio
async def test_execute_turn_runner_processes_permission_response(monkeypatch):
    handled = []
    complete_event = asyncio.Event()
    result = SimpleNamespace(name="result")

    def _handle_permission_response(request_id, approved, session_id=None):
        handled.append((request_id, approved, session_id))
        complete_event.set()
        return True

    monkeypatch.setattr(
        "code_puppy.api.permissions.handle_permission_response",
        _handle_permission_response,
    )

    cleanup_calls = []
    agent = _BlockingAgent(complete_event=complete_event, result=result)
    websocket = _FakeWebSocket(
        [{"type": "permission_response", "request_id": "req-1", "approved": True}]
    )

    outcome = await execute_turn_runner(
        websocket=websocket,
        session_id="session-1",
        ctx=SimpleNamespace(),
        agent=agent,
        agent_name="code-puppy",
        model_name="gpt-test",
        session_title="title",
        session_working_directory="/tmp",
        session_pinned=False,
        message_to_send="hello",
        run_kwargs={},
        turn_state=WebSocketTurnState(),
        clear_session_working_directory=lambda: cleanup_calls.append("cleared"),
    )

    assert handled == [("req-1", True, "session-1")]
    assert outcome.result is result
    assert outcome.deferred_msg is None
    assert cleanup_calls == ["cleared"]


@pytest.mark.asyncio
async def test_execute_turn_runner_cancels_active_agent_on_cancel_message():
    cancel_seen = []
    cleanup_calls = []
    agent = _BlockingAgent(on_cancel=lambda: cancel_seen.append(True))
    websocket = _FakeWebSocket([{"type": "cancel"}])
    turn_state = WebSocketTurnState()

    outcome = await execute_turn_runner(
        websocket=websocket,
        session_id="session-2",
        ctx=SimpleNamespace(),
        agent=agent,
        agent_name="code-puppy",
        model_name="gpt-test",
        session_title="title",
        session_working_directory="/tmp",
        session_pinned=False,
        message_to_send="hello",
        run_kwargs={},
        turn_state=turn_state,
        clear_session_working_directory=lambda: cleanup_calls.append("cleared"),
    )
    await asyncio.sleep(0)

    assert outcome.result is None
    assert outcome.deferred_msg is None
    assert cancel_seen == [True]
    assert cleanup_calls == ["cleared"]


@pytest.mark.asyncio
async def test_execute_turn_runner_defers_switch_and_background_saves(monkeypatch):
    bg_calls = []
    bg_tasks = []
    agent = _BlockingAgent()
    websocket = _FakeWebSocket(
        [{"type": "switch_session", "session_id": "next-session"}]
    )

    async def _fake_background_save(**kwargs):
        bg_calls.append(kwargs)
        task = kwargs.get("agent_task")
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    def _fake_fire_and_track(coro):
        task = asyncio.create_task(coro)
        bg_tasks.append(task)
        return task

    monkeypatch.setattr(
        "code_puppy.api.ws.chat_turn_runner.save_agent_result_in_background",
        _fake_background_save,
    )
    monkeypatch.setattr(
        "code_puppy.api.ws.chat_turn_runner.fire_and_track",
        _fake_fire_and_track,
    )

    cleanup_calls = []
    outcome = await execute_turn_runner(
        websocket=websocket,
        session_id="session-3",
        ctx=SimpleNamespace(),
        agent=agent,
        agent_name="code-puppy",
        model_name="gpt-test",
        session_title="title",
        session_working_directory="/tmp",
        session_pinned=True,
        message_to_send="hello",
        run_kwargs={},
        turn_state=WebSocketTurnState(),
        clear_session_working_directory=lambda: cleanup_calls.append("cleared"),
    )
    await asyncio.gather(*bg_tasks)

    assert outcome.result is None
    assert outcome.deferred_msg == {
        "type": "switch_session",
        "session_id": "next-session",
    }
    assert bg_calls and bg_calls[0]["label"] == "switch"
    assert bg_calls[0]["pinned"] is True
    assert cleanup_calls == ["cleared"]


@pytest.mark.asyncio
async def test_execute_turn_runner_background_saves_on_disconnect(monkeypatch):
    bg_calls = []
    bg_tasks = []
    agent = _BlockingAgent()
    websocket = _FakeWebSocket([WebSocketDisconnect()])

    async def _fake_background_save(**kwargs):
        bg_calls.append(kwargs)
        task = kwargs.get("agent_task")
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    def _fake_fire_and_track(coro):
        task = asyncio.create_task(coro)
        bg_tasks.append(task)
        return task

    monkeypatch.setattr(
        "code_puppy.api.ws.chat_turn_runner.save_agent_result_in_background",
        _fake_background_save,
    )
    monkeypatch.setattr(
        "code_puppy.api.ws.chat_turn_runner.fire_and_track",
        _fake_fire_and_track,
    )

    cleanup_calls = []
    outcome = await execute_turn_runner(
        websocket=websocket,
        session_id="session-4",
        ctx=SimpleNamespace(),
        agent=agent,
        agent_name="code-puppy",
        model_name="gpt-test",
        session_title="title",
        session_working_directory="/tmp",
        session_pinned=False,
        message_to_send="hello",
        run_kwargs={},
        turn_state=WebSocketTurnState(),
        clear_session_working_directory=lambda: cleanup_calls.append("cleared"),
    )
    await asyncio.gather(*bg_tasks)

    assert outcome.result is None
    assert outcome.deferred_msg is None
    assert bg_calls and bg_calls[0]["label"] == "disconnect"
    assert cleanup_calls == ["cleared"]
