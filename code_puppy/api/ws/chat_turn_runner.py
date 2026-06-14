"""Per-turn WebSocket agent-runner helpers.

This module extracts the most delicate part of ``chat_handler``: the window
where an agent is running while the WebSocket must continue accepting inbound
messages such as permission responses, cancel requests, and session switches.

The goal is to preserve runtime behavior exactly while reducing the amount of
concurrent-control logic embedded directly in the endpoint handler.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from code_puppy.api.ws.chat_context import (
    begin_agent_run_context,
    cleanup_agent_run_context,
)
from code_puppy.api.ws.chat_turn_state import WebSocketTurnState
from code_puppy.api.ws.schemas import ClientMessage
from code_puppy.messaging.bus import get_message_bus
from code_puppy.messaging.commands import (
    AskUserQuestionResponse,
    ConfirmationResponse,
    SelectionResponse,
    UserInputResponse,
)

_ClientMessageAdapter = TypeAdapter(ClientMessage)
logger = logging.getLogger(__name__)


def handle_user_interaction_response(message: dict[str, Any]) -> bool:
    """Resolve MessageBus user-interaction responses during an active turn."""
    msg_type = message.get("type")
    if msg_type not in {
        "user_input_response",
        "confirmation_response",
        "selection_response",
        "ask_user_question_response",
    }:
        return False

    bus = get_message_bus()
    if msg_type == "user_input_response":
        bus.provide_response(
            UserInputResponse(
                prompt_id=message.get("prompt_id", ""),
                value=message.get("value", ""),
            )
        )
    elif msg_type == "confirmation_response":
        bus.provide_response(
            ConfirmationResponse(
                prompt_id=message.get("prompt_id", ""),
                confirmed=bool(message.get("confirmed", False)),
                feedback=message.get("feedback"),
            )
        )
    elif msg_type == "selection_response":
        bus.provide_response(
            SelectionResponse(
                prompt_id=message.get("prompt_id", ""),
                selected_index=int(message.get("selected_index", -1)),
                selected_value=message.get("selected_value", ""),
            )
        )
    else:
        bus.provide_response(
            AskUserQuestionResponse(
                prompt_id=message.get("prompt_id", ""),
                answers=message.get("answers") or [],
                cancelled=bool(message.get("cancelled", False)),
            )
        )
    return True


async def save_agent_result_in_background(**kwargs: Any) -> None:
    """Lazy proxy to avoid importing DB-heavy background-save code at module load."""
    from code_puppy.api.ws.background_save import (
        save_agent_result_in_background as _save_agent_result_in_background,
    )

    await _save_agent_result_in_background(**kwargs)


def fire_and_track(coro: Any) -> asyncio.Task:
    """Lazy proxy for tracked background tasks."""
    from code_puppy.api.ws.background_save import fire_and_track as _fire_and_track

    return _fire_and_track(coro)


@dataclass(slots=True)
class WebSocketTurnRunResult:
    """Outcome of one ``run_with_mcp`` execution window."""

    result: Any | None = None
    deferred_msg: dict[str, Any] | None = None


async def execute_turn_runner(
    *,
    websocket: Any,
    session_id: str,
    ctx: Any,
    agent: Any,
    agent_name: str,
    model_name: str,
    session_title: str,
    session_working_directory: str,
    session_pinned: bool,
    message_to_send: str,
    run_kwargs: dict[str, Any],
    turn_state: WebSocketTurnState,
    clear_session_working_directory: Callable[[], None],
) -> WebSocketTurnRunResult:
    """Run one agent turn while still receiving control messages.

    This preserves the existing concurrent behavior from ``chat_handler``:
    - permission responses are handled immediately
    - cancel requests cancel the in-flight agent task
    - switch/create_session requests disown the task to background-save logic
    - disconnects let the task finish in the background
    """

    _ws_run_context = begin_agent_run_context(session_id=session_id)
    active_agent_task = asyncio.create_task(
        agent.run_with_mcp(message_to_send, **run_kwargs)
    )

    result = None
    agent_completed = False
    deferred_msg: dict[str, Any] | None = None

    try:
        while not agent_completed:
            receive_task = asyncio.create_task(websocket.receive_json())
            done, pending = await asyncio.wait(
                {active_agent_task, receive_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if active_agent_task in done:
                try:
                    result = await active_agent_task
                    logger.debug(
                        "run_with_mcp completed, result type: %s", type(result)
                    )
                    agent_completed = True
                    active_agent_task = None
                except asyncio.CancelledError:
                    logger.debug("run_with_mcp task was cancelled by user")
                    turn_state.agent_error = "cancelled"
                    result = None
                    agent_completed = True
                    active_agent_task = None
                except Exception as e:
                    logger.error("Agent task error: %s", e, exc_info=True)
                    logger.debug(
                        "[WS:%s] agent task exception captured: type=%s repr=%r",
                        session_id,
                        type(e).__name__,
                        e,
                    )
                    turn_state.agent_error = e
                    result = None
                    agent_completed = True
                    active_agent_task = None

                if receive_task in pending:
                    receive_task.cancel()
                    try:
                        await receive_task
                    except asyncio.CancelledError:
                        pass

            elif receive_task in done:
                try:
                    new_msg = await receive_task

                    try:
                        _ClientMessageAdapter.validate_python(new_msg)
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

                    if handle_user_interaction_response(new_msg):
                        logger.debug(
                            "[UserInteraction] Handled response: %s",
                            new_msg.get("type"),
                        )

                    elif new_msg.get("type") == "permission_response":
                        from code_puppy.api.permissions import (
                            handle_permission_response,
                        )

                        request_id = new_msg.get("request_id")
                        approved = new_msg.get("approved", False)

                        if request_id:
                            handled = handle_permission_response(
                                request_id, approved, session_id=session_id
                            )
                            if handled:
                                logger.debug(
                                    "[Permission] ✅ Handled response: %s = %s",
                                    request_id,
                                    approved,
                                )
                            else:
                                logger.warning(
                                    "[Permission] ❌ Unknown request: %s",
                                    request_id,
                                )
                        else:
                            logger.error(
                                "[WebSocket] ❌ No request_id in permission_response!"
                            )

                    elif new_msg.get("type") == "cancel":
                        logger.debug("Cancel request received during agent execution")
                        if active_agent_task and not active_agent_task.done():
                            active_agent_task.cancel()
                            agent_completed = True

                    elif new_msg.get("type") in ("switch_session", "create_session"):
                        logger.debug(
                            "[WS:%s] Session switch during streaming — agent continues in background, switching to: %s",
                            session_id,
                            new_msg.get("session_id"),
                        )
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
                        deferred_msg = new_msg
                        active_agent_task = None
                        agent_completed = True

                    else:
                        logger.warning(
                            "[WebSocket] Received %s message while agent running - ignoring",
                            new_msg.get("type"),
                        )

                except asyncio.CancelledError:
                    pass
                except WebSocketDisconnect:
                    logger.debug(
                        "[WS:%s] Disconnect during streaming — agent continues in background",
                        session_id,
                    )
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
                        logger.debug(
                            "[WS:%s] WebSocket already disconnected: %s — agent continues in background",
                            session_id,
                            e,
                        )
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
                            "RuntimeError processing message during agent execution: %s",
                            e,
                        )
                except Exception as e:
                    logger.error(
                        "Error processing message during agent execution: %s",
                        e,
                    )
    finally:
        cleanup_agent_run_context(
            _ws_run_context,
            clear_session_working_directory=clear_session_working_directory,
        )

    return WebSocketTurnRunResult(result=result, deferred_msg=deferred_msg)
