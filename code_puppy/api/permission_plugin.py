"""
Permission Plugin for Tool Call Execution

This plugin registers callbacks that intercept tool executions
and request user permission via the WebSocket API.

It handles:
- All tool calls via pre_tool_call callback
- Shell commands via run_shell_command callback (for backward compatibility)

Permission is automatically granted in yolo mode.
For WebSocket mode (CLI web interface), permission is requested via UI.
For terminal mode, permission is bypassed to maintain backward compatibility.
"""

import logging
from contextvars import ContextVar
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Task-scoped WebSocket context — each asyncio task (i.e. each WS connection)
# gets its own isolated value via Python's ContextVar mechanism.
_ws_context: ContextVar[Optional[Tuple[Any, str]]] = ContextVar(
    "ws_permission_context", default=None
)

# Task-scoped flag used by chat websocket streaming to suppress duplicate
# tool_call/tool_result events from frontend_emitter pre/post_tool_call hooks.
_suppress_emitter_tool_events: ContextVar[bool] = ContextVar(
    "ws_suppress_emitter_tool_events", default=False
)


def set_websocket_context(websocket: Any, session_id: str) -> None:
    """Set the current WebSocket context for permission requests (task-scoped)."""
    _ws_context.set((websocket, session_id))
    logger.debug("[Permission] WebSocket context set for session %s", session_id)


def get_websocket_context() -> Optional[Tuple[Any, str]]:
    """Get the current WebSocket context. Returns ``(websocket, session_id)`` or ``None``."""
    return _ws_context.get()


def clear_websocket_context() -> None:
    """Clear the WebSocket context for the current task."""
    _ws_context.set(None)
    logger.debug("[Permission] WebSocket context cleared")


def set_suppress_emitter_tool_events(suppress: bool) -> None:
    """Enable/disable suppression of frontend_emitter tool lifecycle events."""
    _suppress_emitter_tool_events.set(bool(suppress))


def get_suppress_emitter_tool_events() -> bool:
    """Return True when frontend_emitter tool_call_start/complete should be skipped."""
    return _suppress_emitter_tool_events.get()


async def pre_tool_call_permission(
    tool_name: str, tool_args: dict, context: Any = None
) -> Optional[Dict[str, Any]]:
    """
    Permission callback for all tool executions via pre_tool_call.

    Args:
        tool_name: Name of the tool being called
        tool_args: Arguments for the tool
        context: Execution context

    Returns:
        None to allow the tool, or a dict with error info to block it
    """
    # Check if we have a WebSocket context (CLI web mode)
    ctx = get_websocket_context()
    if ctx is None:
        # Terminal mode or no WebSocket - allow tool
        logger.debug("[Permission] No WebSocket context, allowing tool: %s", tool_name)
        return None

    ws, sid = ctx

    # WebSocket mode - request permission
    logger.info("[Permission] Requesting permission for tool: %s", tool_name)

    try:
        from code_puppy.api.permissions import request_permission

        # Build human-readable description using formatters
        from code_puppy.api.tool_formatters import format_tool_call

        try:
            formatted_args = format_tool_call(tool_name, tool_args)
            description = formatted_args
        except Exception as e:
            # Fallback to raw args if formatting fails
            logger.warning("[Permission] Failed to format tool args: %s", e)
            description = f"Tool: {tool_name}"
            if tool_args:
                arg_preview = str(tool_args)[:200]
                if len(str(tool_args)) > 200:
                    arg_preview += "..."
                description = f"{description}\nArguments: {arg_preview}"

        approved = await request_permission(
            websocket=ws,
            session_id=sid,
            request_type="tool_call",
            title=f"Execute Tool: {tool_name}",
            description=description,
            details={
                "tool_name": tool_name,
                "tool_args": tool_args,
            },
            timeout=300,  # 5 minute timeout
        )

        if not approved:
            logger.info("[Permission] ❌ Tool DENIED: %s", tool_name)
            # Return error dict to block the tool execution
            return {
                "error": "Permission denied by user",
                "blocked": True,
                "tool_name": tool_name,
            }

        logger.info("[Permission] Tool APPROVED: %s", tool_name)
        return None  # Allow the tool

    except Exception as e:
        logger.error("[Permission] Error requesting permission: %s", e)
        return {
            "error": "Permission system error",
            "blocked": True,
            "tool_name": tool_name,
        }


async def shell_command_permission(
    context: Any, command: str, cwd: str, timeout: int
) -> Optional[Dict[str, Any]]:
    """
    Permission callback for shell command execution (legacy/backward compatibility).

    This is kept for backward compatibility but the main permission handling
    now happens via pre_tool_call_permission.

    Args:
        context: The execution context
        command: The shell command to execute
        cwd: Working directory
        timeout: Command timeout

    Returns:
        None to allow the command, or a dict with 'blocked': True to deny
    """
    # Check if we have a WebSocket context (CLI web mode)
    ctx = get_websocket_context()
    if ctx is None:
        # Terminal mode or no WebSocket - allow command
        logger.debug("[Permission] No WebSocket context, allowing command: %s", command)
        return None

    ws, sid = ctx

    # WebSocket mode - request permission
    logger.info("[Permission] Requesting permission for shell command: %s", command)

    try:
        from code_puppy.api.permissions import request_permission

        approved = await request_permission(
            websocket=ws,
            session_id=sid,
            request_type="shell_command",
            title="Execute Shell Command",
            description=f"Run: {command}",
            details={
                "command": command,
                "cwd": cwd or "current directory",
                "timeout": timeout,
            },
            timeout=300,  # 5 minute timeout
        )

        if not approved:
            logger.info("[Permission] Command DENIED: %s", command)
            return {
                "blocked": True,
                "error": "Permission denied by user",
                "reasoning": f"User denied execution of command: {command}",
            }

        logger.info("[Permission] Command APPROVED: %s", command)
        return None  # Allow the command

    except Exception as e:
        logger.error("[Permission] Error requesting permission for command: %s", e)
        return {
            "blocked": True,
            "error": "Permission system error",
            "reasoning": f"Permission request failed for command: {command}",
        }


def register_permission_callbacks():
    """Register the permission callbacks with code-puppy."""
    from code_puppy.callbacks import register_callback

    # Register for all tool calls
    register_callback("pre_tool_call", pre_tool_call_permission)
    logger.info("[Permission Plugin] Registered pre_tool_call permission callback")

    # Keep shell command callback for backward compatibility
    register_callback("run_shell_command", shell_command_permission)
    logger.info("[Permission Plugin] Registered shell command permission callback")


# Auto-register when imported
register_permission_callbacks()
