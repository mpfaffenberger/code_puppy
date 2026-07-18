"""WebSocket session management router.

Handles CRUD operations for chat sessions.
Now exclusively uses SQLite as the source of truth.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from code_puppy.api.db.queries import (
    get_active_messages,
    get_session_history_parity,
    get_session_metadata,
    get_session_tool_calls,
    soft_delete_session,
    update_session_meta_fields,
)
from code_puppy.config import get_ws_sessions_dir

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_ws_sessions_dir() -> Path:
    """Get the WebSocket sessions directory."""
    return get_ws_sessions_dir()


def _validate_session_name(session_name: str, ws_dir: Path) -> str:
    """Validate session name prevents path traversal."""
    if not session_name or ".." in session_name or "/" in session_name:
        raise HTTPException(400, "Invalid session name")
    return session_name


@router.get("/{session_name}/messages")
async def get_ws_session_messages(
    session_name: str,
    include_tool_calls: Optional[bool] = Query(
        default=None,
        description="Include tool_call rows interleaved with messages (Full Parity Model). "
        "When true, returns unified row format with row_type discriminator.",
    ),
    include_compacted: bool = Query(
        default=True,
        description="Include compacted (summarized) messages. Only applies when include_tool_calls=true.",
    ),
) -> List[Dict[str, Any]]:
    """Get the full message history for a WebSocket session from SQLite.

    Args:
        session_name: The session name / session_id
        include_tool_calls: Feature flag for Full Parity Model.
            - None/False: Legacy behavior, returns only message rows
            - True: Returns interleaved message + tool_call rows with row_type discriminator
        include_compacted: When using parity mode, whether to include compacted messages

    Returns:
        List of serialized message dictionaries.

        When include_tool_calls=true, each row has:
        - row_type: 'message' | 'tool_call'
        - row_id: unique identifier
        - seq: ordering key
        - Plus type-specific fields (content for messages, result_json for tool_calls, etc.)
    """
    _validate_session_name(session_name, _get_ws_sessions_dir())

    try:
        # ──────────────────────────────────────────────────────────────────
        # Full Parity Model: interleaved messages + tool_calls
        # ──────────────────────────────────────────────────────────────────
        if include_tool_calls:
            rows = await get_session_history_parity(
                session_name,
                include_compacted=include_compacted,
            )

            if rows:
                logger.debug(
                    "get_ws_session_messages (parity): session=%s total_rows=%d "
                    "messages=%d tool_calls=%d",
                    session_name,
                    len(rows),
                    sum(1 for r in rows if r.get("row_type") == "message"),
                    sum(1 for r in rows if r.get("row_type") == "tool_call"),
                )
                return rows

            # Check if session exists but has no data
            meta = await get_session_metadata(session_name)
            if meta:
                return []

            raise HTTPException(404, f"WebSocket session '{session_name}' not found")

        # ──────────────────────────────────────────────────────────────────
        # Legacy behavior: message rows only (backward compatible)
        # ──────────────────────────────────────────────────────────────────
        rows = await get_active_messages(session_name)
        serialized_rows: List[Dict[str, Any]] = []

        for row in rows:
            base_row = {
                "role": row["role"],
                "content": row["content"],
                "type": row["type"],
                "agent_name": row["agent_name"],
                "model_name": row["model_name"],
                "timestamp": row["timestamp"],
                "thinking": row["thinking"],
                "clean_content": row["clean_content"],
                "seq": row["seq"],
            }

            if row.get("pydantic_json"):
                serialized_rows.append(base_row)
                continue

            if row.get("type") == "error":
                payload: Dict[str, Any] = {}
                raw_payload = row.get("attachments_json")
                if raw_payload:
                    try:
                        payload = json.loads(raw_payload)
                    except (TypeError, ValueError):
                        logger.warning(
                            "get_ws_session_messages: invalid error payload JSON for %s seq=%s",
                            session_name,
                            row.get("seq"),
                        )

                serialized_rows.append(
                    {
                        **base_row,
                        "type": "error",
                        "error": payload.get("error", row["content"]),
                        "error_type": payload.get("error_type", "unknown"),
                        "technical_details": payload.get("technical_details", ""),
                        "action_required": payload.get("action_required"),
                        "session_id": payload.get("session_id", session_name),
                    }
                )
                continue

            if row.get("type") == "system":
                serialized_rows.append(
                    {
                        **base_row,
                        "system_message_type": row.get("system_message_type"),
                        "system_message_path": row.get("system_message_path"),
                    }
                )
                continue

            serialized_rows.append(base_row)

        if serialized_rows:
            return serialized_rows

        # If no messages found, check if session exists at all
        meta = await get_session_metadata(session_name)
        if meta:
            # Session exists but has no messages yet - return empty list
            return []

        raise HTTPException(404, f"WebSocket session '{session_name}' not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_ws_session_messages: SQLite error for %s: %s", session_name, e
        )
        raise HTTPException(503, "Service unavailable: database error")


@router.get("/{session_name}/tool-calls")
async def get_ws_session_tool_calls(session_name: str) -> List[Dict[str, Any]]:
    """Get all tool calls for a session.

    This is a diagnostic/debugging endpoint that returns just the tool_calls
    table rows for a session, useful for verifying persistence.

    Args:
        session_name: The session name / session_id

    Returns:
        List of tool_call rows with id, tool_name, args_json, result_json, status, etc.
    """
    _validate_session_name(session_name, _get_ws_sessions_dir())

    try:
        rows = await get_session_tool_calls(session_name)

        if rows:
            logger.debug(
                "get_ws_session_tool_calls: session=%s count=%d",
                session_name,
                len(rows),
            )
            return rows

        # Check if session exists
        meta = await get_session_metadata(session_name)
        if meta:
            return []  # Session exists but has no tool calls

        raise HTTPException(404, f"WebSocket session '{session_name}' not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_ws_session_tool_calls: SQLite error for %s: %s", session_name, e
        )
        raise HTTPException(503, "Service unavailable: database error")


@router.delete("/{session_name}")
async def delete_ws_session(session_name: str) -> Dict[str, str]:
    """Soft-delete a WebSocket session in SQLite."""
    _validate_session_name(session_name, _get_ws_sessions_dir())

    # Soft delete in SQLite
    try:
        await soft_delete_session(session_name, datetime.now(timezone.utc).isoformat())
        # We don't check if it existed, soft_delete is idempotent-ish
        # But we might want to know if we actually updated anything.
        # For now, we assume success if no error.
    except Exception as e:
        logger.error("delete_ws_session: SQLite error for %s: %s", session_name, e)
        raise HTTPException(503, "Service unavailable: database error")

    return {"message": f"WebSocket session '{session_name}' deleted"}


@router.patch("/{session_name}")
async def update_ws_session(
    session_name: str, updates: Dict[str, Any]
) -> Dict[str, Any]:
    """Update WebSocket session metadata in SQLite.

    Supports updating: title, pinned.
    """
    _validate_session_name(session_name, _get_ws_sessions_dir())

    # Get current metadata
    current_meta = await get_session_metadata(session_name)
    if not current_meta:
        raise HTTPException(404, f"WebSocket session '{session_name}' not found")

    # Prepare updates
    new_title = current_meta["title"]
    new_pinned = bool(current_meta["pinned"])
    updated_at = datetime.now(timezone.utc).isoformat()

    if "title" in updates or "name" in updates:
        val = updates.get("title") or updates.get("name")
        if val and isinstance(val, str) and val.strip():
            new_title = val.strip()

    if "pinned" in updates:
        if isinstance(updates["pinned"], bool):
            new_pinned = updates["pinned"]

    # Write to SQLite
    try:
        await update_session_meta_fields(
            session_name,
            title=new_title,
            pinned=new_pinned,
            updated_at=updated_at,
        )
    except Exception as e:
        logger.error("update_ws_session: SQLite error for %s: %s", session_name, e)
        raise HTTPException(503, "Service unavailable: database error")

    return {
        "session_id": session_name,
        "title": new_title,
        "pinned": new_pinned,
        "updated_at": updated_at,
    }
