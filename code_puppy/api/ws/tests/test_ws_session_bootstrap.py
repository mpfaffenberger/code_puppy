from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest

from code_puppy.api.ws.ws_chat_runtime import WebSocketChatRuntime


class _FakeAgent:
    def __init__(self, history=None):
        self._history = list(history or [])

    def get_message_history(self):
        return list(self._history)


class _FakeSessionManager:
    def __init__(self, ctx):
        self.ctx = ctx
        self.created = []
        self.loaded = []
        self.activated = []

    async def create_session(self, session_id):
        self.created.append(session_id)
        return self.ctx

    async def get_or_load_session(self, session_id):
        self.loaded.append(session_id)
        return self.ctx

    async def mark_session_active(self, session_id):
        self.activated.append(session_id)


class _FakeWebSocket:
    def __init__(self):
        self.closed = []

    async def close(self, *, code, reason):
        self.closed.append((code, reason))


class _FakeSender:
    def __init__(self):
        self.session_id = None
        self.ctx = None


class _FakeBus:
    def __init__(self):
        self.contexts = []

    def set_session_context(self, session_id):
        self.contexts.append(session_id)


def _install_bootstrap_deps(
    monkeypatch,
    *,
    session_exists=False,
    session_metadata=None,
    session_row=None,
    active_messages=None,
    session_manager=None,
    writes=None,
    bus=None,
    init_calls=None,
):
    fake_db_pkg = ModuleType("code_puppy.api.db")
    fake_db_pkg.__path__ = []
    fake_queries = ModuleType("code_puppy.api.db.queries")

    async def _write_system_message_to_sqlite(**kwargs):
        writes.append(kwargs)

    async def _session_exists(_session_id):
        return session_exists

    async def _get_session_metadata(_session_id):
        return dict(session_metadata or {})

    async def _get_session_row(_session_id):
        return dict(session_row or {})

    async def _get_active_messages(_session_id):
        return list(active_messages or [])

    fake_queries.write_system_message_to_sqlite = _write_system_message_to_sqlite
    fake_queries.session_exists = _session_exists
    fake_queries.get_session_metadata = _get_session_metadata
    fake_queries.get_session_row = _get_session_row
    fake_queries.get_active_messages = _get_active_messages
    fake_db_pkg.queries = fake_queries
    monkeypatch.setitem(sys.modules, "code_puppy.api.db", fake_db_pkg)
    monkeypatch.setitem(sys.modules, "code_puppy.api.db.queries", fake_queries)

    fake_session_context = ModuleType("code_puppy.api.session_context")
    fake_session_context._validate_session_id = lambda value: value
    fake_session_context.session_manager = session_manager
    monkeypatch.setitem(
        sys.modules, "code_puppy.api.session_context", fake_session_context
    )

    fake_bus_module = ModuleType("code_puppy.messaging.bus")
    fake_bus_module.get_message_bus = lambda: bus
    monkeypatch.setitem(sys.modules, "code_puppy.messaging.bus", fake_bus_module)

    fake_command_runner = ModuleType("code_puppy.tools.command_runner")
    fake_command_runner.init_session_process_tracking = lambda: init_calls.append(
        "init"
    )
    monkeypatch.setitem(
        sys.modules, "code_puppy.tools.command_runner", fake_command_runner
    )

    fake_session_persistence = ModuleType("code_puppy.api.ws.session_persistence")
    fake_session_persistence.build_session_meta_payload = lambda **kwargs: kwargs
    monkeypatch.setitem(
        sys.modules,
        "code_puppy.api.ws.session_persistence",
        fake_session_persistence,
    )


def _load_bootstrap_module(monkeypatch, **kwargs):
    sys.modules.pop("code_puppy.api.ws.ws_session_bootstrap", None)
    _install_bootstrap_deps(monkeypatch, **kwargs)
    return importlib.import_module("code_puppy.api.ws.ws_session_bootstrap")


@pytest.mark.asyncio
async def test_initialize_ws_session_creates_new_session(monkeypatch):
    ctx = SimpleNamespace(
        agent=_FakeAgent([]),
        agent_name="code-puppy",
        model_name="gpt-test",
        title="",
        working_directory="",
        pinned=False,
    )
    manager = _FakeSessionManager(ctx)
    writes = []
    bus = _FakeBus()
    init_calls = []
    module = _load_bootstrap_module(
        monkeypatch,
        session_exists=False,
        session_manager=manager,
        writes=writes,
        bus=bus,
        init_calls=init_calls,
    )

    sent = []
    meta = []

    async def _send_typed(message):
        sent.append(message)

    async def _safe_send_json(payload):
        meta.append(payload)

    runtime = await module.initialize_ws_session(
        websocket=_FakeWebSocket(),
        requested_session_id="session-1",
        sender=_FakeSender(),
        safe_send_json=_safe_send_json,
        send_typed=_send_typed,
    )

    assert isinstance(runtime, WebSocketChatRuntime)
    assert runtime.session_id == "session-1"
    assert manager.created == ["session-1"]
    assert manager.activated == ["session-1"]
    assert init_calls == ["init"]
    assert bus.contexts == ["session-1"]
    assert writes[0]["system_message_type"] == "config"
    assert sent[0].type == "system"
    assert sent[0].resumed is False
    assert meta[0]["session_id"] == "session-1"
    assert meta[0]["message_count"] == 0


@pytest.mark.asyncio
async def test_initialize_ws_session_restores_existing_session(monkeypatch):
    ctx = SimpleNamespace(
        agent=_FakeAgent([{"role": "user"}, {"role": "assistant"}]),
        agent_name="restored-agent",
        model_name="restored-model",
        title="Saved title",
        working_directory="/tmp/project",
        pinned=True,
    )
    manager = _FakeSessionManager(ctx)
    writes = []
    bus = _FakeBus()
    init_calls = []
    module = _load_bootstrap_module(
        monkeypatch,
        session_exists=True,
        session_metadata={
            "title": "Saved title",
            "working_directory": "/tmp/project",
            "pinned": True,
        },
        active_messages=[
            {
                "role": "system",
                "system_message_type": "config",
                "content": "restored config",
                "agent_name": "restored-agent",
                "model_name": "restored-model",
            }
        ],
        session_manager=manager,
        writes=writes,
        bus=bus,
        init_calls=init_calls,
    )

    sent = []
    meta = []

    async def _send_typed(message):
        sent.append(message)

    async def _safe_send_json(payload):
        meta.append(payload)

    runtime = await module.initialize_ws_session(
        websocket=_FakeWebSocket(),
        requested_session_id="session-2",
        sender=_FakeSender(),
        safe_send_json=_safe_send_json,
        send_typed=_send_typed,
    )

    assert runtime.session_id == "session-2"
    assert manager.loaded == ["session-2"]
    assert writes == []
    assert sent[0].type == "system"
    assert sent[0].resumed is True
    assert any(message.type == "session_restored" for message in sent)
    assert any(
        message.type == "system"
        and getattr(message, "content", "") == "restored config"
        for message in sent[1:]
    )
    assert meta[0]["title"] == "Saved title"
