"""In-place steps ledger for compact, Claude-Code / Codex style status.

When ``compact_steps`` is enabled, tool-call peeks and intermediate assistant
narration collapse into a single live region that updates in place — like the
spinner, but with a rolling list of recent / completed steps.

Design goals
------------
- **Bounded** — the on-screen ledger is the last *k* rows; older rows roll off
  silently. The full per-turn log is preserved (see ``snapshot`` / ``history``)
  so a ``/steps`` command can replay it without ever needing to re-parse
  scrollback.
- **Thread-safe** — the spinner thread reads while the agent / event-stream
  handler writes. A single ``threading.Lock`` mirrors the pattern used by
  ``SpinnerBase._activity_lock`` and ``_context_lock``.
- **Cheap to render** — the renderable is a plain ``rich.text.Text`` built on
  demand, not a heavy ``Group`` / ``Panel`` chain.
- **No external state** — the ledger is module-scoped (one per process), but
  each turn resets it. Tests get a clean state via ``reset()``.

Glyphs
------
- ``•`` — a buffered intermediate narration step (collapsed into the ledger,
  never written to scrollback).
- ``✓`` — a completed tool step (the activity label at completion time).
- ``▸`` — the per-turn summary marker used in Phase 3.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional

from rich.text import Text

# Default ledger depth. Overridable via ``compact_steps_max_visible`` config.
_DEFAULT_MAX_VISIBLE = 5

# Max character width for a rendered ledger row. Long labels truncate with an
# ellipsis so the live region never wraps / pushes the spinner off-screen.
_MAX_ROW_WIDTH = 120


@dataclass(frozen=True)
class StepRow:
    """One row in the ledger.

    ``kind`` is one of ``"narration"`` (intermediate agent text, never reaches
    scrollback when deferred), ``"tool"`` (a completed tool step), or
    ``"summary"`` (the rolled-up ``▸ N steps`` marker from Phase 3).
    """

    kind: str
    label: str
    completed: bool = True
    meta: dict = field(default_factory=dict)


class StepLedger:
    """Thread-safe, bounded ledger of recent steps for the current turn."""

    def __init__(self, max_visible: int = _DEFAULT_MAX_VISIBLE):
        self._lock = threading.Lock()
        self._max_visible = max(1, int(max_visible))
        self._active: Optional[StepRow] = None
        # Completed rows that should remain visible (bounded).
        self._recent: Deque[StepRow] = deque(maxlen=self._max_visible)
        # Full per-turn history — *unbounded*; cleared by ``reset``. Powers
        # the optional ``/steps`` replay command and any future analytics.
        self._history: List[StepRow] = []

    # ---- capacity ----------------------------------------------------------

    @property
    def max_visible(self) -> int:
        return self._max_visible

    def set_max_visible(self, n: int) -> None:
        with self._lock:
            self._max_visible = max(1, int(n))
            # Rebuild the recent deque with the new bound; preserve as much
            # tail as possible so an in-flight turn doesn't visually reset.
            tail = list(self._recent)
            self._recent = deque(tail[-self._max_visible :], maxlen=self._max_visible)

    # ---- mutation ----------------------------------------------------------

    def begin_active(self, label: str, kind: str = "tool") -> None:
        """Mark a step as the currently running one (animates in the Live row)."""
        with self._lock:
            self._active = StepRow(kind=kind, label=label, completed=False)

    def complete_active(self, label: Optional[str] = None) -> None:
        """Collapse the active step into a completed row.

        If ``label`` is supplied, it replaces the active label in the
        completed row — useful when the spinner shows ``Running: npm test``
        during execution and we want the persisted step to be
        ``✓ npm test (passed)`` afterwards.
        """
        with self._lock:
            if self._active is None:
                return
            final_label = label if label is not None else self._active.label
            row = StepRow(kind=self._active.kind, label=final_label, completed=True)
            self._recent.append(row)
            self._history.append(row)
            self._active = None

    def cancel_active(self) -> None:
        """Drop the active step without recording it (e.g. tool errored before
        a useful label existed)."""
        with self._lock:
            self._active = None

    def push_completed(self, label: str, kind: str = "tool") -> StepRow:
        """Append a one-shot completed step (no active phase)."""
        row = StepRow(kind=kind, label=label, completed=True)
        with self._lock:
            self._recent.append(row)
            self._history.append(row)
        return row

    def push_narration(self, gist: str) -> StepRow:
        """Record an intermediate narration step (no scrollback write)."""
        row = StepRow(kind="narration", label=gist, completed=True)
        with self._lock:
            self._recent.append(row)
            self._history.append(row)
        return row

    def reset(self) -> List[StepRow]:
        """Clear all ledger state and return the per-turn history snapshot.

        Used at end-of-turn so the next turn starts clean.
        """
        with self._lock:
            snapshot = list(self._history)
            self._active = None
            self._recent.clear()
            self._history.clear()
            return snapshot

    # ---- introspection -----------------------------------------------------

    @property
    def active(self) -> Optional[StepRow]:
        with self._lock:
            return self._active

    @property
    def recent(self) -> List[StepRow]:
        with self._lock:
            return list(self._recent)

    @property
    def history(self) -> List[StepRow]:
        with self._lock:
            return list(self._history)

    def completed_count(self) -> int:
        with self._lock:
            return sum(1 for r in self._history if r.completed)

    def has_active(self) -> bool:
        with self._lock:
            return self._active is not None

    # ---- rendering ---------------------------------------------------------

    def render(self, frame: str = "", include_active: bool = True) -> Text:
        """Build a Rich ``Text`` representing the current ledger.

        ``frame`` is the braille spinner glyph (animated separately by the
        spinner). When an active row exists and ``include_active`` is True,
        the active row is prepended; otherwise only the completed tail is
        returned.
        """
        with self._lock:
            active = self._active
            recent = list(self._recent)

        text = Text()

        if active is not None and include_active:
            text.append("Running: ", style="bold cyan")
            text.append(_truncate(active.label), style="bold cyan")
            if frame:
                text.append(" ")
                text.append(frame, style="bold cyan")
            text.append("\n")

        # Render tail rows dim so the eye reads them as "already done".
        for row in recent:
            bullet = {
                "tool": "✓",
                "narration": "•",
                "summary": "▸",
            }.get(row.kind, "•")
            prefix = f"  {bullet} "
            label = _truncate(row.label)
            text.append(prefix, style="dim")
            text.append(label, style="dim")
            text.append("\n")

        # Strip the trailing newline so Rich doesn't add a phantom blank
        # row inside the Live region. Drop the trailing dim span rather
        # than rebuilding the Text from scratch — rebuilding loses the
        # per-span styles (the dim glyph rows) we just set above.
        if text.plain.endswith("\n"):
            if text.spans and text.spans[-1].start >= len(text) - 1:
                text.spans.pop()
            text.plain = text.plain.rstrip("\n")
        return text


def _truncate(label: str, limit: int = _MAX_ROW_WIDTH) -> str:
    """Collapse a label to a single line and bound its width."""
    text = " ".join(str(label or "").split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


# Module-level singleton. Tests reset via ``_ledger.reset()``.
_ledger: StepLedger = StepLedger()


def get_ledger() -> StepLedger:
    """Return the process-wide steps ledger."""
    return _ledger


def configure_ledger(max_visible: Optional[int] = None) -> StepLedger:
    """Reconfigure (and reset) the process-wide ledger. Used at startup and
    when the user toggles ``compact_steps_max_visible`` mid-session.
    """
    global _ledger
    with _ledger._lock:  # type: ignore[attr-defined]
        pass
    _ledger = StepLedger(max_visible or _DEFAULT_MAX_VISIBLE)
    return _ledger


__all__ = ["StepLedger", "StepRow", "get_ledger", "configure_ledger"]
