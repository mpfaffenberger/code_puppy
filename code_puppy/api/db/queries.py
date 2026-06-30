"""Typed async query helpers for the shared chat_messages.db.

All functions are coroutines.  aiosqlite serialises writes internally via its
own background thread — no threading.Lock is needed here.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from code_puppy.api.db.connection import get_db
from code_puppy.api.db.sql_loader import load_sql

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


async def session_exists(session_id: str) -> bool:
    """Return True if a session row already exists (regardless of deleted_at)."""
    db = get_db()
    cursor = await db.execute(
        "SELECT 1 FROM sessions WHERE session_id = ? LIMIT 1", (session_id,)
    )
    row = await cursor.fetchone()
    return row is not None


async def get_session_row(session_id: str) -> Optional[dict]:
    """Return the full session row as a plain dict, or None if not found.

    Non-fatal: returns None on any exception (DB unavailable, etc.).
    """
    try:
        db = get_db()
        cursor = await db.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    except Exception:
        return None


async def get_session_metadata(session_id: str) -> Optional[dict]:
    """Return a subset of session columns useful for the chat handler.

    Returns keys: session_id, title, agent_name, model_name,
    working_directory, pinned, created_at — or None if not found.
    Non-fatal: returns None on any exception.
    """
    try:
        db = get_db()
        cursor = await db.execute(
            """
            SELECT session_id, title, agent_name, model_name,
                   working_directory, pinned, created_at
            FROM sessions
            WHERE session_id = ?
            """,
            (session_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)
    except Exception:
        return None


async def upsert_session(
    *,
    session_id: str,
    title: str = "",
    agent_name: str = "code-puppy",
    model_name: str = "",
    working_directory: str = "",
    pinned: bool = False,
    created_at: str,
    updated_at: str,
    message_count: int = 0,
    total_tokens: int = 0,
    deleted_at: Optional[str] = None,
) -> None:
    """Insert or replace a session row."""
    db = get_db()
    try:
        await db.execute(
            """
            INSERT INTO sessions
                (session_id, title, agent_name, model_name, working_directory,
                 pinned, created_at, updated_at, message_count, total_tokens, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                title          = excluded.title,
                agent_name     = excluded.agent_name,
                model_name     = excluded.model_name,
                working_directory = excluded.working_directory,
                pinned         = excluded.pinned,
                updated_at     = excluded.updated_at,
                message_count  = excluded.message_count,
                total_tokens   = excluded.total_tokens,
                deleted_at     = COALESCE(sessions.deleted_at, excluded.deleted_at)
            """,
            (
                session_id,
                title,
                agent_name,
                model_name,
                working_directory,
                1 if pinned else 0,
                created_at,
                updated_at,
                message_count,
                total_tokens,
                deleted_at,
            ),
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def update_session_stats(
    session_id: str,
    *,
    message_count: int,
    total_tokens: int,
    updated_at: str,
) -> None:
    """Bump message_count, total_tokens, and updated_at after a save."""
    db = get_db()
    try:
        await db.execute(
            """
            UPDATE sessions
            SET message_count = ?, total_tokens = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (message_count, total_tokens, updated_at, session_id),
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def update_session_working_directory(
    session_id: str,
    working_directory: str,
    updated_at: str,
) -> None:
    """Update only the working_directory and updated_at columns for a session.

    Narrow UPDATE — does not touch title, agent, model, pinned, counts, etc.
    Called after a successful set_working_directory WS message.
    """
    db = get_db()
    await db.execute(
        "UPDATE sessions SET working_directory = ?, updated_at = ? WHERE session_id = ?",
        (working_directory, updated_at, session_id),
    )
    await db.commit()


async def update_session_meta_fields(
    session_id: str,
    *,
    title: str,
    pinned: bool,
    updated_at: str,
) -> None:
    """Update only title, pinned, and updated_at for an existing session.

    Narrow UPDATE — does NOT touch message_count, total_tokens, agent_name,
    model_name, or working_directory.  Called by the update_session_meta WS
    message handler (user renames or pins/unpins a session).
    """
    db = get_db()
    await db.execute(
        "UPDATE sessions SET title = ?, pinned = ?, updated_at = ? WHERE session_id = ?",
        (title, 1 if pinned else 0, updated_at, session_id),
    )
    await db.commit()


async def soft_delete_session(session_id: str, deleted_at: str) -> None:
    """Set deleted_at on a session (soft delete). Data is preserved."""
    db = get_db()
    await db.execute(
        "UPDATE sessions SET deleted_at = ? WHERE session_id = ?",
        (deleted_at, session_id),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


async def get_next_seq(session_id: str) -> int:
    """Return the next available seq number for a session (1-based)."""
    db = get_db()
    cursor = await db.execute(
        "SELECT COALESCE(MAX(seq), 0) FROM messages WHERE session_id = ?",
        (session_id,),
    )
    row = await cursor.fetchone()
    return (row[0] or 0) + 1


async def _insert_immediate_message_and_sync_session(
    *,
    session_id: str,
    role: str,
    content: str,
    type: str,
    agent_name: str = "",
    model_name: str = "",
    timestamp: str,
    thinking: Optional[str] = None,
    attachments_json: Optional[str] = None,
    clean_content: Optional[str] = None,
    system_message_type: Optional[str] = None,
    system_message_path: Optional[str] = None,
    token_count: int = 0,
    increment_message_count: bool = True,
) -> int:
    """Insert an immediate WS message and sync session metadata atomically.

    This path is used for system/error frames that must persist immediately,
    outside the normal end-of-turn batch save. The session row is created if
    needed, the next seq is allocated atomically, the message row is inserted,
    and session metadata is updated in the same transaction so
    message_count/updated_at cannot drift.

    increment_message_count controls whether the sessions.message_count should
    track this row. Persisted system banners/config rows should not affect the
    user-visible chat turn count, while persisted error rows should.
    """
    db = get_db()
    try:
        await db.execute("BEGIN IMMEDIATE")
        cursor = await db.execute(
            "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
        )
        existing = await cursor.fetchone()
        if not existing:
            await db.execute(
                """
                INSERT INTO sessions
                    (session_id, title, agent_name, model_name, working_directory,
                     pinned, created_at, updated_at, message_count, total_tokens, deleted_at)
                VALUES (?, '', ?, ?, '', 0, ?, ?, 0, 0, NULL)
                """,
                (
                    session_id,
                    agent_name or "code-puppy",
                    model_name or "",
                    timestamp,
                    timestamp,
                ),
            )

        cursor = await db.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM messages WHERE session_id = ?",
            (session_id,),
        )
        seq_row = await cursor.fetchone()
        seq = int(seq_row["next_seq"] if seq_row is not None else 1)

        await db.execute(
            """
            INSERT INTO messages
                (session_id, seq, role, content, type, agent_name, model_name,
                 timestamp, thinking, attachments_json, clean_content,
                 system_message_type, system_message_path,
                 token_count, compacted, pydantic_json, compaction_log_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL)
            """,
            (
                session_id,
                seq,
                role,
                content,
                type,
                agent_name,
                model_name,
                timestamp,
                thinking,
                attachments_json,
                clean_content,
                system_message_type,
                system_message_path,
                token_count,
            ),
        )
        await db.execute(
            """
            UPDATE sessions
            SET message_count = COALESCE(message_count, 0) + ?,
                total_tokens = COALESCE(total_tokens, 0) + ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (
                1 if increment_message_count else 0,
                token_count,
                timestamp,
                session_id,
            ),
        )
        await db.commit()
        return seq
    except Exception:
        await db.rollback()
        raise


async def write_system_message_to_sqlite(
    *,
    session_id: str,
    system_message_type: str,
    content: str,
    system_message_path: str = "",
    agent_name: str = "",
    model_name: str = "",
    timestamp: Optional[str] = None,
) -> None:
    """Write a single system-event row to SQLite immediately.

    Used by the WS chat handler to persist agent/model switches, CWD changes,
    and new-session initialisation messages so the FE cold-load path sees them
    without relying on ephemeral WS-only state.

    For directory banners, deduplicates to avoid multiple banners for the same path.
    """
    import datetime as _dt

    ts = timestamp or _dt.datetime.now(_dt.timezone.utc).isoformat()

    # Dedup: for directory system messages, check if one already exists with same path
    if system_message_type == "directory" and system_message_path:
        try:
            db = get_db()
            cursor = await db.execute(
                """
                SELECT 1 FROM messages
                WHERE session_id = ?
                  AND system_message_type = 'directory'
                  AND system_message_path = ?
                LIMIT 1
                """,
                (session_id, system_message_path),
            )
            existing = await cursor.fetchone()
            if existing:
                import logging

                logging.getLogger(__name__).debug(
                    "Skipping duplicate directory banner: session=%s path=%s",
                    session_id,
                    system_message_path,
                )
                return  # Already have a banner for this path
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning("Directory dedup check failed: %s", e)
            # Continue with insert on error

    try:
        await _insert_immediate_message_and_sync_session(
            session_id=session_id,
            role="system",
            content=content,
            type="system",
            agent_name=agent_name,
            model_name=model_name,
            timestamp=ts,
            system_message_type=system_message_type,
            system_message_path=system_message_path,
            increment_message_count=False,
        )
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "write_system_message_to_sqlite failed (session=%s type=%s): %s",
            session_id,
            system_message_type,
            exc,
            exc_info=True,
        )


async def write_error_message_to_sqlite(
    *,
    session_id: str,
    error: str,
    error_type: str = "unknown",
    technical_details: str = "",
    action_required: Optional[str] = None,
    agent_name: str = "",
    model_name: str = "",
    timestamp: Optional[str] = None,
) -> None:
    """Write a structured error row to SQLite immediately.

    Error rows are stored as regular message rows with type='error' so they
    survive session reloads. The structured payload is serialized into
    attachments_json for the read path to reconstruct for the frontend.
    """
    import datetime as _dt

    ts = timestamp or _dt.datetime.now(_dt.timezone.utc).isoformat()
    payload = {
        "error": error,
        "error_type": error_type,
        "technical_details": technical_details,
        "action_required": action_required,
        "session_id": session_id,
    }

    try:
        await _insert_immediate_message_and_sync_session(
            session_id=session_id,
            role="system",
            content=error,
            type="error",
            agent_name=agent_name,
            model_name=model_name,
            timestamp=ts,
            clean_content=error,
            attachments_json=json.dumps(payload),
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "write_error_message_to_sqlite failed (session=%s error_type=%s): %s",
            session_id,
            error_type,
            exc,
            exc_info=True,
        )


async def insert_message(
    *,
    session_id: str,
    seq: int,
    role: str,
    content: str = "",
    type: str = "",
    agent_name: str = "",
    model_name: str = "",
    timestamp: str,
    thinking: Optional[str] = None,
    attachments_json: Optional[str] = None,
    clean_content: Optional[str] = None,
    system_message_type: Optional[str] = None,
    system_message_path: Optional[str] = None,
    token_count: int = 0,
    compacted: int = 0,
    pydantic_json: Optional[str] = None,
    compaction_log_id: Optional[int] = None,
) -> None:
    """Insert a single message row."""
    # Guard: skip empty visible content for user/assistant roles
    # unless attachments are present (non-text payloads are still valid).
    if (
        role in ("user", "assistant")
        and not content.strip()
        and not attachments_json
        and not pydantic_json
    ):
        logger.debug(
            "insert_message: skipping empty %s message for session=%s seq=%d",
            role,
            session_id,
            seq,
        )
        return

    db = get_db()
    await db.execute(
        """
        INSERT OR IGNORE INTO messages
            (session_id, seq, role, content, type, agent_name, model_name,
             timestamp, thinking, attachments_json, clean_content,
             system_message_type, system_message_path,
             token_count, compacted, pydantic_json, compaction_log_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            seq,
            role,
            content,
            type,
            agent_name,
            model_name,
            timestamp,
            thinking,
            attachments_json,
            clean_content,
            system_message_type,
            system_message_path,
            token_count,
            compacted,
            pydantic_json,
            compaction_log_id,
        ),
    )
    await db.commit()


async def insert_messages_batch(rows: list[dict[str, Any]]) -> None:
    """Insert multiple message rows in a single transaction.

    Each dict in *rows* must have all the same keys as insert_message kwargs.
    Uses OR IGNORE so duplicate (session_id, seq) pairs are skipped silently.
    Rolls back on any failure so later immediate error/system writes can still
    open a fresh transaction.
    """
    if not rows:
        return

    # Guard: filter out empty visible content for user/assistant roles,
    # unless attachments are present (non-text payloads are still valid).
    original_count = len(rows)
    rows = [
        r
        for r in rows
        if not (
            r.get("role") in ("user", "assistant")
            and not r.get("content", "").strip()
            and not r.get("attachments_json")
            and not r.get("pydantic_json")
        )
    ]
    dropped = original_count - len(rows)
    if dropped > 0:
        logger.info(
            "insert_messages_batch: filtered %d empty user/assistant rows",
            dropped,
        )
    if not rows:
        return

    db = get_db()
    params = [
        (
            r["session_id"],
            r["seq"],
            r["role"],
            r.get("content", ""),
            r.get("type", ""),
            r.get("agent_name", ""),
            r.get("model_name", ""),
            r["timestamp"],
            r.get("thinking"),
            r.get("attachments_json"),
            r.get("clean_content"),
            r.get("system_message_type"),
            r.get("system_message_path"),
            r.get("token_count", 0),
            r.get("compacted", 0),
            r.get("pydantic_json"),
            r.get("compaction_log_id"),
        )
        for r in rows
    ]
    try:
        await db.executemany(
            """
            INSERT OR IGNORE INTO messages
                (session_id, seq, role, content, type, agent_name, model_name,
                 timestamp, thinking, attachments_json, clean_content,
                 system_message_type, system_message_path,
                 token_count, compacted, pydantic_json, compaction_log_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            params,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def get_active_messages(session_id: str) -> list[dict[str, Any]]:
    """Return all non-compacted message rows for a session, ordered by seq.

    This is what the agent uses to reconstruct its context via pydantic_json.
    """
    db = get_db()
    cursor = await db.execute(
        """
        SELECT session_id, seq, role, content, type, agent_name, model_name,
               timestamp, thinking, attachments_json, clean_content,
               system_message_type, system_message_path,
               token_count, compacted, pydantic_json, compaction_log_id
        FROM messages
        WHERE session_id = ? AND compacted = 0
        ORDER BY seq
        """,
        (session_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Tool calls
# ---------------------------------------------------------------------------


async def insert_tool_call(
    *,
    id: str,
    session_id: str,
    parent_message_seq: Optional[int],
    seq: int,
    tool_name: str,
    args_json: Optional[str] = None,
    result_json: Optional[str] = None,
    status: str = "success",
    duration_ms: Optional[int] = None,
    error_text: Optional[str] = None,
    agent_name: str = "",
    model_name: str = "",
    timestamp: float,
) -> None:
    db = get_db()
    await db.execute(
        """
        INSERT OR IGNORE INTO tool_calls
            (id, session_id, parent_message_seq, seq, tool_name,
             args_json, result_json, status, duration_ms, error_text,
             agent_name, model_name, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            id,
            session_id,
            parent_message_seq,
            seq,
            tool_name,
            args_json,
            result_json,
            status,
            duration_ms,
            error_text,
            agent_name,
            model_name,
            timestamp,
        ),
    )
    await db.commit()


async def insert_tool_calls_batch(rows: list[dict[str, Any]]) -> None:
    """Insert multiple tool call rows in a single transaction."""
    if not rows:
        return
    db = get_db()
    params = [
        (
            r["id"],
            r["session_id"],
            r.get("parent_message_seq"),
            r["seq"],
            r["tool_name"],
            r.get("args_json"),
            r.get("result_json"),
            r.get("status", "success"),
            r.get("duration_ms"),
            r.get("error_text"),
            r.get("agent_name", ""),
            r.get("model_name", ""),
            r["timestamp"],
        )
        for r in rows
    ]
    await db.executemany(
        """
        INSERT OR IGNORE INTO tool_calls
            (id, session_id, parent_message_seq, seq, tool_name,
             args_json, result_json, status, duration_ms, error_text,
             agent_name, model_name, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        params,
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Compaction
# ---------------------------------------------------------------------------


async def mark_messages_compacted(
    session_id: str, start_seq: int, end_seq: int
) -> None:
    """Soft-delete a range of messages by setting compacted=1."""
    db = get_db()
    await db.execute(
        """
        UPDATE messages SET compacted = 1
        WHERE session_id = ? AND seq BETWEEN ? AND ? AND compacted = 0
        """,
        (session_id, start_seq, end_seq),
    )
    await db.commit()


async def insert_compaction_log(
    *,
    session_id: str,
    summary_text: str,
    source_start: int,
    source_end: int,
    source_count: int,
    source_tokens: int,
    summary_tokens: int,
    strategy: str = "summarization",
    created_at: str,
) -> int:
    """Insert a compaction log entry and return its id."""
    db = get_db()
    cursor = await db.execute(
        """
        INSERT INTO compaction_log
            (session_id, summary_text, source_start, source_end,
             source_count, source_tokens, summary_tokens, strategy, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            summary_text,
            source_start,
            source_end,
            source_count,
            source_tokens,
            summary_tokens,
            strategy,
            created_at,
        ),
    )
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Per-turn chat write
# ---------------------------------------------------------------------------


async def write_turn_to_sqlite(
    *,
    session_id: str,
    enhanced_history: list[Any],
    title: str = "",
    working_directory: str = "",
    pinned: bool = False,
    agent_name: str = "code-puppy",
    model_name: str = "",
    total_tokens: int = 0,
    updated_at: str,
    created_at: str,
    ctx: Any,
) -> None:
    """Write an entire enhanced_history to SQLite after a chat turn.

    Called from chat_handler.py after save_session() succeeds.
    Uses INSERT OR IGNORE throughout — fully idempotent.

    Message seq: For non-user messages, we query the current max seq from the DB
    and increment from there. User messages are skipped (already written pre-stream
    via insert_message() with get_next_seq()).
    Tool call seq: max_message_seq + tc_global_idx + 1 (after all messages).
    Tool calls carry parent_message_seq so the FE doesn't need to infer it.

    Args:
        enhanced_history: List of dicts (already-wrapped format from chat_handler):
                          {'msg': ModelMessage, 'agent': str, 'model': str, 'ts': str}
                          Possibly also: {'clean_content': str, 'attachments': [...]}
        ctx: SessionContext — used for estimate_tokens_for_message().
             Pass None to use a simple len(content)//4 fallback.
    """
    import re
    import time
    from datetime import datetime

    from code_puppy.api.db.message_utils import (
        extract_content,
        extract_thinking,
        extract_tool_calls,
        extract_tool_returns,
        get_message_timestamp,
        get_role,
        pydantic_json_for_message,
    )

    # Upsert session first
    try:
        await upsert_session(
            session_id=session_id,
            title=title,
            agent_name=agent_name,
            model_name=model_name,
            working_directory=working_directory,
            pinned=pinned,
            created_at=created_at,
            updated_at=updated_at,
            message_count=len(enhanced_history),
            total_tokens=total_tokens,
            deleted_at=None,
        )
    except Exception as exc:
        logger.warning("write_turn_to_sqlite: upsert_session failed: %s", exc)
        return

    # ------------------------------------------------------------------ #
    # Build message rows and collect pending tool calls                    #
    # ------------------------------------------------------------------ #
    message_rows: list[dict[str, Any]] = []
    # pending_tool_calls: tool_call_id → {name, args, parent_seq, agent, model, ts}
    pending_tool_calls: dict[str, dict[str, Any]] = {}
    tool_call_rows_pending: list[dict[str, Any]] = []

    _ctx_re = re.compile(r"^\[Session Context:[^\]]*\]\n\n?")

    # Get the current max seq from the DB so we can assign correct seq numbers
    # to non-user messages. User messages are already written pre-stream with
    # get_next_seq(), so we must not collide with them.
    current_max_seq = await get_next_seq(session_id) - 1  # get_next_seq returns max+1

    for idx, item in enumerate(enhanced_history):
        # Unwrap the enhanced wrapper
        if isinstance(item, dict) and "msg" in item:
            actual_msg = item["msg"]
            wrapper = item
        else:
            actual_msg = item
            wrapper = {}

        if not hasattr(actual_msg, "parts"):
            continue  # skip system dict entries

        role = get_role(actual_msg)
        ts = wrapper.get("ts") or get_message_timestamp(actual_msg) or updated_at
        content = extract_content(actual_msg)

        if role in {"user", "assistant"} and not content.strip():
            diag_tool_calls_present = bool(extract_tool_calls(actual_msg))
            diag_tool_returns_present = bool(extract_tool_returns(actual_msg))
            logger.debug(
                "write_turn_to_sqlite empty visible content: "
                "session=%s role=%s history_idx=%d has_tool_calls=%s has_tool_returns=%s",
                session_id,
                role,
                idx,
                diag_tool_calls_present,
                diag_tool_returns_present,
            )

        # Extract tool returns from user (ModelRequest) messages BEFORE skipping.
        # BUG FIX: previously this block was placed AFTER the early `continue`
        # below, making it dead code — tool_call_rows_pending was never populated
        # and insert_tool_calls_batch() always received an empty list.
        if role == "user":
            for tr in extract_tool_returns(actual_msg):
                tid = tr["id"]
                if tid in pending_tool_calls:
                    tc = pending_tool_calls.pop(tid)
                    try:
                        args_json_str = json.dumps(tc["args"])
                    except Exception:
                        args_json_str = str(tc["args"])
                    # Serialize result - handle Pydantic models and complex objects
                    result_val = tr["result"]
                    try:
                        # Try Pydantic model_dump first
                        if hasattr(result_val, "model_dump"):
                            result_json_str = json.dumps(result_val.model_dump())
                        elif hasattr(result_val, "dict"):
                            # Older Pydantic v1 style
                            result_json_str = json.dumps(result_val.dict())
                        elif hasattr(result_val, "__dict__"):
                            # Generic object - convert to dict
                            result_json_str = json.dumps(vars(result_val))
                        else:
                            result_json_str = json.dumps(result_val)
                    except Exception:
                        # Last resort - try to make it JSON-serializable
                        try:
                            result_json_str = json.dumps(str(result_val))
                        except Exception:
                            result_json_str = json.dumps({"raw": str(result_val)})

                    try:
                        tool_ts = datetime.fromisoformat(
                            str(tc["ts"]).replace("Z", "+00:00")
                        ).timestamp()
                    except Exception:
                        tool_ts = time.time()

                    tool_call_rows_pending.append(
                        {
                            "id": tid,
                            "session_id": session_id,
                            "parent_message_seq": tc["parent_seq"],
                            "tool_name": tc["name"],
                            "args_json": args_json_str,
                            "result_json": result_json_str,
                            "status": "success",
                            "agent_name": tc["agent"],
                            "model_name": tc["model"],
                            "timestamp": tool_ts,
                        }
                    )
            # Skip writing user message rows — already pre-written by
            # chat_handler.py via insert_message()/get_next_seq(). Writing
            # them again here would create duplicates.
            continue

        # Assign seq for non-user messages: increment from current max
        current_max_seq += 1
        seq = current_max_seq

        thinking = extract_thinking(actual_msg)
        pj = pydantic_json_for_message(actual_msg)

        msg_agent = wrapper.get("agent") or agent_name or "code-puppy"
        msg_model = wrapper.get("model") or model_name or "unknown"

        # clean_content: prefer wrapper value, then strip session context for user
        clean_content: str | None = wrapper.get("clean_content") or None
        if clean_content is None and role == "user" and content:
            stripped = _ctx_re.sub("", content).lstrip()
            if stripped != content:
                clean_content = stripped

        # attachments_json: from wrapper
        raw_attachments = wrapper.get("attachments")
        attachments_json: str | None = (
            json.dumps(raw_attachments) if raw_attachments else None
        )

        # token count
        try:
            token_count = (
                ctx.agent.estimate_tokens_for_message(actual_msg)
                if ctx
                else max(1, len(content) // 4)
            )
        except Exception:
            token_count = max(1, len(content) // 4)

        assistant_tool_calls = (
            extract_tool_calls(actual_msg) if role == "assistant" else []
        )

        # Preserve non-text assistant payloads (tool-call-only responses).
        # This keeps the row from being filtered by insert_messages_batch.
        if role == "assistant" and assistant_tool_calls and not attachments_json:
            attachments_json = json.dumps({"tool_calls": assistant_tool_calls})

        # Guard: skip only truly empty assistant messages
        # (no text AND no tool calls).
        if role == "assistant" and not content.strip() and not assistant_tool_calls:
            logger.debug(
                "write_turn_to_sqlite: skipping empty assistant message "
                "session=%s history_idx=%d (no text, no tool calls)",
                session_id,
                idx,
            )
            continue  # truly empty - skip

        message_rows.append(
            {
                "session_id": session_id,
                "seq": seq,
                "role": role,
                "content": content,
                "type": type(actual_msg).__name__,
                "agent_name": msg_agent,
                "model_name": msg_model,
                "timestamp": ts,
                "thinking": thinking,
                "attachments_json": attachments_json,
                "clean_content": clean_content,
                "token_count": token_count,
                "pydantic_json": pj,
            }
        )

        # Collect tool calls from assistant messages
        if role == "assistant":
            for tc in assistant_tool_calls:
                pending_tool_calls[tc["id"]] = {
                    "name": tc["name"],
                    "args": tc["args"],
                    "parent_seq": seq,
                    "agent": msg_agent,
                    "model": msg_model,
                    "ts": ts,
                }

    # Assign seqs to tool calls: current_max_seq + 1, current_max_seq + 2, ...
    # (current_max_seq was already incremented for each message we added)
    tool_call_rows: list[dict[str, Any]] = []
    for tc_idx, tc_row in enumerate(tool_call_rows_pending):
        tc_row["seq"] = current_max_seq + tc_idx + 1
        tool_call_rows.append(tc_row)

    # Write everything
    try:
        await insert_messages_batch(message_rows)
    except Exception as exc:
        logger.warning("write_turn_to_sqlite: insert_messages_batch failed: %s", exc)

    if tool_call_rows:
        try:
            await insert_tool_calls_batch(tool_call_rows)
        except Exception as exc:
            logger.warning(
                "write_turn_to_sqlite: insert_tool_calls_batch failed: %s", exc
            )

    # Update session stats
    computed_tokens = sum(r.get("token_count", 0) for r in message_rows)
    final_tokens = total_tokens if total_tokens > 0 else computed_tokens
    try:
        await update_session_stats(
            session_id,
            message_count=len(message_rows),
            total_tokens=final_tokens,
            updated_at=updated_at,
        )
    except Exception as exc:
        logger.warning("write_turn_to_sqlite: update_session_stats failed: %s", exc)

    # Log with diagnostic counts for forensic debugging
    unmatched_calls = len(pending_tool_calls)
    logger.info(
        "write_turn_to_sqlite: session=%s messages=%d tool_calls=%d pending_unmatched=%d",
        session_id,
        len(message_rows),
        len(tool_call_rows),
        unmatched_calls,
    )

    # Warn if tool calls were detected but not matched to returns
    if unmatched_calls > 0:
        logger.warning(
            "write_turn_to_sqlite: %d tool calls not matched to returns for session=%s: %s",
            unmatched_calls,
            session_id,
            list(pending_tool_calls.keys()),
        )


# ---------------------------------------------------------------------------
# Interleaved session history query (Full Parity Model)
#
# Returns messages + tool_calls in a single ordered result set with a
# row_type discriminator, matching the desktop GUI's SESSION_LOAD_SQL.
# This enables the browser API to return the same data shape as the desktop.
# ---------------------------------------------------------------------------

# SQL query for interleaved messages + tool_calls, ordered by seq
_SESSION_HISTORY_PARITY_SQL = load_sql("session_history_parity.sql")
_SESSION_HISTORY_PARITY_NO_COMPACTED_SQL = load_sql(
    "session_history_parity_no_compacted.sql"
)


async def get_session_history_parity(
    session_id: str,
    *,
    include_compacted: bool = True,
) -> list[dict[str, Any]]:
    """Return interleaved messages + tool_calls for a session.

    This is the Full Parity Model query — returns the same row shape as the
    desktop GUI's SESSION_LOAD_SQL, enabling consistent behavior across:
    - Desktop GUI (Electron)
    - Browser chat UI
    - API consumers

    Args:
        session_id: The session to load
        include_compacted: If False, filter out compacted message rows
                          (tool_call rows are never compacted)

    Returns:
        List of dicts with keys:
        - row_type: 'message' | 'tool_call'
        - row_id: str (message id or tool_call id)
        - seq: int (ordering key)
        - role: str
        - content, type, agent_name, model_name, timestamp, ...
        - tool_name, args_json, result_json, status, ... (for tool_call rows)
        - parent_message_seq: int | None (for tool_call rows)
    """
    db = get_db()

    if include_compacted:
        # Use the standard parity SQL
        cursor = await db.execute(
            _SESSION_HISTORY_PARITY_SQL,
            (session_id, session_id),
        )
    else:
        cursor = await db.execute(
            _SESSION_HISTORY_PARITY_NO_COMPACTED_SQL,
            (session_id, session_id),
        )

    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_session_tool_calls(session_id: str) -> list[dict[str, Any]]:
    """Return all tool_call rows for a session, ordered by seq.

    Useful for diagnostics and validation.
    """
    db = get_db()
    cursor = await db.execute(
        """
        SELECT id, session_id, parent_message_seq, seq, tool_name,
               args_json, result_json, status, duration_ms, error_text,
               agent_name, model_name, timestamp
        FROM tool_calls
        WHERE session_id = ?
        ORDER BY seq
        """,
        (session_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
