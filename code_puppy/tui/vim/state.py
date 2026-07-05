"""State, the editor value object, and coordinate helpers for the vim engine.

Everything here is pure Python -- no Textual imports -- so the engine can be
exercised in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- Mode constants -------------------------------------------------------
INSERT = "insert"
NORMAL = "normal"
VISUAL = "visual"


@dataclass
class Editor:
    """The slice of editor state the engine reads and mutates.

    ``cursor`` and ``anchor`` are character *offsets* into ``text`` (0..len).
    ``anchor`` is the other end of a VISUAL selection (``None`` otherwise).
    """

    text: str
    cursor: int
    anchor: int | None = None


@dataclass
class VimState:
    """Per-prompt vim state. One instance lives on the prompt widget."""

    mode: str = INSERT
    # Accumulated command keys waiting for completion (operators, finds, g...).
    pending: str = ""
    # Accumulated count digits (e.g. "12" for 12w). Empty == no count.
    count: str = ""
    # Yank register (session-local; deliberately NOT the system clipboard).
    register: str = ""
    register_linewise: bool = False
    # Last f/F/t/T for ; and , -- (command_char, target_char).
    last_find: tuple[str, str] | None = None
    # Dot-repeat record. One of:
    #   ("keys", [key, ...])              -- replay a non-insert mutation
    #   ("insert", entry_keys, text)      -- replay an insert/change session
    last_change: tuple | None = None
    # Bookkeeping for capturing inserted text on the way out of INSERT.
    insert_start: int | None = None
    insert_entry_keys: list[str] = field(default_factory=list)
    # Guard so replaying dot-repeat doesn't recursively re-record itself.
    replaying: bool = False
    # Undo history: snapshots of (text, cursor) taken before each mutation.
    undo_stack: list = field(default_factory=list)

    def reset_pending(self) -> None:
        self.pending = ""
        self.count = ""

    def count_value(self, default: int = 1) -> int:
        return int(self.count) if self.count else default


# --- Coordinate helpers (offset <-> row/col) ------------------------------
def offset_to_rowcol(text: str, offset: int) -> tuple[int, int]:
    """Convert a character offset into a (row, col) location."""
    offset = max(0, min(offset, len(text)))
    row = text.count("\n", 0, offset)
    line_start = text.rfind("\n", 0, offset) + 1
    return row, offset - line_start


def rowcol_to_offset(text: str, row: int, col: int) -> int:
    """Convert a (row, col) location into a character offset."""
    lines = text.split("\n")
    row = max(0, min(row, len(lines) - 1))
    offset = sum(len(line) + 1 for line in lines[:row])
    return offset + max(0, min(col, len(lines[row])))
