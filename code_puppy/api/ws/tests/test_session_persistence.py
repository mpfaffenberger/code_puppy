from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.api.ws.session_persistence import persist_session_turn_and_broadcast


class _Logger:
    def __init__(self):
        self.debug_messages = []

    def debug(self, message, *args):
        self.debug_messages.append(message % args if args else message)


@pytest.mark.asyncio
async def test_persist_session_turn_and_broadcast_returns_none_for_empty_history():
    safe_send_json = AsyncMock()

    with (
        patch(
            "code_puppy.api.ws.session_persistence.persist_turn_to_sqlite",
            new_callable=AsyncMock,
        ) as mock_persist,
        patch(
            "code_puppy.api.ws.session_persistence.connection_manager.broadcast_session_update",
            new_callable=AsyncMock,
        ) as mock_broadcast,
    ):
        result = await persist_session_turn_and_broadcast(
            history=[],
            session_id="sess-1",
            session_title="",
            session_working_directory="/tmp",
            session_pinned=False,
            agent=MagicMock(),
            agent_name="code-puppy",
            model_name="gpt-4",
            ctx=SimpleNamespace(created_at=datetime.datetime(2025, 1, 1)),
            original_user_message="hello",
            attachment_metadata=None,
            safe_send_json=safe_send_json,
        )

    assert result is None
    safe_send_json.assert_not_called()
    mock_persist.assert_not_called()
    mock_broadcast.assert_not_called()


@pytest.mark.asyncio
async def test_persist_session_turn_and_broadcast_persists_and_notifies_with_generated_title():
    history = [object(), object()]
    enhanced_history = [{"msg": "u"}, {"msg": "a"}]
    safe_send_json = AsyncMock()
    logger = _Logger()
    ctx = SimpleNamespace(
        created_at=datetime.datetime(2025, 1, 2, 3, 4, 5),
        agent_name="ctx-agent",
        model_name="ctx-model",
    )
    agent = MagicMock()
    agent.name = "agent-object"
    agent.get_model_name.return_value = "agent-model"

    with (
        patch(
            "code_puppy.api.ws.session_persistence.generate_heuristic_title",
            return_value="Generated Title",
        ) as mock_title,
        patch(
            "code_puppy.api.ws.session_persistence.build_enhanced_history",
            return_value=enhanced_history,
        ) as mock_build,
        patch(
            "code_puppy.api.ws.session_persistence.estimate_total_tokens",
            return_value=42,
        ) as mock_tokens,
        patch(
            "code_puppy.api.ws.session_persistence.persist_turn_to_sqlite",
            new_callable=AsyncMock,
        ) as mock_persist,
        patch(
            "code_puppy.api.ws.session_persistence.connection_manager.broadcast_session_update",
            new_callable=AsyncMock,
        ) as mock_broadcast,
    ):
        summary = await persist_session_turn_and_broadcast(
            history=history,
            session_id="sess-2",
            session_title="untitled-session",
            session_working_directory="/work",
            session_pinned=True,
            agent=agent,
            agent_name="wire-agent",
            model_name="wire-model",
            ctx=ctx,
            original_user_message="show logs",
            attachment_metadata=[{"name": "demo.txt"}],
            safe_send_json=safe_send_json,
            logger_override=logger,
        )

    assert summary is not None
    assert summary.session_title == "Generated Title"
    assert summary.message_count == 2
    assert summary.total_tokens == 42

    mock_title.assert_called_once_with(history)
    mock_build.assert_called_once_with(
        history,
        agent_name_meta="agent-object",
        model_name_meta="agent-model",
        original_user_message="show logs",
        attachment_metadata=[{"name": "demo.txt"}],
    )
    mock_tokens.assert_called_once_with(enhanced_history, agent)
    mock_persist.assert_awaited_once_with(
        session_id="sess-2",
        enhanced_history=enhanced_history,
        title="Generated Title",
        working_directory="/work",
        pinned=True,
        agent_name="wire-agent",
        model_name="wire-model",
        total_tokens=42,
        created_at_iso=ctx.created_at.isoformat(),
        ctx=ctx,
    )
    safe_send_json.assert_awaited_once()
    session_meta_payload = safe_send_json.await_args.args[0]
    assert session_meta_payload["type"] == "session_meta"
    assert session_meta_payload["session_id"] == "sess-2"
    assert session_meta_payload["title"] == "Generated Title"
    assert session_meta_payload["total_tokens"] == 42
    assert session_meta_payload["message_count"] == 2
    assert session_meta_payload["agent_name"] == "wire-agent"
    assert session_meta_payload["model_name"] == "wire-model"

    mock_broadcast.assert_awaited_once()
    session_update_payload = mock_broadcast.await_args.args[0]
    assert session_update_payload["session_id"] == "sess-2"
    assert session_update_payload["title"] == "Generated Title"
    assert session_update_payload["message_count"] == 2
    assert session_update_payload["total_tokens"] == 42
    assert logger.debug_messages
    assert "Added UI metadata" in logger.debug_messages[0]


@pytest.mark.asyncio
async def test_persist_session_turn_and_broadcast_preserves_existing_title():
    safe_send_json = AsyncMock()
    ctx = SimpleNamespace(created_at=datetime.datetime(2025, 1, 1))

    with (
        patch(
            "code_puppy.api.ws.session_persistence.generate_heuristic_title"
        ) as mock_title,
        patch(
            "code_puppy.api.ws.session_persistence.build_enhanced_history",
            return_value=[{"msg": "only"}],
        ),
        patch(
            "code_puppy.api.ws.session_persistence.estimate_total_tokens",
            return_value=9,
        ),
        patch(
            "code_puppy.api.ws.session_persistence.persist_turn_to_sqlite",
            new_callable=AsyncMock,
        ),
        patch(
            "code_puppy.api.ws.session_persistence.connection_manager.broadcast_session_update",
            new_callable=AsyncMock,
        ),
    ):
        summary = await persist_session_turn_and_broadcast(
            history=[object()],
            session_id="sess-3",
            session_title="Keep Me",
            session_working_directory="/tmp",
            session_pinned=False,
            agent=MagicMock(),
            agent_name="a",
            model_name="m",
            ctx=ctx,
            original_user_message="hi",
            attachment_metadata=[],
            safe_send_json=safe_send_json,
        )

    assert summary is not None
    assert summary.session_title == "Keep Me"
    mock_title.assert_not_called()
