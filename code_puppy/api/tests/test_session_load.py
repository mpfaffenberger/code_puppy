"""Unit tests for SessionManager._load_from_sqlite and .load_session.

Phase 4 coverage from the session-management bug plan:

_load_from_sqlite:
 1.  Session not in DB           → returns None
 2.  SQLite import unavailable   → returns None
 3.  get_active_messages raises  → returns None (outer except)
 4.  All rows NULL pydantic_json → returns ([], meta) – graceful degradation
 5.  Mixed NULL + valid rows     → only valid rows parsed
 6.  Valid rows                  → messages parsed correctly
 7.  Malformed pydantic_json     → row skipped + warning, rest succeed
 8.  Metadata populated from sessions table
 9.  No session row in sessions table → meta = {}
10.  Sessions table query fails  → meta = {}

load_session:
11. Invalid session_id           → ValueError before touching DB
12. _load_from_sqlite → None    → load_session returns None
13. Normal happy path            → history set, ctx in _sessions
14. Unknown agent_name in DB    → falls back to code-puppy
15. Valid created_at string      → parsed as datetime correctly
16. Malformed created_at         → datetime.now() fallback
17. Empty created_at             → datetime.now() fallback
18. Session registered in _sessions after load
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pydantic_json(content: str = "hello from user") -> str:
    """Produce a valid pydantic_json string using real pydantic-ai types."""
    from pydantic_ai.messages import (
        ModelMessagesTypeAdapter,
        ModelRequest,
        UserPromptPart,
    )

    msg = ModelRequest(parts=[UserPromptPart(content=content)])
    return ModelMessagesTypeAdapter.dump_json([msg]).decode("utf-8")


def _make_response_pydantic_json(content: str = "hello from assistant") -> str:
    """Produce a valid pydantic_json string for a ModelResponse."""
    from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, TextPart

    msg = ModelResponse(parts=[TextPart(content=content)], model_name="test-model")
    return ModelMessagesTypeAdapter.dump_json([msg]).decode("utf-8")


def _make_row(
    seq: int = 1,
    role: str = "user",
    pydantic_json: str | None = None,
) -> dict:
    """Build a minimal message row dict as returned by get_active_messages."""
    return {
        "seq": seq,
        "role": role,
        "content": "some content",
        "pydantic_json": pydantic_json,
    }


def _make_session_row(
    session_id: str = "test-session",
    agent_name: str = "code-puppy",
    model_name: str = "gpt-4o",
    title: str = "Test Session",
    pinned: bool = False,
    working_directory: str = "/tmp",
    created_at: str = "2026-01-01T00:00:00+00:00",
) -> dict:
    """Build a minimal sessions table row dict."""
    return {
        "session_id": session_id,
        "agent_name": agent_name,
        "model_name": model_name,
        "title": title,
        "pinned": 1 if pinned else 0,
        "working_directory": working_directory,
        "created_at": created_at,
    }


def _make_db_mock(session_row: dict | None) -> MagicMock:
    """Return a db mock whose cursor.fetchone() returns *session_row*."""
    cursor = AsyncMock()
    cursor.fetchone.return_value = session_row
    db = MagicMock()
    db.execute = AsyncMock(return_value=cursor)
    return db


def _make_fresh_manager():
    """Return a brand-new SessionManager instance (not the module singleton)."""
    from code_puppy.api.session_context import SessionManager

    return SessionManager()


def _make_agent_mock(history: list | None = None) -> MagicMock:
    """Return a minimal agent mock."""
    agent = MagicMock()
    agent.get_message_history.return_value = history or []
    agent.set_message_history.return_value = None
    agent.set_session_model.return_value = None
    return agent


# ---------------------------------------------------------------------------
# _load_from_sqlite tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_from_sqlite_session_not_in_db():
    """session_exists returns False → _load_from_sqlite returns None."""
    mgr = _make_fresh_manager()
    db_mock = _make_db_mock(None)

    with (
        patch(
            "code_puppy.api.db.queries.session_exists",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "code_puppy.api.db.queries.get_active_messages",
            new=AsyncMock(return_value=[]),
        ),
        patch("code_puppy.api.db.connection.get_db", return_value=db_mock),
    ):
        result = await mgr._load_from_sqlite("test-session")

    assert result is None


@pytest.mark.asyncio
async def test_load_from_sqlite_import_error_returns_none():
    """If the DB queries module is unavailable, _load_from_sqlite returns None."""
    mgr = _make_fresh_manager()

    # Raising ImportError inside the try block that wraps the lazy import
    # is the canonical way to simulate "SQLite not available".
    with patch(
        "code_puppy.api.db.queries.session_exists",
        side_effect=ImportError("aiosqlite not installed"),
    ):
        result = await mgr._load_from_sqlite("test-session")

    assert result is None


@pytest.mark.asyncio
async def test_load_from_sqlite_get_active_messages_raises_returns_none():
    """An exception from get_active_messages is caught → None."""
    mgr = _make_fresh_manager()

    with (
        patch(
            "code_puppy.api.db.queries.session_exists", new=AsyncMock(return_value=True)
        ),
        patch(
            "code_puppy.api.db.queries.get_active_messages",
            new=AsyncMock(side_effect=RuntimeError("db locked")),
        ),
    ):
        result = await mgr._load_from_sqlite("test-session")

    assert result is None


@pytest.mark.asyncio
async def test_load_from_sqlite_all_null_pydantic_json_returns_empty_history():
    """All rows have pydantic_json=None → empty message list, but NOT None.

    This is graceful degradation: the session exists but has no serialisable
    messages (e.g. seeded without the BE write path).  The agent starts with
    empty history rather than crashing.
    """
    mgr = _make_fresh_manager()
    rows = [
        _make_row(seq=1, role="user", pydantic_json=None),
        _make_row(seq=2, role="assistant", pydantic_json=None),
    ]
    db_mock = _make_db_mock(_make_session_row())

    with (
        patch(
            "code_puppy.api.db.queries.session_exists", new=AsyncMock(return_value=True)
        ),
        patch(
            "code_puppy.api.db.queries.get_active_messages",
            new=AsyncMock(return_value=rows),
        ),
        patch("code_puppy.api.db.connection.get_db", return_value=db_mock),
    ):
        result = await mgr._load_from_sqlite("test-session")

    assert result is not None, "Should return (messages, meta) not None"
    messages, meta = result
    assert messages == [], (
        "Empty history expected when all rows have NULL pydantic_json"
    )


@pytest.mark.asyncio
async def test_load_from_sqlite_mixed_null_and_valid_rows():
    """NULL pydantic_json rows are skipped; valid rows are parsed."""
    mgr = _make_fresh_manager()
    valid_json = _make_pydantic_json("hello")
    rows = [
        _make_row(seq=1, role="user", pydantic_json=None),  # NULL – skip
        _make_row(seq=2, role="user", pydantic_json=valid_json),  # valid
        _make_row(seq=3, role="user", pydantic_json=None),  # NULL – skip
    ]
    db_mock = _make_db_mock(_make_session_row())

    with (
        patch(
            "code_puppy.api.db.queries.session_exists", new=AsyncMock(return_value=True)
        ),
        patch(
            "code_puppy.api.db.queries.get_active_messages",
            new=AsyncMock(return_value=rows),
        ),
        patch("code_puppy.api.db.connection.get_db", return_value=db_mock),
    ):
        result = await mgr._load_from_sqlite("test-session")

    assert result is not None
    messages, _ = result
    assert len(messages) == 1, "Only the valid row should be parsed"


@pytest.mark.asyncio
async def test_load_from_sqlite_valid_rows_parsed_correctly():
    """Valid pydantic_json rows deserialise into proper ModelMessage objects."""
    from pydantic_ai.messages import ModelRequest

    mgr = _make_fresh_manager()
    user_json = _make_pydantic_json("user turn")
    assistant_json = _make_response_pydantic_json("assistant reply")
    rows = [
        _make_row(seq=1, role="user", pydantic_json=user_json),
        _make_row(seq=2, role="assistant", pydantic_json=assistant_json),
    ]
    db_mock = _make_db_mock(_make_session_row())

    with (
        patch(
            "code_puppy.api.db.queries.session_exists", new=AsyncMock(return_value=True)
        ),
        patch(
            "code_puppy.api.db.queries.get_active_messages",
            new=AsyncMock(return_value=rows),
        ),
        patch("code_puppy.api.db.connection.get_db", return_value=db_mock),
    ):
        result = await mgr._load_from_sqlite("test-session")

    assert result is not None
    messages, _ = result
    assert len(messages) == 2
    # First message must be a ModelRequest (user turn)
    assert isinstance(messages[0], ModelRequest)


@pytest.mark.asyncio
async def test_load_from_sqlite_malformed_pydantic_json_skipped(caplog):
    """A row with corrupt JSON is skipped with a warning; valid rows still load."""
    import logging

    mgr = _make_fresh_manager()
    valid_json = _make_pydantic_json("good message")
    rows = [
        _make_row(seq=1, role="user", pydantic_json="{this is not valid json!!!"),
        _make_row(seq=2, role="user", pydantic_json=valid_json),
    ]
    db_mock = _make_db_mock(_make_session_row())

    with (
        patch(
            "code_puppy.api.db.queries.session_exists", new=AsyncMock(return_value=True)
        ),
        patch(
            "code_puppy.api.db.queries.get_active_messages",
            new=AsyncMock(return_value=rows),
        ),
        patch("code_puppy.api.db.connection.get_db", return_value=db_mock),
        caplog.at_level(logging.WARNING, logger="code_puppy.api.session_context"),
    ):
        result = await mgr._load_from_sqlite("test-session")

    assert result is not None
    messages, _ = result
    # Only the valid row should come through
    assert len(messages) == 1
    # A warning must have been emitted for the bad row
    assert any("Failed to deserialise" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_load_from_sqlite_metadata_populated():
    """Meta dict is populated from the sessions table row."""
    mgr = _make_fresh_manager()
    session_row = _make_session_row(
        agent_name="planning-agent",
        model_name="claude-3",
        title="My Session",
        pinned=True,
        working_directory="/home/user/project",
    )
    db_mock = _make_db_mock(session_row)

    with (
        patch(
            "code_puppy.api.db.queries.session_exists", new=AsyncMock(return_value=True)
        ),
        patch(
            "code_puppy.api.db.queries.get_active_messages",
            new=AsyncMock(return_value=[]),
        ),
        patch("code_puppy.api.db.connection.get_db", return_value=db_mock),
    ):
        result = await mgr._load_from_sqlite("test-session")

    assert result is not None
    _, meta = result
    assert meta["agent_name"] == "planning-agent"
    assert meta["model_name"] == "claude-3"
    assert meta["title"] == "My Session"
    assert meta["working_directory"] == "/home/user/project"


@pytest.mark.asyncio
async def test_load_from_sqlite_no_session_row_gives_empty_meta():
    """If the sessions table has no row, meta is an empty dict."""
    mgr = _make_fresh_manager()
    db_mock = _make_db_mock(None)  # cursor.fetchone() → None

    with (
        patch(
            "code_puppy.api.db.queries.session_exists", new=AsyncMock(return_value=True)
        ),
        patch(
            "code_puppy.api.db.queries.get_active_messages",
            new=AsyncMock(return_value=[]),
        ),
        patch("code_puppy.api.db.connection.get_db", return_value=db_mock),
    ):
        result = await mgr._load_from_sqlite("test-session")

    assert result is not None
    _, meta = result
    assert meta == {}


@pytest.mark.asyncio
async def test_load_from_sqlite_sessions_table_query_fails_gives_empty_meta():
    """If the sessions table query raises, meta falls back to {} without crashing."""
    mgr = _make_fresh_manager()

    # get_db() itself raises on first call (for the metadata query only)
    failing_db = MagicMock()
    failing_db.execute = AsyncMock(side_effect=RuntimeError("table locked"))

    with (
        patch(
            "code_puppy.api.db.queries.session_exists", new=AsyncMock(return_value=True)
        ),
        patch(
            "code_puppy.api.db.queries.get_active_messages",
            new=AsyncMock(return_value=[]),
        ),
        patch("code_puppy.api.db.connection.get_db", return_value=failing_db),
    ):
        result = await mgr._load_from_sqlite("test-session")

    assert result is not None
    _, meta = result
    assert meta == {}


# ---------------------------------------------------------------------------
# load_session tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_session_invalid_session_id_raises():
    """load_session raises ValueError before touching the DB for bad IDs."""
    mgr = _make_fresh_manager()
    with pytest.raises(ValueError, match="Invalid session_id"):
        await mgr.load_session("../etc/passwd")


@pytest.mark.asyncio
async def test_load_session_returns_none_when_sqlite_has_no_data():
    """If _load_from_sqlite returns None, load_session returns None."""
    mgr = _make_fresh_manager()
    mgr._load_from_sqlite = AsyncMock(return_value=None)

    result = await mgr.load_session("valid-session-id")

    assert result is None


@pytest.mark.asyncio
async def test_load_session_happy_path_sets_history_and_registers_context():
    """Normal path: history loaded from SQLite is set on the agent, and the
    context is registered in the manager's _sessions dict.
    """
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    mgr = _make_fresh_manager()
    real_msg = ModelRequest(parts=[UserPromptPart(content="hello")])
    db_meta = _make_session_row(
        agent_name="code-puppy",
        model_name="gpt-4o",
        title="My Chat",
        created_at="2026-01-15T12:00:00+00:00",
    )
    mgr._load_from_sqlite = AsyncMock(return_value=([real_msg], db_meta))
    agent_mock = _make_agent_mock()

    with (
        patch("code_puppy.api.session_context.load_agent", return_value=agent_mock),
        patch(
            "code_puppy.api.session_context.get_global_model_name",
            return_value="gpt-4o",
        ),
    ):
        ctx = await mgr.load_session("my-chat-session")

    assert ctx is not None
    assert ctx.session_id == "my-chat-session"
    assert ctx.agent is agent_mock
    assert ctx.agent_name == "code-puppy"
    assert ctx.model_name == "gpt-4o"
    assert ctx.title == "My Chat"
    # set_message_history must have been called with the loaded messages
    agent_mock.set_message_history.assert_called_once_with([real_msg])


@pytest.mark.asyncio
async def test_load_session_registers_context_in_sessions_dict():
    """The loaded SessionContext must end up in SessionManager._sessions."""
    mgr = _make_fresh_manager()
    db_meta = _make_session_row()
    mgr._load_from_sqlite = AsyncMock(return_value=([], db_meta))
    agent_mock = _make_agent_mock()

    with (
        patch("code_puppy.api.session_context.load_agent", return_value=agent_mock),
        patch(
            "code_puppy.api.session_context.get_global_model_name",
            return_value="gpt-4o",
        ),
    ):
        ctx = await mgr.load_session("registered-session")

    assert "registered-session" in mgr._sessions
    assert mgr._sessions["registered-session"] is ctx


@pytest.mark.asyncio
async def test_load_session_unknown_agent_falls_back_to_code_puppy():
    """If the agent stored in DB is no longer available, code-puppy is used."""
    mgr = _make_fresh_manager()
    db_meta = _make_session_row(agent_name="deleted-custom-agent")
    mgr._load_from_sqlite = AsyncMock(return_value=([], db_meta))
    fallback_agent = _make_agent_mock()

    def _load_agent_side_effect(name):
        if name == "deleted-custom-agent":
            raise ValueError(f"Unknown agent {name!r}")
        return fallback_agent

    with (
        patch(
            "code_puppy.api.session_context.load_agent",
            side_effect=_load_agent_side_effect,
        ),
        patch(
            "code_puppy.api.session_context.get_global_model_name",
            return_value="gpt-4o",
        ),
    ):
        ctx = await mgr.load_session("fallback-session")

    assert ctx is not None
    assert ctx.agent_name == "code-puppy"
    assert ctx.agent is fallback_agent


@pytest.mark.asyncio
async def test_load_session_valid_created_at_parsed():
    """A valid ISO created_at string in DB meta is parsed into a datetime."""
    mgr = _make_fresh_manager()
    iso = "2026-03-15T09:30:00+00:00"
    db_meta = _make_session_row(created_at=iso)
    mgr._load_from_sqlite = AsyncMock(return_value=([], db_meta))

    with (
        patch(
            "code_puppy.api.session_context.load_agent", return_value=_make_agent_mock()
        ),
        patch(
            "code_puppy.api.session_context.get_global_model_name",
            return_value="gpt-4o",
        ),
    ):
        ctx = await mgr.load_session("dated-session")

    assert ctx is not None
    expected = datetime.fromisoformat(iso)
    assert ctx.created_at == expected


@pytest.mark.asyncio
async def test_load_session_malformed_created_at_falls_back_to_now():
    """A malformed created_at string results in datetime.now() being used."""
    mgr = _make_fresh_manager()
    db_meta = _make_session_row(created_at="not-a-date")
    mgr._load_from_sqlite = AsyncMock(return_value=([], db_meta))
    before = datetime.now(timezone.utc)

    with (
        patch(
            "code_puppy.api.session_context.load_agent", return_value=_make_agent_mock()
        ),
        patch(
            "code_puppy.api.session_context.get_global_model_name",
            return_value="gpt-4o",
        ),
    ):
        ctx = await mgr.load_session("bad-date-session")

    after = datetime.now(timezone.utc)
    assert ctx is not None
    assert before <= ctx.created_at <= after, "created_at should be close to now()"


@pytest.mark.asyncio
async def test_load_session_empty_created_at_falls_back_to_now():
    """An empty created_at string also results in datetime.now() being used."""
    mgr = _make_fresh_manager()
    db_meta = _make_session_row(created_at="")
    mgr._load_from_sqlite = AsyncMock(return_value=([], db_meta))
    before = datetime.now(timezone.utc)

    with (
        patch(
            "code_puppy.api.session_context.load_agent", return_value=_make_agent_mock()
        ),
        patch(
            "code_puppy.api.session_context.get_global_model_name",
            return_value="gpt-4o",
        ),
    ):
        ctx = await mgr.load_session("empty-date-session")

    after = datetime.now(timezone.utc)
    assert ctx is not None
    assert before <= ctx.created_at <= after
