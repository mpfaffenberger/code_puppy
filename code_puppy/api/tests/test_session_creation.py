from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from code_puppy.api.session_context import SessionManager


@pytest.mark.asyncio
async def test_create_session_rejects_duplicate_ids(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.api.session_context.get_available_agents",
        lambda: {"code-puppy": "Code Puppy"},
    )
    monkeypatch.setattr(
        "code_puppy.api.session_context.load_agent",
        lambda _name: MagicMock(),
    )
    monkeypatch.setattr(
        "code_puppy.api.session_context.get_global_model_name",
        lambda: "gpt-test",
    )

    manager = SessionManager()

    first = await manager.create_session("session-1")
    assert first.session_id == "session-1"

    with pytest.raises(ValueError, match="Session already exists"):
        await manager.create_session("session-1")
