"""CSI/SS3 action dispatch for the raw editor.

Split out of ``line_editor.py`` for the 600-line cap: a single
``apply_action(editor, action)`` function that mutates the editor's
buffer/cursor and coordinates the menu / history / reverse-search /
multiline features. Runs under the editor's lock (called from
``_feed_one``).
"""

from __future__ import annotations

from typing import Optional

from . import editor_keys as ek
from .chords import clear_chord_hint, dispatch_chord, show_chord_hint


def handle_chord(ed, ch: str) -> bool:
    """Ctrl+X chord prefix handling; True = key consumed.

    First press arms the prefix (+ hint on the bottom bar); the next
    key resolves against the chords registry. Unbound follow-ups fall
    through (False) so the editor processes them normally — Esc and
    Ctrl+C disarm via the editor's own branches before reaching here.
    """
    if ed._ctrl_x_pending:
        ed._ctrl_x_pending = False
        clear_chord_hint()
        return dispatch_chord(ch)
    if ch == ek.CTRL_X:
        ed._ctrl_x_pending = True
        show_chord_hint()
        return True
    return False


def apply_action(ed, action: Optional[str]) -> None:
    """Dispatch a classified key action against editor ``ed``."""
    if action is None:
        return
    if action == "paste_start":
        ed._paste.start()
        return
    if action == "f2":
        ed._toggle_multiline()
        return
    if ed._rsearch.active:
        return  # navigation/insertion is inert during reverse search
    if action == "newline":
        # Shift+Enter / Ctrl+Enter: insert a newline in ANY mode — the
        # soft-wrap viewport grows even in single-line mode.
        ed._insert_text("\n")
        return
    menu_open = ed._completion_open()
    if action == "up":
        if menu_open:
            ed._completion.move(-1)
        elif ek.line_up(ed._buffer, ed._cursor) is not None:
            ed._cursor = ek.line_up(ed._buffer, ed._cursor)
            ed._repaint()
        else:
            ed._history_recall(ed._history.up(ed._buffer))
    elif action == "down":
        if menu_open:
            ed._completion.move(1)
        elif ek.line_down(ed._buffer, ed._cursor) is not None:
            ed._cursor = ek.line_down(ed._buffer, ed._cursor)
            ed._repaint()
        else:
            ed._history_recall(ed._history.down(ed._buffer))
    elif action == "shift_tab":
        if menu_open:
            ed._completion.move(-1)
    elif action == "left":
        if ed._cursor > 0:
            ed._cursor -= 1
            ed._repaint()
    elif action == "right":
        if ed._cursor < len(ed._buffer):
            ed._cursor += 1
            ed._repaint()
    elif action == "home":
        ed._cursor = ek.line_bounds(ed._buffer, ed._cursor)[0]
        ed._repaint()
    elif action == "end":
        ed._cursor = ek.line_bounds(ed._buffer, ed._cursor)[1]
        ed._repaint()
    elif action == "delete":
        if ed._cursor < len(ed._buffer):
            ed._buffer = ed._buffer[: ed._cursor] + ed._buffer[ed._cursor + 1 :]
            ed._after_edit()
    elif action == "word_left":
        ed._cursor = ek.word_left(ed._buffer, ed._cursor)
        ed._repaint()
    elif action == "word_right":
        ed._cursor = ek.word_right(ed._buffer, ed._cursor)
        ed._repaint()


__all__ = ["apply_action", "handle_chord"]
