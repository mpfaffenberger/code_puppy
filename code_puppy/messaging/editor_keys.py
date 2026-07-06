"""Key-sequence classification + cursor movement math for the raw editor.

Pure functions only (no editor state) — split out of ``line_editor.py``
to respect the 600-line cap. CSI sequences arrive WITHOUT the ``ESC[``
prefix but WITH the final byte; anything unrecognized returns ``None``
and the editor keeps its swallow-unknown-CSI safety.
"""

from __future__ import annotations

from typing import Optional

# --- Raw control chars fed to the editor (shared with line_editor) ---
ENTER = "\r"
CTRL_J = "\n"
BACKSPACE_KEYS = ("\x7f", "\x08")
TAB = "\t"
CTRL_A = "\x01"  # beginning of (logical) line
# NOTE: On POSIX, Ctrl+C normally never reaches the editor — the
# terminal turns it into SIGINT and the REPL's handlers clear/cancel.
# On Windows we strip ENABLE_PROCESSED_INPUT for the whole session (so
# Ctrl+C can't become a console-wide event that kills wrapper launchers
# like uvx.exe), so ^C arrives as this raw byte via the key listener.
CTRL_C = "\x03"
CTRL_D = "\x04"
CTRL_E = "\x05"  # end of (logical) line
# NOTE: Ctrl+K (\x0b) can be remapped as the cancel-agent hotkey via
# cancel_agent_key in puppy.cfg. The key listener's priority dispatch
# swallows it BEFORE the editor in that configuration — kill-to-end
# simply won't fire there; with the ctrl+c default it reaches us
# normally on every platform.
CTRL_K = "\x0b"
CTRL_R = "\x12"
CTRL_U = "\x15"
CTRL_V = "\x16"  # smart paste fallback (most terminals bracket-paste first)
CTRL_W = "\x17"  # delete word backwards
ESC = "\x1b"

#: CSI body (params + final byte) → editor action.
_CSI_ACTIONS = {
    "A": "up",
    "B": "down",
    "C": "right",
    "D": "left",
    "H": "home",
    "F": "end",
    "Z": "shift_tab",  # Shift-Tab
    "1~": "home",
    "7~": "home",
    "4~": "end",
    "8~": "end",
    "3~": "delete",
    "1;5C": "word_right",  # Ctrl+arrow (xterm)
    "1;5D": "word_left",
    "5C": "word_right",  # Ctrl+arrow (legacy)
    "5D": "word_left",
    "1;3C": "word_right",  # Alt+arrow (xterm/iTerm2/Linux)
    "1;3D": "word_left",
    "1;9C": "word_right",  # Option+arrow (macOS Terminal.app configs)
    "1;9D": "word_left",
    # Alt/Option+Up/Down: no distinct editor gesture — treated as plain
    # Up/Down (history / menu / line move) rather than silently swallowed.
    "1;3A": "up",
    "1;3B": "down",
    "1;9A": "up",
    "1;9B": "down",
    "200~": "paste_start",  # bracketed paste opener (ESC[?2004h mode)
    "12~": "f2",  # F2 (CSI variant)
    # Modified Enter → newline. Two protocol encodings for each:
    # CSI-u (kitty-style / iTerm2 "CSI u") and xterm modifyOtherKeys
    # (armed via CSI >4;1m — see bottom_bar). Plain-\r terminals CANNOT
    # encode Shift+Enter at all; users there have Ctrl+J / F2 multiline.
    # On Windows (where the console ignores modifyOtherKeys) the key
    # listener synthesizes 13;2u itself via GetAsyncKeyState — see
    # _key_listeners._windows_char_to_seq.
    "13;2u": "newline",  # Shift+Enter (CSI-u)
    "13;5u": "newline",  # Ctrl+Enter  (CSI-u)
    "27;2;13~": "newline",  # Shift+Enter (modifyOtherKeys)
    "27;5;13~": "newline",  # Ctrl+Enter  (modifyOtherKeys)
    # Other modifier combos on Enter (e.g. 13;3u = Alt+Enter via CSI-u)
    # intentionally unmapped → swallowed by the unknown-CSI safety.
}

#: SS3 final byte (after ESC O) → editor action.
_SS3_ACTIONS = {
    "Q": "f2",  # F2 (SS3 variant)
    "A": "up",
    "B": "down",
    "C": "right",
    "D": "left",
    "H": "home",
    "F": "end",
}


def classify_csi(seq: str) -> Optional[str]:
    """Map a complete CSI body to an action name (None = swallow)."""
    return _CSI_ACTIONS.get(seq)


def classify_ss3(ch: str) -> Optional[str]:
    """Map an SS3 final byte to an action name (None = swallow)."""
    return _SS3_ACTIONS.get(ch)


# =============================================================================
# Cursor movement math (index-based, multiline-aware)
# =============================================================================


def word_left(buffer: str, cursor: int) -> int:
    """Ctrl+Left: jump to the start of the previous word."""
    i = cursor
    while i > 0 and not buffer[i - 1].isalnum():
        i -= 1
    while i > 0 and buffer[i - 1].isalnum():
        i -= 1
    return i


def word_right(buffer: str, cursor: int) -> int:
    """Ctrl+Right: jump past the end of the next word."""
    i = cursor
    n = len(buffer)
    while i < n and not buffer[i].isalnum():
        i += 1
    while i < n and buffer[i].isalnum():
        i += 1
    return i


def line_bounds(buffer: str, cursor: int) -> tuple:
    """(line_start, line_end) of the line containing ``cursor``."""
    start = buffer.rfind("\n", 0, cursor) + 1
    end = buffer.find("\n", cursor)
    if end == -1:
        end = len(buffer)
    return start, end


def on_first_line(buffer: str, cursor: int) -> bool:
    return "\n" not in buffer[:cursor]


def on_last_line(buffer: str, cursor: int) -> bool:
    return "\n" not in buffer[cursor:]


def line_up(buffer: str, cursor: int) -> Optional[int]:
    """Cursor position one line up (same column, clamped); None on line 1."""
    if on_first_line(buffer, cursor):
        return None
    start, _end = line_bounds(buffer, cursor)
    col = cursor - start
    prev_start, prev_end = line_bounds(buffer, start - 1)
    return min(prev_start + col, prev_end)


def line_down(buffer: str, cursor: int) -> Optional[int]:
    """Cursor position one line down (same column, clamped); None on last."""
    if on_last_line(buffer, cursor):
        return None
    start, end = line_bounds(buffer, cursor)
    col = cursor - start
    next_start = end + 1
    _s, next_end = line_bounds(buffer, next_start)
    return min(next_start + col, next_end)


__all__ = [
    "classify_csi",
    "classify_ss3",
    "line_bounds",
    "line_down",
    "line_up",
    "on_first_line",
    "on_last_line",
    "word_left",
    "word_right",
]
