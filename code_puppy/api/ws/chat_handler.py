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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from code_puppy.api.session_context import session_manager
from code_puppy.api.ws.ws_stream_drain import (
    start_stream_drain,
    stop_stream_drain,
)
from code_puppy.api.ws.ws_post_run import resolve_post_run_resolution
from code_puppy.api.ws.ws_resume_recovery import (
    reload_session_from_sqlite_with_sanitization,
)
from code_puppy.api.ws.ws_turn_finalization import (
    emit_pre_stream_end_tool_results,
    finalize_turn_history,
)
from code_puppy.api.ws.chat_event_adapter import (
    collect_final_stream_text_delta,
    handle_assistant_part_delta,
    handle_assistant_part_end,
    handle_assistant_part_start,
)
from code_puppy.api.ws.chat_tool_lifecycle import (
    accumulate_tool_call_part_delta as lifecycle_accumulate_tool_call_part_delta,
    finish_tool_call_part as lifecycle_finish_tool_call_part,
    handle_tool_call_complete_event as lifecycle_handle_tool_call_complete_event,
    handle_tool_call_start_event as lifecycle_handle_tool_call_start_event,
    send_status_only_pending_tool_results as lifecycle_send_status_only_pending_tool_results,
    start_tool_call_part as lifecycle_start_tool_call_part,
    start_tool_return_part as lifecycle_start_tool_return_part,
)
from code_puppy.api.ws.ws_turn_preparation import prepare_turn_input
from code_puppy.api.ws.response_frames import (
    build_assistant_text_stream_frames,
    parse_api_error,
)
from code_puppy.api.ws.ws_command_handler import handle_command_message
from code_puppy.api.ws.ws_control_messages import handle_control_message
from code_puppy.api.ws.schemas import (
    ClientMessage,
    ServerAgentInvoked,
    ServerAssistantMessageDelta,
    ServerAssistantMessageEnd,
    ServerAssistantMessageStart,
    ServerCancelled,
    ServerError,
    ServerStatus,
    ServerSystem,
    ServerStreamEnd,
    ServerUserMessage,
    ServerConfirmationRequest,
    ServerSelectionRequest,
    ServerUserInputRequest,
    ServerAskUserQuestionRequest,
)
from code_puppy.api.ws.send_utils import WebSocketSender
from code_puppy.api.ws.ws_session_bootstrap import initialize_ws_session
from code_puppy.api.ws.chat_context import (
    cleanup_message_context,
    setup_message_context,
)
from code_puppy.api.ws.chat_turn_runner import execute_turn_runner
from code_puppy.api.ws.chat_turn_state import WebSocketTurnState
from code_puppy.api.ws.session_persistence import persist_session_turn_and_broadcast
from code_puppy.config import get_global_model_name
from code_puppy.messaging.bus import get_message_bus
from code_puppy.messaging.commands import (
    AskUserQuestionResponse,
    ConfirmationResponse,
    SelectionResponse,
    UserInputResponse,
)
from code_puppy.messaging.messages import (
    AskUserQuestionRequest,
    ConfirmationRequest,
    SelectionRequest,
    UserInputRequest,
)
from code_puppy.tools.command_runner import cleanup_session_process_tracking

# Per-agent-run working-directory context for shell/tool execution.
# This is intentionally core (not Walmart-plugin-specific) so the desk UI works
# in both the open-source and Walmart worktrees.
from code_puppy.api.session_cwd import (
    clear_session_working_directory,
    set_session_working_directory,
)

HAS_SESSION_CONTEXT = True


_ClientMessageAdapter = TypeAdapter(ClientMessage)

logger = logging.getLogger(__name__)


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

            # Final stream marker
            {"type": "stream_end", "success": true, "total_length": 123,
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

        # WebSocketSender encapsulates sender.ws_closed, safe_send_json,
        # persist_error_payload, send_typed, and send_typed_tool_lifecycle.
        sender = WebSocketSender(websocket, session_id)

        # Convenience aliases for call-site compatibility.
        safe_send_json = sender.safe_send_json
        send_typed = sender.send_typed
        send_typed_tool_lifecycle = sender.send_typed_tool_lifecycle
        persist_error_payload = sender.persist_error_payload

        runtime = await initialize_ws_session(
            websocket=websocket,
            requested_session_id=session_id,
            sender=sender,
            safe_send_json=safe_send_json,
            send_typed=send_typed,
        )
        if runtime is None:
            return

        session_id = runtime.session_id
        ctx = runtime.ctx
        session_title = runtime.session_title
        session_working_directory = runtime.session_working_directory
        session_pinned = runtime.session_pinned
        last_context_sent_directory = runtime.last_context_sent_directory
        existing_history = runtime.existing_history
        agent = runtime.agent
        agent_name = runtime.agent_name
        model_name = runtime.model_name
        active_drain_task = runtime.active_drain_task
        active_agent_task = runtime.active_agent_task
        stop_draining = runtime.stop_draining

        try:
            get_message_bus().mark_renderer_active()
        except Exception:
            logger.debug("Failed to mark MessageBus renderer active", exc_info=True)

        async def forward_message_bus_interactions() -> None:
            """Forward pending MessageBus user-interaction prompts to chat.html."""
            try:
                bus = get_message_bus()
                # Keep the drain bounded so regular stream events stay responsive.
                for _ in range(20):
                    request = bus.get_message_nowait()
                    if request is None:
                        break
                    if isinstance(request, UserInputRequest):
                        await send_typed(
                            ServerUserInputRequest(
                                prompt_id=request.prompt_id,
                                prompt_text=request.prompt_text,
                                default_value=request.default_value,
                                input_type=request.input_type,
                                session_id=session_id,
                            )
                        )
                    elif isinstance(request, ConfirmationRequest):
                        await send_typed(
                            ServerConfirmationRequest(
                                prompt_id=request.prompt_id,
                                title=request.title,
                                description=request.description,
                                options=request.options,
                                allow_feedback=request.allow_feedback,
                                session_id=session_id,
                            )
                        )
                    elif isinstance(request, SelectionRequest):
                        await send_typed(
                            ServerSelectionRequest(
                                prompt_id=request.prompt_id,
                                prompt_text=request.prompt_text,
                                options=request.options,
                                allow_cancel=request.allow_cancel,
                                session_id=session_id,
                            )
                        )
                    elif isinstance(request, AskUserQuestionRequest):
                        await send_typed(
                            ServerAskUserQuestionRequest(
                                prompt_id=request.prompt_id,
                                questions=request.questions,
                                timeout_seconds=request.timeout_seconds,
                                session_id=session_id,
                            )
                        )
                    else:
                        logger.debug(
                            "Dropping unsupported MessageBus UI message: %s",
                            type(request).__name__,
                        )
            except Exception:
                logger.debug("Failed to forward MessageBus interaction", exc_info=True)

        async def send_session_meta_snapshot() -> None:
            runtime.session_id = session_id
            runtime.ctx = ctx
            runtime.session_title = session_title
            runtime.session_working_directory = session_working_directory
            runtime.session_pinned = session_pinned
            runtime.last_context_sent_directory = last_context_sent_directory
            runtime.agent = agent
            runtime.agent_name = agent_name
            runtime.model_name = model_name
            runtime.active_drain_task = active_drain_task
            runtime.active_agent_task = active_agent_task
            from code_puppy.api.ws.ws_session_bootstrap import (
                send_session_meta_snapshot as _send_session_meta_snapshot,
            )

            await _send_session_meta_snapshot(
                runtime=runtime,
                safe_send_json=safe_send_json,
            )

        try:
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

                    if msg.get("type") in {
                        "user_input_response",
                        "confirmation_response",
                        "selection_response",
                        "ask_user_question_response",
                    }:
                        bus = get_message_bus()
                        try:
                            if msg.get("type") == "user_input_response":
                                bus.provide_response(
                                    UserInputResponse(
                                        prompt_id=msg.get("prompt_id", ""),
                                        value=msg.get("value", ""),
                                    )
                                )
                            elif msg.get("type") == "confirmation_response":
                                bus.provide_response(
                                    ConfirmationResponse(
                                        prompt_id=msg.get("prompt_id", ""),
                                        confirmed=bool(msg.get("confirmed", False)),
                                        feedback=msg.get("feedback"),
                                    )
                                )
                            elif msg.get("type") == "selection_response":
                                bus.provide_response(
                                    SelectionResponse(
                                        prompt_id=msg.get("prompt_id", ""),
                                        selected_index=int(
                                            msg.get("selected_index", -1)
                                        ),
                                        selected_value=msg.get("selected_value", ""),
                                    )
                                )
                            else:
                                bus.provide_response(
                                    AskUserQuestionResponse(
                                        prompt_id=msg.get("prompt_id", ""),
                                        answers=msg.get("answers") or [],
                                        cancelled=bool(msg.get("cancelled", False)),
                                    )
                                )
                        except Exception as exc:
                            logger.warning("Invalid user interaction response: %s", exc)
                            await send_typed(
                                ServerError(
                                    error=f"Invalid user interaction response: {exc}",
                                    session_id=session_id,
                                )
                            )
                        continue

                    if await handle_command_message(
                        msg=msg,
                        session_id=session_id,
                        send_typed=send_typed,
                    ):
                        continue

                    runtime.session_id = session_id
                    runtime.ctx = ctx
                    runtime.session_title = session_title
                    runtime.session_working_directory = session_working_directory
                    runtime.session_pinned = session_pinned
                    runtime.last_context_sent_directory = last_context_sent_directory
                    runtime.agent = agent
                    runtime.agent_name = agent_name
                    runtime.model_name = model_name
                    runtime.active_drain_task = active_drain_task
                    runtime.active_agent_task = active_agent_task

                    if await handle_control_message(
                        msg=msg,
                        runtime=runtime,
                        sender=sender,
                        send_typed=send_typed,
                        send_session_meta_snapshot=send_session_meta_snapshot,
                    ):
                        session_id = runtime.session_id
                        ctx = runtime.ctx
                        session_title = runtime.session_title
                        session_working_directory = runtime.session_working_directory
                        session_pinned = runtime.session_pinned
                        last_context_sent_directory = (
                            runtime.last_context_sent_directory
                        )
                        agent = runtime.agent
                        agent_name = runtime.agent_name
                        model_name = runtime.model_name
                        active_drain_task = runtime.active_drain_task
                        active_agent_task = runtime.active_agent_task
                        continue

                    elif msg.get("type") == "message":
                        # Set WebSocket context for permission requests
                        setup_message_context(
                            websocket=websocket, session_id=session_id
                        )

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
                            turn_state = WebSocketTurnState()
                            stop_draining.clear()  # Reset for this message
                            drain_task = None
                            drain_handle = None

                            async def drain_events_concurrent(
                                stream_event_queue,
                                ready_event: asyncio.Event = None,
                            ):
                                """Background task to drain events and send structured messages in real-time."""
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

                                async def send_status_only_pending_tool_results():
                                    await (
                                        lifecycle_send_status_only_pending_tool_results(
                                            turn_state=turn_state,
                                            session_id=session_id,
                                            agent_name=current_agent_name,
                                            model_name=current_model_name,
                                            send_typed=send_typed,
                                            logger=logger,
                                        )
                                    )

                                event_count = 0
                                first_iteration = True
                                while not stop_draining.is_set():
                                    # Exit if WebSocket is closed
                                    if sender.ws_closed:
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
                                            stream_event_queue.get(), timeout=0.01
                                        )
                                        events_to_send.append(first_event)
                                        event_count += 1

                                        # Collect any additional events already in queue (non-blocking)
                                        # This keeps the batching benefit without polling the clock
                                        while not stream_event_queue.empty():
                                            try:
                                                event = stream_event_queue.get_nowait()
                                                events_to_send.append(event)
                                                event_count += 1
                                            except Exception:
                                                break

                                    except asyncio.TimeoutError:
                                        # No events available within 10ms timeout
                                        # No polling needed - asyncio.wait_for blocks efficiently
                                        pass

                                    await forward_message_bus_interactions()

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
                                                await lifecycle_handle_tool_call_start_event(
                                                    turn_state=turn_state,
                                                    event_data=event_data,
                                                    session_id=session_id,
                                                    agent_name=current_agent_name,
                                                    model_name=current_model_name,
                                                    send_typed_tool_lifecycle=send_typed_tool_lifecycle,
                                                    logger=logger,
                                                )
                                            elif event_type == "tool_call_complete":
                                                await lifecycle_handle_tool_call_complete_event(
                                                    turn_state=turn_state,
                                                    event_data=event_data,
                                                    session_id=session_id,
                                                    agent_name=current_agent_name,
                                                    model_name=current_model_name,
                                                    send_typed_tool_lifecycle=send_typed_tool_lifecycle,
                                                    logger=logger,
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

                                                    if await handle_assistant_part_start(
                                                        turn_state=turn_state,
                                                        part_index=part_index,
                                                        part_type=part_type,
                                                        part_obj=part_obj,
                                                        session_id=session_id,
                                                        agent_name=current_agent_name,
                                                        model_name=current_model_name,
                                                        safe_send_json=safe_send_json,
                                                        logger=logger,
                                                        send_status_only_pending_tool_results=send_status_only_pending_tool_results,
                                                    ):
                                                        continue
                                                    if part_type == "ToolCallPart":
                                                        lifecycle_start_tool_call_part(
                                                            turn_state=turn_state,
                                                            part_index=part_index,
                                                            part_obj=part_obj,
                                                            logger=logger,
                                                        )
                                                    elif part_type == "ToolReturnPart":
                                                        await lifecycle_start_tool_return_part(
                                                            turn_state=turn_state,
                                                            part_index=part_index,
                                                            part_obj=part_obj,
                                                            session_id=session_id,
                                                            agent_name=current_agent_name,
                                                            model_name=current_model_name,
                                                            send_typed_tool_lifecycle=send_typed_tool_lifecycle,
                                                            logger=logger,
                                                        )

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
                                                    if (
                                                        delta_type
                                                        == "ToolCallPartDelta"
                                                    ):
                                                        if lifecycle_accumulate_tool_call_part_delta(
                                                            turn_state=turn_state,
                                                            part_index=part_index,
                                                            delta_obj=delta_obj,
                                                        ):
                                                            continue  # Don't process as text delta

                                                    if await handle_assistant_part_delta(
                                                        turn_state=turn_state,
                                                        part_index=part_index,
                                                        inner_data=inner_data,
                                                        delta_obj=delta_obj,
                                                        session_id=session_id,
                                                        agent_name=current_agent_name,
                                                        model_name=current_model_name,
                                                        safe_send_json=safe_send_json,
                                                        logger=logger,
                                                    ):
                                                        continue

                                                elif inner_type == "part_end":
                                                    part_index = inner_data.get(
                                                        "index", 0
                                                    )
                                                    part_info = (
                                                        turn_state.active_parts.get(
                                                            part_index, {}
                                                        )
                                                    )
                                                    part_type_info = part_info.get(
                                                        "type", "text"
                                                    )

                                                    if await handle_assistant_part_end(
                                                        turn_state=turn_state,
                                                        part_index=part_index,
                                                        session_id=session_id,
                                                        agent_name=current_agent_name,
                                                        model_name=current_model_name,
                                                        safe_send_json=safe_send_json,
                                                    ):
                                                        continue
                                                    if part_type_info == "tool_call":
                                                        await lifecycle_finish_tool_call_part(
                                                            turn_state=turn_state,
                                                            part_index=part_index,
                                                            part_info=part_info,
                                                            session_id=session_id,
                                                            agent_name=current_agent_name,
                                                            model_name=current_model_name,
                                                            send_typed_tool_lifecycle=send_typed_tool_lifecycle,
                                                            logger=logger,
                                                        )
                                                    else:
                                                        turn_state.active_parts.pop(
                                                            part_index, None
                                                        )

                                        except Exception as send_err:
                                            error_msg = str(send_err).lower()
                                            if (
                                                "close message" in error_msg
                                                or "closed" in error_msg
                                            ):
                                                sender.ws_closed = True
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
                                        event = stream_event_queue.get_nowait()
                                        event_type = event.get("type", "")
                                        event_data = event.get("data", {})
                                        final_count += 1

                                        if event_type == "stream_event":
                                            collect_final_stream_text_delta(
                                                turn_state=turn_state,
                                                event=event,
                                            )
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

                            drain_handle = await start_stream_drain(
                                session_id=session_id,
                                drain_coro_factory=drain_events_concurrent,
                                logger=logger,
                            )
                            if drain_handle is not None:
                                drain_task = drain_handle.task
                                active_drain_task = drain_task

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

                                    _prepared_turn = prepare_turn_input(
                                        agent=agent,
                                        user_message=user_message,
                                        msg=msg,
                                        session_working_directory=session_working_directory,
                                        last_context_sent_directory=last_context_sent_directory,
                                    )
                                    message_to_send = _prepared_turn.message_to_send
                                    run_kwargs = _prepared_turn.run_kwargs
                                    attachment_metadata = (
                                        _prepared_turn.attachment_metadata
                                    )
                                    last_context_sent_directory = (
                                        _prepared_turn.last_context_sent_directory
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

                                    _turn_run = await execute_turn_runner(
                                        websocket=websocket,
                                        session_id=session_id,
                                        ctx=ctx,
                                        agent=agent,
                                        agent_name=agent_name,
                                        model_name=model_name,
                                        session_title=session_title,
                                        session_working_directory=session_working_directory,
                                        session_pinned=session_pinned,
                                        message_to_send=message_to_send,
                                        run_kwargs=run_kwargs,
                                        turn_state=turn_state,
                                        clear_session_working_directory=clear_session_working_directory,
                                    )
                                    result = _turn_run.result
                                    _deferred_msg = _turn_run.deferred_msg

                                finally:
                                    pass

                            finally:
                                await stop_stream_drain(
                                    handle=drain_handle,
                                    stop_draining=stop_draining,
                                    logger=logger,
                                )

                            # Process any deferred switch_session that arrived during streaming
                            if _deferred_msg is not None:
                                msg = _deferred_msg
                                _deferred_msg = None
                                # Re-dispatch to outer loop by continuing with msg set
                                # The outer while True loop will handle switch_session/create_session
                                continue

                            post_run = resolve_post_run_resolution(
                                result=result,
                                turn_state=turn_state,
                                agent=agent,
                                session_id=session_id,
                                logger=logger,
                            )
                            if post_run.cancelled:
                                await send_typed(
                                    ServerCancelled(
                                        session_id=session_id,
                                    )
                                )
                                continue
                            if post_run.error_frames is not None:
                                for frame in post_run.error_frames:
                                    await safe_send_json(frame)
                                continue
                            if post_run.no_result_error is not None:
                                recovery_applied = False
                                # Safe one-shot auto-recovery for resumed sessions only.
                                if existing_history is not None:
                                    await send_typed(
                                        ServerSystem(
                                            content=(
                                                "Attempting safe session recovery from SQLite history "
                                                "(one retry)..."
                                            ),
                                            session_id=session_id,
                                            agent_name=agent_name,
                                            model_name=model_name,
                                        )
                                    )
                                    recovery = await reload_session_from_sqlite_with_sanitization(
                                        session_id=session_id,
                                        logger=logger,
                                    )
                                    if recovery.success and recovery.ctx is not None:
                                        ctx = recovery.ctx
                                        sender.ctx = ctx
                                        agent = ctx.agent
                                        agent_name = ctx.agent_name
                                        model_name = ctx.model_name

                                        retry_turn_state = WebSocketTurnState()
                                        retry_run = await execute_turn_runner(
                                            websocket=websocket,
                                            session_id=session_id,
                                            ctx=ctx,
                                            agent=agent,
                                            agent_name=agent_name,
                                            model_name=model_name,
                                            session_title=session_title,
                                            session_working_directory=session_working_directory,
                                            session_pinned=session_pinned,
                                            message_to_send=message_to_send,
                                            run_kwargs=run_kwargs,
                                            turn_state=retry_turn_state,
                                            clear_session_working_directory=clear_session_working_directory,
                                        )
                                        retry_post_run = resolve_post_run_resolution(
                                            result=retry_run.result,
                                            turn_state=retry_turn_state,
                                            agent=agent,
                                            session_id=session_id,
                                            logger=logger,
                                        )
                                        if retry_post_run.cancelled:
                                            await send_typed(
                                                ServerCancelled(
                                                    session_id=session_id,
                                                )
                                            )
                                            continue
                                        if retry_post_run.error_frames is not None:
                                            for frame in retry_post_run.error_frames:
                                                await safe_send_json(frame)
                                            continue
                                        if retry_post_run.no_result_error is None:
                                            post_run = retry_post_run
                                            recovery_applied = True
                                            await send_typed(
                                                ServerSystem(
                                                    content=(
                                                        "Session auto-recovery succeeded; continuing with "
                                                        "reloaded DB history."
                                                    ),
                                                    session_id=session_id,
                                                    agent_name=agent_name,
                                                    model_name=model_name,
                                                )
                                            )
                                        else:
                                            logger.warning(
                                                "[WS:%s] one-shot recovery retry still produced no response",
                                                session_id,
                                            )
                                    else:
                                        logger.warning(
                                            "[WS:%s] recovery reload failed: %s",
                                            session_id,
                                            recovery.reason,
                                        )

                                if not recovery_applied:
                                    await send_typed(post_run.no_result_error)
                                    continue

                            response_text = post_run.response_text
                            tokens_used = post_run.tokens_used
                            thinking_text = post_run.thinking_text

                            # Only send legacy 'response' if B1 streaming wasn't used
                            # B1 streaming already sent the content via assistant_message_end
                            logger.warning(
                                "[WebSocket] turn_state.b1_streaming_used=%s before response/extraction",
                                turn_state.b1_streaming_used,
                            )
                            if not turn_state.b1_streaming_used:
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

                                # Adapt complete non-streaming upstream responses into
                                # the streaming-only GUI protocol. Assistant text is no
                                # longer delivered via legacy `response.content`.
                                for frame in build_assistant_text_stream_frames(
                                    response_text=response_text,
                                    session_id=session_id,
                                    agent_name=agent.name if agent else "code-puppy",
                                    model_name=agent.get_model_name()
                                    if agent
                                    else "unknown",
                                    tokens=tokens_used,
                                ):
                                    await send_typed(frame)
                            else:
                                # B1 streaming: extract real tool results BEFORE stream_end
                                # so the frontend session store is still alive when they arrive.
                                _pre_sent_tool_ids = await emit_pre_stream_end_tool_results(
                                    result=result,
                                    turn_state=turn_state,
                                    session_id=session_id,
                                    agent_name=agent.name if agent else "code-puppy",
                                    model_name=agent.get_model_name()
                                    if agent
                                    else "unknown",
                                    send_typed_tool_lifecycle=send_typed_tool_lifecycle,
                                    logger=logger,
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
                            try:
                                finalized_turn = await finalize_turn_history(
                                    result=result,
                                    agent=agent,
                                    turn_state=turn_state,
                                    session_id=session_id,
                                    agent_name=agent.name if agent else "code-puppy",
                                    model_name=agent.get_model_name()
                                    if agent
                                    else "unknown",
                                    send_typed=send_typed,
                                    pre_sent_tool_ids=locals().get(
                                        "_pre_sent_tool_ids", set()
                                    ),
                                    logger=logger,
                                )

                                history = (
                                    finalized_turn.history_snapshot
                                    if finalized_turn.history_snapshot
                                    else agent.get_message_history()
                                )  # Use pre-await snapshot to avoid race condition
                                persisted_turn = await persist_session_turn_and_broadcast(
                                    history=history,
                                    session_id=session_id,
                                    session_title=session_title,
                                    session_working_directory=session_working_directory,
                                    session_pinned=session_pinned,
                                    agent=agent,
                                    agent_name=agent_name,
                                    model_name=model_name,
                                    ctx=ctx,
                                    original_user_message=original_user_message,
                                    attachment_metadata=attachment_metadata,
                                    safe_send_json=safe_send_json,
                                    logger_override=logger,
                                )
                                if persisted_turn is not None:
                                    session_title = persisted_turn.session_title
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
                        finally:
                            cleanup_message_context(
                                clear_session_working_directory=clear_session_working_directory
                            )

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
                    if sender.ws_closed:
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
            sender.ws_closed = True
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
                bus.mark_renderer_inactive()
            except Exception:
                pass
