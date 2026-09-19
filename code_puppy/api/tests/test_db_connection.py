from __future__ import annotations

import sqlite3

import pytest


@pytest.mark.asyncio
async def test_init_db_creates_sessions_project_id_column(tmp_path, monkeypatch):
    from code_puppy.api.db.connection import close_db, get_db, init_db

    db_path = tmp_path / "chat_messages.db"
    monkeypatch.setenv("PUPPY_DESK_DB", str(db_path))

    await init_db()
    db = get_db()
    cursor = await db.execute("PRAGMA table_info(sessions)")
    rows = await cursor.fetchall()
    await close_db()

    column_names = {row[1] for row in rows}
    assert "project_id" in column_names


@pytest.mark.asyncio
async def test_init_db_rejects_old_prerelease_schema(tmp_path, monkeypatch):
    from code_puppy.api.db.connection import close_db, init_db

    db_path = tmp_path / "chat_messages.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA user_version = 5")
    conn.commit()
    conn.close()

    monkeypatch.setenv("PUPPY_DESK_DB", str(db_path))

    with pytest.raises(
        RuntimeError, match="Unsupported pre-release WS session DB schema"
    ):
        await init_db()

    await close_db()
