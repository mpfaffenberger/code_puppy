"""Compaction tracking — writes compaction metadata to SQLite."""

import logging
from datetime import datetime, timezone
from typing import Any, List

logger = logging.getLogger(__name__)


def track_compaction_event(
    session_id: str,
    messages_before: List[Any],
    messages_after: List[Any],
    strategy: str,
    agent: Any | None = None,
) -> None:
    """
    Track a compaction event in SQLite.

    Called directly from message_history_processor after compaction completes.

    Args:
        session_id: Session identifier
        messages_before: Message history before compaction
        messages_after: Message history after compaction
        strategy: 'summarization' or 'truncation'
        agent: Agent instance (optional, used for token estimation)
    """
    # Only proceed if compaction actually happened (message count decreased)
    if len(messages_after) >= len(messages_before):
        logger.debug(
            "Compaction tracker: no size reduction (%d -> %d), skipping",
            len(messages_before),
            len(messages_after),
        )
        return

    try:
        from code_puppy.api.db.connection import get_db, get_write_lock

        # Estimate tokens (use agent's method if available, else default)
        def fallback_estimate(m: Any) -> int:
            return 100

        if agent and hasattr(agent, "estimate_tokens_for_message"):
            estimate_tokens = agent.estimate_tokens_for_message
        else:
            estimate_tokens = fallback_estimate

        # Calculate compaction metadata
        compacted_count = len(messages_before) - len(messages_after)

        # Estimate tokens for source messages (messages that were compacted)
        # Assume first message is system prompt, compaction starts at index 1
        source_messages = messages_before[1 : compacted_count + 1]
        source_tokens = sum(estimate_tokens(m) for m in source_messages)

        # Extract summary text from new messages (compare object IDs)
        before_ids = {id(m) for m in messages_before}
        new_messages = [m for m in messages_after if id(m) not in before_ids]

        summary_text = "(no summary found)"
        summary_tokens = 0
        if new_messages:
            summary_msg = new_messages[0]
            text_parts = []
            for part in getattr(summary_msg, "parts", []) or []:
                if hasattr(part, "content"):
                    text_parts.append(str(part.content))
            summary_text = " ".join(text_parts) if text_parts else "(empty summary)"
            summary_tokens = estimate_tokens(summary_msg)

        # Assume compaction removes from the start (after system message at seq 1)
        source_start = 2  # First message after system prompt
        source_end = source_start + compacted_count - 1

        # Create compaction_log row
        created_at = datetime.now(timezone.utc).isoformat()

        with get_write_lock():
            db = get_db()
            cursor = db.execute(
                """
                INSERT INTO compaction_log
                    (session_id, summary_text, source_start, source_end,
                     source_count, source_tokens, summary_tokens, strategy, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    summary_text[:1000],  # Truncate very long summaries
                    source_start,
                    source_end,
                    compacted_count,
                    source_tokens,
                    summary_tokens,
                    strategy,
                    created_at,
                ),
            )
            compaction_log_id = cursor.lastrowid

            # Mark compacted messages in the messages table
            rows_updated = db.execute(
                """
                UPDATE messages
                SET compacted = 1, compaction_log_id = ?
                WHERE session_id = ? AND seq >= ? AND seq <= ? AND compacted = 0
                """,
                (compaction_log_id, session_id, source_start, source_end),
            ).rowcount

            db.commit()

            logger.info(
                "Compaction tracked: session=%s log_id=%d seq=%d-%d count=%d marked=%d strategy=%s",
                session_id,
                compaction_log_id,
                source_start,
                source_end,
                compacted_count,
                rows_updated,
                strategy,
            )

    except Exception as e:
        # Non-fatal — compaction still worked, we just didn't track it
        logger.warning(
            "Compaction tracker failed for %s: %s", session_id, e, exc_info=True
        )
