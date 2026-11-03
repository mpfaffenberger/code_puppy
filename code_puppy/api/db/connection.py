"""SQLite connection singleton for the pre-release WS session database.

This feature has not shipped to users yet, so we intentionally keep the schema
policy boring: one canonical schema, one user_version, zero migration archaeology.
If a developer has an older pre-release database, they should delete it and let
Code Puppy recreate it from scratch.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

_PUPPY_DESK_DB_ENV = "PUPPY_DESK_DB"
SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id         TEXT PRIMARY KEY,
    title              TEXT DEFAULT '',
    project_id         TEXT DEFAULT '',
    agent_name         TEXT DEFAULT 'code-puppy',
    model_name         TEXT DEFAULT '',
    working_directory  TEXT DEFAULT '',
    pinned             INTEGER DEFAULT 0,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    message_count      INTEGER DEFAULT 0,
    total_tokens       INTEGER DEFAULT 0,
    deleted_at         TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_deleted ON sessions(deleted_at);
CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id);

CREATE TABLE IF NOT EXISTS compaction_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL,
    summary_text   TEXT NOT NULL,
    source_start   INTEGER NOT NULL,
    source_end     INTEGER NOT NULL,
    source_count   INTEGER NOT NULL,
    source_tokens  INTEGER NOT NULL,
    summary_tokens INTEGER NOT NULL,
    strategy       TEXT DEFAULT 'summarization',
    created_at     TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_compaction_session ON compaction_log(session_id);

CREATE TABLE IF NOT EXISTS messages (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT NOT NULL,
    seq                 INTEGER NOT NULL,
    role                TEXT NOT NULL,
    content             TEXT DEFAULT '',
    type                TEXT DEFAULT '',
    agent_name          TEXT DEFAULT '',
    model_name          TEXT DEFAULT '',
    timestamp           TEXT NOT NULL,
    thinking            TEXT,
    attachments_json    TEXT,
    clean_content       TEXT,
    system_message_type TEXT,
    system_message_path TEXT,
    token_count         INTEGER DEFAULT 0,
    compacted           INTEGER DEFAULT 0,
    pydantic_json       TEXT,
    compaction_log_id   INTEGER REFERENCES compaction_log(id) ON DELETE SET NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    UNIQUE(session_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_messages_session_seq ON messages(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_messages_active ON messages(session_id, compacted);

CREATE TABLE IF NOT EXISTS tool_calls (
    id                 TEXT PRIMARY KEY,
    session_id         TEXT NOT NULL,
    parent_message_seq INTEGER,
    seq                INTEGER NOT NULL,
    tool_name          TEXT NOT NULL,
    args_json          TEXT,
    result_json        TEXT,
    status             TEXT DEFAULT 'running',
    duration_ms        INTEGER,
    error_text         TEXT,
    agent_name         TEXT DEFAULT '',
    model_name         TEXT DEFAULT '',
    timestamp          REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_tool_calls_session_seq ON tool_calls(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_tool_calls_parent ON tool_calls(parent_message_seq);
"""

_aconn: Optional[aiosqlite.Connection] = None


def get_db_path() -> Path:
    """Return path to the shared SQLite database.

    Override with PUPPY_DESK_DB env var for testing.
    """
    env = os.environ.get(_PUPPY_DESK_DB_ENV)
    if env:
        return Path(env)
    return Path.home() / ".puppy_desk" / "chat_messages.db"


async def init_db() -> None:
    """Open the database and ensure the canonical pre-release schema exists."""
    global _aconn

    if _aconn is not None:
        return

    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Opening aiosqlite DB at %s", db_path)
    _aconn = await aiosqlite.connect(str(db_path))
    _aconn.row_factory = aiosqlite.Row

    await _aconn.execute("PRAGMA journal_mode = WAL")
    await _aconn.execute("PRAGMA foreign_keys = ON")
    await _aconn.execute("PRAGMA busy_timeout = 5000")

    cursor = await _aconn.execute("PRAGMA user_version")
    row = await cursor.fetchone()
    current_version = int(row[0]) if row else 0

    if current_version not in {0, SCHEMA_VERSION}:
        raise RuntimeError(
            "Unsupported pre-release WS session DB schema "
            f"v{current_version} at {db_path}. Delete the database and restart "
            "to recreate it with the current schema."
        )

    await _aconn.executescript(_SCHEMA_SQL)
    if current_version != SCHEMA_VERSION:
        await _aconn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    await _aconn.commit()

    logger.info(" aiosqlite DB ready (schema v%d)", SCHEMA_VERSION)


def get_db() -> aiosqlite.Connection:
    """Return the open aiosqlite connection.

    Raises RuntimeError if init_db() has not been awaited.
    """
    if _aconn is None:
        raise RuntimeError(
            "aiosqlite DB not initialised — call `await init_db()` first"
        )
    return _aconn


async def close_db() -> None:
    """Close the database connection. Called during app shutdown."""
    global _aconn
    if _aconn is not None:
        await _aconn.close()
        _aconn = None
        logger.info("aiosqlite DB closed")
