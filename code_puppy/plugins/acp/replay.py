"""Replay a rehydrated session's history back to the client on load/resume.

The ACP ``session/load`` (and ``session/resume``) contract is not just "rebuild
the agent's memory" -- the client rebuilds its *own* thread UI from the
``session/update`` notifications the agent streams while handling the request.
An agent that only rehydrates its internal ``_message_history`` (and streams
nothing) leaves the client with an empty thread: the conversation looks gone,
and clients that treat an empty replayed thread as dead will discard it
outright.

So on load/resume we walk the rehydrated pydantic-ai message history and emit
one ``session/update`` per visible turn -- user prompts, assistant text,
assistant thinking, and past tool calls (as already-``completed`` entries) --
in order, before the load response returns. System prompts and tool-return
plumbing are intentionally skipped: they are model-plumbing, not conversation
the user needs to see re-rendered.

Everything here is best-effort: a replay hiccup must never fail the load, so
per-update send failures are logged and swallowed.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Iterable, List

from acp.helpers import (
    start_tool_call,
    update_agent_message_text,
    update_agent_thought_text,
    update_user_message_text,
)

from code_puppy.plugins.acp import state

logger = logging.getLogger(__name__)


async def replay_history(session_id: str, history: Iterable[Any]) -> None:
    """Stream ``history`` back to the client as ordered ``session/update``s.

    No-op when there is no connection or nothing to replay.
    """
    connection = state.get_connection()
    if connection is None:
        return
    for message in history or []:
        for update in _updates_for_message(message):
            try:
                await connection.session_update(session_id, update)
            except Exception:  # noqa: BLE001
                logger.debug("ACP: history replay update failed", exc_info=True)


def _updates_for_message(message: Any) -> List[Any]:
    """Map one pydantic-ai message to zero or more ACP updates.

    Discriminates on each part's ``part_kind`` (stable across pydantic-ai
    versions) rather than importing concrete part classes, so a version bump
    that renames a class doesn't silently drop history.
    """
    updates: List[Any] = []
    for part in getattr(message, "parts", None) or []:
        kind = getattr(part, "part_kind", None)
        if kind == "user-prompt":
            text = _text_of(getattr(part, "content", None))
            if text:
                updates.append(update_user_message_text(text))
        elif kind == "text":
            text = _text_of(getattr(part, "content", None))
            if text:
                updates.append(update_agent_message_text(text))
        elif kind == "thinking":
            text = _text_of(getattr(part, "content", None))
            if text:
                updates.append(update_agent_thought_text(text))
        elif kind == "tool-call":
            updates.append(_tool_call_update(part))
        # system-prompt / tool-return: model plumbing, not replayed.
    return updates


def _tool_call_update(part: Any) -> Any:
    """Render a past tool call as an already-``completed`` tool-call entry.

    Replayed tool calls are historical, so they open and close in one update
    (status ``completed``). A fresh id is minted -- the original call id isn't
    needed since nothing will update this entry again.
    """
    tool_name = str(getattr(part, "tool_name", "") or "tool")
    return start_tool_call(
        f"tc_{uuid.uuid4().hex[:12]}",
        tool_name,
        kind="other",
        status="completed",
    )


def _text_of(content: Any) -> str:
    """Flatten a part's content to plain text.

    Handles the string case and pydantic-ai's multimodal list form (where a
    user prompt is a list of str + binary/image blocks): string items are
    kept, non-text blocks are dropped, since replay is a text reconstruction.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, (list, tuple)):
        parts = [item for item in content if isinstance(item, str)]
        return "\n".join(p for p in parts if p).strip()
    return str(content).strip()
