"""Retriever — surfaces learned memory into the system prompt.

Fires on ``load_prompt``. Builds a banded recall block:

* ``## Remembered (current)`` — the authoritative durable facts/prefs, sorted
  by importance. A superseded value is absent here (it was ``correct()``-ed).
* ``## Relevant history`` — query-relevant episodic context, only included when
  a ``user_prompt`` is supplied (e.g. an explicit recall call).

Returns ``None`` when disabled, when YantrikDB is unavailable, or when there's
nothing worth surfacing. Fail-soft — any exception returns ``None`` so the host
prompt is never broken.
"""

from __future__ import annotations

from . import substrate
from .config import DB_PATH, HISTORY_TOP_K, PREFS_BAND_SIZE, YANTRIK_MEM_ROOT
from .state import is_enabled

_EMPTY_RETURN = None  # Returning None tells the callback system "skip me."


def _text_of(m: dict) -> str:
    return str((m or {}).get("text", "")).strip()


def build_recall_block(user_prompt: str | None = None) -> str | None:
    """Return a system-prompt fragment from banded recall, or ``None``."""
    if not is_enabled():
        return _EMPTY_RETURN
    if not substrate.MEMORY_AVAILABLE:
        return _EMPTY_RETURN

    mem = None
    try:
        YANTRIK_MEM_ROOT.mkdir(parents=True, exist_ok=True)
        ns = substrate.namespace_for_cwd()
        mem = substrate.Memory(str(DB_PATH), namespace=ns)

        # A query is needed for the history band; for a passive load_prompt with
        # no prompt we still surface the always-on "current" prefs band.
        query = (user_prompt or "").strip()
        current = mem.prefs(PREFS_BAND_SIZE)
        history = []
        if query:
            cur_keys = {(m or {}).get("rid") for m in current}
            history = [
                m
                for m in mem.recall(query, HISTORY_TOP_K)
                if (m or {}).get("rid") not in cur_keys
            ]

        cur_lines = [t for t in (_text_of(m) for m in current) if t]
        if not cur_lines and not history:
            return _EMPTY_RETURN

        sections: list[str] = []
        if cur_lines:
            body = "\n".join(f"- {t}" for t in cur_lines)
            sections.append("## Remembered (current)\n" + body)

        if query:
            hist_lines = [t for t in (_text_of(m) for m in history) if t]
            if hist_lines:
                body = "\n".join(f"- {t}" for t in hist_lines)
                sections.append("## Relevant history\n" + body)

        if not sections:
            return _EMPTY_RETURN
        return "\n\n".join(sections)
    except Exception:
        return _EMPTY_RETURN
    finally:
        if mem is not None:
            mem.close()
