import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from starlette.routing import Router


_original_router_init = Router.__init__


def _compat_router_init(self, *args, **kwargs):
    kwargs.pop("on_startup", None)
    kwargs.pop("on_shutdown", None)
    kwargs.pop("lifespan", None)
    return _original_router_init(self, *args, **kwargs)


Router.__init__ = _compat_router_init
try:
    module_path = (
        Path(__file__).resolve().parents[2]
        / "code_puppy"
        / "api"
        / "routers"
        / "ws_sessions.py"
    )
    spec = importlib.util.spec_from_file_location(
        "test_ws_sessions_module", module_path
    )
    assert spec is not None and spec.loader is not None
    ws_sessions = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ws_sessions)
finally:
    Router.__init__ = _original_router_init


@pytest.mark.asyncio
async def test_get_ws_session_messages_keeps_plain_legacy_rows(monkeypatch):
    monkeypatch.setattr(
        ws_sessions,
        "_validate_session_name",
        lambda session_name, ws_dir: session_name,
    )
    monkeypatch.setattr(
        ws_sessions,
        "get_active_messages",
        AsyncMock(
            return_value=[
                {
                    "role": "assistant",
                    "content": "plain legacy row",
                    "type": "message",
                    "agent_name": "code-puppy",
                    "model_name": "gpt-5",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "thinking": None,
                    "clean_content": "plain legacy row",
                    "seq": 7,
                    "pydantic_json": None,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        ws_sessions,
        "get_session_metadata",
        AsyncMock(return_value=None),
    )

    result = await ws_sessions.get_ws_session_messages(
        "session-1",
        include_tool_calls=False,
    )

    assert result == [
        {
            "role": "assistant",
            "content": "plain legacy row",
            "type": "message",
            "agent_name": "code-puppy",
            "model_name": "gpt-5",
            "timestamp": "2026-01-01T00:00:00Z",
            "thinking": None,
            "clean_content": "plain legacy row",
            "seq": 7,
        }
    ]
