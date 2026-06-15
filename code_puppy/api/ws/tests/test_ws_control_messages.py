from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

from code_puppy.api.ws.ws_chat_runtime import WebSocketChatRuntime


class _FakeSessionManager:
    def __init__(self):
        self.switch_agent_calls = []
        self.switch_model_calls = []

    async def switch_agent(self, session_id, agent_name):
        self.switch_agent_calls.append((session_id, agent_name))
        return SimpleNamespace(get_model_name=lambda: "new-model")

    async def switch_model(self, session_id, model_name):
        self.switch_model_calls.append((session_id, model_name))


def _load_control_module(
    monkeypatch,
    *,
    cancel_calls=None,
    permission_calls=None,
    writes=None,
    update_calls=None,
    set_config_calls=None,
    get_values=None,
):
    fake_db_pkg = ModuleType("code_puppy.api.db")
    fake_db_pkg.__path__ = []
    fake_queries = ModuleType("code_puppy.api.db.queries")

    async def _write_system_message_to_sqlite(**kwargs):
        writes.append(kwargs)

    async def _update_session_working_directory(**kwargs):
        update_calls.append(kwargs)

    fake_queries.write_system_message_to_sqlite = _write_system_message_to_sqlite
    fake_queries.update_session_working_directory = _update_session_working_directory
    fake_db_pkg.queries = fake_queries
    monkeypatch.setitem(sys.modules, "code_puppy.api.db", fake_db_pkg)
    monkeypatch.setitem(sys.modules, "code_puppy.api.db.queries", fake_queries)

    fake_permissions = ModuleType("code_puppy.api.permissions")
    fake_permissions.handle_permission_response = (
        lambda request_id, approved, session_id=None: (
            permission_calls.append((request_id, approved, session_id)) or True
        )
    )
    monkeypatch.setitem(sys.modules, "code_puppy.api.permissions", fake_permissions)

    fake_session_context = ModuleType("code_puppy.api.session_context")
    fake_session_context._validate_session_id = lambda value: value
    fake_session_context.session_manager = _FakeSessionManager()
    monkeypatch.setitem(
        sys.modules, "code_puppy.api.session_context", fake_session_context
    )

    fake_send_utils = ModuleType("code_puppy.api.ws.send_utils")
    fake_send_utils.WebSocketSender = object
    monkeypatch.setitem(sys.modules, "code_puppy.api.ws.send_utils", fake_send_utils)

    fake_stream_drain = ModuleType("code_puppy.api.ws.ws_stream_drain")

    async def _cancel_active_streaming(**kwargs):
        cancel_calls.append(kwargs)

    fake_stream_drain.cancel_active_streaming = _cancel_active_streaming
    monkeypatch.setitem(
        sys.modules, "code_puppy.api.ws.ws_stream_drain", fake_stream_drain
    )

    fake_config = ModuleType("code_puppy.config")
    fake_config.get_puppy_name = lambda: "puppy"
    fake_config.get_value = lambda key: get_values.get(key)
    fake_config.set_config_value = lambda key, value: set_config_calls.append(
        (key, value)
    )
    monkeypatch.setitem(sys.modules, "code_puppy.config", fake_config)

    sys.modules.pop("code_puppy.api.ws.ws_control_messages", None)
    return importlib.import_module("code_puppy.api.ws.ws_control_messages")


@pytest.mark.asyncio
async def test_handle_control_message_switch_model(monkeypatch):
    cancel_calls, permission_calls, writes, update_calls, set_config_calls = (
        [],
        [],
        [],
        [],
        [],
    )
    module = _load_control_module(
        monkeypatch,
        cancel_calls=cancel_calls,
        permission_calls=permission_calls,
        writes=writes,
        update_calls=update_calls,
        set_config_calls=set_config_calls,
        get_values={},
    )
    runtime = WebSocketChatRuntime(
        session_id="session-1",
        ctx=SimpleNamespace(
            agent=object(), agent_name="code-puppy", model_name="old-model"
        ),
        agent_name="code-puppy",
        model_name="old-model",
    )
    sent = []

    async def _send_typed(message):
        sent.append(message)

    handled = await module.handle_control_message(
        msg={"type": "switch_model", "model_name": "new-model"},
        runtime=runtime,
        sender=SimpleNamespace(session_id="session-1", ctx=runtime.ctx),
        send_typed=_send_typed,
        send_session_meta_snapshot=lambda: None,
    )

    assert handled is True
    assert runtime.model_name == "new-model"
    assert sent[-1].type == "system"
    assert "new-model" in sent[-1].content
    assert writes[-1]["model_name"] == "new-model"


@pytest.mark.asyncio
async def test_handle_control_message_set_working_directory(monkeypatch, tmp_path):
    cancel_calls, permission_calls, writes, update_calls, set_config_calls = (
        [],
        [],
        [],
        [],
        [],
    )
    module = _load_control_module(
        monkeypatch,
        cancel_calls=cancel_calls,
        permission_calls=permission_calls,
        writes=writes,
        update_calls=update_calls,
        set_config_calls=set_config_calls,
        get_values={},
    )
    runtime = WebSocketChatRuntime(
        session_id="session-2",
        ctx=SimpleNamespace(
            agent_name="code-puppy", model_name="gpt-test", working_directory=""
        ),
    )
    sent = []

    async def _send_typed(message):
        sent.append(message)

    handled = await module.handle_control_message(
        msg={"type": "set_working_directory", "directory": str(tmp_path)},
        runtime=runtime,
        sender=SimpleNamespace(session_id="session-2", ctx=runtime.ctx),
        send_typed=_send_typed,
        send_session_meta_snapshot=lambda: None,
    )

    assert handled is True
    assert runtime.session_working_directory == str(tmp_path.resolve())
    assert sent[-1].type == "working_directory_changed"
    assert sent[-1].success is True
    assert writes[-1]["system_message_type"] == "directory"
    assert update_calls[-1]["working_directory"] == str(tmp_path.resolve())


@pytest.mark.asyncio
async def test_handle_control_message_cancel(monkeypatch):
    cancel_calls, permission_calls, writes, update_calls, set_config_calls = (
        [],
        [],
        [],
        [],
        [],
    )
    module = _load_control_module(
        monkeypatch,
        cancel_calls=cancel_calls,
        permission_calls=permission_calls,
        writes=writes,
        update_calls=update_calls,
        set_config_calls=set_config_calls,
        get_values={},
    )

    task = None

    async def _never():
        await __import__("asyncio").Future()

    import asyncio

    task = asyncio.create_task(_never())
    runtime = WebSocketChatRuntime(session_id="session-3", active_agent_task=task)
    sent = []

    async def _send_typed(message):
        sent.append(message)

    handled = await module.handle_control_message(
        msg={"type": "cancel"},
        runtime=runtime,
        sender=SimpleNamespace(session_id="session-3", ctx=None),
        send_typed=_send_typed,
        send_session_meta_snapshot=lambda: None,
    )

    assert handled is True
    assert cancel_calls
    assert runtime.active_agent_task is None
    assert sent[-1].type == "status"
    assert sent[-1].status == "cancelled"


@pytest.mark.asyncio
async def test_handle_control_message_permission_response(monkeypatch):
    cancel_calls, permission_calls, writes, update_calls, set_config_calls = (
        [],
        [],
        [],
        [],
        [],
    )
    module = _load_control_module(
        monkeypatch,
        cancel_calls=cancel_calls,
        permission_calls=permission_calls,
        writes=writes,
        update_calls=update_calls,
        set_config_calls=set_config_calls,
        get_values={},
    )
    sent = []

    async def _send_typed(message):
        sent.append(message)

    handled = await module.handle_control_message(
        msg={"type": "permission_response", "request_id": "req-1", "approved": True},
        runtime=WebSocketChatRuntime(session_id="session-4"),
        sender=SimpleNamespace(session_id="session-4", ctx=None),
        send_typed=_send_typed,
        send_session_meta_snapshot=lambda: None,
    )

    assert handled is True
    assert permission_calls == [("req-1", True, "session-4")]
    assert sent == []
