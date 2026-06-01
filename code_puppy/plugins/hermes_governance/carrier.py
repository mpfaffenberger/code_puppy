"""Governance state that rides *inside* the conversation history.

The problem: governance counters kept in module globals are lost on restart
and on ``--resume`` (which only restores ``agent._message_history``), and have
no relationship to context compaction.

The fix: store the state in a single synthetic **carrier message** embedded in
``agent._message_history``. Because it lives in the history list it is:

* pickled with the session (autosave) and restored on resume,
* re-pinned into the protected tail every model call (via a history processor
  attached through the ``wrap_pydantic_agent`` hook), so context compaction
  never summarises it away.

This mirrors how Hermes persists durable memory (re-injected each turn) rather
than holding it in process memory.

Carrier format: a ``ModelRequest`` whose single ``UserPromptPart`` content is::

    <<<HERMES_GOVERNANCE_STATE>>>{json}<<<END>>>

The sentinels let us find and update the carrier in O(n) without confusing it
with real user input, and keep it human-readable in session dumps.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_BEGIN = "<<<HERMES_GOVERNANCE_STATE>>>"
_END = "<<<END_HERMES_GOVERNANCE_STATE>>>"

# Default state shape. ``skill_usage`` maps skill name -> ISO timestamp of last
# activation, consumed by the curator for lifecycle transitions.
_DEFAULT_STATE: Dict[str, Any] = {
    "used": 0,
    "unlocked": False,
    "calls_since_skill": 0,
    "acting_since_skill": 0,
    "skill_usage": {},
}


def default_state() -> Dict[str, Any]:
    return json.loads(json.dumps(_DEFAULT_STATE))


def _encode(state: Dict[str, Any]) -> str:
    return f"{_BEGIN}{json.dumps(state, separators=(',', ':'))}{_END}"


def _decode(text: str) -> Optional[Dict[str, Any]]:
    if _BEGIN not in text or _END not in text:
        return None
    try:
        raw = text[text.index(_BEGIN) + len(_BEGIN) : text.index(_END)]
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        # Validate this is genuinely our governance state, not an accidental
        # echo of the sentinels by the model. Require the core numeric/bool
        # fields with the right types; a prose paragraph that happens to contain
        # the sentinels won't satisfy this.
        if not _looks_like_state(data):
            return None
        # Merge onto defaults so older carriers gain new keys gracefully.
        merged = default_state()
        merged.update(data)
        return merged
    except (ValueError, json.JSONDecodeError):
        return None


def _looks_like_state(data: Dict[str, Any]) -> bool:
    """True only if ``data`` has the shape of a real governance-state payload."""
    if not isinstance(data.get("used"), int):
        return False
    if not isinstance(data.get("unlocked"), bool):
        return False
    return True


def _part_text(part: Any) -> str:
    content = getattr(part, "content", None)
    return content if isinstance(content, str) else ""


def _is_carrier_part(part: Any) -> bool:
    return _BEGIN in _part_text(part)


def find_state(history: List[Any]) -> Optional[Dict[str, Any]]:
    """Return the decoded state from the freshest valid carrier, or None.

    Iterates newest-first and validates payload shape, so (a) an accidental
    model echo of the sentinels is rejected by :func:`_looks_like_state`, and
    (b) if multiple carriers somehow coexist we trust the most recent one
    (``write_state`` always pins exactly one at the tail).
    """
    for msg in reversed(history):
        for part in getattr(msg, "parts", []) or []:
            if _is_carrier_part(part):
                decoded = _decode(_part_text(part))
                if decoded is not None:
                    return decoded
    return None


def _build_carrier_part(state: Dict[str, Any]) -> Any:
    from pydantic_ai.messages import UserPromptPart

    return UserPromptPart(content=_encode(state))


def _build_carrier_message(state: Dict[str, Any]) -> Any:
    from pydantic_ai.messages import ModelRequest

    return ModelRequest(parts=[_build_carrier_part(state)])


def _is_model_request(msg: Any) -> bool:
    """True if ``msg`` is a pydantic-ai ``ModelRequest`` (a user turn).

    We do a duck-typed check (cls name) plus a fallback isinstance so this
    works even if pydantic-ai's import path changes.
    """
    cls = type(msg).__name__
    if cls == "ModelRequest":
        return True
    try:
        from pydantic_ai.messages import ModelRequest  # local import

        return isinstance(msg, ModelRequest)
    except Exception:
        return False


def _strip_carriers(history: List[Any]) -> List[Any]:
    """Return history with any existing carrier messages removed.

    Never mutates the input message objects in place — mutating ``msg.parts``
    can corrupt other history processors or callers that assume message
    immutability. When a message has both carrier and non-carrier parts we emit
    a shallow *copy* with the carrier part filtered out, leaving the original
    untouched.
    """
    import copy as _copy

    kept: List[Any] = []
    for msg in history:
        parts = getattr(msg, "parts", None)
        if parts and any(_is_carrier_part(p) for p in parts):
            non_carrier = [p for p in parts if not _is_carrier_part(p)]
            if not non_carrier:
                # Whole message was just the carrier — drop it entirely.
                continue
            try:
                clone = _copy.copy(msg)
                clone.parts = non_carrier
                kept.append(clone)
                continue
            except Exception:
                # If we can't safely clone, keep the original as-is rather than
                # mutate it. A stray carrier part is harmless (find_state still
                # returns the freshest one); corrupting shared state is not.
                kept.append(msg)
                continue
        kept.append(msg)
    return kept


def write_state(history: List[Any], state: Dict[str, Any]) -> List[Any]:
    """Return a new history list with exactly one up-to-date carrier pinned last.

    The carrier is **merged into the last existing ``ModelRequest``** (user
    turn) as an additional ``UserPromptPart`` whenever possible. Why: appending
    a standalone ``ModelRequest`` produces two consecutive user messages in the
    wire body (the real user turn + the carrier), which Claude Code OAuth's
    endpoint silently stalls on — the actual root cause of the hermes +
    claude-code-oauth hang.

    Only when there's no existing ``ModelRequest`` to ride along with (e.g.
    a freshly constructed agent with no user input yet) do we append a
    standalone carrier message. That edge case is rare and harmless: the
    consecutive-user issue only matters once a real user message is present.

    Removing any stale carrier first guarantees a single source of truth and
    keeps it in the protected tail (most-recent messages survive compaction).
    """
    cleaned = _strip_carriers(list(history))
    carrier_part = _build_carrier_part(state)

    # Find the last ModelRequest and attach the carrier as an extra part.
    for idx in range(len(cleaned) - 1, -1, -1):
        msg = cleaned[idx]
        if _is_model_request(msg):
            try:
                msg.parts = list(getattr(msg, "parts", []) or []) + [carrier_part]
                return cleaned
            except Exception:
                # Fall through to the append path below if we can't mutate.
                break

    # No user turn to ride along with — fall back to a standalone carrier.
    cleaned.append(_build_carrier_message(state))
    return cleaned


def read_or_init(history: List[Any]) -> Dict[str, Any]:
    """Read the carrier state, falling back to a fresh default."""
    state = find_state(history)
    return state if state is not None else default_state()
