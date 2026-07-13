"""Session persistence and broadcast payload builders.

Pure helpers extracted from ``chat_handler.py`` (Phase 3) to make payload
construction independently testable without a live WebSocket or database.

These functions build the dicts that ``chat_handler`` sends to clients and
broadcasts to session-monitoring connections.  They do **not** perform I/O
themselves — the caller is responsible for the actual send / DB write.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from code_puppy.api.ws.connection_manager import connection_manager
from code_puppy.api.ws.history_utils import (
    build_enhanced_history,
    estimate_total_tokens,
)

logger = logging.getLogger(__name__)


def generate_heuristic_title(history: list[Any], max_length: int = 50) -> str:
    """Generate a short title from the first user message in websocket history."""
    import re

    def extract_user_content(msg: Any) -> str | None:
        if isinstance(msg, dict) and "msg" in msg:
            msg = msg["msg"]

        if hasattr(msg, "kind") and msg.kind == "request":
            for part in getattr(msg, "parts", []):
                content = getattr(part, "content", None)
                if isinstance(content, str) and content.strip():
                    return content.strip()

        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()

        return None

    for msg in history:
        content = extract_user_content(msg)
        if content:
            first_line = content.split("\n")[0][:max_length]
            title = first_line.lower()
            title = re.sub(r"[^a-z0-9\s-]", "", title)
            title = re.sub(r"\s+", "-", title)
            title = re.sub(r"-+", "-", title)
            title = title.strip("-")[:max_length]
            return title or "untitled-session"

    return "untitled-session"


def resolve_agent_model_meta(
    agent: Any = None,
    ctx: Any = None,
) -> tuple[str, str]:
    """Return ``(agent_name, model_name)`` with or-chain fallbacks.

    Priority:
    1. ``agent.name`` / ``agent.get_model_name()`` (if agent is not None/empty)
    2. ``ctx.agent_name`` / ``ctx.model_name`` (if ctx is not None)
    3. Hardcoded defaults ``"code-puppy"`` / ``"unknown"``
    """
    agent_name = (
        (agent.name if agent else "") or (ctx.agent_name if ctx else "") or "code-puppy"
    )
    model_name = (
        (agent.get_model_name() if agent else "")
        or (ctx.model_name if ctx else "")
        or "unknown"
    )
    return agent_name, model_name


def build_session_meta_payload(
    *,
    session_id: str,
    session_name: str,
    total_tokens: int,
    message_count: int,
    title: str,
    working_directory: str,
    agent_name: str,
    model_name: str,
) -> dict[str, Any]:
    """Build the ``session_meta`` frame sent to the initiating client.

    Returns a plain dict ready for ``send_json`` / ``send_typed``.
    """
    return {
        "type": "session_meta",
        "session_id": session_id,
        "session_name": session_name,
        "total_tokens": total_tokens,
        "message_count": message_count,
        "title": title,
        "working_directory": working_directory,
        "agent_name": agent_name,
        "model_name": model_name,
    }


def build_session_update_payload(
    *,
    session_id: str,
    session_name: str,
    title: str,
    working_directory: str,
    message_count: int,
    total_tokens: int,
    timestamp: Optional[str] = None,
) -> dict[str, Any]:
    """Build the broadcast payload for ``connection_manager.broadcast_session_update``.

    ``action`` is ``"created"`` when ``message_count == 1`` (first turn),
    otherwise ``"updated"``.
    """
    return {
        "session_id": session_id,
        "session_name": session_name,
        "title": title,
        "working_directory": working_directory,
        "timestamp": timestamp or datetime.datetime.now().isoformat(),
        "message_count": message_count,
        "total_tokens": total_tokens,
        "auto_saved": True,
        "action": "created" if message_count == 1 else "updated",
    }


@dataclass(slots=True)
class PersistedTurnSummary:
    """Summary of a persisted websocket turn."""

    session_title: str
    message_count: int
    total_tokens: int


async def persist_session_turn_and_broadcast(
    *,
    history: list[Any],
    session_id: str,
    session_title: str,
    session_working_directory: str,
    session_pinned: bool,
    agent: Any,
    agent_name: str,
    model_name: str,
    ctx: Any,
    original_user_message: str,
    attachment_metadata: list[Any] | None,
    safe_send_json: Callable[[dict[str, Any]], Awaitable[Any]],
    logger_override: logging.Logger | None = None,
) -> PersistedTurnSummary | None:
    """Persist finalized turn history and notify websocket/session listeners.

    Returns ``None`` when there is no history to persist. Otherwise returns a
    compact summary containing the resolved title and aggregate counts.
    """
    if not history:
        return None

    logger_ = logger_override or logger
    attachment_metadata = attachment_metadata or []

    if not session_title or session_title == "untitled-session":
        session_title = generate_heuristic_title(history)

    session_name = session_id
    agent_name_meta, model_name_meta = resolve_agent_model_meta(agent=agent, ctx=ctx)
    enhanced_history = build_enhanced_history(
        history,
        agent_name_meta=agent_name_meta,
        model_name_meta=model_name_meta,
        original_user_message=original_user_message,
        attachment_metadata=attachment_metadata,
    )

    if attachment_metadata and len(history) >= 2:
        logger_.debug(
            "Added UI metadata to user message: %d attachment(s), clean_content length: %d",
            len(attachment_metadata),
            len(original_user_message),
        )

    message_count = len(enhanced_history)
    total_tokens = estimate_total_tokens(enhanced_history, agent)

    await persist_turn_to_sqlite(
        session_id=session_id,
        enhanced_history=enhanced_history,
        title=session_title,
        working_directory=session_working_directory,
        pinned=session_pinned,
        agent_name=agent_name,
        model_name=model_name,
        total_tokens=total_tokens,
        created_at_iso=ctx.created_at.isoformat(),
        ctx=ctx,
    )

    await safe_send_json(
        build_session_meta_payload(
            session_id=session_id,
            session_name=session_name,
            total_tokens=total_tokens,
            message_count=message_count,
            title=session_title,
            working_directory=session_working_directory,
            agent_name=agent_name,
            model_name=model_name,
        )
    )

    await connection_manager.broadcast_session_update(
        build_session_update_payload(
            session_id=session_id,
            session_name=session_name,
            title=session_title,
            working_directory=session_working_directory,
            message_count=message_count,
            total_tokens=total_tokens,
        )
    )

    return PersistedTurnSummary(
        session_title=session_title,
        message_count=message_count,
        total_tokens=total_tokens,
    )


async def persist_turn_to_sqlite(
    *,
    session_id: str,
    enhanced_history: list[Any],
    title: str,
    working_directory: str,
    pinned: bool,
    agent_name: str,
    model_name: str,
    total_tokens: int,
    created_at_iso: str,
    ctx: Any = None,
) -> bool:
    """Write a conversation turn to SQLite, returning True on success.

    Wraps ``write_turn_to_sqlite`` with the standard try/except guard
    used by ``chat_handler``.  Returns ``False`` (and logs) when the
    database is unavailable instead of raising.
    """
    try:
        from code_puppy.api.db.queries import write_turn_to_sqlite

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await write_turn_to_sqlite(
            session_id=session_id,
            enhanced_history=enhanced_history,
            title=title,
            working_directory=working_directory,
            pinned=pinned,
            agent_name=agent_name,
            model_name=model_name,
            total_tokens=total_tokens,
            updated_at=now_iso,
            created_at=created_at_iso,
            ctx=ctx,
        )
        return True
    except Exception as exc:
        logger.debug(
            "SQLite turn write skipped (DB not available): %s",
            exc,
        )
        return False
