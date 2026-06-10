"""Session bootstrap helpers for the chat WebSocket."""

from __future__ import annotations

import datetime
import logging
from typing import Any

from fastapi import WebSocket

from code_puppy.api.db.queries import write_system_message_to_sqlite
from code_puppy.api.session_context import _validate_session_id, session_manager
from code_puppy.api.ws.schemas import (
    PROTOCOL_VERSION,
    ServerSessionRestored,
    ServerSystem,
)
from code_puppy.api.ws.send_utils import WebSocketSender
from code_puppy.api.ws.session_persistence import build_session_meta_payload
from code_puppy.api.ws.ws_chat_runtime import WebSocketChatRuntime
from code_puppy.messaging.bus import get_message_bus
from code_puppy.tools.command_runner import init_session_process_tracking

logger = logging.getLogger(__name__)


async def send_session_meta_snapshot(
    *,
    runtime: WebSocketChatRuntime,
    safe_send_json: Any,
) -> None:
    """Send the latest session metadata snapshot to the client."""
    try:
        from code_puppy.api.db.queries import get_session_row

        session_row = await get_session_row(runtime.session_id) or {}
    except Exception:
        session_row = {}

    history_for_meta = []
    if runtime.ctx is not None and getattr(runtime.ctx, "agent", None) is not None:
        try:
            history_for_meta = runtime.ctx.agent.get_message_history() or []
        except Exception:
            history_for_meta = []

    await safe_send_json(
        build_session_meta_payload(
            session_id=runtime.session_id,
            session_name=runtime.session_id,
            total_tokens=int(session_row.get("total_tokens") or 0),
            message_count=int(
                session_row.get("message_count") or len(history_for_meta)
            ),
            title=runtime.session_title or str(session_row.get("title") or ""),
            working_directory=(
                runtime.session_working_directory
                or str(session_row.get("working_directory") or "")
            ),
            agent_name=runtime.agent_name,
            model_name=runtime.model_name,
        )
    )


async def replay_restored_system_messages(
    *,
    runtime: WebSocketChatRuntime,
    send_typed: Any,
) -> None:
    """Replay persisted system rows for a restored session."""
    try:
        from code_puppy.api.db.queries import get_active_messages

        rows = await get_active_messages(runtime.session_id)
        system_rows = [
            r
            for r in rows
            if r.get("role") == "system"
            and r.get("system_message_type") in ("init", "config", "directory")
        ]
        for sys_row in system_rows:
            await send_typed(
                ServerSystem(
                    content=sys_row.get("content", ""),
                    session_id=runtime.session_id,
                    agent_name=sys_row.get("agent_name", ""),
                    model_name=sys_row.get("model_name", ""),
                )
            )
        if system_rows:
            logger.debug(
                "Replayed %d system messages for session %s",
                len(system_rows),
                runtime.session_id,
            )
    except Exception as sys_exc:
        logger.warning(
            "Failed to replay system messages for session %s: %s",
            runtime.session_id,
            sys_exc,
        )


async def initialize_ws_session(
    *,
    websocket: WebSocket,
    requested_session_id: str | None,
    sender: WebSocketSender,
    safe_send_json: Any,
    send_typed: Any,
) -> WebSocketChatRuntime | None:
    """Create or load session state for a chat WebSocket connection."""
    session_id = requested_session_id
    existing_history = None
    session_title = ""
    session_working_directory = ""
    session_pinned = False

    if session_id:
        try:
            _validate_session_id(session_id)
        except ValueError as exc:
            logger.warning("Invalid session_id rejected: %r: %s", session_id, exc)
            await websocket.close(code=1008, reason="Invalid session ID")
            return None

        logger.debug("Client requested session: %s", session_id)
        try:
            from code_puppy.api.db.queries import get_session_metadata, session_exists

            if await session_exists(session_id):
                existing_history = True
                db_meta = await get_session_metadata(session_id) or {}
                session_title = db_meta.get("title", "")
                session_working_directory = db_meta.get("working_directory", "")
                session_pinned = bool(db_meta.get("pinned", False))
        except Exception as exc:
            logger.warning("Failed to check session in SQLite: %s", exc)

        if not existing_history:
            logger.debug("Session %s not found in SQLite, will create new", session_id)
    else:
        session_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = f"WS_session_{session_timestamp}"
        sender.session_id = session_id
        logger.debug("Generated new session ID: %s", session_id)

    runtime = WebSocketChatRuntime(
        session_id=session_id,
        session_title=session_title,
        session_working_directory=session_working_directory,
        session_pinned=session_pinned,
        existing_history=existing_history,
    )
    sender.session_id = session_id

    try:
        if existing_history is not None:
            runtime.ctx = await session_manager.get_or_load_session(session_id)
            sender.ctx = runtime.ctx
            if runtime.ctx is None:
                logger.warning(
                    "Session %s exists in SQLite but could not be loaded "
                    "(get_or_load_session returned None). Starting a blank session "
                    "to keep the connection alive.",
                    session_id,
                )
                runtime.ctx = await session_manager.create_session(session_id)
                sender.ctx = runtime.ctx
        else:
            runtime.ctx = await session_manager.create_session(session_id)
            sender.ctx = runtime.ctx
    except Exception as exc:
        logger.warning("SessionManager init failed, falling back: %s", exc)
        try:
            runtime.ctx = await session_manager.create_session(session_id)
            sender.ctx = runtime.ctx
        except Exception:
            logger.error("SessionManager fallback also failed", exc_info=True)
            await websocket.close(code=1011, reason="Session init failed")
            return None

    runtime.sync_from_ctx()
    if not runtime.session_title:
        runtime.session_title = session_title
    if not runtime.session_working_directory:
        runtime.session_working_directory = session_working_directory
    runtime.session_pinned = bool(runtime.session_pinned or session_pinned)

    await session_manager.mark_session_active(runtime.session_id)
    init_session_process_tracking()

    try:
        bus = get_message_bus()
        bus.set_session_context(runtime.session_id)
    except Exception:
        logger.debug("MessageBus session context not available")

    if existing_history is None:
        try:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            init_agent = runtime.agent_name or "code-puppy"
            init_model = runtime.model_name or "unknown"
            await write_system_message_to_sqlite(
                session_id=runtime.session_id,
                system_message_type="config",
                content=f"🐶 Started with {init_agent} ({init_model})",
                agent_name=init_agent,
                model_name=init_model,
                timestamp=now_iso,
            )
            if runtime.session_working_directory:
                path_segments = runtime.session_working_directory.split("/")[-3:]
                relative = "/".join(s for s in path_segments if s)
                await write_system_message_to_sqlite(
                    session_id=runtime.session_id,
                    system_message_type="directory",
                    content=f"Starting in {relative}",
                    system_message_path=runtime.session_working_directory,
                    agent_name=init_agent,
                    model_name=init_model,
                    timestamp=now_iso,
                )
        except Exception as init_exc:
            logger.warning(
                "Failed to write session init to SQLite: %s",
                init_exc,
                exc_info=True,
            )

    await send_typed(
        ServerSystem(
            content=f"Connected! Session: {runtime.session_id}",
            session_id=runtime.session_id,
            agent_name=runtime.agent_name,
            model_name=runtime.model_name,
            resumed=existing_history is not None,
            protocol_version=PROTOCOL_VERSION,
        )
    )
    await send_session_meta_snapshot(runtime=runtime, safe_send_json=safe_send_json)

    if existing_history and runtime.ctx:
        try:
            loaded_messages = runtime.ctx.agent.get_message_history()
            message_count = len(loaded_messages) if loaded_messages else 0
            await send_typed(
                ServerSessionRestored(
                    session_id=runtime.session_id,
                    message_count=message_count,
                    title=runtime.session_title,
                    ui_metadata=[],
                )
            )
            await replay_restored_system_messages(
                runtime=runtime, send_typed=send_typed
            )
            runtime.agent = runtime.ctx.agent
            logger.debug("Restored %d messages to session agent", message_count)
        except Exception as exc:
            logger.warning("Failed to restore session history: %s", exc)

    return runtime


__all__ = [
    "initialize_ws_session",
    "replay_restored_system_messages",
    "send_session_meta_snapshot",
]
