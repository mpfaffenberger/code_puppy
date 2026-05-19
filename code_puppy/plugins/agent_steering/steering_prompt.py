"""Tiny raw-terminal prompt for collecting a steering message + mode.

This deliberately avoids third-party terminal UI libraries. The Ctrl+T steering
prompt runs while agent streaming, spinner teardown, and key-listener machinery
are active; in real terminals CPR/raw-mode negotiation has caused instability
(``WARNING: your terminal doesn't support cursor position requests (CPR)``) and
left users unable to submit. This prompt is boring on purpose: stdlib-only,
single-line, no CPR, no full-screen UI, no bottom toolbar.
"""

from __future__ import annotations

import shutil
import sys
from typing import Literal, Optional, Tuple

SteerMode = Literal["now", "queue"]
SteerResult = Optional[Tuple[str, SteerMode]]
KeyAction = Literal["continue", "submit", "cancel", "redraw"]

# Minimum sensible terminal width — guards against zero/negative widths from
# weird shells. If we ever see anything smaller, we treat the line as a single
# unwrapped row, which is wrong but at least won't divide by zero.
_MIN_WIDTH = 1
_FALLBACK_WIDTH = 80

# DEC private mode 2026 — "synchronized output". Terminals that support it
# (iTerm2, kitty, WezTerm, Alacritty, recent gnome-terminal/xterm, Windows
# Terminal) buffer everything between BEGIN and END and commit it as one
# atomic frame → no mid-redraw flicker. Terminals that don't recognize the
# escape silently ignore it, so this is a free upgrade with zero fallback
# cost. Spec: https://gist.github.com/christianparpart/d8a62cc1ab659194337d73e399004036
_SYNC_BEGIN = "\x1b[?2026h"
_SYNC_END = "\x1b[?2026l"


def _can_run_full_ui() -> bool:
    """True when stdin/stdout look usable for raw terminal input."""
    try:
        return bool(
            getattr(sys, "stdin", None)
            and sys.stdin.isatty()
            and getattr(sys, "stdout", None)
            and sys.stdout.isatty()
        )
    except Exception:
        return False


def _collect_via_input_fallback() -> SteerResult:
    """Last-resort prompt when raw terminal mode can't run.

    The fallback has no Tab handling, so it always returns ``"now"`` mode.
    """
    try:
        text = input("steer> ")
    except (EOFError, KeyboardInterrupt):
        return None
    text = (text or "").strip()
    return (text, "now") if text else None


def _terminal_width() -> int:
    """Best-effort terminal width, clamped to ``_MIN_WIDTH``."""
    try:
        cols = shutil.get_terminal_size(fallback=(_FALLBACK_WIDTH, 24)).columns
    except Exception:
        cols = _FALLBACK_WIDTH
    return max(_MIN_WIDTH, cols)


def _cursor_row_for_length(text_len: int, width: int) -> int:
    """Visual row offset (0-indexed) where the cursor sits after writing
    ``text_len`` chars starting from column 0 of a fresh row.

    Terminals park the cursor on the row of the *last printed character* until
    the next char actually wraps, so for ``N`` chars the row is ``(N-1)//width``.
    """
    if text_len <= 0:
        return 0
    return (text_len - 1) // max(_MIN_WIDTH, width)


def _make_render_state() -> dict:
    """Mutable bookkeeping for the redraw routine. Lives one prompt session."""
    return {"cursor_row": 0}


def _render_prompt(buffer: list[str], mode: SteerMode, state: dict) -> None:
    """Redraw the steering prompt, correctly handling wrapped input.

    On every redraw we jump back up to the prompt's starting row, wipe
    everything from there to the end of the screen, and re-emit the line.
    Without this, ``\r\x1b[K`` only clears the *current* visual row, so wrapped
    input gets re-stamped on every keystroke (see the bug report Mike sent).

    The whole sequence is wrapped in DEC 2026 synchronized output so modern
    terminals commit it atomically — the user never sees the intermediate
    "cleared screen" frame, which is what produced the flicker.
    """
    width = _terminal_width()
    line = f"steer [{mode}]> {''.join(buffer)}"

    prev_row = state.get("cursor_row", 0)
    sys.stdout.write(_SYNC_BEGIN)
    if prev_row > 0:
        sys.stdout.write(f"\x1b[{prev_row}A")
    sys.stdout.write("\r\x1b[J")
    sys.stdout.write(line)
    sys.stdout.write(_SYNC_END)

    state["cursor_row"] = _cursor_row_for_length(len(line), width)
    sys.stdout.flush()


def _handle_key(
    ch: str, buffer: list[str], mode: SteerMode
) -> tuple[KeyAction, SteerMode]:
    """Handle one raw keypress, mutating ``buffer`` when appropriate."""
    if ch in ("\r", "\n"):
        return "submit", mode
    if ch in ("", "\x03", "\x04", "\x1b"):
        return "cancel", mode
    if ch == "\t":
        return "redraw", "queue" if mode == "now" else "now"
    if ch in ("\x7f", "\b"):
        if buffer:
            buffer.pop()
            return "redraw", mode
        return "continue", mode
    if len(ch) == 1 and ch >= " " and ch != "\x7f":
        buffer.append(ch)
        return "continue", mode
    return "continue", mode


def _finish_submit(buffer: list[str], mode: SteerMode) -> SteerResult:
    """Build the public result for an Enter submit."""
    text = "".join(buffer).strip()
    return (text, mode) if text else None


def _collect_via_posix_raw() -> SteerResult:
    """Collect steering text using POSIX cbreak mode. Always restores TTY."""
    import termios
    import tty

    fd = sys.stdin.fileno()
    original_attrs = termios.tcgetattr(fd)
    buffer: list[str] = []
    mode: SteerMode = "now"
    state = _make_render_state()
    try:
        tty.setcbreak(fd)
        _render_prompt(buffer, mode, state)
        while True:
            ch = sys.stdin.read(1)
            action, mode = _handle_key(ch, buffer, mode)
            if action == "submit":
                sys.stdout.write("\n")
                sys.stdout.flush()
                return _finish_submit(buffer, mode)
            if action == "cancel":
                sys.stdout.write("\n")
                sys.stdout.flush()
                return None
            # ``continue`` covers both "buffer grew by one printable char" and
            # "ignored control char"; redrawing on the latter is a harmless
            # no-op and keeps the state machine dead simple.
            _render_prompt(buffer, mode, state)
    except KeyboardInterrupt:
        sys.stdout.write("\n")
        sys.stdout.flush()
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original_attrs)


def _collect_via_windows_raw() -> SteerResult:
    """Collect steering text using ``msvcrt.getwch()`` on Windows."""
    import msvcrt

    buffer: list[str] = []
    mode: SteerMode = "now"
    state = _make_render_state()
    _render_prompt(buffer, mode, state)
    while True:
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            msvcrt.getwch()  # consume and ignore special-key suffix
            continue
        action, mode = _handle_key(ch, buffer, mode)
        if action == "submit":
            sys.stdout.write("\n")
            sys.stdout.flush()
            return _finish_submit(buffer, mode)
        if action == "cancel":
            sys.stdout.write("\n")
            sys.stdout.flush()
            return None
        _render_prompt(buffer, mode, state)


def _collect_via_raw_terminal() -> SteerResult:
    """Dispatch to the platform raw-terminal implementation."""
    if sys.platform.startswith("win"):
        return _collect_via_windows_raw()
    return _collect_via_posix_raw()


def collect_steering_message() -> SteerResult:
    """Open the raw steering prompt and return ``(text, mode)``.

    Returns ``None`` if the user aborts or submits only whitespace.
    """
    if not _can_run_full_ui():
        return _collect_via_input_fallback()
    return _collect_via_raw_terminal()


__all__ = ["SteerMode", "SteerResult", "collect_steering_message"]
