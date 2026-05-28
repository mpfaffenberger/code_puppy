"""SQLite connection singleton using aiosqlite for non-blocking async access.

The Desk Puppy Electron FE owns the schema (creates it at user_version=2).
This module opens the same database from the Python BE, runs any needed
migrations if the FE hasn't run yet, and exposes get_db() / init_db() /
close_db() for use by queries.py and the seeder.

Schema versions:
  0 = no schema yet (fresh DB)
  1 = added token_count, compacted, pydantic_json, compaction_log_id to messages
  2 = added deleted_at to sessions (soft delete)
  3 = rebuilt messages table with UNIQUE(session_id, seq) + dedup
  4 = backfill blank agent_name / model_name in messages + tool_calls from session defaults

Concurrency:
  aiosqlite serialises all DB operations through its own internal background
  thread — no threading.Lock required.  All callers simply await the relevant
  coroutine; the event loop is never blocked.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_PUPPY_DESK_DB_ENV = "PUPPY_DESK_DB"


def get_db_path() -> Path:
    """Return path to the shared SQLite database.

    Override with PUPPY_DESK_DB env var for testing.
    """
    env = os.environ.get(_PUPPY_DESK_DB_ENV)
    if env:
        return Path(env)
    return Path.home() / ".puppy_desk" / "chat_messages.db"


# ---------------------------------------------------------------------------
# Full schema (v4) — created on first BE run if FE hasn't seeded it yet
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id       TEXT PRIMARY KEY,
    title            TEXT DEFAULT '',
    agent_name       TEXT DEFAULT 'code-puppy',
    model_name       TEXT DEFAULT '',
    working_directory TEXT DEFAULT '',
    pinned           INTEGER DEFAULT 0,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    message_count    INTEGER DEFAULT 0,
    total_tokens     INTEGER DEFAULT 0,
    deleted_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_deleted ON sessions(deleted_at);

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

# Migrations applied to existing databases that are below SCHEMA_VERSION
_MIGRATION_V0_TO_V1: list[str] = [
    "ALTER TABLE messages ADD COLUMN token_count INTEGER DEFAULT 0",
    "ALTER TABLE messages ADD COLUMN compacted INTEGER DEFAULT 0",
    "ALTER TABLE messages ADD COLUMN pydantic_json TEXT",
    "ALTER TABLE messages ADD COLUMN compaction_log_id INTEGER REFERENCES compaction_log(id) ON DELETE SET NULL",
]

_MIGRATION_V1_TO_V2: list[str] = [
    "ALTER TABLE sessions ADD COLUMN deleted_at TEXT",
]

# v3: Rebuild messages table to add UNIQUE(session_id, seq).
# SQLite cannot add UNIQUE constraints via ALTER TABLE, so we must rebuild.
_MIGRATION_V2_TO_V3_SQL = """
PRAGMA foreign_keys = OFF;
BEGIN;

CREATE TABLE messages_v3 (
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

INSERT INTO messages_v3
SELECT id, session_id, seq, role, content, type, agent_name, model_name,
       timestamp, thinking, attachments_json, clean_content,
       system_message_type, system_message_path,
       token_count, compacted, pydantic_json, compaction_log_id
FROM messages AS m1
WHERE id = (
    SELECT id FROM messages AS m2
    WHERE m2.session_id = m1.session_id AND m2.seq = m1.seq
    ORDER BY
        (m2.clean_content IS NOT NULL) DESC,
        (m2.pydantic_json  IS NOT NULL) DESC,
        m2.id DESC
    LIMIT 1
);

DROP TABLE messages;
ALTER TABLE messages_v3 RENAME TO messages;

CREATE INDEX IF NOT EXISTS idx_messages_session_seq ON messages(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_messages_active ON messages(session_id, compacted);

COMMIT;
PRAGMA foreign_keys = ON;
""".strip()

SCHEMA_VERSION = 5

# ---------------------------------------------------------------------------
# Async singleton (aiosqlite)
# ---------------------------------------------------------------------------

_aconn: Optional[aiosqlite.Connection] = None


async def init_db() -> None:
    """Open the database and ensure schema is at SCHEMA_VERSION.

    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _aconn

    if _aconn is not None:
        return  # already initialised

    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Opening aiosqlite DB at %s", db_path)
    _aconn = await aiosqlite.connect(str(db_path))
    _aconn.row_factory = aiosqlite.Row

    # Performance + safety pragmas
    await _aconn.execute("PRAGMA journal_mode = WAL")
    await _aconn.execute("PRAGMA foreign_keys = ON")
    await _aconn.execute("PRAGMA busy_timeout = 5000")

    cursor = await _aconn.execute("PRAGMA user_version")
    row = await cursor.fetchone()
    current_version: int = row[0]

    if current_version == 0:
        # Fresh database — create everything at the current schema version
        await _aconn.executescript(_SCHEMA_SQL)
        await _aconn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        await _aconn.commit()
        logger.info(
            "\u2713 aiosqlite DB created (schema v%d) at %s", SCHEMA_VERSION, db_path
        )
    else:
        # Existing database — run incremental migrations
        await _run_alters_and_migrate(current_version)


async def _run_alters_and_migrate(current_version: int) -> None:
    """Apply all pending schema migrations in order."""
    assert _aconn is not None

    if current_version < 1:
        await _run_alters(_MIGRATION_V0_TO_V1)
        await _aconn.execute("PRAGMA user_version = 1")
        await _aconn.commit()
        logger.info("\u2713 aiosqlite DB migrated v0 \u2192 v1")

    if current_version < 2:
        await _run_alters(_MIGRATION_V1_TO_V2)
        # Also create compaction_log and its index if missing (v0 DBs)
        await _aconn.execute("""
            CREATE TABLE IF NOT EXISTS compaction_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                summary_text TEXT NOT NULL,
                source_start INTEGER NOT NULL,
                source_end INTEGER NOT NULL,
                source_count INTEGER NOT NULL,
                source_tokens INTEGER NOT NULL,
                summary_tokens INTEGER NOT NULL,
                strategy TEXT DEFAULT 'summarization',
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            )
        """)
        await _aconn.execute(
            "CREATE INDEX IF NOT EXISTS idx_compaction_session ON compaction_log(session_id)"
        )
        await _aconn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_deleted ON sessions(deleted_at)"
        )
        await _aconn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_active ON messages(session_id, compacted)"
        )
        await _aconn.execute("PRAGMA user_version = 2")
        await _aconn.commit()
        logger.info("\u2713 aiosqlite DB migrated to v2")

    if current_version < 3:
        logger.info(
            "Running v2\u21923 migration: rebuilding messages table with UNIQUE(session_id, seq)..."
        )
        await _aconn.executescript(_MIGRATION_V2_TO_V3_SQL)
        await _aconn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        await _aconn.commit()
        cursor = await _aconn.execute("SELECT COUNT(*) FROM messages")
        row = await cursor.fetchone()
        count = row[0]
        logger.info(
            "\u2713 aiosqlite DB migrated to v%d (%d messages after dedup)",
            SCHEMA_VERSION,
            count,
        )

    if current_version < 4:
        logger.info(
            "Running v3\u2192v4 migration: backfilling blank agent_name/model_name \u2026"
        )
        await _aconn.executescript("""
            -- messages: blank agent_name → session.agent_name
            UPDATE messages
            SET    agent_name = (
                       SELECT s.agent_name
                       FROM   sessions s
                       WHERE  s.session_id = messages.session_id
                   )
            WHERE  (agent_name IS NULL OR agent_name = '')
              AND  (
                       SELECT COALESCE(s.agent_name, '')
                       FROM   sessions s
                       WHERE  s.session_id = messages.session_id
                   ) != '';

            -- messages: blank model_name → session.model_name
            UPDATE messages
            SET    model_name = (
                       SELECT s.model_name
                       FROM   sessions s
                       WHERE  s.session_id = messages.session_id
                   )
            WHERE  (model_name IS NULL OR model_name = '')
              AND  (
                       SELECT COALESCE(s.model_name, '')
                       FROM   sessions s
                       WHERE  s.session_id = messages.session_id
                   ) != '';

            -- tool_calls: blank agent_name → session.agent_name
            UPDATE tool_calls
            SET    agent_name = (
                       SELECT s.agent_name
                       FROM   sessions s
                       WHERE  s.session_id = tool_calls.session_id
                   )
            WHERE  (agent_name IS NULL OR agent_name = '')
              AND  (
                       SELECT COALESCE(s.agent_name, '')
                       FROM   sessions s
                       WHERE  s.session_id = tool_calls.session_id
                   ) != '';

            -- tool_calls: blank model_name → session.model_name
            UPDATE tool_calls
            SET    model_name = (
                       SELECT s.model_name
                       FROM   sessions s
                       WHERE  s.session_id = tool_calls.session_id
                   )
            WHERE  (model_name IS NULL OR model_name = '')
              AND  (
                       SELECT COALESCE(s.model_name, '')
                       FROM   sessions s
                       WHERE  s.session_id = tool_calls.session_id
                   ) != '';
        """)
        await _aconn.execute("PRAGMA user_version = 4")
        await _aconn.commit()
        cursor = await _aconn.execute(
            "SELECT COUNT(*) FROM messages WHERE agent_name != '' AND model_name != ''"
        )
        row = await cursor.fetchone()
        msg_count = row[0]
        logger.info(
            "\u2713 aiosqlite DB migrated to v4 (%d messages with agent+model)",
            msg_count,
        )

    if current_version < 5:
        logger.info(
            "Running v4\u2192v5 migration: backfilling pydantic_json for NULL rows \u2026"
        )
        from code_puppy.api.db.backfill import backfill_pydantic_json

        updated, skipped = await backfill_pydantic_json(_aconn)
        await _aconn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        await _aconn.commit()
        logger.info(
            "\u2713 aiosqlite DB migrated to v5 "
            "(%d pydantic_json rows backfilled, %d skipped)",
            updated,
            skipped,
        )

    logger.info("\u2713 aiosqlite DB ready (schema v%d)", SCHEMA_VERSION)


async def _run_alters(statements: list[str]) -> None:
    """Run ALTER TABLE statements, skipping 'duplicate column' errors gracefully."""
    assert _aconn is not None
    for sql in statements:
        try:
            await _aconn.execute(sql)
        except Exception as exc:
            if "duplicate column" in str(exc).lower():
                logger.debug("Skipping already-applied migration: %s", sql)
            else:
                raise


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
