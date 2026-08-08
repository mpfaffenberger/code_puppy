"""A small, Textual-free vim engine for the TUI prompt box.

The engine operates on a plain string + integer cursor offset (an
:class:`Editor`) and a :class:`VimState`. It knows *nothing* about Textual,
which makes it trivially unit-testable -- the ``PromptArea`` widget is just a
thin adapter that converts between (row, col) and offsets and routes keys.

Public surface:

* :class:`VimState`  -- per-prompt vim state (mode, register, pending keys...)
* :class:`Editor`    -- mutable (text, cursor, anchor) value the engine edits
* :func:`feed`       -- feed one key; returns True if the key was consumed
* :data:`INSERT` / :data:`NORMAL` / :data:`VISUAL` -- mode constants
* :func:`offset_to_rowcol` / :func:`rowcol_to_offset` -- coordinate helpers
"""

from .engine import feed
from .state import (
    INSERT,
    NORMAL,
    VISUAL,
    Editor,
    VimState,
    offset_to_rowcol,
    rowcol_to_offset,
)

__all__ = [
    "feed",
    "VimState",
    "Editor",
    "INSERT",
    "NORMAL",
    "VISUAL",
    "offset_to_rowcol",
    "rowcol_to_offset",
]
