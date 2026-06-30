"""Helpers for WebSocket chat execution context setup/reset.

These helpers centralize per-message and per-agent-run ContextVar management so
chat_handler can delegate setup/cleanup without changing behavior.
"""

from dataclasses import dataclass
from typing import Callable

from code_puppy.api.permission_plugin import (
    clear_websocket_context,
    set_suppress_emitter_tool_events,
    set_websocket_context,
)


@dataclass(slots=True)
class WebSocketRunContext:
    """State needed to clean up one run_with_mcp execution window."""

    emitter_token: object | None = None


def setup_message_context(*, websocket: object, session_id: str) -> None:
    """Set per-message websocket permission context."""
    set_websocket_context(websocket, session_id)


def cleanup_message_context(
    *, clear_session_working_directory: Callable[[], None]
) -> None:
    """Clear per-message websocket/prompt-generation context."""
    clear_websocket_context()
    clear_session_working_directory()


def begin_agent_run_context(*, session_id: str) -> WebSocketRunContext:
    """Enable emitter tagging + tool lifecycle suppression for one agent run."""
    emitter_token = None
    try:
        from code_puppy.plugins.frontend_emitter.session_context import (
            current_emitter_session_id,
        )

        emitter_token = current_emitter_session_id.set(session_id)
    except ImportError:
        emitter_token = None

    set_suppress_emitter_tool_events(True)
    return WebSocketRunContext(emitter_token=emitter_token)


def cleanup_agent_run_context(
    run_context: WebSocketRunContext | None,
    *,
    clear_session_working_directory: Callable[[], None],
) -> None:
    """Reset all ContextVars touched during one agent run window."""
    set_suppress_emitter_tool_events(False)
    if run_context is not None and run_context.emitter_token is not None:
        try:
            from code_puppy.plugins.frontend_emitter.session_context import (
                current_emitter_session_id,
            )

            current_emitter_session_id.reset(run_context.emitter_token)
        except ImportError:
            pass

    cleanup_message_context(
        clear_session_working_directory=clear_session_working_directory
    )
