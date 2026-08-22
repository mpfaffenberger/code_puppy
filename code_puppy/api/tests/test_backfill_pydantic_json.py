"""Unit tests for code_puppy.api.db.backfill.backfill_pydantic_json.

All tests spin up a real in-memory aiosqlite database with the minimal schema
needed — no mocking of the DB layer, no patching of pydantic-ai.  The goal
is to exercise the actual serialisation round-trip so we catch pydantic-ai
API changes as early as possible.

Test inventory
--------------
 1.  Empty table              → (0, 0) returned, no crash
 2.  All rows already filled  → (0, 0), nothing overwritten
 3.  User message backfilled  → pydantic_json set, deserialises to ModelRequest
 4.  Assistant message backf. → pydantic_json set, deserialises to ModelResponse
 5.  System rows skipped      → pydantic_json remains NULL
 6.  Compacted rows skipped   → pydantic_json remains NULL
 7.  Mixed NULL + non-NULL    → only NULL rows updated
 8.  Empty content string     → backfilled with empty UserPromptPart (no crash)
 9.  Idempotent (run twice)   → second run updates 0 rows
10.  Batch splitting          → batch_size=2 with 5 rows all updated correctly
11.  Serialised JSON is valid → round-trips through ModelMessagesTypeAdapter
12.  _build_message bad role  → raises ValueError
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# In-memory DB fixture
# ---------------------------------------------------------------------------

_CREATE_MESSAGES = """
CREATE TABLE messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT    NOT NULL,
    seq          INTEGER NOT NULL,
    role         TEXT    NOT NULL,
    content      TEXT    DEFAULT '',
    model_name   TEXT    DEFAULT '',
    compacted    INTEGER DEFAULT 0,
    pydantic_json TEXT
);
"""


async def _make_db():
    """Return an open in-memory aiosqlite connection with the messages table."""
    import aiosqlite

    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.execute(_CREATE_MESSAGES)
    await db.commit()
    return db


async def _insert(
    db,
    *,
    session_id: str = "s1",
    seq: int = 1,
    role: str = "user",
    content: str = "hello",
    model_name: str = "gpt-4o",
    compacted: int = 0,
    pydantic_json: str | None = None,
) -> int:
    """Insert one row and return its id."""
    cursor = await db.execute(
        """
        INSERT INTO messages (session_id, seq, role, content, model_name, compacted, pydantic_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (session_id, seq, role, content, model_name, compacted, pydantic_json),
    )
    await db.commit()
    return cursor.lastrowid


async def _fetch_pj(db, row_id: int) -> str | None:
    """Fetch pydantic_json for a specific row id."""
    cursor = await db.execute(
        "SELECT pydantic_json FROM messages WHERE id = ?", (row_id,)
    )
    row = await cursor.fetchone()
    return row["pydantic_json"] if row else None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_table_returns_zero_counts():
    """No rows → (0, 0) with no crash."""
    from code_puppy.api.db.backfill import backfill_pydantic_json

    db = await _make_db()
    updated, skipped = await backfill_pydantic_json(db)
    await db.close()

    assert updated == 0
    assert skipped == 0


@pytest.mark.asyncio
async def test_all_rows_already_filled_returns_zero_counts():
    """Rows with existing pydantic_json are not touched."""
    from code_puppy.api.db.backfill import backfill_pydantic_json

    db = await _make_db()
    existing_pj = '{"already": "there"}'
    await _insert(db, pydantic_json=existing_pj)

    updated, skipped = await backfill_pydantic_json(db)
    await db.close()

    assert updated == 0
    assert skipped == 0


@pytest.mark.asyncio
async def test_user_message_backfilled_to_model_request():
    """A user row with NULL pydantic_json is backfilled with a ModelRequest."""
    from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest

    from code_puppy.api.db.backfill import backfill_pydantic_json

    db = await _make_db()
    row_id = await _insert(db, role="user", content="hello world", pydantic_json=None)

    updated, skipped = await backfill_pydantic_json(db)

    pj = await _fetch_pj(db, row_id)
    await db.close()

    assert updated == 1
    assert skipped == 0
    assert pj is not None

    # Round-trip check
    msgs = ModelMessagesTypeAdapter.validate_json(pj)
    assert len(msgs) == 1
    assert isinstance(msgs[0], ModelRequest)
    # Content preserved
    content_parts = [p.content for p in msgs[0].parts if hasattr(p, "content")]
    assert "hello world" in content_parts


@pytest.mark.asyncio
async def test_assistant_message_backfilled_to_model_response():
    """An assistant row with NULL pydantic_json is backfilled with a ModelResponse."""
    from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse

    from code_puppy.api.db.backfill import backfill_pydantic_json

    db = await _make_db()
    row_id = await _insert(
        db,
        role="assistant",
        content="here is my answer",
        model_name="claude-3",
        pydantic_json=None,
    )

    updated, skipped = await backfill_pydantic_json(db)

    pj = await _fetch_pj(db, row_id)
    await db.close()

    assert updated == 1
    assert skipped == 0
    assert pj is not None

    msgs = ModelMessagesTypeAdapter.validate_json(pj)
    assert len(msgs) == 1
    assert isinstance(msgs[0], ModelResponse)
    content_parts = [p.content for p in msgs[0].parts if hasattr(p, "content")]
    assert "here is my answer" in content_parts


@pytest.mark.asyncio
async def test_system_rows_are_skipped():
    """Rows with role='system' are excluded from the backfill query."""
    from code_puppy.api.db.backfill import backfill_pydantic_json

    db = await _make_db()
    row_id = await _insert(
        db, role="system", content="you are helpful", pydantic_json=None
    )

    updated, skipped = await backfill_pydantic_json(db)
    pj = await _fetch_pj(db, row_id)
    await db.close()

    assert updated == 0
    assert skipped == 0
    assert pj is None, "system rows must stay NULL"


@pytest.mark.asyncio
async def test_compacted_rows_are_skipped():
    """Rows with compacted=1 are excluded from the backfill query."""
    from code_puppy.api.db.backfill import backfill_pydantic_json

    db = await _make_db()
    row_id = await _insert(
        db, role="user", content="old message", compacted=1, pydantic_json=None
    )

    updated, skipped = await backfill_pydantic_json(db)
    pj = await _fetch_pj(db, row_id)
    await db.close()

    assert updated == 0
    assert skipped == 0
    assert pj is None, "compacted rows must stay NULL"


@pytest.mark.asyncio
async def test_mixed_null_and_filled_rows():
    """Only NULL rows are updated; already-filled rows are untouched."""
    from code_puppy.api.db.backfill import backfill_pydantic_json

    db = await _make_db()
    existing_pj = '{"sentinel": true}'

    id_null = await _insert(db, seq=1, pydantic_json=None)
    id_filled = await _insert(db, seq=2, pydantic_json=existing_pj)

    updated, skipped = await backfill_pydantic_json(db)

    pj_null = await _fetch_pj(db, id_null)
    pj_filled = await _fetch_pj(db, id_filled)
    await db.close()

    assert updated == 1
    assert pj_null is not None, "NULL row should have been filled"
    assert pj_filled == existing_pj, "Already-filled row must not be overwritten"


@pytest.mark.asyncio
async def test_empty_content_backfilled_without_crash():
    """Empty string content produces a valid pydantic_json (no crash)."""
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    from code_puppy.api.db.backfill import backfill_pydantic_json

    db = await _make_db()
    row_id = await _insert(db, role="user", content="", pydantic_json=None)

    updated, skipped = await backfill_pydantic_json(db)
    pj = await _fetch_pj(db, row_id)
    await db.close()

    assert updated == 1
    assert skipped == 0
    assert pj is not None
    # Must be parseable
    msgs = ModelMessagesTypeAdapter.validate_json(pj)
    assert len(msgs) == 1


@pytest.mark.asyncio
async def test_idempotent_second_run_updates_nothing():
    """Running the backfill twice produces updated=0 on the second run."""
    from code_puppy.api.db.backfill import backfill_pydantic_json

    db = await _make_db()
    await _insert(db, role="user", content="test", pydantic_json=None)

    updated1, _ = await backfill_pydantic_json(db)
    updated2, _ = await backfill_pydantic_json(db)
    await db.close()

    assert updated1 == 1
    assert updated2 == 0, "Second run must be a no-op"


@pytest.mark.asyncio
async def test_batch_splitting_all_rows_updated():
    """batch_size=2 with 5 rows — all rows must be updated correctly."""
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    from code_puppy.api.db.backfill import backfill_pydantic_json

    db = await _make_db()
    row_ids = []
    for i in range(5):
        rid = await _insert(
            db,
            seq=i + 1,
            role="user",
            content=f"message {i}",
            pydantic_json=None,
        )
        row_ids.append(rid)

    updated, skipped = await backfill_pydantic_json(db, batch_size=2)

    for rid in row_ids:
        pj = await _fetch_pj(db, rid)
        assert pj is not None, f"Row {rid} should have been backfilled"
        msgs = ModelMessagesTypeAdapter.validate_json(pj)
        assert len(msgs) == 1

    await db.close()
    assert updated == 5
    assert skipped == 0


@pytest.mark.asyncio
async def test_serialised_json_round_trips_correctly():
    """The generated pydantic_json must survive a full serialise → deserialise cycle."""
    from pydantic_ai.messages import (
        ModelMessagesTypeAdapter,
        ModelRequest,
        UserPromptPart,
    )

    from code_puppy.api.db.backfill import backfill_pydantic_json

    original_content = "does this survive the round trip? 🐶"
    db = await _make_db()
    row_id = await _insert(
        db, role="user", content=original_content, pydantic_json=None
    )

    await backfill_pydantic_json(db)
    pj = await _fetch_pj(db, row_id)
    await db.close()

    msgs = ModelMessagesTypeAdapter.validate_json(pj)
    assert isinstance(msgs[0], ModelRequest)
    prompt_parts = [p for p in msgs[0].parts if isinstance(p, UserPromptPart)]
    assert len(prompt_parts) == 1
    assert prompt_parts[0].content == original_content


def test_build_message_bad_role_raises():
    """_build_message raises ValueError for unsupported roles."""
    from code_puppy.api.db.backfill import _build_message

    with pytest.raises(ValueError, match="Unsupported role"):
        _build_message("system", "content", "model")

    with pytest.raises(ValueError, match="Unsupported role"):
        _build_message("tool", "content", "model")
