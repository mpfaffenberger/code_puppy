"""Adapter between the pure vim engine and Textual's ``TextArea``.

The engine speaks in (string, offset); a ``TextArea`` speaks in
(row, col) + ``Selection``. This module is the *only* place that bridges the
two, keeping ``PromptArea`` and the engine blissfully unaware of each other.
"""

from __future__ import annotations

from textual import events
from textual.widgets.text_area import Selection

from .vim import (
    VISUAL,
    Editor,
    VimState,
    feed,
    offset_to_rowcol,
    rowcol_to_offset,
)


def feed_key(prompt, state: VimState, event: events.Key) -> bool:
    """Route one key event through the vim engine.

    Returns True if the engine consumed the key (and the widget state was
    updated), False if the key should fall through to the default TextArea
    behaviour (printable typing in INSERT, Enter, Ctrl-combos...).
    """
    key_str = _key_for_engine(event)
    text = prompt.text
    row, col = prompt.cursor_location
    ed = Editor(
        text=text,
        cursor=rowcol_to_offset(text, row, col),
        anchor=getattr(prompt, "_vim_anchor", None),
    )

    if not feed(state, ed, key_str):
        return False

    event.prevent_default()
    event.stop()
    if ed.text != text:
        prompt.text = ed.text
    _apply_selection(prompt, state, ed)
    prompt._vim_anchor = ed.anchor
    return True


def _key_for_engine(event: events.Key) -> str:
    """Prefer the produced character (so ``$`` stays ``$``); fall back to the
    key name for specials (``escape``, ``enter``, ``ctrl+*``...)."""
    char = event.character
    if char and len(char) == 1 and char.isprintable():
        return char
    return event.key


def _apply_selection(prompt, state: VimState, ed: Editor) -> None:
    if state.mode == VISUAL and ed.anchor is not None:
        lo = min(ed.anchor, ed.cursor)
        hi = max(ed.anchor, ed.cursor)
        start = offset_to_rowcol(ed.text, lo)
        end = offset_to_rowcol(ed.text, hi + 1)
        prompt.selection = Selection(start, end)
    else:
        loc = offset_to_rowcol(ed.text, ed.cursor)
        prompt.selection = Selection(loc, loc)
