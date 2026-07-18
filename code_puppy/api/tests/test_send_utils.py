"""Focused tests for WebSocketSender (Phase 3)."""

from __future__ import annotations

import pytest

from code_puppy.api.ws.send_utils import WebSocketSender

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeWebSocket:
    """Minimal WebSocket stub for unit tests."""

    def __init__(self, *, fail: bool = False, fail_msg: str = "closed"):
        self.sent: list[dict] = []
        self._fail = fail
        self._fail_msg = fail_msg

    async def send_json(self, data: dict) -> None:
        if self._fail:
            raise RuntimeError(self._fail_msg)
        self.sent.append(data)


class _FakeCtx:
    def __init__(self, agent_name: str = "", model_name: str = ""):
        self.agent_name = agent_name
        self.model_name = model_name


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_sender_initial_state():
    ws = _FakeWebSocket()
    sender = WebSocketSender(ws, session_id="s1")
    assert sender.ws_closed is False
    assert sender.session_id == "s1"
    assert sender.ctx is None


def test_sender_ctx_settable():
    ws = _FakeWebSocket()
    sender = WebSocketSender(ws, session_id="s1")
    ctx = _FakeCtx(agent_name="husky")
    sender.ctx = ctx
    assert sender.ctx is ctx


# ---------------------------------------------------------------------------
# safe_send_json
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safe_send_json_success():
    ws = _FakeWebSocket()
    sender = WebSocketSender(ws, session_id="s1")
    ok = await sender.safe_send_json({"type": "status", "status": "done"})
    assert ok is True
    assert len(ws.sent) == 1
    assert ws.sent[0]["type"] == "status"


@pytest.mark.asyncio
async def test_safe_send_json_skips_when_closed():
    ws = _FakeWebSocket()
    sender = WebSocketSender(ws, session_id="s1")
    sender.ws_closed = True
    ok = await sender.safe_send_json({"type": "status"})
    assert ok is False
    assert len(ws.sent) == 0


@pytest.mark.asyncio
async def test_safe_send_json_marks_closed_on_closed_error():
    ws = _FakeWebSocket(fail=True, fail_msg="WebSocket is closed")
    sender = WebSocketSender(ws, session_id="s1")
    ok = await sender.safe_send_json({"type": "status"})
    assert ok is False
    assert sender.ws_closed is True


@pytest.mark.asyncio
async def test_safe_send_json_non_close_error_keeps_open():
    ws = _FakeWebSocket(fail=True, fail_msg="network timeout")
    sender = WebSocketSender(ws, session_id="s1")
    ok = await sender.safe_send_json({"type": "status"})
    assert ok is False
    assert sender.ws_closed is False


# ---------------------------------------------------------------------------
# send_typed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_typed_serialises_pydantic_model():
    from code_puppy.api.ws.schemas import ServerStatus

    ws = _FakeWebSocket()
    sender = WebSocketSender(ws, session_id="s1")
    msg = ServerStatus(status="done", session_id="s1", agent_name="a", model_name="m")
    ok = await sender.send_typed(msg)
    assert ok is True
    assert ws.sent[0]["type"] == "status"
    assert ws.sent[0]["status"] == "done"


# ---------------------------------------------------------------------------
# send_typed_tool_lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_typed_tool_lifecycle():
    from code_puppy.api.ws.schemas import ServerToolCall

    ws = _FakeWebSocket()
    sender = WebSocketSender(ws, session_id="s1")
    msg = ServerToolCall(
        tool_id="t1",
        tool_name="read_file",
        args={"file_path": "a.py"},
        session_id="s1",
        timestamp=1.0,
    )
    ok = await sender.send_typed_tool_lifecycle(msg)
    assert ok is True
    assert ws.sent[0]["tool_name"] == "read_file"


# ---------------------------------------------------------------------------
# persist_error_payload (unit — no real DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persist_error_skips_non_error_type():
    ws = _FakeWebSocket()
    sender = WebSocketSender(ws, session_id="s1")
    # Should return without attempting DB write
    await sender.persist_error_payload({"type": "status"})


@pytest.mark.asyncio
async def test_persist_error_skips_empty_session_id():
    ws = _FakeWebSocket()
    sender = WebSocketSender(ws, session_id="")
    await sender.persist_error_payload({"type": "error", "error": "boom"})


# ---------------------------------------------------------------------------
# Import isolation
# ---------------------------------------------------------------------------


def test_send_utils_import_does_not_eagerly_load_chat_handler():
    import importlib
    import sys

    sys.modules.pop("code_puppy.api.ws", None)
    sys.modules.pop("code_puppy.api.ws.chat_handler", None)
    sys.modules.pop("code_puppy.api.ws.send_utils", None)

    importlib.import_module("code_puppy.api.ws.send_utils")

    assert "code_puppy.api.ws.chat_handler" not in sys.modules


def test_session_persistence_import_does_not_eagerly_load_chat_handler():
    import importlib
    import sys

    sys.modules.pop("code_puppy.api.ws", None)
    sys.modules.pop("code_puppy.api.ws.chat_handler", None)
    sys.modules.pop("code_puppy.api.ws.session_persistence", None)

    importlib.import_module("code_puppy.api.ws.session_persistence")

    assert "code_puppy.api.ws.chat_handler" not in sys.modules
