"""ACP permission integration — the client's dialog becomes the approval authority.

Code Puppy has two approval edges, and this module wires both to the client via the
SDK's ``AgentSideConnection.request_permission`` — without touching core tool
logic or forcing yolo mode:

* **File operations** go through the pluggable *approval backend* seam in
  ``code_puppy.tools.common``. Sync file tools run in Code Puppy's tool
  threadpool, so the backend bridges to the ACP event loop via
  ``run_coroutine_threadsafe`` to ask the client, then blocks the worker thread for
  the answer. The loop stays free to service the round-trip — no deadlock.
* **Shell commands** go through the ``run_shell_command`` hook, which is async
  and already runs on the ACP loop, so it can ``await`` the client directly.

Both edges fail **closed** (deny) if the connection is gone or the client errors.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional, Tuple

from acp.schema import PermissionOption, ToolCallUpdate

from code_puppy.callbacks import register_callback
from code_puppy.plugins.acp import state

logger = logging.getLogger(__name__)

# How long to wait for a human in the client to answer a permission dialog. Dialogs
# can sit for a while; deny (fail closed) if it's truly abandoned.
_PERMISSION_TIMEOUT_S = 600

# The allow/deny options we present. The client echoes back the chosen ``option_id``.
_OPTIONS = [
    PermissionOption(option_id="allow_once", name="Allow", kind="allow_once"),
    PermissionOption(option_id="reject_once", name="Reject", kind="reject_once"),
]
_ALLOW_IDS = {"allow_once"}


def _tool_call_ref(title: str) -> ToolCallUpdate:
    """Build the ``toolCall`` ref a permission request attaches to.

    Reuses the id/title of the tool call currently open (set by
    ``pre_tool_call``) so the client pins the dialog to the right agent-panel entry;
    falls back to a standalone id when no tool call is active.
    """
    current = state.current_tool_call()
    if current is not None:
        name, tool_call_id = current
        return ToolCallUpdate(tool_call_id=tool_call_id, title=name)
    return ToolCallUpdate(tool_call_id=f"perm_{uuid.uuid4().hex[:12]}", title=title)


async def _ask_client(session_id: str, title: str) -> bool:
    """Show an allow/deny dialog in the client; return ``True`` if allowed."""
    connection = state.get_connection()
    if connection is None:
        return False
    try:
        response = await connection.request_permission(
            options=list(_OPTIONS),
            session_id=session_id,
            tool_call=_tool_call_ref(title),
        )
    except Exception:  # noqa: BLE001
        logger.exception("session/request_permission failed; denying")
        return False
    outcome = getattr(response, "outcome", None)
    if getattr(outcome, "outcome", None) == "selected":
        return getattr(outcome, "option_id", None) in _ALLOW_IDS
    return False


def _approval_backend(
    title: str, message: str, preview: Optional[str]
) -> Tuple[bool, Optional[str]]:
    """Approval backend for file ops; asks the client from the tool threadpool.

    Returns ``(approved, feedback)``. Feedback is always ``None`` — the client's
    dialog is yes/no, not a free-text channel.
    """
    loop = state.get_loop()
    session_id = state.get_active_session_id()
    if loop is None or session_id is None:
        return False, None

    # Guard against being called on the loop thread itself: blocking on
    # run_coroutine_threadsafe there would deadlock. File tools run off-loop,
    # so this is belt-and-suspenders.
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is loop:
        logger.error("Approval backend hit on the ACP loop; denying to avoid deadlock")
        return False, None

    future = asyncio.run_coroutine_threadsafe(_ask_client(session_id, title), loop)
    try:
        allowed = future.result(_PERMISSION_TIMEOUT_S)
    except Exception:  # noqa: BLE001 - includes TimeoutError
        # Abandon the in-flight request so it doesn't linger on the loop.
        future.cancel()
        logger.exception("ACP approval bridge failed; denying")
        return False, None
    return bool(allowed), None


async def _on_run_shell_command(
    context: Any, command: str, cwd: Optional[str] = None, timeout: int = 60
) -> Optional[Dict[str, Any]]:
    """``run_shell_command`` hook: gate shell execution through the client.

    Returns ``None`` to allow (the hook's "no objection"), or a
    ``{"blocked": True, ...}`` dict to deny. Inert outside ACP mode.

    Honors yolo mode: when the user has opted out of approvals we do *not*
    surface a client dialog, matching Code Puppy's file-permission edge (which
    skips its prompt in yolo mode). Otherwise ACP + yolo would silently
    auto-approve file writes yet still prompt for every shell command.
    """
    session_id = state.get_active_session_id()
    if state.get_connection() is None or session_id is None:
        return None
    from code_puppy.config import get_yolo_mode

    if get_yolo_mode():
        return None
    allowed = await _ask_client(session_id, f"Run shell command: {command}")
    if allowed:
        return None
    return {
        "blocked": True,
        "error_message": "Command rejected in the client",
        "reasoning": "The user denied this shell command in the client's permission dialog.",
    }


def install() -> None:
    """Install the file approval backend + the shell permission hook."""
    from code_puppy.tools.common import set_approval_backend

    set_approval_backend(_approval_backend)
    register_callback("run_shell_command", _on_run_shell_command)


def uninstall() -> None:
    """Remove the approval backend + shell hook so normal stdin prompting resumes."""
    from code_puppy.callbacks import unregister_callback
    from code_puppy.tools.common import set_approval_backend

    set_approval_backend(None)
    try:
        unregister_callback("run_shell_command", _on_run_shell_command)
    except Exception:  # noqa: BLE001
        logger.debug("ACP: run_shell_command unregister failed", exc_info=True)
