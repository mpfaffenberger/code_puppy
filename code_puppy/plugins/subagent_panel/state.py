"""Thread-safe registry of active sub-agents + status derivation.

The puppy spinner repaints from a background thread ~20x/second, so all reads
here must be cheap and lock-guarded.

Registration is driven by the sub-agent INVOCATION banner (which carries the
exact name, session_type, model AND session_id), so attribution is exact even
for parallel sub-agents -- no FIFO guessing, no session-id parsing. Status
updates (``record_event``) are UPDATE-ONLY: an event for an unregistered
session is ignored, which cleanly filters out the MAIN agent's own stream
events (the main agent is never registered).
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Optional

# session_id -> {session_id, parent, name, model, status, start, last_seen}
_AGENTS: "Dict[str, Dict[str, Any]]" = {}
_LOCK = threading.RLock()

# --- tunables (env-overridable) -------------------------------------------
MAX_ROWS = int(os.environ.get("SUBAGENT_PANEL_MAX_ROWS", "24"))
IDLE_PRUNE_S = float(os.environ.get("SUBAGENT_PANEL_IDLE_S", "600"))

# Single-char braille spinner frames (defined via escapes to keep the source
# emoji-free; braille isn't emoji but escapes dodge any filter ambiguity).
SPINNER_FRAMES = [
    "\u280b",
    "\u2819",
    "\u2839",
    "\u2838",
    "\u283c",
    "\u2834",
    "\u2826",
    "\u2827",
    "\u2807",
    "\u280f",
]


# ---------------------------------------------------------------------------
# Registration / teardown (driven by the invocation + response banners)
# ---------------------------------------------------------------------------
def register(
    session_id: Optional[str],
    name: str,
    model: Optional[str] = None,
    parent: Optional[str] = None,
) -> None:
    if not session_id:
        return
    now = time.time()
    with _LOCK:
        # Re-invocation of an existing session: keep its original start time.
        existing = _AGENTS.get(session_id)
        _AGENTS[session_id] = {
            "session_id": session_id,
            "parent": parent,
            "name": name,
            "model": model,
            "status": "starting",
            "start": existing["start"] if existing else now,
            "last_seen": now,
        }


def finish(session_id: Optional[str]) -> None:
    if not session_id:
        return
    with _LOCK:
        _AGENTS.pop(session_id, None)


def mark_done(session_id: Optional[str]) -> None:
    """Mark a sub-agent completed but KEEP it in the live tree (frozen) until its
    root flushes. This avoids the vanish-then-reappear gap that happens if a
    nested child is popped the instant it finishes while its parent runs on."""
    if not session_id:
        return
    now = time.time()
    with _LOCK:
        entry = _AGENTS.get(session_id)
        if entry is None:
            return
        entry["done"] = True
        entry["status"] = "completed"
        entry["end"] = now
        entry["last_seen"] = now


def mark_failed(session_id: Optional[str]) -> None:
    """Mark a sub-agent FAILED (errored after exhausting retries) but KEEP it in
    the live tree until its root flushes -- same lifecycle as mark_done, but the
    renderer paints it red 'failed' with an X instead of green 'completed'."""
    if not session_id:
        return
    now = time.time()
    with _LOCK:
        entry = _AGENTS.get(session_id)
        if entry is None:
            return
        entry["done"] = True
        entry["failed"] = True
        entry["status"] = "failed"
        entry["end"] = now
        entry["last_seen"] = now


def clear() -> None:
    """Drop ALL tracked sub-agents. Called when the top-level turn ends so a
    root that errored/was cancelled (and thus never flushed) can't leak its
    'completed' children into the next prompt's live block."""
    with _LOCK:
        _AGENTS.clear()


# ---------------------------------------------------------------------------
# Live status (driven by stream_event) -- UPDATE ONLY
# ---------------------------------------------------------------------------
def record_event(session_id: Optional[str], event_type: str, event_data: Any) -> None:
    if not session_id:
        return
    status = _derive_status(event_type, event_data)
    now = time.time()
    with _LOCK:
        entry = _AGENTS.get(session_id)
        if entry is None:
            return  # not a registered sub-agent (e.g. the main agent) -> ignore
        entry["last_seen"] = now
        if status:
            entry["status"] = status


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def snapshot() -> List[Dict[str, Any]]:
    """Return active sub-agents (oldest first), pruning idle/stale ones.

    DONE entries are never pruned by idle -- they stay in the live tree (shown
    as 'completed') until their root flushes them, so a finished child never
    vanishes mid-run.

    PARENTS are never idle-pruned either: a parent that has invoked children and
    is merely AWAITING them emits no stream events of its own, so its last_seen
    goes stale -- but it is busy, not idle. Pruning it would orphan its whole
    subtree, making the children re-render as depth-0 roots. So only childless,
    not-done, genuinely-stale leaves are eligible. End-of-turn state.clear() is
    the real cleanup for anything that errors/cancels without flushing.
    """
    now = time.time()
    with _LOCK:
        ids = set(_AGENTS)
        # session_ids still referenced as someone's parent == busy (awaiting kids).
        busy_parents = {e.get("parent") for e in _AGENTS.values() if e.get("parent")}
        # Only prune entries DISCONNECTED from the live tree: not a parent of
        # anything AND whose own parent is gone (or is 'main', i.e. a root).
        # Anything still wired into a tree (busy parents + their descendants)
        # is kept until flush/turn-end, so a quiet-but-running node (e.g. a leaf
        # mid `sleep`) never vanishes and never orphans its siblings.
        stale = [
            s
            for s, e in _AGENTS.items()
            if not e.get("done")
            and s not in busy_parents
            and e.get("parent") not in ids
            and now - e["last_seen"] > IDLE_PRUNE_S
        ]
        for s in stale:
            _AGENTS.pop(s, None)
        return sorted(_AGENTS.values(), key=lambda e: e["start"])


def has_active() -> bool:
    with _LOCK:
        return bool(_AGENTS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _derive_status(event_type: str, event_data: Any) -> Optional[str]:
    """Map a sub-agent stream event to a short status. None = no change."""
    if not isinstance(event_data, dict):
        return None
    if event_type == "part_start":
        tool = event_data.get("tool_name")
        if tool:
            return f"calling {tool}"
        part_type = event_data.get("part_type", "") or ""
        if "Thinking" in part_type:
            return "thinking..."
        if "Text" in part_type:
            return "writing response"
    return None


def fmt_elapsed(start: float) -> str:
    """mm:ss elapsed (2-digit minutes), e.g. 00:19."""
    elapsed = int(max(0.0, time.time() - start))
    return f"{elapsed // 60:02d}:{elapsed % 60:02d}"


def fmt_elapsed_entry(entry: Dict[str, Any]) -> str:
    """mm:ss for an entry, frozen at its 'end' time once done."""
    end = entry.get("end")
    start = entry["start"]
    elapsed = int(max(0.0, (end if end else time.time()) - start))
    return f"{elapsed // 60:02d}:{elapsed % 60:02d}"


def spinner_frame() -> str:
    """Wall-clock-derived spinner char (~10fps), independent of caller."""
    return SPINNER_FRAMES[int(time.time() * 10) % len(SPINNER_FRAMES)]


def status_style(status: str) -> str:
    """Color-code the status text by activity type."""
    if status.startswith("calling"):
        return "yellow"
    if status.startswith("thinking"):
        return "magenta"
    if status.startswith("writing"):
        return "green"
    return "dim"
