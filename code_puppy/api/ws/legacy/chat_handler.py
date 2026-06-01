"""WebSocket endpoint for interactive chat with the Code Puppy agent.

This is the largest and most complex WebSocket handler, responsible for:
- Interactive chat sessions with streaming responses
- Session management (create, restore, switch)
- Tool call/result forwarding
- File attachment processing
- Slash command handling
- Permission request/response flow
- Working directory management
- Real-time event streaming from the agent

NOTE: This handler was extracted from the monolithic websocket.py to improve
maintainability. The internal structure is preserved to avoid regressions.
Future refactoring should break down the message handling loop further.
"""

import asyncio
import datetime
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from code_puppy.api.db.queries import (
    update_session_working_directory,
    write_error_message_to_sqlite,
    write_system_message_to_sqlite,
    write_turn_to_sqlite,
)
from code_puppy.api.error_parser import parse_api_error as _legacy_parse_api_error
from code_puppy.api.session_context import _validate_session_id, session_manager
from code_puppy.api.ws.attachments import build_file_context_and_attachments
from code_puppy.api.ws.background_save import (
    fire_and_track,
    save_agent_result_in_background,
)
from code_puppy.api.ws.connection_manager import connection_manager
from code_puppy.api.ws.schemas import (
    PROTOCOL_VERSION,
    ClientMessage,
    ServerAgentInvoked,
    ServerAssistantMessageDelta,
    ServerAssistantMessageEnd,
    ServerAssistantMessageStart,
    ServerCancelled,
    ServerCommandResult,
    ServerConfigValue,
    ServerError,
    ServerMessage,
    ServerResponse,
    ServerSessionMetaUpdated,
    ServerSessionRestored,
    ServerSessionSwitched,
    ServerStatus,
    ServerStreamEnd,
    ServerSystem,
    ServerToolCall,
    ServerToolResult,
    ServerUserMessage,
    ServerWorkingDirectoryChanged,
)
from code_puppy.config import get_global_model_name
from code_puppy.messaging.bus import get_message_bus
from code_puppy.model_errors import normalize_model_error as _normalize_model_error
from code_puppy.session_storage import generate_heuristic_title
from code_puppy.tools.command_runner import (
    cleanup_session_process_tracking,
    init_session_process_tracking,
)

# Import session context for desk-puppy working directory support
try:
    from code_puppy.plugins.walmart_specific.session_context import (
        clear_session_working_directory,
        set_session_working_directory,
    )

    HAS_SESSION_CONTEXT = True
except ImportError:
    HAS_SESSION_CONTEXT = False

    def set_session_working_directory(d):
        pass

    def clear_session_working_directory():
        pass


_ClientMessageAdapter = TypeAdapter(ClientMessage)

logger = logging.getLogger(__name__)

# === TOOL-CALL-PARITY BRANCH LOADED ===
logger.warning(
    "🐕 CHAT_HANDLER LOADED FROM TOOL-CALL-PARITY BRANCH - ToolReturnPart fix active!"
)
print("🐕 CHAT_HANDLER LOADED FROM TOOL-CALL-PARITY BRANCH", flush=True)


# ---------------------------------------------------------------------------
# WebSocket error frame helpers  (see fix/orphaned-tool-use-id-history)
# ---------------------------------------------------------------------------

_UNKNOWN_ERROR_TYPE = "unknown_error"
_TOOL_HISTORY_ERROR_TYPE = "tool_history_error"

_CODE_TO_ERROR_TYPE: dict = {
    "rate_limit_or_overloaded": "rate_limit",
    "backend_unavailable": "server_error",
    "auth_error": "auth_error",
    "quota_exceeded": "quota_exceeded",
    "content_blocked": "content_blocked",
    "invalid_tool_history": _TOOL_HISTORY_ERROR_TYPE,
}


def parse_api_error(exc: Exception) -> dict:
    """Convert an agent-run exception into a structured frontend error dict.

    Wraps ``normalize_model_error`` for primary classification (including the
    new ``invalid_tool_history`` code for Anthropic HTTP 400 tool-mismatch
    errors), falling back to the legacy ``_legacy_parse_api_error`` for all
    other categories so existing behaviour is unchanged.

    Returns:
        Dict with keys: user_message, error_type, technical_details, action_required.
    """
    norm = _normalize_model_error(exc)
    if norm.code in _CODE_TO_ERROR_TYPE:
        error_type = _CODE_TO_ERROR_TYPE[norm.code]
        user_message = norm.user_message or str(exc)
        action_required = error_type in ("rate_limit", "quota_exceeded")
        return {
            "user_message": user_message,
            "error_type": error_type,
            "technical_details": repr(exc),
            "action_required": action_required,
        }
    # Fall back to legacy parser for unclassified errors
    return _legacy_parse_api_error(exc)


def has_streamed_content(collected_text) -> bool:
    """Return True when the client has already received streaming output chunks.

    Args:
        collected_text: List of text chunks accumulated during the agent run.
            Elements may be None or empty strings.

    Returns:
        True if at least one chunk has substantive (non-whitespace) content.
    """
    return any((chunk or "").strip() for chunk in collected_text)


def build_error_response_frames(
    agent_error: Exception,
    collected_text,
    session_id: str,
) -> list:
    """Build the ordered WebSocket frames to send when an agent error occurs.

    When streaming output was already delivered to the client, a ``stream_end``
    frame (``success=False``) is prepended so the frontend can exit its
    streaming state before processing the error frame.  Without this handshake
    the frontend hangs indefinitely waiting for a ``stream_end`` that never
    arrives.

    Args:
        agent_error: The exception raised by the agent run.
        collected_text: Accumulated streaming chunks from the current turn.
        session_id: The WebSocket session identifier.

    Returns:
        List of JSON-serialisable dicts to send to the client in order.
    """
    frames: list[dict] = []
    if has_streamed_content(collected_text):
        frames.append(
            ServerStreamEnd(
                success=False,
                session_id=session_id,
            ).model_dump(exclude_none=True)
        )
    parsed = parse_api_error(agent_error)
    frames.append(
        ServerError(
            error=parsed["user_message"],
            error_type=parsed["error_type"],
            technical_details=parsed["technical_details"],
            action_required=parsed.get("action_required"),
            session_id=session_id,
        ).model_dump(exclude_none=True)
    )
    return frames


def register_chat_endpoint(app: FastAPI) -> None:
    """Register the /ws/chat WebSocket endpoint."""

    @app.websocket("/ws/chat")
    async def websocket_chat(
        websocket: WebSocket, session_id: str | None = None
    ) -> None:
        """Interactive chat with the Code Puppy agent.

        Protocol:
        Client sends:
            {"type": "message", "content": "your message here"}

        Server sends:
            # Streaming message events (all include agent_name, model_name, tool_name metadata)
            {"type": "assistant_message_start", "message_id": "...", "part_type": "text|thinking",
             "agent_name": "...", "model_name": "...", "tool_name": "..." or null}
            {"type": "assistant_message_delta", "message_id": "...", "content": "...",
             "agent_name": "...", "model_name": "...", "tool_name": "..." or null}
            {"type": "assistant_message_end", "message_id": "...", "full_content": "...",
             "agent_name": "...", "model_name": "...", "tool_name": "..." or null}

            # Tool call events (include agent_name, model_name metadata)
            {"type": "tool_call", "tool_name": "...", "args": {...},
             "agent_name": "...", "model_name": "..."}
            {"type": "tool_result", "tool_name": "...", "result": "...", "success": true,
             "agent_name": "...", "model_name": "..."}

            # Final response
            {"type": "response", "content": "...", "done": true,
             "agent_name": "...", "model_name": "...", "tokens": {...}}

            # Errors
            {"type": "error", "error": "..."}

        Query Parameters:
            session_id: Optional session ID to resume. If not provided, a new session is created.
                       Example: /ws/chat?session_id=WS_session_20260115_143022
        """
        await websocket.accept()
        logger.debug(
            "Chat WebSocket client connected (session_id param: %s)", session_id
        )

        # Flag to track if WebSocket is still open
        ws_closed = False

        async def persist_error_payload(data: dict[str, Any]) -> None:
            """Persist structured error frames so they survive reloads."""
            if data.get("type") != "error" or not session_id:
                return

            try:
                await write_error_message_to_sqlite(
                    session_id=session_id,
                    error=str(data.get("error") or "An unknown error occurred"),
                    error_type=str(data.get("error_type") or "unknown"),
                    technical_details=str(data.get("technical_details") or ""),
                    action_required=data.get("action_required"),
                    agent_name=(ctx.agent_name if ctx else ""),
                    model_name=(ctx.model_name if ctx else ""),
                    timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                )
            except Exception:
                logger.warning(
                    "[WS:%s] Failed to persist error payload to SQLite",
                    session_id,
                    exc_info=True,
                )

        async def safe_send_json(data: dict) -> bool:
            """Safely send JSON to WebSocket, returns False if connection is closed."""
            nonlocal ws_closed
            if ws_closed:
                logger.debug(
                    "[WS:%s] safe_send_json skipped (ws_closed=True): type=%s",
                    session_id,
                    data.get("type"),
                )
                return False

            msg_type = data.get("type")
            if msg_type in {
                "error",
                "response",
                "assistant_message_start",
                "assistant_message_end",
            }:
                # Keep this low-noise but useful for tracing request lifecycle
                logger.debug(
                    "[WS:%s] → send_json type=%s keys=%s",
                    session_id,
                    msg_type,
                    sorted(list(data.keys())),
                )
                if msg_type == "error":
                    logger.debug(
                        "[WS:%s] error payload: error_type=%r action_required=%r error=%r",
                        session_id,
                        data.get("error_type"),
                        data.get("action_required"),
                        (data.get("error") or "")[:300],
                    )

            try:
                if msg_type == "error":
                    await persist_error_payload(data)
                await websocket.send_json(data)
                return True
            except Exception as e:
                logger.warning(
                    "[WS:%s] send_json failed for type=%s: %s",
                    session_id,
                    msg_type,
                    e,
                    exc_info=True,
                )
                if "close message" in str(e).lower() or "closed" in str(e).lower():
                    ws_closed = True
                    logger.debug("WebSocket closed, stopping sends")
                return False

        async def send_typed(msg: ServerMessage) -> bool:
            """Send a typed protocol message to the client."""
            return await safe_send_json(msg.model_dump(exclude_none=True))

        async def send_typed_tool_lifecycle(
            msg: ServerToolCall | ServerToolResult,
        ) -> bool:
            """Send tool lifecycle frames to the client."""
            return await send_typed(msg)

        ctx = None
        session_title = ""
        session_working_directory = ""  # Will be set by client or loaded from metadata
        session_pinned = False  # Track pinned state for persistence
        last_context_sent_directory = ""  # Track when we last sent directory context
        existing_history = None

        # Use provided session_id or generate new one
        if session_id:
            # Validate session_id to prevent path traversal
            try:
                _validate_session_id(session_id)
            except ValueError as e:
                logger.warning("Invalid session_id rejected: %r: %s", session_id, e)
                await websocket.close(code=1008, reason="Invalid session ID")
                return

            # Client wants to resume/continue a specific session
            logger.debug("Client requested session: %s", session_id)

            # SQLite is the source of truth — check session existence there.
            try:
                from code_puppy.api.db.queries import (
                    get_session_metadata,
                    session_exists,
                )

                if await session_exists(session_id):
                    existing_history = True
                    db_meta = await get_session_metadata(session_id) or {}
                    session_title = db_meta.get("title", "")
                    session_working_directory = db_meta.get("working_directory", "")
                    session_pinned = bool(db_meta.get("pinned", False))
            except Exception as e:
                logger.warning("Failed to check session in SQLite: %s", e)

            if not existing_history:
                logger.debug(
                    "Session %s not found in SQLite, will create new", session_id
                )
        else:
            # Generate new timestamp-based session ID
            session_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            session_id = f"WS_session_{session_timestamp}"
            logger.debug("Generated new session ID: %s", session_id)

        try:
            # --- SESSION ISOLATION: create or load via SessionManager ---
            try:
                if existing_history is not None:
                    # Session confirmed in SQLite — load it via SessionManager.
                    # get_or_load_session checks in-memory first, then falls
                    # back to a fresh SQLite load. SQLite is the sole source of truth.
                    ctx = await session_manager.get_or_load_session(session_id)
                    if ctx is None:
                        # SQLite confirmed this session exists but load returned None.
                        # This is unexpected (DB race, corrupt row, or schema mismatch).
                        # Log a warning and start fresh so the WebSocket can still
                        # function — silent data loss is worse than a blank session.
                        logger.warning(
                            "Session %s exists in SQLite but could not be loaded "
                            "(get_or_load_session returned None). "
                            "Starting a blank session to keep the connection alive.",
                            session_id,
                        )
                        ctx = await session_manager.create_session(session_id)
                    else:
                        # Update local state from loaded metadata
                        session_title = ctx.title
                        session_working_directory = ctx.working_directory
                        session_pinned = ctx.pinned
                else:
                    ctx = await session_manager.create_session(session_id)
            except Exception as e:
                logger.warning("SessionManager init failed, falling back: %s", e)
                try:
                    ctx = await session_manager.create_session(session_id)
                except Exception:
                    logger.error("SessionManager fallback also failed", exc_info=True)
                    await websocket.close(code=1011, reason="Session init failed")
                    return

            # Mark session as active (cancels any pending cleanup from previous disconnect)
            await session_manager.mark_session_active(session_id)

            # Initialize per-session process tracking (ContextVar isolation)
            init_session_process_tracking()

            # Set MessageBus session context for this WS connection
            try:
                bus = get_message_bus()
                bus.set_session_context(session_id)
            except Exception:
                logger.debug("MessageBus session context not available")

            # Convenience aliases — use ctx.agent everywhere instead of get_current_agent()
            agent = ctx.agent
            agent_name = ctx.agent_name
            model_name = ctx.model_name

            # ── Persist initial session context to SQLite (new sessions only) ───────
            # Write a config row (agent + model) and, if a CWD is set, a directory
            # row so the FE cold-load path sees them before the first user message.
            # Skipped for resumed sessions — their init rows were written at creation.
            if existing_history is None:
                try:
                    _now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                    _init_agent = agent_name or "code-puppy"
                    _init_model = model_name or "unknown"
                    await write_system_message_to_sqlite(
                        session_id=session_id,
                        system_message_type="config",
                        content=f"🐶 Started with {_init_agent} ({_init_model})",
                        agent_name=_init_agent,
                        model_name=_init_model,
                        timestamp=_now_iso,
                    )
                    if session_working_directory:
                        _path_segments = session_working_directory.split("/")[-3:]
                        _relative = "/".join(s for s in _path_segments if s)
                        await write_system_message_to_sqlite(
                            session_id=session_id,
                            system_message_type="directory",
                            content=f"Starting in {_relative}",
                            system_message_path=session_working_directory,
                            agent_name=_init_agent,
                            model_name=_init_model,
                            timestamp=_now_iso,
                        )
                except Exception as _init_exc:
                    logger.warning(
                        "Failed to write session init to SQLite: %s",
                        _init_exc,
                        exc_info=True,
                    )

            # Send welcome message
            await send_typed(
                ServerSystem(
                    content=f"Connected! Session: {session_id}",
                    session_id=session_id,
                    agent_name=agent_name,
                    model_name=model_name,
                    resumed=existing_history is not None,
                    protocol_version=PROTOCOL_VERSION,
                )
            )

            # If we resumed an existing session, notify the client
            if existing_history and ctx:
                try:
                    # History is already loaded into ctx.agent by session_manager.load_session().
                    # Pull it back out for the client-side UI metadata notification.
                    loaded_messages = ctx.agent.get_message_history()
                    message_count = len(loaded_messages) if loaded_messages else 0

                    # Notify client about restored session
                    await send_typed(
                        ServerSessionRestored(
                            session_id=session_id,
                            message_count=message_count,
                            title=session_title,
                            ui_metadata=[],
                        )
                    )

                    # Replay system messages (agent/model switches, CWD banners) to UI.
                    # These are persisted with pydantic_json=NULL so _load_from_sqlite
                    # skips them — we must send them separately so the UI shows them.
                    try:
                        from code_puppy.api.db.queries import get_active_messages

                        rows = await get_active_messages(session_id)
                        system_rows = [
                            r
                            for r in rows
                            if r.get("role") == "system"
                            and r.get("system_message_type")
                            in ("init", "config", "directory")
                        ]
                        for sys_row in system_rows:
                            await send_typed(
                                ServerSystem(
                                    content=sys_row.get("content", ""),
                                    session_id=session_id,
                                    agent_name=sys_row.get("agent_name", ""),
                                    model_name=sys_row.get("model_name", ""),
                                )
                            )
                        if system_rows:
                            logger.debug(
                                "Replayed %d system messages for session %s",
                                len(system_rows),
                                session_id,
                            )
                    except Exception as sys_exc:
                        logger.warning(
                            "Failed to replay system messages for session %s: %s",
                            session_id,
                            sys_exc,
                        )

                    agent = ctx.agent  # Refresh local alias
                    logger.debug("Restored %d messages to session agent", message_count)
                except Exception as e:
                    logger.warning("Failed to restore session history: %s", e)
            # Track active streaming task for cancellation
            active_drain_task = None
            # Track active agent task (run_with_mcp) for cancellation
            active_agent_task: asyncio.Task | None = None
            # Track stop_draining event for cancellation across iterations
            stop_draining = asyncio.Event()

            while True:
                try:
                    msg = await websocket.receive_json()

                    # Advisory validation — log but never reject
                    try:
                        _parsed = _ClientMessageAdapter.validate_python(msg)
                    except ValidationError as _val_err:
                        logger.warning(
                            "Client message failed validation: %s",
                            str(_val_err),
                            extra={
                                "type": msg.get("type")
                                if isinstance(msg, dict)
                                else "unknown"
                            },
                        )

                    if msg.get("type") == "switch_agent":
                        agent_name = msg.get("agent_name")
                        if agent_name:
                            try:
                                new_agent = await session_manager.switch_agent(
                                    session_id, agent_name
                                )
                                agent = new_agent  # Update local alias
                                ctx.agent = new_agent
                                model_name = (
                                    new_agent.get_model_name()
                                    if new_agent
                                    else "unknown"
                                )

                                # Persist to SQLite so the FE cold-load path sees it
                                try:
                                    await write_system_message_to_sqlite(
                                        session_id=session_id,
                                        system_message_type="config",
                                        content=f"🔄 Switched to {agent_name} ({model_name})",
                                        agent_name=agent_name,
                                        model_name=model_name,
                                    )
                                except Exception as _sw_exc:
                                    logger.warning(
                                        "Agent-switch SQLite write failed: %s",
                                        _sw_exc,
                                        exc_info=True,
                                    )

                                await send_typed(
                                    ServerSystem(
                                        content=f"🔄 Switched to {agent_name} ({model_name})",
                                        session_id=session_id,
                                        agent_name=agent_name,
                                        model_name=model_name,
                                    )
                                )
                            except Exception as e:
                                logger.error("Error switching agent: %s", e)
                                await send_typed(
                                    ServerError(
                                        error=f"Failed to switch to agent {agent_name}: {str(e)}",
                                        session_id=session_id,
                                    )
                                )

                    elif msg.get("type") == "switch_model":
                        model_name = msg.get("model_name") or msg.get("model")
                        if model_name:
                            try:
                                await session_manager.switch_model(
                                    session_id, model_name
                                )
                                agent = ctx.agent  # Refresh local alias
                                logger.debug("Switched model to: %s", model_name)

                                # Persist to SQLite so the FE cold-load path sees it
                                _sw_agent = ctx.agent_name or agent_name or "code-puppy"
                                try:
                                    await write_system_message_to_sqlite(
                                        session_id=session_id,
                                        system_message_type="config",
                                        content=f"🔄 Switched to {_sw_agent} ({model_name})",
                                        agent_name=_sw_agent,
                                        model_name=model_name,
                                    )
                                except Exception as _sw_exc:
                                    logger.warning(
                                        "Model-switch SQLite write failed: %s",
                                        _sw_exc,
                                        exc_info=True,
                                    )

                                await send_typed(
                                    ServerSystem(
                                        content=f"🔄 Switched to {_sw_agent} ({model_name})",
                                        session_id=session_id,
                                        model_name=model_name,
                                        agent_name=_sw_agent,
                                    )
                                )
                            except Exception as e:
                                logger.error("Error switching model: %s", e)
                                await send_typed(
                                    ServerError(
                                        error=f"Failed to switch to model {model_name}: {str(e)}",
                                        session_id=session_id,
                                    )
                                )
                        else:
                            await send_typed(
                                ServerError(
                                    error="No model_name provided for switch_model",
                                    session_id=session_id,
                                )
                            )

                    elif msg.get("type") == "switch_session":
                        """
                        Switch to a different session without reconnecting WebSocket.

                        How it works:
                        1. Client sends: {"type": "switch_session", "session_id": "WS_session_20260120_124356"}
                        2. Server loads session from ~/.code_puppy/ws_sessions/{session_id}.pkl
                        3. Server restores message history to the current agent
                        4. Server responds with session_switched event containing message count and title
                        5. Client can continue chatting with full conversation context

                        This approach keeps a single WebSocket connection alive while allowing
                        users to switch between multiple sessions instantly. All session data
                        stays on the local filesystem for privacy.
                        """
                        # Cancel any active streaming first
                        if active_drain_task and not active_drain_task.done():
                            logger.debug(
                                "Cancelling active streaming due to session switch"
                            )
                            stop_draining.set()  # Signal drain to stop
                            active_drain_task.cancel()
                            try:
                                await active_drain_task
                            except asyncio.CancelledError:
                                pass
                            stop_draining.clear()  # Reset for next streaming

                        new_session_id = msg.get("session_id")
                        if not new_session_id:
                            await send_typed(
                                ServerError(
                                    error="No session_id provided for switch_session",
                                    session_id=session_id,
                                )
                            )
                            continue

                        # Validate session_id to prevent path traversal
                        try:
                            _validate_session_id(new_session_id)
                        except ValueError as e:
                            logger.warning(
                                f"Invalid session_id in switch_session: {new_session_id!r}"
                            )
                            await send_typed(
                                ServerError(
                                    error=f"Invalid session ID: {e}",
                                    session_id=session_id,
                                )
                            )
                            continue

                        logger.debug("Switching to session: %s", new_session_id)

                        try:
                            # Check if target session exists in SQLite
                            try:
                                from code_puppy.api.db.queries import (
                                    session_exists as _se,
                                )

                                _target_exists = await _se(new_session_id)
                            except Exception:
                                _target_exists = False

                            if not _target_exists:
                                # Session doesn't exist - create new one with this ID
                                logger.debug(
                                    f"Session {new_session_id} not found, creating new"
                                )

                                # Save current session and mark inactive (keep in memory for 15 min)
                                try:
                                    await session_manager.save_session(session_id)
                                except Exception:
                                    pass
                                await session_manager.mark_session_inactive(session_id)

                                session_id = new_session_id
                                session_title = ""
                                session_working_directory = ""
                                session_pinned = False

                                ctx = await session_manager.create_session(session_id)
                                # Mark the new session as active
                                await session_manager.mark_session_active(session_id)
                                agent = ctx.agent
                                agent_name = ctx.agent_name
                                model_name = ctx.model_name

                                await send_typed(
                                    ServerSessionSwitched(
                                        session_id=new_session_id,
                                        message_count=0,
                                        title="",
                                        created=True,
                                        agent_name=agent_name,
                                        model_name=model_name,
                                    )
                                )
                                continue

                            # Load existing session via SessionManager
                            # Save current session and mark inactive (keep in memory for 15 min)
                            try:
                                await session_manager.save_session(session_id)
                            except Exception:
                                pass
                            await session_manager.mark_session_inactive(session_id)

                            session_id = new_session_id

                            # Try loading via SessionManager (checks in-memory first, then SQLite)
                            loaded_ctx = await session_manager.get_or_load_session(
                                session_id
                            )
                            if loaded_ctx is not None:
                                ctx = loaded_ctx
                                session_title = ctx.title
                                session_working_directory = ctx.working_directory
                                session_pinned = ctx.pinned
                            else:
                                # Legacy session or HMAC missing — load metadata
                                # from JSON (safe) and create fresh context
                                new_title = ""
                                new_working_directory = ""
                                new_pinned = False
                                try:
                                    from code_puppy.api.db.queries import (
                                        get_session_metadata as _gsm,
                                    )

                                    _sm = await _gsm(session_id) or {}
                                    new_title = _sm.get("title", "")
                                    new_working_directory = _sm.get(
                                        "working_directory", ""
                                    )
                                    new_pinned = bool(_sm.get("pinned", False))
                                except Exception:
                                    pass

                                ctx = await session_manager.create_session(session_id)
                                ctx.title = new_title
                                ctx.working_directory = new_working_directory
                                ctx.pinned = new_pinned
                                session_title = new_title
                                session_working_directory = new_working_directory
                                session_pinned = new_pinned

                            # Mark the new session as active
                            await session_manager.mark_session_active(session_id)

                            agent = ctx.agent
                            agent_name = ctx.agent_name
                            model_name = ctx.model_name
                            message_count = len(ctx.agent.get_message_history() or [])
                            logger.debug(
                                f"Restored {message_count} messages to session agent"
                            )

                            await send_typed(
                                ServerSessionSwitched(
                                    session_id=new_session_id,
                                    message_count=message_count,
                                    title=session_title,
                                    working_directory=session_working_directory,
                                    created=False,
                                    agent_name=agent_name,
                                    model_name=model_name,
                                )
                            )

                            logger.debug(
                                f"Switched to session {new_session_id} with {message_count} messages"
                            )

                        except Exception as e:
                            logger.error("Error switching session: %s", e)
                            await send_typed(
                                ServerError(
                                    error=f"Failed to switch to session {new_session_id}: {str(e)}",
                                    session_id=session_id,
                                )
                            )

                    elif msg.get("type") == "set_working_directory":
                        new_directory = msg.get("directory", "")
                        if new_directory:
                            # Expand ~ and resolve symlinks before validation
                            new_directory = str(
                                Path(new_directory).expanduser().resolve()
                            )
                            logger.info(
                                "[CWD DEBUG] set_working_directory received: new=%r, current=%r, session=%s",
                                new_directory,
                                session_working_directory,
                                session_id,
                            )
                            # Validate the directory exists
                            if Path(new_directory).is_dir():
                                # Skip if directory hasn't actually changed (avoids duplicate banners on reload)
                                if new_directory == session_working_directory:
                                    logger.info(
                                        "[CWD DEBUG] Skipping unchanged directory: %r, session=%s",
                                        new_directory,
                                        session_id,
                                    )
                                    await send_typed(
                                        ServerWorkingDirectoryChanged(
                                            directory=new_directory,
                                            success=True,
                                            session_id=session_id,
                                            unchanged=True,
                                        )
                                    )
                                    continue  # Skip to next message, don't write banner

                                session_working_directory = new_directory
                                logger.debug(
                                    "Working directory set to: %s",
                                    session_working_directory,
                                )

                                # NOTE: Do NOT append raw dict entries into agent
                                # message history here. The runtime expects typed
                                # ModelMessage objects; dict injection can corrupt
                                # subsequent turns and lead to result=None failures.

                                # Persist directory banner to SQLite so FE cold-load sees it
                                try:
                                    # Bug 4: use ctx.agent_name / ctx.model_name directly
                                    # so this works even when ctx.agent is None.
                                    _cwd_agent = (
                                        ctx.agent_name if ctx else None
                                    ) or "code-puppy"
                                    _cwd_model = (
                                        ctx.model_name if ctx else None
                                    ) or "unknown"
                                    _cwd_segs = session_working_directory.split("/")[
                                        -3:
                                    ]
                                    _cwd_rel = "/".join(s for s in _cwd_segs if s)
                                    from code_puppy.config import get_puppy_name as _gpn

                                    _pname = _gpn() or "puppy"
                                    logger.info(
                                        "[CWD DEBUG] Writing CWD banner to SQLite: path=%r, session=%s",
                                        session_working_directory,
                                        session_id,
                                    )
                                    await write_system_message_to_sqlite(
                                        session_id=session_id,
                                        system_message_type="directory",
                                        content=f"{_pname} is now at {_cwd_rel}",
                                        system_message_path=session_working_directory,
                                        agent_name=_cwd_agent,
                                        model_name=_cwd_model,
                                    )
                                    # Bug 5: also stamp working_directory on the sessions row
                                    _now_cwd = datetime.datetime.now(
                                        datetime.timezone.utc
                                    ).isoformat()
                                    await update_session_working_directory(
                                        session_id=session_id,
                                        working_directory=session_working_directory,
                                        updated_at=_now_cwd,
                                    )
                                except Exception as _cwd_exc:
                                    logger.warning(
                                        "CWD SQLite write failed: %s",
                                        _cwd_exc,
                                        exc_info=True,
                                    )

                                await send_typed(
                                    ServerWorkingDirectoryChanged(
                                        directory=session_working_directory,
                                        success=True,
                                        session_id=session_id,
                                    )
                                )
                            else:
                                await send_typed(
                                    ServerWorkingDirectoryChanged(
                                        directory=new_directory,
                                        success=False,
                                        error="Directory does not exist",
                                        session_id=session_id,
                                    )
                                )
                        else:
                            await send_typed(
                                ServerError(
                                    error="No directory provided for set_working_directory",
                                    session_id=session_id,
                                )
                            )

                    elif msg.get("type") == "update_session_meta":
                        # Update session metadata (pinned, title) — persisted to SQLite.
                        try:
                            # Update in-memory state (local vars AND SessionContext)
                            if "pinned" in msg and isinstance(msg["pinned"], bool):
                                session_pinned = msg["pinned"]
                                if ctx is not None:
                                    ctx.pinned = session_pinned
                            if "title" in msg and isinstance(msg["title"], str):
                                session_title = msg["title"]
                                if ctx is not None:
                                    ctx.title = session_title

                            # Persist to SQLite (single source of truth).
                            # Use a targeted UPDATE — NOT upsert_session() — so that
                            # message_count, total_tokens, and other stats are
                            # never zeroed out by a rename/pin operation.
                            try:
                                from datetime import datetime as _dt
                                from datetime import timezone as _tz

                                from code_puppy.api.db.queries import (
                                    update_session_meta_fields,
                                )

                                await update_session_meta_fields(
                                    session_id=session_id,
                                    title=session_title,
                                    pinned=session_pinned,
                                    updated_at=_dt.now(_tz.utc).isoformat(),
                                )
                                logger.debug(
                                    f"Updated session meta in SQLite for {session_id}: pinned={session_pinned}"
                                )
                            except Exception as meta_exc:
                                logger.warning(
                                    "Failed to persist session meta to SQLite: %s",
                                    meta_exc,
                                )

                            await send_typed(
                                ServerSessionMetaUpdated(
                                    session_id=session_id,
                                    pinned=session_pinned,
                                    title=session_title,
                                )
                            )
                        except Exception as e:
                            logger.error("Error updating session meta: %s", e)
                            await send_typed(
                                ServerError(
                                    error=f"Failed to update session metadata: {str(e)}",
                                    session_id=session_id,
                                )
                            )

                    elif msg.get("type") == "get_config":
                        config_key = msg.get("key", "")
                        if config_key:
                            from code_puppy.config import get_value

                            value = get_value(config_key)
                            await send_typed(
                                ServerConfigValue(
                                    key=config_key,
                                    value=value,
                                    session_id=session_id,
                                )
                            )
                        else:
                            await send_typed(
                                ServerError(
                                    error="No key provided for get_config",
                                    session_id=session_id,
                                )
                            )

                    elif msg.get("type") == "set_config":
                        config_key = msg.get("key", "")
                        config_value = msg.get("value", "")
                        if config_key:
                            from code_puppy.config import set_config_value

                            try:
                                set_config_value(config_key, str(config_value))
                                logger.debug(
                                    f"Config set: {config_key} = {config_value}"
                                )
                                await send_typed(
                                    ServerConfigValue(
                                        key=config_key,
                                        value=config_value,
                                        success=True,
                                        session_id=session_id,
                                    )
                                )
                            except Exception as e:
                                await send_typed(
                                    ServerError(
                                        error=f"Failed to set config: {e}",
                                        session_id=session_id,
                                    )
                                )
                        else:
                            await send_typed(
                                ServerError(
                                    error="No key provided for set_config",
                                    session_id=session_id,
                                )
                            )

                    # Handle slash command execution
                    elif msg.get("type") == "command":
                        command_str = msg.get("command", "")
                        logger.debug("Command requested: %s", command_str)

                        try:
                            from io import StringIO

                            from rich.console import Console

                            from code_puppy.command_line.command_handler import (
                                get_commands_help,
                                handle_command,
                            )

                            output = None
                            captured_messages = []

                            # Special handling for /help - we can get the text directly
                            cmd_name = (
                                command_str.strip().lstrip("/").split()[0]
                                if command_str.strip()
                                else ""
                            )
                            if cmd_name in ("help", "h"):
                                # Get help text directly
                                help_text = get_commands_help()
                                # Render to plain text
                                output_buffer = StringIO()
                                console = Console(
                                    file=output_buffer,
                                    force_terminal=False,
                                    width=100,
                                    no_color=True,
                                )
                                console.print(help_text)
                                output = output_buffer.getvalue().strip()
                                result = True
                            else:
                                # For other commands, just execute and report success/failure
                                # The actual output goes to the message queue/terminal
                                result = handle_command(command_str)
                                # Some commands might return a string as output
                                if isinstance(result, str):
                                    output = result
                                    result = True

                            # Send command result
                            await send_typed(
                                ServerCommandResult(
                                    command=command_str,
                                    success=result is True or result is not False,
                                    output=output,
                                    messages=captured_messages,
                                    result=str(result)
                                    if result and result is not True
                                    else None,
                                    session_id=session_id,
                                )
                            )
                            logger.debug(
                                f"Command executed: {command_str} -> success={result is True or result is not False}, output_len={len(output) if output else 0}"
                            )

                        except Exception as cmd_error:
                            import traceback

                            error_details = traceback.format_exc()
                            logger.error("Command error: %s", cmd_error)
                            logger.error("Traceback: %s", error_details)
                            await send_typed(
                                ServerCommandResult(
                                    command=command_str,
                                    success=False,
                                    error=str(cmd_error),
                                    session_id=session_id,
                                )
                            )
                        continue

                    # Handle cancel/interrupt request
                    elif msg.get("type") == "cancel":
                        logger.debug(
                            "Cancel request received - stopping active streaming and agent task"
                        )

                        # Cancel any active streaming
                        if active_drain_task and not active_drain_task.done():
                            stop_draining.set()  # Signal drain to stop
                            active_drain_task.cancel()
                            try:
                                await active_drain_task
                            except asyncio.CancelledError:
                                pass
                            stop_draining.clear()  # Reset for next streaming
                            logger.debug("Active streaming cancelled")

                        # Cancel the in-flight agent run (run_with_mcp) if present
                        if active_agent_task and not active_agent_task.done():
                            logger.debug(
                                "Cancelling active agent task due to user interrupt"
                            )
                            active_agent_task.cancel()
                            try:
                                await active_agent_task
                            except asyncio.CancelledError:
                                logger.debug("Active agent task cancelled successfully")
                            active_agent_task = None

                        # Send confirmation
                        await send_typed(
                            ServerStatus(
                                status="cancelled",
                                session_id=session_id,
                            )
                        )
                        continue

                    elif msg.get("type") == "permission_response":
                        # Handle permission response from user
                        from code_puppy.api.permissions import (
                            handle_permission_response,
                        )

                        request_id = msg.get("request_id")
                        approved = msg.get("approved", False)

                        if request_id:
                            handled = handle_permission_response(request_id, approved)
                            if handled:
                                logger.debug(
                                    f"[Permission] ✅ Handled response: {request_id} = {approved}"
                                )
                            else:
                                logger.warning(
                                    f"[Permission] ❌ Unknown request: {request_id}"
                                )
                        else:
                            logger.error(
                                "[WebSocket] ❌ No request_id in permission_response!"
                            )
                        continue

                    elif msg.get("type") == "message":
                        # Set WebSocket context for permission requests
                        from code_puppy.api.permission_plugin import (
                            set_suppress_emitter_tool_events,
                            set_websocket_context,
                        )

                        set_websocket_context(websocket, session_id)

                        user_message = msg.get("content", "")

                        # Initialize attachment tracking variables at message scope
                        original_user_message = user_message  # Store clean message
                        attachment_metadata = []  # Will be populated if attachments exist

                        # Check if a specific model was requested for this message
                        requested_model = msg.get("model")
                        if requested_model:
                            current_model = ctx.model_name
                            if requested_model != current_model:
                                try:
                                    await session_manager.switch_model(
                                        session_id, requested_model
                                    )
                                    agent = ctx.agent  # Refresh alias
                                    model_name = requested_model
                                    logger.debug(
                                        f"Switching to model {requested_model} for this message"
                                    )
                                except Exception as e:
                                    logger.warning("Failed to switch model: %s", e)

                        # Apply model_settings from frontend (reasoning_effort, verbosity, etc.)
                        model_settings = msg.get("model_settings", {})
                        if model_settings:
                            from code_puppy.config import set_model_setting

                            target_model = requested_model or get_global_model_name()
                            for setting_name, value in model_settings.items():
                                try:
                                    set_model_setting(target_model, setting_name, value)
                                    logger.debug(
                                        f"Applied model_setting {setting_name}={value} for {target_model}"
                                    )
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to apply model_setting {setting_name}: {e}"
                                    )

                        if not user_message.strip():
                            await send_typed(
                                ServerError(
                                    error="Empty message",
                                    session_id=session_id,
                                )
                            )
                            continue

                        logger.debug(
                            f"Chat message from client: {user_message[:50]}..."
                        )

                        # Echo the user message back
                        await send_typed(
                            ServerUserMessage(
                                content=user_message,
                                session_id=session_id,
                            )
                        )

                        # Get the session agent and process the message
                        try:
                            agent = ctx.agent

                            # Reload agent if a different model was requested
                            if requested_model:
                                agent.reload_code_generation_agent()
                                logger.debug(
                                    f"Reloaded agent with model: {requested_model}"
                                )

                            if not agent:
                                await send_typed(
                                    ServerError(
                                        error="Agent not available. Please start Code Puppy first.",
                                        session_id=session_id,
                                    )
                                )
                                continue

                            # Subscribe to frontend emitter and run drain task CONCURRENTLY
                            event_queue = None
                            collected_text = []
                            stop_draining.clear()  # Reset for this message
                            drain_task = None
                            active_parts: dict[
                                int, dict
                            ] = {}  # Track message parts by index
                            tool_id_aliases: dict[str, str] = {}
                            tool_group_ids: dict[
                                str, str
                            ] = {}  # tool_id -> tool_group_id mapping
                            b1_streaming_used = (
                                False  # Track if B1 streaming sent any content
                            )
                            agent_error = None  # Will hold exception if agent run fails

                            async def drain_events_concurrent(
                                ready_event: asyncio.Event = None,
                            ):
                                """Background task to drain events and send structured messages in real-time."""
                                nonlocal collected_text, b1_streaming_used, ws_closed
                                import time as time_module

                                # Capture agent and model metadata at the start.
                                # Chain `or` fallbacks so that an empty-string agent.name
                                # (possible before agent is fully initialised) still resolves
                                # to a meaningful value via the session context defaults.
                                current_agent_name = (
                                    (agent.name if agent else "")
                                    or ctx.agent_name
                                    or "code-puppy"
                                )
                                current_model_name = (
                                    (agent.get_model_name() if agent else "")
                                    or ctx.model_name
                                    or "unknown"
                                )
                                current_tool_name = None  # Track active tool name
                                current_tool_group_id: str | None = (
                                    None  # Track current tool batch group ID
                                )

                                # Track pending tool calls for tool_result generation
                                # {tool_id: {tool_name, start_time, part_index}}
                                pending_tool_calls: dict[str, dict] = {}

                                def resolve_pending_tool_id(
                                    *,
                                    tool_call_id: str | None = None,
                                    tool_name: str | None = None,
                                ) -> str | None:
                                    """Resolve canonical frontend tool_id for a backend tool call reference."""
                                    if (
                                        tool_call_id
                                        and tool_call_id in pending_tool_calls
                                    ):
                                        return tool_call_id

                                    if tool_call_id:
                                        for (
                                            _pending_id,
                                            _pending_info,
                                        ) in pending_tool_calls.items():
                                            if (
                                                _pending_info.get("raw_tool_call_id")
                                                == tool_call_id
                                            ):
                                                return _pending_id

                                    if tool_name:
                                        for (
                                            _pending_id,
                                            _pending_info,
                                        ) in pending_tool_calls.items():
                                            if (
                                                _pending_info.get("tool_name")
                                                == tool_name
                                            ):
                                                return _pending_id

                                    return None

                                def resolve_tool_group_id(
                                    *,
                                    tool_id: str | None = None,
                                    pending_info: dict | None = None,
                                    fallback_group_id: str | None = None,
                                    tool_name: str | None = None,
                                    source: str = "unknown",
                                ) -> str:
                                    """Return a non-empty tool_group_id for tool lifecycle frames.

                                    Priority order:
                                    1) pending tool info
                                    2) tool_id -> group map
                                    3) explicit fallback passed by caller
                                    4) current in-flight batch group
                                    5) synthetic deterministic-ish fallback (last resort)
                                    """
                                    nonlocal current_tool_group_id

                                    group_id = None
                                    if pending_info is not None:
                                        group_id = pending_info.get("tool_group_id")

                                    if not group_id and tool_id:
                                        group_id = tool_group_ids.get(tool_id)

                                    if not group_id and fallback_group_id:
                                        group_id = fallback_group_id

                                    if not group_id:
                                        group_id = current_tool_group_id

                                    if not group_id:
                                        raw_hint = tool_id or tool_name or "unknown"
                                        stable_hint = (
                                            re.sub(
                                                r"[^a-z0-9_-]",
                                                "-",
                                                raw_hint.lower(),
                                            )[:24].strip("-")
                                            or "unknown"
                                        )
                                        group_id = f"tg-fallback-{stable_hint}-{str(uuid.uuid4())[:6]}"
                                        logger.warning(
                                            "[ws] Synthesized missing tool_group_id "
                                            "for source=%s tool_id=%s tool_name=%s",
                                            source,
                                            tool_id,
                                            tool_name,
                                        )

                                    if tool_id:
                                        tool_group_ids[tool_id] = group_id
                                        if pending_info is not None:
                                            pending_info["tool_group_id"] = group_id
                                        elif tool_id in pending_tool_calls:
                                            pending_tool_calls[tool_id][
                                                "tool_group_id"
                                            ] = group_id

                                    if current_tool_group_id is None:
                                        current_tool_group_id = group_id

                                    return group_id

                                event_count = 0
                                first_iteration = True
                                while not stop_draining.is_set():
                                    # Exit if WebSocket is closed
                                    if ws_closed:
                                        logger.debug(
                                            "WebSocket closed, exiting drain loop"
                                        )
                                        break
                                    # Signal ready on first iteration (we're in the loop now)
                                    if first_iteration and ready_event:
                                        ready_event.set()
                                        first_iteration = False
                                        # Yield to allow run_with_mcp to start and emit first events
                                        await asyncio.sleep(0)
                                        continue  # Re-enter loop to collect any queued events
                                    # Event-driven batch collection with 10ms timeout for responsiveness.
                                    # Instead of polling the clock, we use asyncio.wait_for to block until
                                    # the first event arrives, then collect any additional events already queued.
                                    events_to_send = []
                                    try:
                                        # Wait for first event with 10ms timeout (blocks efficiently)
                                        first_event = await asyncio.wait_for(
                                            event_queue.get(), timeout=0.01
                                        )
                                        events_to_send.append(first_event)
                                        event_count += 1

                                        # Collect any additional events already in queue (non-blocking)
                                        # This keeps the batching benefit without polling the clock
                                        while not event_queue.empty():
                                            try:
                                                event = event_queue.get_nowait()
                                                events_to_send.append(event)
                                                event_count += 1
                                            except Exception:
                                                break

                                    except asyncio.TimeoutError:
                                        # No events available within 10ms timeout
                                        # No polling needed - asyncio.wait_for blocks efficiently
                                        pass

                                    # Log batch composition for debugging
                                    if events_to_send:
                                        event_types = {}
                                        for e in events_to_send:
                                            et = e.get("type", "unknown")
                                            event_types[et] = event_types.get(et, 0) + 1
                                        logger.debug(
                                            "[%s] Batch: %d events - %s",
                                            session_id,
                                            len(events_to_send),
                                            event_types,
                                        )

                                    # Process collected events
                                    for event in events_to_send:
                                        # If cancellation was requested, stop processing immediately
                                        if stop_draining.is_set():
                                            logger.debug(
                                                "stop_draining set during batch - stopping event processing"
                                            )
                                            break

                                        event_type = event.get("type", "")
                                        event_data = event.get("data", {})

                                        try:
                                            # Handle tool call events
                                            if event_type == "tool_call_start":
                                                tool_name = event_data.get(
                                                    "tool_name", "unknown"
                                                )
                                                tool_args = event_data.get(
                                                    "tool_args", {}
                                                )
                                                tool_id = str(uuid.uuid4())[:8]

                                                # Generate tool group ID for this batch if not already set
                                                if current_tool_group_id is None:
                                                    current_tool_group_id = (
                                                        f"tg-{str(uuid.uuid4())[:8]}"
                                                    )

                                                logger.debug(
                                                    "[ws] tool_call: %s", tool_name
                                                )

                                                # Track current tool name
                                                current_tool_name = tool_name

                                                # Register in pending_tool_calls so
                                                # tool_call_complete can echo back the
                                                # same tool_id the frontend already knows.
                                                pending_tool_calls[tool_id] = {
                                                    "tool_name": tool_name,
                                                    "start_time": time_module.time(),
                                                    "tool_group_id": current_tool_group_id,
                                                }

                                                await send_typed_tool_lifecycle(
                                                    ServerToolCall(
                                                        tool_id=tool_id,
                                                        tool_name=tool_name,
                                                        args=tool_args,
                                                        timestamp=time_module.time(),
                                                        session_id=session_id,
                                                        agent_name=current_agent_name,
                                                        model_name=current_model_name,
                                                        tool_group_id=current_tool_group_id,
                                                    )
                                                )

                                            elif event_type == "tool_call_complete":
                                                tool_name = event_data.get(
                                                    "tool_name", "unknown"
                                                )
                                                result = event_data.get(
                                                    "result",
                                                    event_data.get(
                                                        "result_summary", ""
                                                    ),
                                                )
                                                success = event_data.get(
                                                    "success", True
                                                )
                                                duration = event_data.get(
                                                    "duration_ms", 0
                                                )

                                                logger.debug(
                                                    "[ws] tool_result: %s", tool_name
                                                )

                                                # Clear current tool name after completion
                                                current_tool_name = None

                                                # Match the tool_id we generated at
                                                # tool_call_start so the frontend can
                                                # correlate result → call by ID, not
                                                # just by name (names are not unique).
                                                matching_tool_id = next(
                                                    (
                                                        tid
                                                        for tid, info in pending_tool_calls.items()
                                                        if info["tool_name"]
                                                        == tool_name
                                                    ),
                                                    None,
                                                )
                                                matching_pending_info = (
                                                    pending_tool_calls.get(
                                                        matching_tool_id
                                                    )
                                                    if matching_tool_id
                                                    else None
                                                )
                                                tool_group_id_for_result = resolve_tool_group_id(
                                                    tool_id=matching_tool_id,
                                                    pending_info=matching_pending_info,
                                                    fallback_group_id=current_tool_group_id,
                                                    tool_name=tool_name,
                                                    source="tool_call_complete",
                                                )

                                                if matching_tool_id:
                                                    pending_tool_calls.pop(
                                                        matching_tool_id, None
                                                    )

                                                await send_typed_tool_lifecycle(
                                                    ServerToolResult(
                                                        tool_id=matching_tool_id,
                                                        tool_name=tool_name,
                                                        result=result,
                                                        success=success,
                                                        duration_ms=duration,
                                                        timestamp=time_module.time(),
                                                        session_id=session_id,
                                                        agent_name=current_agent_name,
                                                        model_name=current_model_name,
                                                        tool_group_id=tool_group_id_for_result,
                                                    )
                                                )

                                            elif event_type == "agent_invoked":
                                                agent_name_inv = event_data.get(
                                                    "agent_name", "unknown"
                                                )
                                                prompt_preview = event_data.get(
                                                    "prompt_preview", ""
                                                )

                                                logger.debug(
                                                    "[ws] agent_invoked: %s",
                                                    agent_name_inv,
                                                )

                                                await send_typed(
                                                    ServerAgentInvoked(
                                                        agent_name=agent_name_inv,
                                                        prompt_preview=prompt_preview,
                                                        timestamp=time_module.time(),
                                                        session_id=session_id,
                                                    )
                                                )

                                            # Handle streaming events
                                            elif event_type == "stream_event":
                                                inner_type = event_data.get(
                                                    "event_type", ""
                                                )
                                                inner_data = event_data.get(
                                                    "event_data", {}
                                                )
                                                if inner_type == "part_start":
                                                    part_index = inner_data.get(
                                                        "index", 0
                                                    )
                                                    part_type = inner_data.get(
                                                        "part_type", "unknown"
                                                    )
                                                    logger.warning(
                                                        "[ws] part_start: part_type=%s, part_index=%s",
                                                        part_type,
                                                        part_index,
                                                    )

                                                    # Extract initial content from the part if present
                                                    # The part object may have content already (especially for TextPart/ThinkingPart)
                                                    part_obj = inner_data.get(
                                                        "part", {}
                                                    )
                                                    initial_content = ""

                                                    if (
                                                        hasattr(part_obj, "content")
                                                        and part_obj.content
                                                    ):
                                                        initial_content = (
                                                            part_obj.content
                                                        )
                                                    elif isinstance(
                                                        part_obj, dict
                                                    ) and part_obj.get("content"):
                                                        initial_content = part_obj.get(
                                                            "content", ""
                                                        )

                                                    if part_type in (
                                                        "TextPart",
                                                        "ThinkingPart",
                                                    ):
                                                        msg_type = (
                                                            "thinking"
                                                            if part_type
                                                            == "ThinkingPart"
                                                            else "text"
                                                        )

                                                        # When a TextPart starts, any pending tool calls have completed
                                                        # Send status-only tool_result during streaming to update UI
                                                        # The actual result data will be sent later from extraction code
                                                        if (
                                                            pending_tool_calls
                                                            and part_type == "TextPart"
                                                        ):
                                                            for (
                                                                tool_id,
                                                                tool_info,
                                                            ) in list(
                                                                pending_tool_calls.items()
                                                            ):
                                                                if tool_info.get(
                                                                    "status_only_sent"
                                                                ):
                                                                    continue
                                                                duration_ms = (
                                                                    time_module.time()
                                                                    - tool_info[
                                                                        "start_time"
                                                                    ]
                                                                ) * 1000
                                                                logger.debug(
                                                                    f"[WebSocket] Sending status-only tool_result for: {tool_info['tool_name']} (duration: {duration_ms:.1f}ms)"
                                                                )
                                                                await send_typed(
                                                                    ServerToolResult(
                                                                        tool_id=tool_id,
                                                                        result={
                                                                            "_status": "completed",
                                                                            "_pending_full_result": True,
                                                                        },
                                                                        tool_name=tool_info[
                                                                            "tool_name"
                                                                        ],
                                                                        success=True,
                                                                        duration_ms=duration_ms,
                                                                        timestamp=time_module.time(),
                                                                        session_id=session_id,
                                                                        agent_name=current_agent_name,
                                                                        model_name=current_model_name,
                                                                        tool_group_id=resolve_tool_group_id(
                                                                            tool_id=tool_id,
                                                                            pending_info=tool_info,
                                                                            fallback_group_id=current_tool_group_id,
                                                                            tool_name=tool_info.get(
                                                                                "tool_name"
                                                                            ),
                                                                            source="status_only_result",
                                                                        ),
                                                                    )
                                                                )
                                                                tool_info[
                                                                    "status_only_sent"
                                                                ] = True
                                                            current_tool_name = None

                                                        # Check if part already exists (created by early delta)
                                                        if part_index in active_parts:
                                                            # Just update the type, keep existing message_id
                                                            active_parts[part_index][
                                                                "type"
                                                            ] = msg_type
                                                            message_id = active_parts[
                                                                part_index
                                                            ]["id"]
                                                            # If there's initial content, add it to the existing accumulated content
                                                            if initial_content:
                                                                active_parts[
                                                                    part_index
                                                                ]["content"] = (
                                                                    initial_content
                                                                    + active_parts[
                                                                        part_index
                                                                    ]["content"]
                                                                )
                                                                collected_text.insert(
                                                                    0, initial_content
                                                                )  # Prepend to collected text too
                                                            logger.debug(
                                                                f"[Stream Debug] Part already exists, reusing message_id={message_id}"
                                                            )
                                                            # Don't send another start event
                                                            continue

                                                        message_id = f"msg-{int(time_module.time() * 1000)}-{part_index}"
                                                        active_parts[part_index] = {
                                                            "id": message_id,
                                                            "type": msg_type,
                                                            "content": initial_content,  # Start with initial content if present
                                                        }

                                                        # If there's initial content, add it to collected_text
                                                        if initial_content:
                                                            collected_text.append(
                                                                initial_content
                                                            )

                                                        # New assistant output part indicates turn boundary for tool grouping
                                                        if part_index == 0:
                                                            current_tool_group_id = None

                                                        await safe_send_json(
                                                            ServerAssistantMessageStart(
                                                                message_id=message_id,
                                                                part_type=msg_type,
                                                                part_index=part_index,
                                                                timestamp=time_module.time(),
                                                                session_id=session_id,
                                                                agent_name=current_agent_name,
                                                                model_name=current_model_name,
                                                                tool_name=current_tool_name,
                                                            ).model_dump(
                                                                exclude_none=True
                                                            )
                                                        )

                                                        # If there's initial content, send it as a delta immediately
                                                        if initial_content:
                                                            _delta = ServerAssistantMessageDelta.model_construct(
                                                                type="assistant_message_delta",
                                                                message_id=message_id,
                                                                content=initial_content,
                                                                part_index=part_index,
                                                                session_id=session_id,
                                                                agent_name=current_agent_name,
                                                                model_name=current_model_name,
                                                                tool_name=current_tool_name,
                                                            )
                                                            await safe_send_json(
                                                                _delta.model_dump(
                                                                    exclude_none=True
                                                                )
                                                            )
                                                            # Mark that B1 streaming was used (nonlocal already declared above)
                                                            b1_streaming_used = True

                                                    elif part_type == "ToolCallPart":
                                                        # Extract tool info from the part
                                                        tool_name = "unknown"
                                                        tool_call_id = None
                                                        tool_args_str = ""

                                                        # Extract tool info from part_obj (dict or object)
                                                        if hasattr(
                                                            part_obj, "tool_name"
                                                        ):
                                                            tool_name = (
                                                                part_obj.tool_name
                                                            )
                                                        elif isinstance(part_obj, dict):
                                                            tool_name = part_obj.get(
                                                                "tool_name", "unknown"
                                                            )

                                                        if hasattr(
                                                            part_obj, "tool_call_id"
                                                        ):
                                                            tool_call_id = (
                                                                part_obj.tool_call_id
                                                            )
                                                        elif isinstance(part_obj, dict):
                                                            tool_call_id = part_obj.get(
                                                                "tool_call_id"
                                                            )

                                                        if hasattr(part_obj, "args"):
                                                            tool_args_str = (
                                                                part_obj.args or ""
                                                            )
                                                        elif isinstance(part_obj, dict):
                                                            tool_args_str = (
                                                                part_obj.get("args", "")
                                                                or ""
                                                            )

                                                        tool_id = (
                                                            tool_call_id
                                                            or str(uuid.uuid4())[:8]
                                                        )

                                                        # Track this tool call part with args buffer for accumulation
                                                        # Don't send tool_call yet - wait for part_end when args are complete
                                                        active_parts[part_index] = {
                                                            "id": tool_id,
                                                            "raw_tool_call_id": tool_call_id,
                                                            "type": "tool_call",
                                                            "tool_name": tool_name,
                                                            "args": tool_args_str,
                                                            "args_buffer": tool_args_str,  # Buffer for accumulating args_delta
                                                            "start_time": time_module.time(),  # Track when tool started
                                                        }

                                                        # Track current tool name
                                                        current_tool_name = tool_name

                                                        logger.debug(
                                                            f"[WebSocket] ToolCallPart started: {tool_name} (id: {tool_id})"
                                                        )
                                                        # tool_call event will be sent on part_end when args are complete

                                                    elif part_type == "ToolReturnPart":
                                                        logger.info(
                                                            f"[WebSocket] ToolReturnPart detected! part_index={part_index}"
                                                        )
                                                        # Extract tool result info from the part
                                                        tool_call_id = None
                                                        tool_content = None

                                                        # Extract tool_call_id
                                                        if hasattr(
                                                            part_obj, "tool_call_id"
                                                        ):
                                                            tool_call_id = (
                                                                part_obj.tool_call_id
                                                            )
                                                        elif isinstance(part_obj, dict):
                                                            tool_call_id = part_obj.get(
                                                                "tool_call_id"
                                                            )

                                                        # Extract content (the tool result)
                                                        if hasattr(part_obj, "content"):
                                                            tool_content = (
                                                                part_obj.content
                                                            )
                                                        elif isinstance(part_obj, dict):
                                                            tool_content = part_obj.get(
                                                                "content"
                                                            )

                                                        # Try to serialize complex result objects
                                                        if (
                                                            tool_content
                                                            and not isinstance(
                                                                tool_content,
                                                                (
                                                                    str,
                                                                    dict,
                                                                    list,
                                                                    int,
                                                                    float,
                                                                    bool,
                                                                    type(None),
                                                                ),
                                                            )
                                                        ):
                                                            try:
                                                                import json

                                                                # Try to convert to dict first (for Pydantic models)
                                                                if hasattr(
                                                                    tool_content,
                                                                    "model_dump",
                                                                ):
                                                                    tool_content = tool_content.model_dump()
                                                                elif hasattr(
                                                                    tool_content, "dict"
                                                                ):
                                                                    tool_content = tool_content.dict()
                                                                elif hasattr(
                                                                    tool_content,
                                                                    "__dict__",
                                                                ):
                                                                    tool_content = tool_content.__dict__
                                                                else:
                                                                    tool_content = str(
                                                                        tool_content
                                                                    )
                                                            except Exception as e:
                                                                logger.debug(
                                                                    f"[WebSocket] Could not serialize tool result: {e}"
                                                                )
                                                                tool_content = str(
                                                                    tool_content
                                                                )

                                                        # Find the corresponding pending tool call, store and SEND the result
                                                        _result_sent = False
                                                        if tool_call_id:
                                                            resolved_pending_id = resolve_pending_tool_id(
                                                                tool_call_id=tool_call_id
                                                            )
                                                            if resolved_pending_id:
                                                                _result_sent = True
                                                                pending_info = pending_tool_calls[
                                                                    resolved_pending_id
                                                                ]
                                                                pending_info[
                                                                    "result"
                                                                ] = tool_content
                                                                _tool_name = (
                                                                    pending_info.get(
                                                                        "tool_name",
                                                                        "unknown",
                                                                    )
                                                                )
                                                                _start_time = pending_info.get(
                                                                    "start_time",
                                                                    time_module.time(),
                                                                )
                                                                _duration_ms = (
                                                                    time_module.time()
                                                                    - _start_time
                                                                ) * 1000
                                                                _group_id = resolve_tool_group_id(
                                                                    tool_id=resolved_pending_id,
                                                                    pending_info=pending_info,
                                                                    fallback_group_id=current_tool_group_id,
                                                                    tool_name=_tool_name,
                                                                    source="tool_return_resolved",
                                                                )
                                                                logger.info(
                                                                    f"[WebSocket] ToolReturnPart: Sending result for {_tool_name} (id: {resolved_pending_id}, raw: {tool_call_id})"
                                                                )
                                                                # Send the REAL tool_result with actual content
                                                                await send_typed_tool_lifecycle(
                                                                    ServerToolResult(
                                                                        tool_id=resolved_pending_id,
                                                                        tool_name=_tool_name,
                                                                        result=tool_content,
                                                                        success=True,
                                                                        duration_ms=_duration_ms,
                                                                        timestamp=time_module.time(),
                                                                        session_id=session_id,
                                                                        agent_name=current_agent_name
                                                                        or "code-puppy",
                                                                        model_name=current_model_name
                                                                        or "unknown",
                                                                        tool_group_id=_group_id,
                                                                    )
                                                                )
                                                            else:
                                                                logger.warning(
                                                                    f"[WebSocket] ToolReturnPart: Could not resolve tool_call_id {tool_call_id}, pending keys: {list(pending_tool_calls.keys())}"
                                                                )

                                                        # Fallback: proximity-based matching if no tool_call_id or resolution failed
                                                        if not _result_sent:
                                                            for (
                                                                pending_id,
                                                                pending_info,
                                                            ) in sorted(
                                                                pending_tool_calls.items(),
                                                                key=lambda x: abs(
                                                                    x[1].get(
                                                                        "part_index",
                                                                        9999,
                                                                    )
                                                                    - part_index
                                                                ),
                                                            ):
                                                                if (
                                                                    abs(
                                                                        pending_info.get(
                                                                            "part_index",
                                                                            9999,
                                                                        )
                                                                        - part_index
                                                                    )
                                                                    <= 3
                                                                ):
                                                                    # Close enough - assume it's the result for this tool call
                                                                    pending_info[
                                                                        "result"
                                                                    ] = tool_content
                                                                    _tool_name = pending_info.get(
                                                                        "tool_name",
                                                                        "unknown",
                                                                    )
                                                                    _start_time = pending_info.get(
                                                                        "start_time",
                                                                        time_module.time(),
                                                                    )
                                                                    _duration_ms = (
                                                                        time_module.time()
                                                                        - _start_time
                                                                    ) * 1000
                                                                    _group_id = resolve_tool_group_id(
                                                                        tool_id=pending_id,
                                                                        pending_info=pending_info,
                                                                        fallback_group_id=current_tool_group_id,
                                                                        tool_name=_tool_name,
                                                                        source="tool_return_proximity",
                                                                    )
                                                                    logger.info(
                                                                        f"[WebSocket] ToolReturnPart: Sending result (by proximity) for {_tool_name} (id: {pending_id})"
                                                                    )
                                                                    # Send the REAL tool_result with actual content
                                                                    await send_typed_tool_lifecycle(
                                                                        ServerToolResult(
                                                                            tool_id=pending_id,
                                                                            tool_name=_tool_name,
                                                                            result=tool_content,
                                                                            success=True,
                                                                            duration_ms=_duration_ms,
                                                                            timestamp=time_module.time(),
                                                                            session_id=session_id,
                                                                            agent_name=current_agent_name
                                                                            or "code-puppy",
                                                                            model_name=current_model_name
                                                                            or "unknown",
                                                                            tool_group_id=_group_id,
                                                                        )
                                                                    )
                                                                    _result_sent = True
                                                                    break

                                                        # Warn if we couldn't send the result
                                                        if not _result_sent:
                                                            logger.warning(
                                                                f"[WebSocket] ToolReturnPart: Could NOT send result! tool_call_id={tool_call_id}, pending_tool_calls={list(pending_tool_calls.keys())}, part_index={part_index}"
                                                            )

                                                        # Track this part for cleanup
                                                        active_parts[part_index] = {
                                                            "id": f"tool-return-{part_index}",
                                                            "type": "tool_return",
                                                            "tool_call_id": tool_call_id,
                                                            "content": tool_content,
                                                        }

                                                elif inner_type == "part_delta":
                                                    part_index = inner_data.get(
                                                        "index", 0
                                                    )
                                                    delta_type = inner_data.get(
                                                        "delta_type", ""
                                                    )
                                                    delta_obj = inner_data.get(
                                                        "delta", {}
                                                    )

                                                    # Handle ToolCallPartDelta - accumulate args
                                                    if (
                                                        delta_type
                                                        == "ToolCallPartDelta"
                                                    ):
                                                        args_delta = ""
                                                        if hasattr(
                                                            delta_obj, "args_delta"
                                                        ):
                                                            args_delta = (
                                                                delta_obj.args_delta
                                                                or ""
                                                            )
                                                        elif isinstance(
                                                            delta_obj, dict
                                                        ):
                                                            args_delta = (
                                                                delta_obj.get(
                                                                    "args_delta", ""
                                                                )
                                                                or ""
                                                            )

                                                        if (
                                                            args_delta
                                                            and part_index
                                                            in active_parts
                                                        ):
                                                            part_info = active_parts[
                                                                part_index
                                                            ]
                                                            if (
                                                                part_info.get("type")
                                                                == "tool_call"
                                                            ):
                                                                part_info[
                                                                    "args_buffer"
                                                                ] = (
                                                                    part_info.get(
                                                                        "args_buffer",
                                                                        "",
                                                                    )
                                                                    + args_delta
                                                                )
                                                        continue  # Don't process as text delta

                                                    # Extract content_delta (supports both direct and nested formats)
                                                    content_delta = inner_data.get(
                                                        "content_delta", ""
                                                    )
                                                    if not content_delta:
                                                        if isinstance(delta_obj, dict):
                                                            content_delta = (
                                                                delta_obj.get(
                                                                    "content_delta", ""
                                                                )
                                                            )

                                                    if content_delta:
                                                        collected_text.append(
                                                            content_delta
                                                        )

                                                        # Ensure we have an entry for this part (handles delta before start)
                                                        if (
                                                            part_index
                                                            not in active_parts
                                                        ):
                                                            # Create entry with consistent message_id
                                                            message_id = f"msg-{int(time_module.time() * 1000)}-{part_index}"
                                                            active_parts[part_index] = {
                                                                "id": message_id,
                                                                "type": "text",  # Default, will be updated by part_start if it arrives
                                                                "content": "",
                                                            }
                                                            # Send a start event so client creates the message
                                                            logger.debug(
                                                                f"[Stream Debug] Creating part on first delta: message_id={message_id}"
                                                            )
                                                            if part_index == 0:
                                                                current_tool_group_id = None
                                                            await safe_send_json(
                                                                ServerAssistantMessageStart(
                                                                    message_id=message_id,
                                                                    part_type="text",
                                                                    part_index=part_index,
                                                                    timestamp=time_module.time(),
                                                                    session_id=session_id,
                                                                    agent_name=current_agent_name,
                                                                    model_name=current_model_name,
                                                                    tool_name=current_tool_name,
                                                                ).model_dump(
                                                                    exclude_none=True
                                                                )
                                                            )

                                                        part_info = active_parts[
                                                            part_index
                                                        ]
                                                        message_id = part_info["id"]

                                                        if part_index in active_parts:
                                                            active_parts[part_index][
                                                                "content"
                                                            ] += content_delta

                                                        _delta = ServerAssistantMessageDelta.model_construct(
                                                            type="assistant_message_delta",
                                                            message_id=message_id,
                                                            content=content_delta,
                                                            part_index=part_index,
                                                            session_id=session_id,
                                                            agent_name=current_agent_name,
                                                            model_name=current_model_name,
                                                            tool_name=current_tool_name,
                                                        )
                                                        await safe_send_json(
                                                            _delta.model_dump(
                                                                exclude_none=True
                                                            )
                                                        )
                                                        # Mark that B1 streaming was used
                                                        b1_streaming_used = True

                                                elif inner_type == "part_end":
                                                    part_index = inner_data.get(
                                                        "index", 0
                                                    )
                                                    part_info = active_parts.get(
                                                        part_index, {}
                                                    )
                                                    part_type_info = part_info.get(
                                                        "type", "text"
                                                    )
                                                    message_id = part_info.get(
                                                        "id", f"msg-{part_index}"
                                                    )
                                                    full_content = part_info.get(
                                                        "content", ""
                                                    )

                                                    # Handle tool_call parts - send tool_call event now that args are complete
                                                    if part_type_info == "tool_call":
                                                        tool_name = part_info.get(
                                                            "tool_name", "unknown"
                                                        )
                                                        tool_id = part_info.get(
                                                            "id", str(uuid.uuid4())[:8]
                                                        )
                                                        tool_args_str = part_info.get(
                                                            "args_buffer", ""
                                                        ) or part_info.get("args", "")
                                                        start_time = part_info.get(
                                                            "start_time",
                                                            time_module.time(),
                                                        )
                                                        raw_tool_call_id = (
                                                            part_info.get(
                                                                "raw_tool_call_id"
                                                            )
                                                        )

                                                        # Parse args if they're a JSON string
                                                        try:
                                                            import json

                                                            args_dict = (
                                                                json.loads(
                                                                    tool_args_str
                                                                )
                                                                if tool_args_str
                                                                else {}
                                                            )
                                                        except (
                                                            json.JSONDecodeError,
                                                            TypeError,
                                                        ):
                                                            args_dict = {}

                                                        logger.debug(
                                                            f"[WebSocket] Sending tool_call (args complete): {tool_name}"
                                                        )

                                                        # Generate tool group ID for this batch if not already set
                                                        if (
                                                            current_tool_group_id
                                                            is None
                                                        ):
                                                            current_tool_group_id = f"tg-{str(uuid.uuid4())[:8]}"

                                                        # Send tool_call now that we have complete args
                                                        await send_typed_tool_lifecycle(
                                                            ServerToolCall(
                                                                tool_id=tool_id,
                                                                tool_name=tool_name,
                                                                args=args_dict,
                                                                timestamp=time_module.time(),
                                                                session_id=session_id,
                                                                agent_name=current_agent_name,
                                                                model_name=current_model_name,
                                                                tool_group_id=current_tool_group_id,
                                                            )
                                                        )

                                                        # Track as pending tool call for later tool_result
                                                        pending_tool_calls[tool_id] = {
                                                            "tool_name": tool_name,
                                                            "start_time": start_time,
                                                            "part_index": part_index,
                                                            "raw_tool_call_id": raw_tool_call_id,
                                                            "status_only_sent": False,
                                                            "result": None,  # Will be populated by ToolReturnPart
                                                            "tool_group_id": current_tool_group_id,
                                                        }
                                                        if raw_tool_call_id:
                                                            tool_id_aliases[
                                                                raw_tool_call_id
                                                            ] = tool_id
                                                        # Also track tool_group_id for pre-stream_end extraction
                                                        if current_tool_group_id:
                                                            tool_group_ids[tool_id] = (
                                                                current_tool_group_id
                                                            )

                                                        # Clear current tool name tracking
                                                        current_tool_name = None
                                                    else:
                                                        await safe_send_json(
                                                            ServerAssistantMessageEnd(
                                                                message_id=message_id,
                                                                part_index=part_index,
                                                                full_content=full_content,
                                                                timestamp=time_module.time(),
                                                                session_id=session_id,
                                                                agent_name=current_agent_name,
                                                                model_name=current_model_name,
                                                                tool_name=current_tool_name,
                                                            ).model_dump(
                                                                exclude_none=True
                                                            )
                                                        )

                                                    if part_index in active_parts:
                                                        del active_parts[part_index]

                                        except Exception as send_err:
                                            error_msg = str(send_err).lower()
                                            if (
                                                "close message" in error_msg
                                                or "closed" in error_msg
                                            ):
                                                ws_closed = True
                                                logger.debug(
                                                    "WebSocket closed during streaming, stopping drain"
                                                )
                                                break
                                            logger.warning(
                                                f"Error sending event to WebSocket: {type(send_err).__name__}: {send_err}"
                                            )
                                            import traceback

                                            logger.warning(
                                                f"Traceback: {traceback.format_exc()}"
                                            )

                                    # No idle polling - event-driven approach handles empty event sets gracefully

                                # Final drain after stop signal
                                final_count = 0
                                while True:
                                    try:
                                        event = event_queue.get_nowait()
                                        event_type = event.get("type", "")
                                        event_data = event.get("data", {})
                                        final_count += 1

                                        if event_type == "stream_event":
                                            inner_type = event_data.get(
                                                "event_type", ""
                                            )
                                            inner_data = event_data.get(
                                                "event_data", {}
                                            )
                                            if inner_type == "part_delta":
                                                content_delta = inner_data.get(
                                                    "content_delta", ""
                                                )
                                                if not content_delta:
                                                    delta_obj = inner_data.get(
                                                        "delta", {}
                                                    )
                                                    if isinstance(delta_obj, dict):
                                                        content_delta = delta_obj.get(
                                                            "content_delta", ""
                                                        )
                                                if content_delta:
                                                    collected_text.append(content_delta)
                                    except Exception:
                                        break

                                # Calculate batching efficiency
                                avg_batch_size = (
                                    event_count / max(1, event_count)
                                    if event_count > 0
                                    else 0
                                )
                                logger.debug(
                                    f"[{session_id}] Drain complete: "
                                    f"{event_count} events during run, {final_count} final, "
                                    f"batching efficiency: {avg_batch_size:.2f}"
                                )

                            # Event to signal drain task is ready
                            drain_ready = asyncio.Event()

                            try:
                                from code_puppy.plugins.frontend_emitter.emitter import (
                                    subscribe,
                                    unsubscribe,
                                )

                                event_queue = subscribe(session_id=session_id)
                                logger.debug(
                                    "Subscribed to frontend emitter for streaming"
                                )

                                # Modify drain function to signal when ready
                                async def drain_events_with_signal():
                                    """Wrapper that signals readiness before starting drain loop."""
                                    await drain_events_concurrent(drain_ready)

                                # Start concurrent drain task
                                drain_task = asyncio.create_task(
                                    drain_events_with_signal()
                                )
                                active_drain_task = (
                                    drain_task  # Track for potential cancellation
                                )

                                # Wait for drain task to be ready before proceeding
                                await drain_ready.wait()

                            except ImportError:
                                logger.warning("Frontend emitter not available")

                            try:
                                # Send status: thinking
                                await send_typed(
                                    ServerStatus(
                                        status="thinking",
                                        session_id=session_id,
                                        agent_name=agent.name
                                        if agent
                                        else "code-puppy",
                                        model_name=agent.get_model_name()
                                        if agent
                                        else "unknown",
                                    )
                                )

                                # Change to session working directory if set
                                # Set session context for prompt generation (desk-puppy)
                                set_session_working_directory(session_working_directory)

                                try:
                                    # Call run_with_mcp (drain task runs concurrently!)
                                    logger.debug(
                                        "About to run agent, working_directory=%s",
                                        session_working_directory,
                                    )

                                    # Inject working directory as a system message in the
                                    # agent's conversation history (once per directory change)
                                    # so the LLM knows the CWD without polluting user messages.
                                    message_to_send = user_message
                                    if (
                                        session_working_directory
                                        and session_working_directory
                                        != last_context_sent_directory
                                    ):
                                        from pydantic_ai.messages import (
                                            ModelRequest,
                                            SystemPromptPart,
                                        )

                                        wd_system_msg = ModelRequest(
                                            parts=[
                                                SystemPromptPart(
                                                    content=(
                                                        f"The user's current working directory is updated to"
                                                        f" {session_working_directory}"
                                                    )
                                                )
                                            ]
                                        )
                                        agent.append_to_message_history(wd_system_msg)
                                        last_context_sent_directory = (
                                            session_working_directory
                                        )
                                        logger.debug(
                                            "Injected working directory system message: %s",
                                            session_working_directory,
                                        )

                                    logger.debug(
                                        f"Calling run_with_mcp with message: {message_to_send[:100]}..."
                                    )

                                    # Build file context and binary attachments
                                    file_context, binary_attachments = (
                                        build_file_context_and_attachments(msg)
                                    )

                                    # CHANGE 1: Update attachment metadata for UI (variables already initialized)
                                    if msg.get("attachments"):
                                        from pathlib import Path as _AttachmentPath

                                        for raw_path in msg.get("attachments", []):
                                            if (
                                                isinstance(raw_path, str)
                                                and raw_path.strip()
                                            ):
                                                try:
                                                    file_path = _AttachmentPath(
                                                        raw_path
                                                    )
                                                    if file_path.exists():
                                                        attachment_metadata.append(
                                                            {
                                                                "name": file_path.name,
                                                                "path": str(
                                                                    file_path.absolute()
                                                                ),
                                                                "sizeBytes": file_path.stat().st_size,
                                                            }
                                                        )
                                                except Exception as e:
                                                    logger.warning(
                                                        f"Error building attachment metadata for '{raw_path}': {e}"
                                                    )

                                    # Prepend file context to the message
                                    if file_context:
                                        message_to_send = (
                                            file_context + "\n\n" + message_to_send
                                        )
                                        logger.debug(
                                            f"Added file context ({len(file_context)} chars)"
                                        )

                                    run_kwargs = {}
                                    if binary_attachments:
                                        run_kwargs["attachments"] = binary_attachments
                                        logger.debug(
                                            f"Including {len(binary_attachments)} binary attachment(s)"
                                        )

                                    # ──────────────────────────────────────────────────────────────────
                                    # Phase 7: Create session + user message in SQLite BEFORE streaming
                                    # This prevents "Session not found" errors when FE queries mid-stream
                                    # ──────────────────────────────────────────────────────────────────
                                    try:
                                        import os
                                        from datetime import timezone as tz

                                        from code_puppy.api.db.queries import (
                                            upsert_session,
                                        )

                                        now_iso = datetime.datetime.now(
                                            tz.utc
                                        ).isoformat()

                                        # Ensure session row exists
                                        await upsert_session(
                                            session_id=session_id,
                                            title="",  # Will be updated later with actual title
                                            agent_name=ctx.agent_name,
                                            model_name=ctx.model_name,
                                            working_directory=os.getcwd(),
                                            pinned=False,
                                            created_at=now_iso,
                                            updated_at=now_iso,
                                            message_count=0,  # Will be updated after streaming
                                            total_tokens=0,
                                        )

                                        # Write user message immediately (before agent processes it)
                                        # Use get_next_seq() + insert_message() so the user message
                                        # lands at MAX(seq)+1, AFTER any system messages (config,
                                        # directory banners) that were already written at seq=1, 2, …
                                        # The old write_turn_to_sqlite([single_item]) always assigned
                                        # seq=1, silently colliding with those rows via INSERT OR IGNORE.
                                        from pydantic_ai.messages import (
                                            ModelRequest,
                                            UserPromptPart,
                                        )

                                        from code_puppy.api.db.message_utils import (
                                            pydantic_json_for_message,
                                        )
                                        from code_puppy.api.db.queries import (
                                            get_next_seq,
                                            insert_message,
                                        )

                                        user_msg_obj = ModelRequest(
                                            parts=[
                                                UserPromptPart(
                                                    content=original_user_message
                                                )
                                            ]
                                        )

                                        user_seq = await get_next_seq(session_id)
                                        await insert_message(
                                            session_id=session_id,
                                            seq=user_seq,
                                            role="user",
                                            content=original_user_message,
                                            type="ModelRequest",
                                            agent_name=ctx.agent_name,
                                            model_name=ctx.model_name,
                                            timestamp=now_iso,
                                            clean_content=original_user_message,
                                            attachments_json=(
                                                json.dumps(attachment_metadata)
                                                if attachment_metadata
                                                else None
                                            ),
                                            pydantic_json=pydantic_json_for_message(
                                                user_msg_obj
                                            ),
                                        )

                                        logger.debug(
                                            "Pre-stream write: session %s created with user message in SQLite",
                                            session_id,
                                        )
                                    except Exception as pre_write_exc:
                                        # Non-fatal: WS streaming will still work, SQLite just won't have the
                                        # session yet. The post-stream write will create it.
                                        logger.warning(
                                            "Pre-stream SQLite write failed for %s: %s",
                                            session_id,
                                            pre_write_exc,
                                            exc_info=True,
                                        )

                                    # Run the agent in its own task so it can be cancelled independently.
                                    # Suppress duplicate emitter lifecycle callbacks only during the
                                    # run_with_mcp execution window (pre/post_tool_call hooks fire there).
                                    set_suppress_emitter_tool_events(True)
                                    active_agent_task = asyncio.create_task(
                                        agent.run_with_mcp(
                                            message_to_send, **run_kwargs
                                        )
                                    )

                                    # ===== CONCURRENT MESSAGE PROCESSING FIX =====
                                    # Instead of awaiting the agent task here (which blocks the receive loop),
                                    # we use asyncio.wait() to handle BOTH the agent task AND incoming messages.
                                    # This allows permission_response messages to be processed while the agent runs.

                                    result = None
                                    agent_completed = False
                                    # Deferred message for switch_session/create_session during streaming
                                    _deferred_msg: dict | None = None

                                    while not agent_completed:
                                        # Create a task for the next message (or wait for agent)
                                        receive_task = asyncio.create_task(
                                            websocket.receive_json()
                                        )

                                        # Wait for either the agent to complete OR a new message to arrive
                                        done, pending = await asyncio.wait(
                                            {active_agent_task, receive_task},
                                            return_when=asyncio.FIRST_COMPLETED,
                                        )

                                        # Check if agent completed
                                        if active_agent_task in done:
                                            try:
                                                result = await active_agent_task
                                                logger.debug(
                                                    f"run_with_mcp completed, result type: {type(result)}"
                                                )
                                                agent_completed = True
                                                active_agent_task = None
                                            except asyncio.CancelledError:
                                                logger.debug(
                                                    "run_with_mcp task was cancelled by user"
                                                )
                                                agent_error = "cancelled"
                                                result = None
                                                agent_completed = True
                                                active_agent_task = None
                                            except Exception as e:
                                                logger.error(
                                                    "Agent task error: %s",
                                                    e,
                                                    exc_info=True,
                                                )
                                                logger.debug(
                                                    "[WS:%s] agent task exception captured: type=%s repr=%r",
                                                    session_id,
                                                    type(e).__name__,
                                                    e,
                                                )
                                                agent_error = e
                                                result = None
                                                agent_completed = True
                                                active_agent_task = None

                                            # Cancel the receive task if it's still pending
                                            if receive_task in pending:
                                                receive_task.cancel()
                                                try:
                                                    await receive_task
                                                except asyncio.CancelledError:
                                                    pass

                                        # Check if a new message arrived
                                        elif receive_task in done:
                                            try:
                                                new_msg = await receive_task

                                                # Advisory validation — log but never reject
                                                try:
                                                    _parsed_inner = _ClientMessageAdapter.validate_python(
                                                        new_msg
                                                    )
                                                except ValidationError as _val_err:
                                                    logger.warning(
                                                        "Client message failed validation: %s",
                                                        str(_val_err),
                                                        extra={
                                                            "type": new_msg.get("type")
                                                            if isinstance(new_msg, dict)
                                                            else "unknown"
                                                        },
                                                    )

                                                # Handle permission_response immediately
                                                if (
                                                    new_msg.get("type")
                                                    == "permission_response"
                                                ):
                                                    from code_puppy.api.permissions import (
                                                        handle_permission_response,
                                                    )

                                                    request_id = new_msg.get(
                                                        "request_id"
                                                    )
                                                    approved = new_msg.get(
                                                        "approved", False
                                                    )

                                                    if request_id:
                                                        handled = (
                                                            handle_permission_response(
                                                                request_id, approved
                                                            )
                                                        )
                                                        if handled:
                                                            logger.debug(
                                                                f"[Permission] ✅ Handled response: {request_id} = {approved}"
                                                            )
                                                        else:
                                                            logger.warning(
                                                                f"[Permission] ❌ Unknown request: {request_id}"
                                                            )
                                                    else:
                                                        logger.error(
                                                            "[WebSocket] ❌ No request_id in permission_response!"
                                                        )

                                                # Handle cancel request
                                                elif new_msg.get("type") == "cancel":
                                                    logger.debug(
                                                        "Cancel request received during agent execution"
                                                    )
                                                    if (
                                                        active_agent_task
                                                        and not active_agent_task.done()
                                                    ):
                                                        active_agent_task.cancel()
                                                        agent_completed = (
                                                            True  # Exit the loop
                                                        )

                                                # Handle session switch during streaming
                                                elif new_msg.get("type") in (
                                                    "switch_session",
                                                    "create_session",
                                                ):
                                                    # User switched to a new chat while agent was running.
                                                    # The agent will finish in background and save to SQLite.
                                                    logger.debug(
                                                        "[WS:%s] Session switch during streaming — "
                                                        "agent continues in background, switching to: %s",
                                                        session_id,
                                                        new_msg.get("session_id"),
                                                    )

                                                    # Fire and forget — background task owns the agent result.
                                                    fire_and_track(
                                                        save_agent_result_in_background(
                                                            agent_task=active_agent_task,
                                                            session_id=session_id,
                                                            ctx=ctx,
                                                            agent=agent,
                                                            agent_name=agent_name,
                                                            model_name=model_name,
                                                            title=session_title,
                                                            working_directory=session_working_directory,
                                                            pinned=session_pinned,
                                                            label="switch",
                                                        )
                                                    )

                                                    _deferred_msg = new_msg
                                                    active_agent_task = None  # disown — background task now owns it
                                                    agent_completed = (
                                                        True  # exit inner loop
                                                    )

                                                # For other message types, log and ignore (or queue for later)
                                                else:
                                                    logger.warning(
                                                        f"[WebSocket] Received {new_msg.get('type')} message while agent running - ignoring"
                                                    )

                                            except asyncio.CancelledError:
                                                # Receive was cancelled, continue
                                                pass
                                            except WebSocketDisconnect:
                                                # WebSocket gone — let agent finish and save to SQLite
                                                logger.debug(
                                                    "[WS:%s] Disconnect during streaming — agent continues in background",
                                                    session_id,
                                                )

                                                # Fire and forget — background task owns the agent result.
                                                fire_and_track(
                                                    save_agent_result_in_background(
                                                        agent_task=active_agent_task,
                                                        session_id=session_id,
                                                        ctx=ctx,
                                                        agent=agent,
                                                        agent_name=agent_name,
                                                        model_name=model_name,
                                                        title=session_title,
                                                        working_directory=session_working_directory,
                                                        pinned=session_pinned,
                                                        label="disconnect",
                                                    )
                                                )
                                                active_agent_task = None
                                                agent_completed = True
                                            except RuntimeError as e:
                                                if "disconnect" in str(e).lower():
                                                    # Starlette raises RuntimeError when calling receive after disconnect
                                                    logger.debug(
                                                        "[WS:%s] WebSocket already disconnected: %s — agent continues in background",
                                                        session_id,
                                                        e,
                                                    )

                                                    # Fire and forget — background task owns the agent result.
                                                    fire_and_track(
                                                        save_agent_result_in_background(
                                                            agent_task=active_agent_task,
                                                            session_id=session_id,
                                                            ctx=ctx,
                                                            agent=agent,
                                                            agent_name=agent_name,
                                                            model_name=model_name,
                                                            title=session_title,
                                                            working_directory=session_working_directory,
                                                            pinned=session_pinned,
                                                            label="runtime",
                                                        )
                                                    )
                                                    active_agent_task = None
                                                    agent_completed = True
                                                else:
                                                    logger.error(
                                                        f"RuntimeError processing message during agent execution: {e}"
                                                    )
                                            except Exception as e:
                                                logger.error(
                                                    f"Error processing message during agent execution: {e}"
                                                )

                                    # ===== END CONCURRENT MESSAGE PROCESSING FIX =====

                                finally:
                                    # End suppression scope once run_with_mcp window ends,
                                    # including completion/cancel/background handoff paths.
                                    set_suppress_emitter_tool_events(False)
                                    # Clear session context for prompt generation
                                    clear_session_working_directory()

                            finally:
                                # Stop the drain task
                                if drain_task:
                                    stop_draining.set()
                                    try:
                                        await asyncio.wait_for(drain_task, timeout=2.0)
                                    except asyncio.TimeoutError:
                                        drain_task.cancel()
                                        try:
                                            await drain_task
                                        except asyncio.CancelledError:
                                            pass

                                # Unsubscribe from emitter
                                if event_queue:
                                    unsubscribe(event_queue)
                                    logger.debug("Unsubscribed from frontend emitter")

                            # Process any deferred switch_session that arrived during streaming
                            if _deferred_msg is not None:
                                msg = _deferred_msg
                                _deferred_msg = None
                                # Re-dispatch to outer loop by continuing with msg set
                                # The outer while True loop will handle switch_session/create_session
                                continue

                            # If agent errored, send error to GUI and skip success path
                            if agent_error == "cancelled":
                                await send_typed(
                                    ServerCancelled(
                                        session_id=session_id,
                                    )
                                )
                                continue
                            elif agent_error is not None:
                                logger.debug(
                                    "[WS:%s] agent_error -> sending frame(s) to client. type=%s",
                                    session_id,
                                    type(agent_error).__name__,
                                )
                                # If streaming was already in progress, send stream_end first so
                                # the frontend exits its streaming state before the error frame.
                                # Without this handshake the UI hangs indefinitely.
                                for frame in build_error_response_frames(
                                    agent_error, collected_text, session_id
                                ):
                                    await safe_send_json(frame)
                                continue

                            # Safety net: if the agent task completed without raising but returned
                            # no result and produced no streamed text, treat it as an error.
                            has_nonempty_stream = any(
                                (chunk or "").strip() for chunk in collected_text
                            )
                            logger.debug(
                                "[WS:%s] post-run: result_is_none=%s collected_chunks=%d has_nonempty_stream=%s",
                                session_id,
                                result is None,
                                len(collected_text),
                                has_nonempty_stream,
                            )

                            if result is None and not has_nonempty_stream:
                                logger.warning(
                                    "[WS:%s] Agent task completed with result=None and no streamed text; treating as error.",
                                    session_id,
                                )
                                parsed_error = parse_api_error(
                                    RuntimeError(
                                        "Agent run failed (no result returned). Check server logs for the underlying exception."
                                    )
                                )
                                await send_typed(
                                    ServerError(
                                        error=parsed_error["user_message"],
                                        error_type=parsed_error["error_type"],
                                        technical_details=parsed_error[
                                            "technical_details"
                                        ],
                                        action_required=parsed_error.get(
                                            "action_required"
                                        ),
                                        session_id=session_id,
                                    )
                                )
                                continue

                            # Extract final response text
                            response_text = ""

                            # Priority 1: Use collected text from streaming events
                            if has_nonempty_stream:
                                response_text = "".join(collected_text)
                                logger.debug(
                                    f"Using collected streaming text ({len(response_text)} chars)"
                                )
                            # Priority 2: Extract from result.output (AgentRunResult) or result.data (legacy)
                            elif result:
                                if hasattr(result, "output"):
                                    response_text = (
                                        str(result.output)
                                        if result.output
                                        else "(Empty response)"
                                    )
                                    logger.debug(
                                        f"Using result.output ({len(response_text)} chars)"
                                    )
                                elif hasattr(result, "data"):
                                    response_text = (
                                        str(result.data)
                                        if result.data
                                        else "(Empty response)"
                                    )
                                    logger.debug(
                                        f"Using result.data ({len(response_text)} chars)"
                                    )
                            # Priority 3: Get last assistant message from history
                            elif agent:
                                messages = agent.get_message_history()

                                for msg in reversed(messages):
                                    if hasattr(msg, "role") and msg.role == "assistant":
                                        if hasattr(msg, "content"):
                                            response_text = str(msg.content)
                                            logger.debug(
                                                f"Using message history ({len(response_text)} chars)"
                                            )

                                            break

                            if not response_text:
                                response_text = "Agent returned no response"

                            # Extract token usage from result if available
                            tokens_used = None
                            if result:
                                # Try to get usage from result
                                if hasattr(result, "usage"):
                                    usage = result.usage
                                    if usage:
                                        tokens_used = {
                                            "input_tokens": getattr(
                                                usage, "input_tokens", None
                                            )
                                            or getattr(usage, "prompt_tokens", None),
                                            "output_tokens": getattr(
                                                usage, "output_tokens", None
                                            )
                                            or getattr(
                                                usage, "completion_tokens", None
                                            ),
                                            "total_tokens": getattr(
                                                usage, "total_tokens", None
                                            ),
                                        }
                                # Also try _usage or other common patterns
                                elif hasattr(result, "_usage"):
                                    usage = result._usage
                                    if usage:
                                        tokens_used = {
                                            "input_tokens": getattr(
                                                usage, "input_tokens", None
                                            )
                                            or getattr(usage, "prompt_tokens", None),
                                            "output_tokens": getattr(
                                                usage, "output_tokens", None
                                            )
                                            or getattr(
                                                usage, "completion_tokens", None
                                            ),
                                            "total_tokens": getattr(
                                                usage, "total_tokens", None
                                            ),
                                        }

                            # If we couldn't get usage from result, estimate from message history
                            if not tokens_used and agent:
                                try:
                                    history = agent.get_message_history()
                                    total_estimated = sum(
                                        agent.estimate_tokens_for_message(msg)
                                        for msg in history
                                    )
                                    tokens_used = {
                                        "total_tokens": total_estimated,
                                        "estimated": True,
                                    }
                                except Exception:
                                    pass

                            # Only send legacy 'response' if B1 streaming wasn't used
                            # B1 streaming already sent the content via assistant_message_end
                            logger.warning(
                                "[WebSocket] b1_streaming_used=%s before response/extraction",
                                b1_streaming_used,
                            )
                            if not b1_streaming_used:
                                # For non-streaming models (like Gemini), extract and send thinking content first
                                thinking_text = ""
                                if agent:
                                    try:
                                        history = agent.get_message_history()
                                        logger.debug(
                                            f"[Thinking Debug] Checking history for thinking parts, {len(history) if history else 0} messages"
                                        )
                                        if history:
                                            # Look for ThinkingPart in the last ModelResponse
                                            for i, msg in enumerate(reversed(history)):
                                                msg_type = type(msg).__name__
                                                logger.debug(
                                                    f"[Thinking Debug] Message {i}: type={msg_type}, has_parts={hasattr(msg, 'parts')}"
                                                )
                                                if "Response" in msg_type and hasattr(
                                                    msg, "parts"
                                                ):
                                                    logger.debug(
                                                        f"[Thinking Debug] Found Response with {len(msg.parts)} parts"
                                                    )
                                                    for j, part in enumerate(msg.parts):
                                                        part_type = type(part).__name__
                                                        part_content_preview = (
                                                            str(
                                                                getattr(
                                                                    part, "content", ""
                                                                )
                                                            )[:100]
                                                            if hasattr(part, "content")
                                                            else "N/A"
                                                        )
                                                        logger.debug(
                                                            f"[Thinking Debug] Part {j}: type={part_type}, content_preview={part_content_preview}"
                                                        )
                                                        if (
                                                            "Thinking" in part_type
                                                            and hasattr(part, "content")
                                                        ):
                                                            thinking_text = part.content
                                                            logger.debug(
                                                                f"[Thinking Debug] Found thinking content: {len(thinking_text)} chars"
                                                            )
                                                            break
                                                    if thinking_text:
                                                        break
                                    except Exception as e:
                                        logger.warning(
                                            f"Could not extract thinking content: {e}"
                                        )
                                        import traceback

                                        logger.warning(traceback.format_exc())

                                if not thinking_text:
                                    logger.debug(
                                        "[Thinking Debug] No thinking content found in message history"
                                    )

                                # Send thinking content as B1 message if available
                                if thinking_text:
                                    import time as time_module

                                    thinking_message_id = f"thinking-{session_id}-{int(time_module.time() * 1000)}"
                                    await send_typed(
                                        ServerAssistantMessageStart(
                                            message_id=thinking_message_id,
                                            part_type="thinking",
                                            part_index=0,
                                            timestamp=time_module.time(),
                                            session_id=session_id,
                                            agent_name=agent.name
                                            if agent
                                            else "code-puppy",
                                            model_name=agent.get_model_name()
                                            if agent
                                            else "unknown",
                                        )
                                    )
                                    _delta = (
                                        ServerAssistantMessageDelta.model_construct(
                                            type="assistant_message_delta",
                                            message_id=thinking_message_id,
                                            content=thinking_text,
                                            part_index=0,
                                            session_id=session_id,
                                            agent_name=agent.name
                                            if agent
                                            else "code-puppy",
                                            model_name=agent.get_model_name()
                                            if agent
                                            else "unknown",
                                        )
                                    )
                                    await safe_send_json(
                                        _delta.model_dump(exclude_none=True)
                                    )
                                    await send_typed(
                                        ServerAssistantMessageEnd(
                                            message_id=thinking_message_id,
                                            part_index=0,
                                            full_content=thinking_text,
                                            timestamp=time_module.time(),
                                            session_id=session_id,
                                            agent_name=agent.name
                                            if agent
                                            else "code-puppy",
                                            model_name=agent.get_model_name()
                                            if agent
                                            else "unknown",
                                        )
                                    )
                                    logger.debug(
                                        f"Sent thinking content ({len(thinking_text)} chars) for non-streaming model"
                                    )

                                # Send the main response
                                await send_typed(
                                    ServerResponse(
                                        content=response_text,
                                        done=True,
                                        session_id=session_id,
                                        agent_name=agent.name
                                        if agent
                                        else "code-puppy",
                                        model_name=agent.get_model_name()
                                        if agent
                                        else "unknown",
                                        tokens=tokens_used,
                                    )
                                )
                            else:
                                # B1 streaming: extract real tool results BEFORE stream_end
                                # so the frontend session store is still alive when they arrive.
                                _pre_sent_tool_ids: set = set()
                                logger.warning(
                                    "[WebSocket] B1 Pre-stream_end extraction: result=%s, has_all_messages=%s",
                                    type(result).__name__ if result else None,
                                    hasattr(result, "all_messages")
                                    if result
                                    else False,
                                )
                                if result and hasattr(result, "all_messages"):
                                    try:
                                        import time as _time_pre

                                        from pydantic_ai.messages import (
                                            ToolReturn,
                                            ToolReturnPart,
                                        )

                                        _pre_msgs = list(result.all_messages())
                                        for _pre_msg in _pre_msgs:
                                            if not hasattr(_pre_msg, "parts"):
                                                continue
                                            for _pre_part in _pre_msg.parts:
                                                if not isinstance(
                                                    _pre_part,
                                                    (ToolReturnPart, ToolReturn),
                                                ):
                                                    continue
                                                _pre_tool_name = getattr(
                                                    _pre_part, "tool_name", "unknown"
                                                )
                                                _pre_raw_tool_id = getattr(
                                                    _pre_part, "tool_call_id", None
                                                )
                                                _pre_tool_id = (
                                                    tool_id_aliases.get(
                                                        _pre_raw_tool_id,
                                                        _pre_raw_tool_id,
                                                    )
                                                    if _pre_raw_tool_id
                                                    else "unknown"
                                                )
                                                _pre_result = getattr(
                                                    _pre_part, "content", None
                                                )
                                                # Serialize complex objects
                                                if _pre_result and not isinstance(
                                                    _pre_result,
                                                    (
                                                        str,
                                                        dict,
                                                        list,
                                                        int,
                                                        float,
                                                        bool,
                                                        type(None),
                                                    ),
                                                ):
                                                    try:
                                                        if hasattr(
                                                            _pre_result, "model_dump"
                                                        ):
                                                            _pre_result = (
                                                                _pre_result.model_dump()
                                                            )
                                                        elif hasattr(
                                                            _pre_result, "dict"
                                                        ):
                                                            _pre_result = (
                                                                _pre_result.dict()
                                                            )
                                                        elif hasattr(
                                                            _pre_result, "__dict__"
                                                        ):
                                                            _pre_result = (
                                                                _pre_result.__dict__
                                                            )
                                                        else:
                                                            _pre_result = str(
                                                                _pre_result
                                                            )
                                                    except Exception:
                                                        _pre_result = str(_pre_result)
                                                logger.warning(
                                                    "[WebSocket] Pre-stream_end tool result: %s (id: %s), content_preview=%s",
                                                    _pre_tool_name,
                                                    _pre_tool_id,
                                                    str(_pre_result)[:100]
                                                    if _pre_result
                                                    else None,
                                                )
                                                _pre_group_id = tool_group_ids.get(
                                                    _pre_tool_id
                                                )

                                                await send_typed_tool_lifecycle(
                                                    ServerToolResult(
                                                        tool_id=_pre_tool_id,
                                                        tool_name=_pre_tool_name,
                                                        result=_pre_result,
                                                        success=True,
                                                        duration_ms=0,
                                                        timestamp=_time_pre.time(),
                                                        session_id=session_id,
                                                        agent_name=agent.name
                                                        if agent
                                                        else "code-puppy",
                                                        model_name=agent.get_model_name()
                                                        if agent
                                                        else "unknown",
                                                        tool_group_id=_pre_group_id,
                                                    )
                                                )
                                                _pre_sent_tool_ids.add(_pre_tool_id)
                                    except Exception as _pre_e:
                                        logger.warning(
                                            "Pre-stream_end tool result extraction failed: %s",
                                            _pre_e,
                                        )

                                # Send stream_end AFTER real tool results are delivered
                                await send_typed(
                                    ServerStreamEnd(
                                        success=True,
                                        total_length=len(response_text),
                                        agent_name=agent.name
                                        if agent
                                        else "code-puppy",
                                        model_name=agent.get_model_name()
                                        if agent
                                        else "unknown",
                                        tokens=tokens_used,
                                        session_id=session_id,
                                    )
                                )

                            # Save session after each response
                            # Track tool IDs already sent before stream_end to skip duplicates later
                            if "_pre_sent_tool_ids" not in dir():
                                _pre_sent_tool_ids: set = set()
                            _save_history_snapshot = []  # Snapshot of history before await points
                            try:
                                # CRITICAL: Update message history from result to include final response
                                # The pydantic-ai result.all_messages() contains the complete conversation
                                # including the final assistant response that may not be in agent's history yet
                                if result and hasattr(result, "all_messages"):
                                    try:
                                        all_msgs = list(result.all_messages())
                                        if all_msgs:
                                            agent.set_message_history(all_msgs)
                                            _save_history_snapshot = list(
                                                agent.get_message_history()
                                            )  # Snapshot before any awaits can corrupt shared global state
                                            logger.debug(
                                                f"Updated message history from result.all_messages(): {len(all_msgs)} messages"
                                            )

                                        # Extract and send tool results from message history
                                        try:
                                            import time as _time

                                            from pydantic_ai.messages import (
                                                ToolReturn,
                                                ToolReturnPart,
                                            )

                                            for msg in all_msgs:
                                                if hasattr(msg, "parts"):
                                                    for part in msg.parts:
                                                        if isinstance(
                                                            part,
                                                            (
                                                                ToolReturnPart,
                                                                ToolReturn,
                                                            ),
                                                        ):
                                                            tool_name = getattr(
                                                                part,
                                                                "tool_name",
                                                                "unknown",
                                                            )
                                                            tool_call_id = getattr(
                                                                part,
                                                                "tool_call_id",
                                                                "unknown",
                                                            )
                                                            # Serialize the result
                                                            result_data = getattr(
                                                                part, "content", None
                                                            )
                                                            if (
                                                                result_data
                                                                and not isinstance(
                                                                    result_data,
                                                                    (
                                                                        str,
                                                                        dict,
                                                                        list,
                                                                        int,
                                                                        float,
                                                                        bool,
                                                                        type(None),
                                                                    ),
                                                                )
                                                            ):
                                                                try:
                                                                    if hasattr(
                                                                        result_data,
                                                                        "model_dump",
                                                                    ):
                                                                        result_data = result_data.model_dump()
                                                                    elif hasattr(
                                                                        result_data,
                                                                        "dict",
                                                                    ):
                                                                        result_data = result_data.dict()
                                                                    elif hasattr(
                                                                        result_data,
                                                                        "__dict__",
                                                                    ):
                                                                        result_data = result_data.__dict__
                                                                    else:
                                                                        result_data = str(
                                                                            result_data
                                                                        )
                                                                except Exception:
                                                                    result_data = str(
                                                                        result_data
                                                                    )

                                                            # Log for shell commands
                                                            if (
                                                                tool_name
                                                                == "agent_run_shell_command"
                                                            ):
                                                                stdout_val = (
                                                                    result_data.get(
                                                                        "stdout", "N/A"
                                                                    )
                                                                    if isinstance(
                                                                        result_data,
                                                                        dict,
                                                                    )
                                                                    else "not dict"
                                                                )
                                                                logger.debug(
                                                                    "Extracted shell result: id=%s, stdout=%s",
                                                                    tool_call_id,
                                                                    stdout_val,
                                                                )

                                                            # Skip tool IDs already sent before stream_end
                                                            if (
                                                                tool_call_id
                                                                in _pre_sent_tool_ids
                                                            ):
                                                                logger.debug(
                                                                    "[WebSocket] Skipping duplicate tool result (pre-sent): %s",
                                                                    tool_call_id,
                                                                )
                                                                continue
                                                            logger.info(
                                                                f"[WebSocket] Sending extracted tool result for {tool_name} (id: {tool_call_id})"
                                                            )
                                                            _post_group_id = (
                                                                tool_group_ids.get(
                                                                    tool_call_id
                                                                )
                                                            )

                                                            await send_typed(
                                                                ServerToolResult(
                                                                    tool_id=tool_call_id,
                                                                    tool_name=tool_name,
                                                                    result=result_data,
                                                                    success=True,
                                                                    duration_ms=0,
                                                                    timestamp=_time.time(),
                                                                    session_id=session_id,
                                                                    agent_name=agent.name
                                                                    if agent
                                                                    else "code-puppy",
                                                                    model_name=agent.get_model_name()
                                                                    if agent
                                                                    else "unknown",
                                                                    tool_group_id=_post_group_id,
                                                                )
                                                            )
                                        except Exception as e:
                                            logger.warning(
                                                f"Could not extract tool results from messages: {e}"
                                            )

                                    except Exception as e:
                                        logger.warning(
                                            f"Could not update history from result.all_messages(): {e}"
                                        )

                                history = (
                                    _save_history_snapshot
                                    if _save_history_snapshot
                                    else agent.get_message_history()
                                )  # Use pre-await snapshot to avoid race condition
                                if history:
                                    # Regenerate title if it's empty or still the default "untitled-session"
                                    if (
                                        not session_title
                                        or session_title == "untitled-session"
                                    ):
                                        session_title = generate_heuristic_title(
                                            history
                                        )

                                    # Session name is just the ID (WS_session_timestamp format)
                                    # Title is stored only in the meta file, not in the filename
                                    session_name = session_id

                                    # Wrap each message with metadata for complete session information.
                                    # Chain `or` fallbacks: agent.name can be "" before the agent
                                    # object is fully configured, so we cascade to context defaults.
                                    agent_name_meta = (
                                        (agent.name if agent else "")
                                        or ctx.agent_name
                                        or "code-puppy"
                                    )
                                    model_name_meta = (
                                        (agent.get_model_name() if agent else "")
                                        or ctx.model_name
                                        or "unknown"
                                    )

                                    def _extract_message_timestamp(
                                        raw_msg: Any, default_ts: str
                                    ) -> str:
                                        """Best-effort extraction of an existing timestamp for a message.

                                        This is important for WebSocket sessions where history may
                                        already contain older messages. We don't want to overwrite
                                        their original timestamps every time we auto-save.

                                        Precedence:
                                        1. If the message is a dict with a numeric epoch 'timestamp',
                                           convert to ISO.
                                        2. If the message is a dict with an ISO-ish 'timestamp' str,
                                           reuse it as-is.
                                        3. If the message is a dict with 'ts', reuse it.
                                        4. If the message object has a 'timestamp' attribute, try that.
                                        5. Fall back to the provided default_ts ("now" for new messages).
                                        """
                                        # Dict-based histories (e.g. CLI format or older WS formats)
                                        if isinstance(raw_msg, dict):
                                            ts_val = raw_msg.get("timestamp")

                                            # Epoch seconds
                                            if isinstance(ts_val, (int, float)):
                                                try:
                                                    return (
                                                        datetime.datetime.fromtimestamp(
                                                            ts_val
                                                        ).isoformat()
                                                    )
                                                except Exception:
                                                    pass

                                            # Already an ISO string
                                            if isinstance(ts_val, str) and ts_val:
                                                return ts_val

                                            # Our enhanced WS wrapper sometimes uses 'ts'
                                            ts_field = raw_msg.get("ts")
                                            if isinstance(ts_field, str) and ts_field:
                                                return ts_field

                                        # Pydantic / custom objects that carry a timestamp attribute
                                        try:
                                            attr_ts = getattr(
                                                raw_msg, "timestamp", None
                                            )
                                            if isinstance(attr_ts, (int, float)):
                                                return datetime.datetime.fromtimestamp(
                                                    attr_ts
                                                ).isoformat()
                                            if isinstance(attr_ts, str) and attr_ts:
                                                return attr_ts
                                        except Exception:
                                            pass

                                        # Fallback: use provided default
                                        return default_ts

                                    # Create enhanced history: list of dicts with message + metadata
                                    # Each entry: {'msg': <original pydantic-ai message>, 'agent': str, 'model': str, 'ts': str}
                                    enhanced_history = []
                                    for idx, msg in enumerate(history):
                                        # Check if already wrapped (for idempotency). If the wrapper
                                        # already has a 'ts', leave it untouched so older sessions
                                        # keep their original per-message timestamps.
                                        if (
                                            isinstance(msg, dict)
                                            and "msg" in msg
                                            and "agent" in msg
                                        ):
                                            enhanced_history.append(msg)
                                        else:
                                            # Use existing timestamp if present; otherwise compute a default now()
                                            current_timestamp = (
                                                datetime.datetime.now().isoformat()
                                            )
                                            msg_ts = _extract_message_timestamp(
                                                msg, current_timestamp
                                            )
                                            wrapper = {
                                                "msg": msg,
                                                "agent": agent_name_meta,
                                                "model": model_name_meta,
                                                "ts": msg_ts,
                                            }

                                            # Add clean_content and attachments to the user message we just processed.
                                            # clean_content is only needed when attachments were injected into content
                                            # (file blocks like --- File: auth.ts ---). Without attachments, content
                                            # is already the user's words (FE strips [Session Context:] as fallback).
                                            is_user_message_just_processed = (
                                                idx == len(history) - 2
                                                and len(history) >= 2
                                                and attachment_metadata  # only needed when file content was injected
                                            )

                                            if is_user_message_just_processed:
                                                wrapper["clean_content"] = (
                                                    original_user_message
                                                )
                                                wrapper["attachments"] = (
                                                    attachment_metadata
                                                )
                                                logger.debug(
                                                    "Added UI metadata to user message: %d attachment(s), "
                                                    "clean_content length: %d",
                                                    len(attachment_metadata),
                                                    len(original_user_message),
                                                )

                                            enhanced_history.append(wrapper)

                                    message_count = len(enhanced_history)
                                    total_tokens = 0
                                    try:
                                        for item in enhanced_history:
                                            msg_obj = (
                                                item["msg"]
                                                if isinstance(item, dict)
                                                and "msg" in item
                                                else item
                                            )
                                            total_tokens += (
                                                agent.estimate_tokens_for_message(
                                                    msg_obj
                                                )
                                            )
                                    except Exception:
                                        total_tokens = 0

                                    # Write to SQLite for FE read path
                                    try:
                                        import datetime as _dt_mod

                                        _now_iso = _dt_mod.datetime.now(
                                            _dt_mod.timezone.utc
                                        ).isoformat()
                                        await write_turn_to_sqlite(
                                            session_id=session_id,
                                            enhanced_history=enhanced_history,
                                            title=session_title,
                                            working_directory=session_working_directory,
                                            pinned=session_pinned,
                                            agent_name=agent_name,
                                            model_name=model_name,
                                            total_tokens=total_tokens,
                                            updated_at=_now_iso,
                                            created_at=ctx.created_at.isoformat(),
                                            ctx=ctx,
                                        )
                                    except Exception as _db_exc:
                                        logger.debug(
                                            "SQLite turn write skipped (DB not available): %s",
                                            _db_exc,
                                        )

                                    # Send session metadata update to client
                                    await websocket.send_json(
                                        {
                                            "type": "session_meta",
                                            "session_id": session_id,
                                            "session_name": session_name,
                                            "total_tokens": total_tokens,
                                            "message_count": message_count,
                                            "title": session_title,
                                            "working_directory": session_working_directory,
                                            "agent_name": agent_name,
                                            "model_name": model_name,
                                        }
                                    )

                                    # Broadcast session update to session monitoring clients
                                    session_update_data = {
                                        "session_id": session_id,
                                        "session_name": session_name,
                                        "title": session_title,
                                        "working_directory": session_working_directory,
                                        "timestamp": datetime.datetime.now().isoformat(),
                                        "message_count": message_count,
                                        "total_tokens": total_tokens,
                                        "auto_saved": True,
                                        "pickle_path": "",
                                        "metadata_path": "",
                                        "action": "created"
                                        if message_count == 1
                                        else "updated",
                                    }
                                    await connection_manager.broadcast_session_update(
                                        session_update_data
                                    )
                            except Exception as save_err:
                                logger.warning(
                                    f"Failed to save WebSocket session: {save_err}"
                                )

                            # Send final status to signal completion
                            await send_typed(
                                ServerStatus(
                                    status="done",
                                    session_id=session_id,
                                    agent_name=agent.name if agent else "code-puppy",
                                    model_name=agent.get_model_name()
                                    if agent
                                    else "unknown",
                                )
                            )

                        except Exception as e:
                            logger.error(
                                f"Error processing message: {e}", exc_info=True
                            )

                            # Parse error and send user-friendly message
                            parsed_error = parse_api_error(e)
                            _err_msg = ServerError(
                                error=parsed_error["user_message"],
                                error_type=parsed_error["error_type"],
                                technical_details=parsed_error["technical_details"],
                                action_required=parsed_error.get("action_required"),
                                session_id=session_id,
                            )
                            error_payload = _err_msg.model_dump(exclude_none=True)
                            await persist_error_payload(error_payload)
                            await send_typed(_err_msg)

                except WebSocketDisconnect:
                    break
                except RuntimeError as e:
                    # Handle disconnect-related RuntimeErrors (starlette raises these)
                    if (
                        "disconnect" in str(e).lower()
                        or "websocket.close" in str(e).lower()
                    ):
                        logger.debug("WebSocket disconnected (RuntimeError): %s", e)
                        break
                    # Re-raise other RuntimeErrors to be handled as generic exceptions
                    raise
                except Exception as e:
                    logger.error("Chat WebSocket error: %s", e, exc_info=True)
                    # Don't try to send error if websocket is already closed
                    if ws_closed:
                        break
                    try:
                        _err_msg = ServerError(
                            error=str(e),
                            error_type="unknown",
                            technical_details=str(e),
                            session_id=session_id,
                        )
                        error_payload = _err_msg.model_dump(exclude_none=True)
                        await persist_error_payload(error_payload)
                        await send_typed(_err_msg)
                    except Exception:
                        break

        except WebSocketDisconnect:
            ws_closed = True
            logger.debug("Chat WebSocket client disconnected")
        except Exception as e:
            logger.error("Chat WebSocket error: %s", e, exc_info=True)
        finally:
            logger.debug("Chat session %s ended", session_id)

            # --- SESSION ISOLATION CLEANUP ---
            # Save and tear down session-scoped resources
            try:
                await session_manager.save_session(session_id)
            except Exception:
                logger.debug("Failed to save session on disconnect", exc_info=True)

            # Don't destroy immediately - mark as inactive for 15-min retention
            await session_manager.mark_session_inactive(session_id)
            cleanup_session_process_tracking()

            try:
                bus = get_message_bus()
                bus.set_session_context(None)
            except Exception:
                pass
