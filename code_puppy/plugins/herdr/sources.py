"""Fail-soft adapters from code-puppy internals to herdr report payloads.

This is the single seam between the herdr plugin and the rest of
code-puppy. Every function here catches ordinary runtime failures, logs at
debug level, and returns a safe fallback -- reporting to herdr must never
be able to disturb the agent. Reporter/client code depends only on this
module's return shapes, and its tests mock this module.

Three adapters:

* :func:`current_tokens_payload` -- a static-keyed, string-valued map of
  ``model`` / ``context`` / ``tokens`` for ``pane.report_metadata``.
* :func:`current_session_ref` -- a stable ``(session_id, session_path)``
  reference for ``pane.report_agent_session``.
* :func:`activity_message` -- a short human-readable activity string for
  the decorative ``message`` field on ``pane.report_agent``.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

#: herdr caps metadata values; keep every value comfortably short.
_MAX_VALUE_LEN = 128


def _compact_tokens(n: int) -> str:
    """Render a token count compactly: 999 -> ``999``; 48200 -> ``48k``."""
    n = int(n)
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n // 1000}k"
    return f"{n // 1_000_000}M"


def _clip(value: object) -> str:
    """Coerce to a string and cap length so a payload can't balloon."""
    text = str(value)
    return text[:_MAX_VALUE_LEN]


def _current_model() -> Optional[str]:
    try:
        from code_puppy.agents.agent_manager import get_current_agent

        agent = get_current_agent()
        if agent is None:
            return None
        return agent.get_model_name()
    except Exception:
        logger.debug("herdr: could not resolve current model", exc_info=True)
        return None


def current_tokens_payload() -> Optional[Dict[str, str]]:
    """Return a static-keyed metadata map, or ``None`` when unavailable.

    Keys are always ``model``, ``context``, and ``tokens``; values are
    coerced to strings and clipped. Indicator glyphs are omitted on purpose
    -- herdr rows already carry their own state icons. Returns ``None`` if
    context usage can't be computed so the pane keeps its last good values
    (which the metadata TTL eventually clears).
    """
    try:
        from code_puppy.token_usage import get_current_usage

        usage = get_current_usage()
        if usage is None:
            return None
        payload: Dict[str, str] = {
            "context": _clip(f"{round(usage.percent)}%"),
            "tokens": _clip(
                f"{_compact_tokens(usage.total_tokens)}/{_compact_tokens(usage.capacity)}"
            ),
        }
        model = _current_model()
        if model:
            payload["model"] = _clip(model)
        return payload
    except Exception:
        logger.debug("herdr: token payload unavailable", exc_info=True)
        return None


def current_session_ref() -> Optional[Tuple[str, str]]:
    """Return ``(session_id, session_path)`` for the process's autosave.

    The name is stable for the life of a session (until ``/clear``,
    ``/session new``, resume, load, or rotation), and the pickle path stays
    canonical because the CLI pins the resolved stem and writes later saves
    to ``AUTOSAVE_DIR``. Returns ``None`` on any failure.
    """
    try:
        from pathlib import Path

        from code_puppy.config import AUTOSAVE_DIR, get_current_session_name
        from code_puppy.session_storage import build_session_paths

        name = get_current_session_name()
        if not name:
            return None
        paths = build_session_paths(Path(AUTOSAVE_DIR), name)
        return name, str(paths.pickle_path)
    except Exception:
        logger.debug("herdr: session ref unavailable", exc_info=True)
        return None


def activity_message(tool_name: str) -> str:
    """Return a short activity string for a starting tool call.

    ``read_file`` -> ``running read file``. Fail-soft: an odd or missing
    name degrades to a generic ``running tool``.
    """
    try:
        humanized = str(tool_name).replace("_", " ").strip()
        if not humanized:
            return "running tool"
        return f"running {humanized}"
    except Exception:
        logger.debug("herdr: could not humanize tool name", exc_info=True)
        return "running tool"


__all__ = [
    "current_tokens_payload",
    "current_session_ref",
    "activity_message",
]
