"""Multi-step undo/redo for the raw line editor's prompt buffer.

Every buffer mutation records the PRE-edit ``(text, cursor)`` snapshot
via :meth:`UndoHistory.record` before it happens. Consecutive edits of
a coalescing kind collapse into one step when nothing else touched the
buffer in between (the editor reports its post-edit state through
:meth:`UndoHistory.settle`; a cursor move or a programmatic rewrite
makes the next record start a fresh step):

* ``type``: printable keystrokes; a new step starts at each word
  (a non-space typed right after whitespace), so ``hello world``
  undoes as ``hello `` then empty.
* ``backspace`` / ``delete``: runs of single-character deletions.

Everything else (kills, clear, paste, completion, history recall,
``$EDITOR`` round-trip) is its own step. Any new edit drops the redo
stack; submitting a prompt resets both stacks. Pure state, no locking:
the editor calls in under its own lock.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

#: ``(buffer_text, cursor_index)``.
Snapshot = Tuple[str, int]

#: Kinds whose consecutive edits merge into one undo step.
COALESCING_KINDS = frozenset({"type", "backspace", "delete"})

#: Max undo steps kept; the oldest step falls off first.
DEFAULT_UNDO_LIMIT = 100


class UndoHistory:
    """Bounded undo + redo stacks of buffer snapshots."""

    def __init__(self, limit: int = DEFAULT_UNDO_LIMIT) -> None:
        self._limit = max(1, limit)
        self._undo: List[Snapshot] = []
        self._redo: List[Snapshot] = []
        self._kind: Optional[str] = None  # kind of the open coalescing step
        self._settled: Optional[Snapshot] = None  # state after the last edit

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def record(self, kind: str, text: str, cursor: int, boundary: bool = False) -> None:
        """Remember the state BEFORE an edit of ``kind``.

        ``boundary`` forces a new step even for a coalescing kind (the
        editor sets it at word starts while typing).
        """
        self._redo.clear()
        if (
            kind in COALESCING_KINDS
            and kind == self._kind
            and not boundary
            and self._settled == (text, cursor)
        ):
            return  # same run, buffer untouched since: extend the open step
        self._undo.append((text, cursor))
        if len(self._undo) > self._limit:
            del self._undo[0]
        self._kind = kind

    def settle(self, text: str, cursor: int) -> None:
        """Note the post-edit state so the next record can coalesce."""
        self._settled = (text, cursor)

    def undo(self, text: str, cursor: int) -> Optional[Snapshot]:
        """Pop the previous state (current goes to redo); None if empty."""
        return self._step(self._undo, self._redo, (text, cursor))

    def redo(self, text: str, cursor: int) -> Optional[Snapshot]:
        """Re-apply an undone state (current goes to undo); None if empty."""
        return self._step(self._redo, self._undo, (text, cursor))

    def reset(self) -> None:
        """Forget everything (prompt submitted)."""
        self._undo.clear()
        self._redo.clear()
        self._kind = None
        self._settled = None

    def _step(
        self, source: List[Snapshot], target: List[Snapshot], current: Snapshot
    ) -> Optional[Snapshot]:
        # Skip snapshots identical to the current state (a recorded rewrite
        # that changed nothing, e.g. a no-op completion accept).
        while source and source[-1] == current:
            source.pop()
        if not source:
            return None
        target.append(current)
        self._kind = None  # an undo/redo always closes the open step
        return source.pop()


def apply_snapshot(ed, snapshot: Optional[Snapshot]) -> None:
    """Restore an undo/redo snapshot into editor ``ed`` (no-op on None)."""
    if snapshot is None:
        return
    ed._buffer, ed._cursor = snapshot
    # Programmatic rewrite: close the menu, reset history browsing, repaint.
    ed._after_edit(typed=False)


__all__ = [
    "COALESCING_KINDS",
    "DEFAULT_UNDO_LIMIT",
    "Snapshot",
    "UndoHistory",
    "apply_snapshot",
]
