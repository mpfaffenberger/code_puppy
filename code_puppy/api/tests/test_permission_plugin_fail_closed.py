from __future__ import annotations

import pytest

from code_puppy.api.permission_plugin import (
    clear_websocket_context,
    pre_tool_call_permission,
    set_websocket_context,
    shell_command_permission,
)


@pytest.mark.asyncio
async def test_pre_tool_call_permission_fails_closed_on_request_error(monkeypatch):
    set_websocket_context(websocket=object(), session_id="session-1")
    try:

        async def _boom(**_kwargs):
            raise RuntimeError("permission transport down")

        monkeypatch.setattr("code_puppy.api.permissions.request_permission", _boom)

        result = await pre_tool_call_permission(
            "agent_run_shell_command", {"command": "ls"}
        )
        assert isinstance(result, dict)
        assert result["blocked"] is True
        assert result["error"] == "Permission system error"
    finally:
        clear_websocket_context()


@pytest.mark.asyncio
async def test_shell_command_permission_fails_closed_on_request_error(monkeypatch):
    set_websocket_context(websocket=object(), session_id="session-1")
    try:

        async def _boom(**_kwargs):
            raise RuntimeError("permission transport down")

        monkeypatch.setattr("code_puppy.api.permissions.request_permission", _boom)

        result = await shell_command_permission(
            context=None,
            command="ls",
            cwd=".",
            timeout=30,
        )
        assert isinstance(result, dict)
        assert result["blocked"] is True
        assert result["error"] == "Permission system error"
    finally:
        clear_websocket_context()
