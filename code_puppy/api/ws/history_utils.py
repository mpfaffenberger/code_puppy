"""History-wrapping helpers for WebSocket session persistence.

These functions keep the message-history decoration logic out of the main chat
handler so it can be tested independently and reused by future persistence
refactors.
"""

from __future__ import annotations

import datetime
from typing import Any


def extract_message_timestamp(raw_msg: Any, default_ts: str) -> str:
    """Best-effort extraction of an existing timestamp for a message."""
    if isinstance(raw_msg, dict):
        ts_val = raw_msg.get("timestamp")

        if isinstance(ts_val, (int, float)):
            try:
                return datetime.datetime.fromtimestamp(ts_val).isoformat()
            except Exception:
                pass

        if isinstance(ts_val, str) and ts_val:
            return ts_val

        ts_field = raw_msg.get("ts")
        if isinstance(ts_field, str) and ts_field:
            return ts_field

    try:
        attr_ts = getattr(raw_msg, "timestamp", None)
        if isinstance(attr_ts, (int, float)):
            return datetime.datetime.fromtimestamp(attr_ts).isoformat()
        if isinstance(attr_ts, str) and attr_ts:
            return attr_ts
    except Exception:
        pass

    return default_ts


def build_enhanced_history(
    history: list[Any],
    *,
    agent_name_meta: str,
    model_name_meta: str,
    original_user_message: str,
    attachment_metadata: list[Any] | None = None,
) -> list[dict[str, Any]]:
    """Wrap raw history entries with agent/model/timestamp metadata.

    Existing wrapped entries are preserved as-is for idempotency. When
    attachments were injected into the just-processed user message, we backfill
    clean UI metadata onto the penultimate history entry.
    """
    attachment_metadata = attachment_metadata or []
    enhanced_history: list[dict[str, Any]] = []

    for idx, msg in enumerate(history):
        if isinstance(msg, dict) and "msg" in msg and "agent" in msg:
            enhanced_history.append(msg)
            continue

        current_timestamp = datetime.datetime.now().isoformat()
        msg_ts = extract_message_timestamp(msg, current_timestamp)
        wrapper: dict[str, Any] = {
            "msg": msg,
            "agent": agent_name_meta,
            "model": model_name_meta,
            "ts": msg_ts,
        }

        is_user_message_just_processed = (
            idx == len(history) - 2 and len(history) >= 2 and bool(attachment_metadata)
        )

        if is_user_message_just_processed:
            wrapper["clean_content"] = original_user_message
            wrapper["attachments"] = attachment_metadata

        enhanced_history.append(wrapper)

    return enhanced_history


def estimate_total_tokens(enhanced_history: list[Any], agent: Any) -> int:
    """Estimate total tokens for wrapped history, returning 0 on failure."""
    try:
        total_tokens = 0
        for item in enhanced_history:
            msg_obj = item["msg"] if isinstance(item, dict) and "msg" in item else item
            total_tokens += agent.estimate_tokens_for_message(msg_obj)
        return total_tokens
    except Exception:
        return 0


__all__ = [
    "build_enhanced_history",
    "estimate_total_tokens",
    "extract_message_timestamp",
]
