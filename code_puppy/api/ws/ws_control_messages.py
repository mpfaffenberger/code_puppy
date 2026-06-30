"""Top-level non-chat control-message handlers for the chat WebSocket."""

from __future__ import annotations

import asyncio
import datetime
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

from code_puppy.api.db.queries import (
    update_session_working_directory,
    write_system_message_to_sqlite,
)
from code_puppy.api.permissions import handle_permission_response
from code_puppy.api.session_context import _validate_session_id, session_manager
from code_puppy.api.ws.schemas import (
    ServerConfigValue,
    ServerError,
    ServerSessionMetaUpdated,
    ServerSessionSwitched,
    ServerStatus,
    ServerSystem,
    ServerWorkingDirectoryChanged,
)
from code_puppy.api.ws.send_utils import WebSocketSender
from code_puppy.api.ws.ws_chat_runtime import WebSocketChatRuntime
from code_puppy.api.ws.ws_stream_drain import cancel_active_streaming

logger = logging.getLogger(__name__)


async def handle_control_message(
    *,
    msg: dict[str, Any],
    runtime: WebSocketChatRuntime,
    sender: WebSocketSender,
    send_typed: Any,
    send_session_meta_snapshot: Callable[[], Awaitable[None]],
) -> bool:
    """Handle non-chat, non-command websocket control messages."""
    return (
        await _handle_switch_agent(
            msg=msg,
            runtime=runtime,
            send_typed=send_typed,
        )
        or await _handle_switch_model(
            msg=msg,
            runtime=runtime,
            send_typed=send_typed,
        )
        or await _handle_switch_session(
            msg=msg,
            runtime=runtime,
            sender=sender,
            send_typed=send_typed,
            send_session_meta_snapshot=send_session_meta_snapshot,
        )
        or await _handle_set_working_directory(
            msg=msg,
            runtime=runtime,
            send_typed=send_typed,
        )
        or await _handle_update_session_meta(
            msg=msg,
            runtime=runtime,
            send_typed=send_typed,
        )
        or await _handle_get_config(
            msg=msg,
            runtime=runtime,
            send_typed=send_typed,
        )
        or await _handle_set_config(
            msg=msg,
            runtime=runtime,
            send_typed=send_typed,
        )
        or await _handle_cancel(
            msg=msg,
            runtime=runtime,
            send_typed=send_typed,
        )
        or await _handle_permission_response(msg=msg, session_id=runtime.session_id)
    )


async def _handle_switch_agent(
    *, msg: dict[str, Any], runtime: WebSocketChatRuntime, send_typed: Any
) -> bool:
    if msg.get("type") != "switch_agent":
        return False

    agent_name = msg.get("agent_name")
    if agent_name:
        try:
            new_agent = await session_manager.switch_agent(
                runtime.session_id, agent_name
            )
            runtime.agent = new_agent
            if runtime.ctx is not None:
                runtime.ctx.agent = new_agent
                runtime.ctx.agent_name = agent_name
            runtime.agent_name = agent_name
            runtime.model_name = new_agent.get_model_name() if new_agent else "unknown"

            try:
                await write_system_message_to_sqlite(
                    session_id=runtime.session_id,
                    system_message_type="config",
                    content=f"🔄 Switched to {agent_name} ({runtime.model_name})",
                    agent_name=agent_name,
                    model_name=runtime.model_name,
                )
            except Exception as exc:
                logger.warning(
                    "Agent-switch SQLite write failed: %s", exc, exc_info=True
                )

            await send_typed(
                ServerSystem(
                    content=f"🔄 Switched to {agent_name} ({runtime.model_name})",
                    session_id=runtime.session_id,
                    agent_name=agent_name,
                    model_name=runtime.model_name,
                )
            )
        except Exception as exc:
            logger.error("Error switching agent: %s", exc)
            await send_typed(
                ServerError(
                    error=f"Failed to switch to agent {agent_name}: {str(exc)}",
                    session_id=runtime.session_id,
                )
            )
    return True


async def _handle_switch_model(
    *, msg: dict[str, Any], runtime: WebSocketChatRuntime, send_typed: Any
) -> bool:
    if msg.get("type") != "switch_model":
        return False

    model_name = msg.get("model_name") or msg.get("model")
    if model_name:
        try:
            await session_manager.switch_model(runtime.session_id, model_name)
            runtime.agent = runtime.ctx.agent if runtime.ctx else runtime.agent
            runtime.model_name = model_name
            if runtime.ctx is not None:
                runtime.ctx.model_name = model_name
            logger.debug("Switched model to: %s", model_name)

            switch_agent = (
                (runtime.ctx.agent_name if runtime.ctx else None)
                or runtime.agent_name
                or "code-puppy"
            )
            try:
                await write_system_message_to_sqlite(
                    session_id=runtime.session_id,
                    system_message_type="config",
                    content=f"🔄 Switched to {switch_agent} ({model_name})",
                    agent_name=switch_agent,
                    model_name=model_name,
                )
            except Exception as exc:
                logger.warning(
                    "Model-switch SQLite write failed: %s", exc, exc_info=True
                )

            await send_typed(
                ServerSystem(
                    content=f"🔄 Switched to {switch_agent} ({model_name})",
                    session_id=runtime.session_id,
                    model_name=model_name,
                    agent_name=switch_agent,
                )
            )
        except Exception as exc:
            logger.error("Error switching model: %s", exc)
            await send_typed(
                ServerError(
                    error=f"Failed to switch to model {model_name}: {str(exc)}",
                    session_id=runtime.session_id,
                )
            )
    else:
        await send_typed(
            ServerError(
                error="No model_name provided for switch_model",
                session_id=runtime.session_id,
            )
        )
    return True


async def _handle_switch_session(
    *,
    msg: dict[str, Any],
    runtime: WebSocketChatRuntime,
    sender: WebSocketSender,
    send_typed: Any,
    send_session_meta_snapshot: Callable[[], Awaitable[None]],
) -> bool:
    if msg.get("type") != "switch_session":
        return False

    logger.debug("Cancelling active streaming due to session switch")
    await cancel_active_streaming(
        active_drain_task=runtime.active_drain_task,
        stop_draining=runtime.stop_draining,
        logger=logger,
    )

    new_session_id = msg.get("session_id")
    if not new_session_id:
        await send_typed(
            ServerError(
                error="No session_id provided for switch_session",
                session_id=runtime.session_id,
            )
        )
        return True

    try:
        _validate_session_id(new_session_id)
    except ValueError as exc:
        logger.warning("Invalid session_id in switch_session: %r", new_session_id)
        await send_typed(
            ServerError(
                error=f"Invalid session ID: {exc}",
                session_id=runtime.session_id,
            )
        )
        return True

    logger.debug("Switching to session: %s", new_session_id)
    try:
        try:
            from code_puppy.api.db.queries import session_exists as _session_exists

            target_exists = await _session_exists(new_session_id)
        except Exception:
            target_exists = False

        try:
            await session_manager.save_session(runtime.session_id)
        except Exception:
            pass
        await session_manager.mark_session_inactive(runtime.session_id)

        if not target_exists:
            logger.debug("Session %s not found, creating new", new_session_id)
            runtime.session_id = new_session_id
            sender.session_id = new_session_id
            runtime.session_title = ""
            runtime.session_working_directory = ""
            runtime.session_pinned = False
            runtime.existing_history = None
            runtime.ctx = await session_manager.create_session(new_session_id)
            sender.ctx = runtime.ctx
            await session_manager.mark_session_active(new_session_id)
            runtime.sync_from_ctx()
            await send_typed(
                ServerSessionSwitched(
                    session_id=new_session_id,
                    message_count=0,
                    title="",
                    created=True,
                    agent_name=runtime.agent_name,
                    model_name=runtime.model_name,
                )
            )
            return True

        loaded_ctx = await session_manager.get_or_load_session(new_session_id)
        runtime.session_id = new_session_id
        sender.session_id = new_session_id
        if loaded_ctx is not None:
            runtime.ctx = loaded_ctx
            runtime.sync_from_ctx()
        else:
            new_title = ""
            new_working_directory = ""
            new_pinned = False
            try:
                from code_puppy.api.db.queries import (
                    get_session_metadata as _get_session_metadata,
                )

                session_meta = await _get_session_metadata(new_session_id) or {}
                new_title = session_meta.get("title", "")
                new_working_directory = session_meta.get("working_directory", "")
                new_pinned = bool(session_meta.get("pinned", False))
            except Exception:
                pass

            runtime.ctx = await session_manager.create_session(new_session_id)
            sender.ctx = runtime.ctx
            runtime.ctx.title = new_title
            runtime.ctx.working_directory = new_working_directory
            runtime.ctx.pinned = new_pinned
            runtime.sync_from_ctx()

        sender.ctx = runtime.ctx
        await session_manager.mark_session_active(new_session_id)
        runtime.sync_from_ctx()
        message_count = (
            len(runtime.ctx.agent.get_message_history() or []) if runtime.ctx else 0
        )
        logger.debug("Restored %d messages to session agent", message_count)

        await send_typed(
            ServerSessionSwitched(
                session_id=new_session_id,
                message_count=message_count,
                title=runtime.session_title,
                working_directory=runtime.session_working_directory,
                created=False,
                agent_name=runtime.agent_name,
                model_name=runtime.model_name,
            )
        )
        await send_session_meta_snapshot()
        logger.debug(
            "Switched to session %s with %d messages",
            new_session_id,
            message_count,
        )
    except Exception as exc:
        logger.error("Error switching session: %s", exc)
        await send_typed(
            ServerError(
                error=f"Failed to switch to session {new_session_id}: {str(exc)}",
                session_id=runtime.session_id,
            )
        )
    return True


async def _handle_set_working_directory(
    *, msg: dict[str, Any], runtime: WebSocketChatRuntime, send_typed: Any
) -> bool:
    if msg.get("type") != "set_working_directory":
        return False

    new_directory = msg.get("directory", "")
    if not new_directory:
        await send_typed(
            ServerError(
                error="No directory provided for set_working_directory",
                session_id=runtime.session_id,
            )
        )
        return True

    new_directory = str(Path(new_directory).expanduser().resolve())
    logger.info(
        "[CWD DEBUG] set_working_directory received: new=%r, current=%r, session=%s",
        new_directory,
        runtime.session_working_directory,
        runtime.session_id,
    )
    if not Path(new_directory).is_dir():
        await send_typed(
            ServerWorkingDirectoryChanged(
                directory=new_directory,
                success=False,
                error="Directory does not exist",
                session_id=runtime.session_id,
            )
        )
        return True

    if new_directory == runtime.session_working_directory:
        logger.info(
            "[CWD DEBUG] Skipping unchanged directory: %r, session=%s",
            new_directory,
            runtime.session_id,
        )
        await send_typed(
            ServerWorkingDirectoryChanged(
                directory=new_directory,
                success=True,
                session_id=runtime.session_id,
                unchanged=True,
            )
        )
        return True

    runtime.session_working_directory = new_directory
    if runtime.ctx is not None:
        runtime.ctx.working_directory = new_directory
    logger.debug("Working directory set to: %s", runtime.session_working_directory)

    try:
        cwd_agent = (runtime.ctx.agent_name if runtime.ctx else None) or "code-puppy"
        cwd_model = (runtime.ctx.model_name if runtime.ctx else None) or "unknown"
        cwd_segs = runtime.session_working_directory.split("/")[-3:]
        cwd_rel = "/".join(s for s in cwd_segs if s)
        from code_puppy.config import get_puppy_name as _get_puppy_name

        puppy_name = _get_puppy_name() or "puppy"
        logger.info(
            "[CWD DEBUG] Writing CWD banner to SQLite: path=%r, session=%s",
            runtime.session_working_directory,
            runtime.session_id,
        )
        await write_system_message_to_sqlite(
            session_id=runtime.session_id,
            system_message_type="directory",
            content=f"{puppy_name} is now at {cwd_rel}",
            system_message_path=runtime.session_working_directory,
            agent_name=cwd_agent,
            model_name=cwd_model,
        )
        now_cwd = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await update_session_working_directory(
            session_id=runtime.session_id,
            working_directory=runtime.session_working_directory,
            updated_at=now_cwd,
        )
    except Exception as exc:
        logger.warning("CWD SQLite write failed: %s", exc, exc_info=True)

    await send_typed(
        ServerWorkingDirectoryChanged(
            directory=runtime.session_working_directory,
            success=True,
            session_id=runtime.session_id,
        )
    )
    return True


async def _handle_update_session_meta(
    *, msg: dict[str, Any], runtime: WebSocketChatRuntime, send_typed: Any
) -> bool:
    if msg.get("type") != "update_session_meta":
        return False

    try:
        if "pinned" in msg and isinstance(msg["pinned"], bool):
            runtime.session_pinned = msg["pinned"]
            if runtime.ctx is not None:
                runtime.ctx.pinned = runtime.session_pinned
        if "title" in msg and isinstance(msg["title"], str):
            runtime.session_title = msg["title"]
            if runtime.ctx is not None:
                runtime.ctx.title = runtime.session_title

        try:
            from datetime import datetime as _dt
            from datetime import timezone as _tz

            from code_puppy.api.db.queries import update_session_meta_fields

            await update_session_meta_fields(
                session_id=runtime.session_id,
                title=runtime.session_title,
                pinned=runtime.session_pinned,
                updated_at=_dt.now(_tz.utc).isoformat(),
            )
            logger.debug(
                "Updated session meta in SQLite for %s: pinned=%s",
                runtime.session_id,
                runtime.session_pinned,
            )
        except Exception as meta_exc:
            logger.warning("Failed to persist session meta to SQLite: %s", meta_exc)

        await send_typed(
            ServerSessionMetaUpdated(
                session_id=runtime.session_id,
                pinned=runtime.session_pinned,
                title=runtime.session_title,
            )
        )
    except Exception as exc:
        logger.error("Error updating session meta: %s", exc)
        await send_typed(
            ServerError(
                error=f"Failed to update session metadata: {str(exc)}",
                session_id=runtime.session_id,
            )
        )
    return True


async def _handle_get_config(
    *, msg: dict[str, Any], runtime: WebSocketChatRuntime, send_typed: Any
) -> bool:
    if msg.get("type") != "get_config":
        return False

    config_key = msg.get("key", "")
    if config_key:
        from code_puppy.config import get_value

        value = get_value(config_key)
        await send_typed(
            ServerConfigValue(
                key=config_key,
                value=value,
                session_id=runtime.session_id,
            )
        )
    else:
        await send_typed(
            ServerError(
                error="No key provided for get_config",
                session_id=runtime.session_id,
            )
        )
    return True


async def _handle_set_config(
    *, msg: dict[str, Any], runtime: WebSocketChatRuntime, send_typed: Any
) -> bool:
    if msg.get("type") != "set_config":
        return False

    config_key = msg.get("key", "")
    config_value = msg.get("value", "")
    if config_key:
        from code_puppy.config import set_config_value

        try:
            set_config_value(config_key, str(config_value))
            logger.debug("Config set: %s = %s", config_key, config_value)
            await send_typed(
                ServerConfigValue(
                    key=config_key,
                    value=config_value,
                    success=True,
                    session_id=runtime.session_id,
                )
            )
        except Exception as exc:
            await send_typed(
                ServerError(
                    error=f"Failed to set config: {exc}",
                    session_id=runtime.session_id,
                )
            )
    else:
        await send_typed(
            ServerError(
                error="No key provided for set_config",
                session_id=runtime.session_id,
            )
        )
    return True


async def _handle_cancel(
    *, msg: dict[str, Any], runtime: WebSocketChatRuntime, send_typed: Any
) -> bool:
    if msg.get("type") != "cancel":
        return False

    logger.debug("Cancel request received - stopping active streaming and agent task")
    await cancel_active_streaming(
        active_drain_task=runtime.active_drain_task,
        stop_draining=runtime.stop_draining,
        logger=logger,
        log_message="Active streaming cancelled",
    )

    if runtime.active_agent_task and not runtime.active_agent_task.done():
        logger.debug("Cancelling active agent task due to user interrupt")
        runtime.active_agent_task.cancel()
        try:
            await runtime.active_agent_task
        except asyncio.CancelledError:
            logger.debug("Active agent task cancelled successfully")
        runtime.active_agent_task = None

    await send_typed(ServerStatus(status="cancelled", session_id=runtime.session_id))
    return True


async def _handle_permission_response(*, msg: dict[str, Any], session_id: str) -> bool:
    if msg.get("type") != "permission_response":
        return False

    request_id = msg.get("request_id")
    approved = msg.get("approved", False)
    if request_id:
        handled = handle_permission_response(
            request_id, approved, session_id=session_id
        )
        if handled:
            logger.debug(
                "[Permission] ✅ Handled response: %s = %s", request_id, approved
            )
        else:
            logger.warning("[Permission] ❌ Unknown request: %s", request_id)
    else:
        logger.error("[WebSocket] ❌ No request_id in permission_response!")
    return True


__all__ = ["handle_control_message"]
