"""Backfill helpers for the messages table.

Currently contains one migration helper:

    backfill_pydantic_json(db)
        Reconstructs pydantic_json from the plain `content` column for any
        message row where pydantic_json IS NULL.  Used by the v4→v5 schema
        migration in connection.py.

Design notes
------------
* Only 'user' and 'assistant' roles are processed — 'system' rows have no
  pydantic_json and the load path already skips them.
* The reconstruction is lossy for assistant messages that originally contained
  tool calls or extended thinking, because that structure was never stored in
  the `content` column.  The backfill preserves the visible text so sessions
  resume with *something* rather than blank history.
* The function is idempotent: it filters on ``pydantic_json IS NULL`` so
  running it twice is safe.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)


def _build_message(role: str, content: str, model_name: str) -> Any:
    """Build a pydantic-ai ModelMessage from a plain content string.

    Args:
        role:       'user' or 'assistant'.
        content:    Plain text content extracted from the messages row.
        model_name: Model name stored on the row (used for ModelResponse).

    Returns:
        A ModelRequest or ModelResponse instance ready for serialisation.

    Raises:
        ValueError: If *role* is not 'user' or 'assistant'.
    """
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        UserPromptPart,
    )

    if role == "user":
        return ModelRequest(parts=[UserPromptPart(content=content)])
    if role == "assistant":
        return ModelResponse(
            parts=[TextPart(content=content)],
            model_name=model_name or "unknown",
        )
    raise ValueError(f"Unsupported role for backfill: {role!r}")


def _serialize(msg: Any) -> str:
    """Serialise a single ModelMessage to the pydantic_json wire format.

    Stores as a single-element JSON array — identical to what
    pydantic_json_for_message() produces during normal chat saves.
    """
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    return ModelMessagesTypeAdapter.dump_json([msg]).decode("utf-8")


async def backfill_pydantic_json(
    db: "aiosqlite.Connection",
    *,
    batch_size: int = 200,
) -> tuple[int, int]:
    """Backfill pydantic_json for message rows where it is currently NULL.

    Reads all eligible rows in one query, groups UPDATE statements into
    batches of *batch_size* to keep transactions small, and commits after
    each batch so a mid-run crash leaves the DB consistent.

    Args:
        db:         Open aiosqlite connection (must have row_factory set).
        batch_size: Number of rows updated per transaction.

    Returns:
        ``(updated, skipped)`` — row counts for rows successfully backfilled
        and rows skipped due to serialisation errors.
    """
    cursor = await db.execute(
        """
        SELECT id, session_id, seq, role, content, model_name
        FROM   messages
        WHERE  pydantic_json IS NULL
          AND  compacted = 0
          AND  role IN ('user', 'assistant')
        ORDER  BY session_id, seq
        """
    )
    rows = await cursor.fetchall()

    if not rows:
        logger.info("backfill_pydantic_json: no NULL rows found — nothing to do")
        return 0, 0

    logger.info("backfill_pydantic_json: %d rows to backfill", len(rows))

    updated = 0
    skipped = 0
    batch: list[tuple[str, int]] = []  # (pydantic_json, id)

    for row in rows:
        row_id: int = row["id"]
        role: str = row["role"]
        content: str = row["content"] or ""
        model_name: str = row["model_name"] or "unknown"
        session_id: str = row["session_id"]
        seq: int = row["seq"]

        try:
            msg = _build_message(role, content, model_name)
            pj = _serialize(msg)
            batch.append((pj, row_id))
        except Exception as exc:
            logger.warning(
                "backfill_pydantic_json: skipping id=%s (session=%s seq=%s role=%s): %s",
                row_id,
                session_id,
                seq,
                role,
                exc,
            )
            skipped += 1

        if len(batch) >= batch_size:
            await _flush_batch(db, batch)
            updated += len(batch)
            batch = []

    if batch:
        await _flush_batch(db, batch)
        updated += len(batch)

    logger.info(
        "backfill_pydantic_json: done — %d updated, %d skipped",
        updated,
        skipped,
    )
    return updated, skipped


async def _flush_batch(
    db: "aiosqlite.Connection",
    batch: list[tuple[str, int]],
) -> None:
    """Write one batch of (pydantic_json, id) pairs and commit."""
    await db.executemany(
        "UPDATE messages SET pydantic_json = ? WHERE id = ?",
        batch,
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Tool-call backfill (added to fix the early-continue bug in
# write_turn_to_sqlite that prevented tool_calls rows from ever being written)
# ---------------------------------------------------------------------------


async def backfill_tool_calls(
    db: "aiosqlite.Connection",
    *,
    session_id: str | None = None,
    batch_size: int = 100,
) -> tuple[int, int]:
    """Backfill tool_call rows from pydantic_json for sessions saved without them.

    Sessions written before the fix for the early-continue bug in
    ``write_turn_to_sqlite`` have no rows in ``tool_calls`` even though the
    pydantic_json column contains full ToolCallPart / ToolReturnPart data.

    This function replays each session's message history in seq order,
    matches ToolCallPart entries in assistant messages with ToolReturnPart
    entries in the following user messages, and inserts the reconstructed
    rows into ``tool_calls``.  Uses ``INSERT OR IGNORE`` — fully idempotent.

    Args:
        db:         Open aiosqlite connection with ``row_factory`` set to
                    ``aiosqlite.Row``.
        session_id: If provided, only process that one session; otherwise
                    process every session that has pydantic_json rows.
        batch_size: Number of ``tool_calls`` rows inserted per commit.

    Returns:
        ``(inserted, skipped)`` row counts.
    """
    import json
    import time
    import uuid

    from pydantic_ai.messages import ModelMessagesTypeAdapter

    where_clause = "WHERE m.pydantic_json IS NOT NULL AND m.compacted = 0"
    params: tuple = ()
    if session_id:
        where_clause += " AND m.session_id = ?"
        params = (session_id,)

    cursor = await db.execute(
        f"""
        SELECT m.id, m.session_id, m.seq, m.role,
               m.agent_name, m.model_name, m.timestamp, m.pydantic_json
        FROM   messages m
        {where_clause}
        ORDER  BY m.session_id, m.seq
        """,
        params,
    )
    rows = await cursor.fetchall()

    if not rows:
        logger.info("backfill_tool_calls: no eligible messages found — nothing to do")
        return 0, 0

    logger.info(
        "backfill_tool_calls: processing %d message rows%s",
        len(rows),
        f" for session={session_id}" if session_id else "",
    )

    inserted = 0
    skipped = 0
    batch: list[tuple] = []

    # Per-session state: pending tool calls keyed by tool_call_id
    current_session: str | None = None
    # tool_call_id → {name, args, parent_seq, agent, model, ts}
    pending: dict[str, dict] = {}

    for row in rows:
        row_session = row["session_id"]
        if row_session != current_session:
            # Reset pending state when we enter a new session
            current_session = row_session
            pending = {}

        try:
            parsed = ModelMessagesTypeAdapter.validate_json(row["pydantic_json"])
        except Exception as exc:
            logger.warning(
                "backfill_tool_calls: skip seq=%s session=%s parse error: %s",
                row["seq"],
                row["session_id"],
                exc,
            )
            skipped += 1
            continue

        if not parsed:
            continue

        msg = parsed[0]
        role: str = row["role"]
        seq: int = row["seq"]
        agent_name: str = row["agent_name"] or ""
        model_name: str = row["model_name"] or ""

        # Collect ToolCallParts from assistant (ModelResponse) messages
        if role == "assistant":
            for part in getattr(msg, "parts", []):
                if type(part).__name__ != "ToolCallPart":
                    continue
                tc_id = getattr(part, "tool_call_id", "") or str(uuid.uuid4())
                args = getattr(part, "args", {})
                if hasattr(args, "model_dump"):
                    args = args.model_dump()
                elif hasattr(args, "__dict__"):
                    args = dict(args.__dict__)
                pending[tc_id] = {
                    "name": getattr(part, "tool_name", "unknown"),
                    "args": args,
                    "parent_seq": seq,
                    "agent": agent_name,
                    "model": model_name,
                    "ts": row["timestamp"],
                }

        # Match ToolReturnParts from user (ModelRequest) messages
        elif role == "user":
            for part in getattr(msg, "parts", []):
                if type(part).__name__ != "ToolReturnPart":
                    continue
                tc_id = getattr(part, "tool_call_id", "")
                if not tc_id or tc_id not in pending:
                    continue

                tc = pending.pop(tc_id)
                content = getattr(part, "content", "")
                try:
                    result_val = (
                        json.loads(content) if isinstance(content, str) else content
                    )
                except Exception:
                    result_val = content

                try:
                    args_json_str = json.dumps(tc["args"])
                except Exception:
                    args_json_str = str(tc["args"])
                try:
                    result_json_str = json.dumps(result_val)
                except Exception:
                    result_json_str = str(result_val)

                try:
                    from datetime import datetime as _dt

                    tool_ts = _dt.fromisoformat(
                        str(tc["ts"]).replace("Z", "+00:00")
                    ).timestamp()
                except Exception:
                    tool_ts = time.time()

                batch.append(
                    (
                        tc_id,  # id
                        row_session,  # session_id
                        tc["parent_seq"],  # parent_message_seq
                        tc[
                            "parent_seq"
                        ],  # seq  (best approximation without original seq)
                        tc["name"],  # tool_name
                        args_json_str,  # args_json
                        result_json_str,  # result_json
                        "success",  # status
                        None,  # duration_ms
                        None,  # error_text
                        tc["agent"],  # agent_name
                        tc["model"],  # model_name
                        tool_ts,  # timestamp
                    )
                )

        if len(batch) >= batch_size:
            n = await _flush_tool_call_batch(db, batch)
            inserted += n
            batch = []

    if batch:
        n = await _flush_tool_call_batch(db, batch)
        inserted += n

    logger.info(
        "backfill_tool_calls: done — %d inserted, %d skipped",
        inserted,
        skipped,
    )
    return inserted, skipped


async def _flush_tool_call_batch(
    db: "aiosqlite.Connection",
    batch: list[tuple],
) -> int:
    """INSERT OR IGNORE a batch of tool_call rows and commit."""
    await db.executemany(
        """
        INSERT OR IGNORE INTO tool_calls
            (id, session_id, parent_message_seq, seq, tool_name,
             args_json, result_json, status, duration_ms, error_text,
             agent_name, model_name, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    await db.commit()
    return len(batch)
