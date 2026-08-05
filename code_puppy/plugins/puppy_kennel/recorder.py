"""Recorder — captures agent runs into the kennel.

Fires on ``agent_run_end``. The recorder writes the agent's response to
**one** wing: the current repo wing. The autosave path treats every
response as "a conversation that happened in this project" — that's the
honest framing.

Cross-project agent reflections belong in ``agent:<name>`` and are an
opt-in concern handled by the ``kennel_remember`` tool, not autosave.
User preferences likewise live in ``user:default`` and only land there
via explicit ``kennel_remember`` calls.

Capturing user input is a phase-2 concern that will hook ``stream_event``
instead.
"""

from __future__ import annotations

import re
from typing import Any

from code_puppy.messaging.bus import emit_debug

from . import kennel
from .config import STRIP_NOISE
from .state import is_enabled
from .wings import detect_cwd, repo_wing

# Lines entirely wrapped in *...* (not **...**) are personality emotes:
#   *wags tail excitedly*,  *zooms around happily*,  *woof woof*
# Bold (**...**), bullet points (* item), and inline italics mid-sentence
# are all unaffected because they don't match this pattern.
_EMOTE_LINE_RE = re.compile(r"^\s*\*(?!\*)[^*\n]+\*\s*$")


def _strip_noise(text: str) -> str:
    """Remove personality emote lines from a response before kennel storage.

    Processes line-by-line so code-fence content is never touched, even if
    a fence happens to contain a line that looks like *emote*.
    """
    in_fence = False
    out: list[str] = []
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and _EMOTE_LINE_RE.match(line):
            continue
        out.append(line)
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return cleaned.strip()


def _room_name(session_id: str | None) -> str:
    """Rooms partition a wing by session. Keep the name human-scannable."""
    if not session_id:
        return "session-unknown"
    short = session_id.split("-")[0][:12] if "-" in session_id else session_id[:12]
    return f"session-{short}"


def record_run_end(
    agent_name: str,
    model_name: str,
    session_id: str | None = None,
    success: bool = True,
    error: Exception | None = None,
    response_text: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Persist the agent's final response into the kennel.

    Writes a single drawer to the repo wing (shared project memory).
    Failures here must never crash the host app — the kennel is best-
    effort memory, not a transactional system of record.
    """
    if STRIP_NOISE and response_text:
        response_text = _strip_noise(response_text)
    if not response_text or not response_text.strip():
        return
    if not success:
        # Don't memorialize broken runs. The error log is the right place.
        return
    if not is_enabled():
        # Memory is toggled off — silently skip. Slash commands surface state.
        return

    try:
        cwd = detect_cwd()
        room = _room_name(session_id)
        drawer_meta: dict[str, Any] = {
            "agent": agent_name,
            "model": model_name,
            "cwd": str(cwd),
        }
        if metadata:
            drawer_meta["run_metadata"] = metadata

        # Shared project memory — the only autosave destination.
        repo_w = repo_wing(cwd)
        repo_wing_id = kennel.ensure_wing(repo_w)
        repo_room_id = kennel.ensure_room(repo_wing_id, room)
        kennel.add_drawer(
            repo_room_id,
            content=response_text,
            role="assistant",
            session_id=session_id,
            metadata=drawer_meta,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort memory.
        emit_debug(f"[puppy_kennel] recorder skipped: {exc!r}")
