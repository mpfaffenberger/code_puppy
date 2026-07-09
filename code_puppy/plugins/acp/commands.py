"""Execute client-typed slash commands headless and return their output.

The advertised ``available_commands_update`` tells the client which ``/commands``
Code Puppy exposes; when the user picks one, the client sends it as a prompt.
Rather than feed ``/help`` to the model, we route it through Code Puppy's
``command_handler`` and forward whatever it emits on the message bus back as an
``agent_message_chunk``.

Command side-effects go to the ``MessageBus`` (``emit_info`` etc.), which has no
renderer in ACP mode. We capture that output by attaching a listener + draining
the queue around the call. We deliberately do **not** touch ``sys.stdin`` — the
SDK reads the JSON-RPC pipe from it — so interactive prompt_toolkit menus (a TUI
affordance) simply aren't driven over ACP; non-interactive commands (``/help``,
status-style commands) work well. Everything is best-effort and never raises
into the turn.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Optional

from code_puppy.plugins.acp import state

logger = logging.getLogger(__name__)


def is_command(text: str) -> bool:
    """True if ``text`` is a leading ``/slash`` command."""
    return text.strip().startswith("/")


async def run(session_id: str, command: str) -> Optional[str]:
    """Execute ``command`` and forward its bus output to the client.

    Returns ``None`` when the command was fully handled (its output has been
    forwarded to the client). Returns a **string** when the command handler
    signalled "process this as user input" -- i.e. a custom/markdown command
    that expands into a prompt for the model. The caller then runs the agent on
    that string, exactly as ``cli_runner`` does with a string command result.
    Internal ``__SENTINEL__`` strings (e.g. ``__AUTOSAVE_LOAD__``) are TUI-only
    affordances with no ACP meaning, so they are treated as handled, not modelled.
    """
    from code_puppy.command_line.command_handler import handle_command
    from code_puppy.messaging.message_queue import get_global_queue

    queue = get_global_queue()
    collected: List[Any] = []

    def _listener(message: Any) -> None:
        collected.append(message)

    queue.add_listener(_listener)
    result: Any = None
    try:
        result = await asyncio.to_thread(handle_command, command.strip())
    except Exception:  # noqa: BLE001
        logger.debug("ACP: slash command failed", exc_info=True)
    finally:
        # Drain anything still queued (no renderer thread runs in ACP mode).
        while True:
            message = queue.get_nowait()
            if message is None:
                break
            collected.append(message)
        queue.remove_listener(_listener)

    text = _render(collected)
    if _is_prompt_expansion(result):
        # Handler expanded the command into a prompt for the model. Surface any
        # incidental bus output first, then hand the prompt back to the caller
        # to run through the agent (not display it as a canned answer).
        if text:
            await _emit(session_id, text)
        return result.strip()
    await _emit(session_id, text or f"Ran `{command.strip()}`.")
    return None


def _is_prompt_expansion(result: Any) -> bool:
    """True if ``handle_command`` returned a string to be modelled as a prompt.

    A non-empty string means "process as user input"; ``__SENTINEL__`` strings
    are internal TUI markers (e.g. ``__AUTOSAVE_LOAD__``) that must not reach
    the model.
    """
    if not isinstance(result, str):
        return False
    stripped = result.strip()
    if not stripped:
        return False
    return not (stripped.startswith("__") and stripped.endswith("__"))


def _render(messages: List[Any]) -> str:
    """Flatten captured bus messages into display text."""
    out: List[str] = []
    for message in messages:
        content = getattr(message, "content", None)
        if content is None:
            continue
        out.append(content if isinstance(content, str) else str(content))
    return "\n".join(s for s in out if s).strip()


async def _emit(session_id: str, text: str) -> None:
    from acp.helpers import update_agent_message_text

    connection = state.get_connection()
    if connection is None or not text:
        return
    try:
        await connection.session_update(session_id, update_agent_message_text(text))
    except Exception:  # noqa: BLE001
        logger.debug("ACP: command output emit failed", exc_info=True)
