from __future__ import annotations

import asyncio

import pytest

from code_puppy.api.permissions import (
    PendingPermissionRequest,
    handle_permission_response,
    permission_futures,
)


@pytest.mark.asyncio
async def test_handle_permission_response_rejects_session_mismatch():
    future = asyncio.get_running_loop().create_future()
    permission_futures["req-1"] = PendingPermissionRequest(
        future=future,
        session_id="session-a",
    )
    try:
        assert (
            handle_permission_response("req-1", True, session_id="session-b") is False
        )
        assert future.done() is False
    finally:
        permission_futures.clear()


@pytest.mark.asyncio
async def test_handle_permission_response_allows_matching_session():
    future = asyncio.get_running_loop().create_future()
    permission_futures["req-2"] = PendingPermissionRequest(
        future=future,
        session_id="session-a",
    )
    try:
        assert handle_permission_response("req-2", True, session_id="session-a") is True
        assert future.done() is True
        assert future.result() is True
    finally:
        permission_futures.clear()


def test_handle_permission_response_unknown_request_returns_false():
    permission_futures.clear()
    assert handle_permission_response("missing", True, session_id="session-a") is False


@pytest.mark.asyncio
async def test_request_permission_auto_approves_when_yolo_enabled(monkeypatch):
    from code_puppy.api.permissions import request_permission
    import code_puppy.config as config

    class FakeWebSocket:
        def __init__(self):
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)

    websocket = FakeWebSocket()
    monkeypatch.setattr(config, "get_yolo_mode", lambda: True)

    approved = await request_permission(
        websocket=websocket,
        session_id="session-a",
        request_type="shell_command",
        title="Execute Shell Command",
        description="Run: pwd",
        details={"command": "pwd"},
        timeout=1,
    )

    assert approved is True
    assert websocket.sent == []


@pytest.mark.asyncio
async def test_request_permission_registers_future_before_send(monkeypatch):
    from code_puppy.api.permissions import request_permission

    class RaceWebSocket:
        def __init__(self):
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)
            assert (
                handle_permission_response(
                    payload["request_id"],
                    True,
                    session_id=payload["session_id"],
                )
                is True
            )

    websocket = RaceWebSocket()
    permission_futures.clear()

    monkeypatch.setattr("code_puppy.config.get_yolo_mode", lambda: False)

    approved = await request_permission(
        websocket=websocket,
        session_id="session-a",
        request_type="shell_command",
        title="Execute Shell Command",
        description="Run: pwd",
        details={"command": "pwd"},
        timeout=1,
    )

    assert approved is True
    assert len(websocket.sent) == 1
    assert permission_futures == {}
