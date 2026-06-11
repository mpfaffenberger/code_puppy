"""Tiny raw-terminal prompt for collecting a steering message + mode.

This deliberately avoids third-party terminal UI libraries. The Ctrl+T steering
prompt runs while agent streaming, spinner teardown, and key-listener machinery
are active; in real terminals CPR/raw-mode negotiation has caused instability
(``WARNING: your terminal doesn't support cursor position requests (CPR)``) and
left users unable to submit. This prompt is boring on purpose: stdlib-only,
single-line, no CPR, no full-screen UI, no bottom toolbar.

Line editing supports left/right arrows, Home/End, Delete, and Backspace at
the cursor. Rendering is incremental (see :mod:`.line_editor`) so legacy
Windows consoles — which ignore DEC 2026 synchronized output — don't flicker.
"""

from __future__ import annotations

import sys
from typing import Iterator, Literal, Optional, Tuple

from .line_editor import make_render_state, render_line

SteerMode = Literal["now", "queue"]
SteerResult = Optional[Tuple[str, SteerMode]]
KeyAction = Literal["continue", "submit", "cancel"]

# Symbolic tokens for navigation keys. Multi-char on purpose so they can
# never collide with a literal single keypress character.
_LEFT, _RIGHT, _HOME, _END, _DELETE = "left", "right", "home", "end", "delete"

# CSI / SS3 final bytes → tokens (ESC [ D, ESC O D, ...). Modifier params
# (e.g. Ctrl+Left = ESC [ 1;5 D) map to the same base key — close enough.
_CSI_FINAL_KEYS = {"D": _LEFT, "C": _RIGHT, "H": _HOME, "F": _END}
# CSI <n> ~ → tokens (vt-style Home/End/Delete).
_CSI_TILDE_KEYS = {"1": _HOME, "7": _HOME, "4": _END, "8": _END, "3": _DELETE}
# Windows scan-code suffixes after a \x00/\xe0 prefix from msvcrt.getwch().
_WIN_SCAN_KEYS = {"K": _LEFT, "M": _RIGHT, "G": _HOME, "O": _END, "S": _DELETE}


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


def _render_prompt(buffer: list[str], pos: int, mode: SteerMode, state: dict) -> None:
    """Render the prompt line with the cursor at ``pos`` (index into buffer)."""
    prefix = f"steer [{mode}]> "
    render_line(prefix + "".join(buffer), len(prefix) + pos, state)


def _exit_prompt(buffer: list[str], mode: SteerMode, state: dict) -> None:
    """Park the cursor after the line's end and drop to a fresh row.

    Without this, submitting/cancelling with the cursor mid-line would emit
    the trailing newline from the middle of wrapped text and later output
    would stomp the tail rows.
    """
    _render_prompt(buffer, len(buffer), mode, state)
    sys.stdout.write("\n")
    sys.stdout.flush()


def _handle_key(
    token: str, buffer: list[str], pos: int, mode: SteerMode
) -> tuple[KeyAction, int, SteerMode]:
    """Handle one key token, mutating ``buffer`` and returning new cursor/mode."""
    if token in ("\r", "\n"):
        return "submit", pos, mode
    if token in ("", "\x03", "\x04", "\x1b"):
        return "cancel", pos, mode
    if token == "\t":
        return "continue", pos, "queue" if mode == "now" else "now"
    if token == _LEFT:
        return "continue", max(0, pos - 1), mode
    if token == _RIGHT:
        return "continue", min(len(buffer), pos + 1), mode
    if token == _HOME:
        return "continue", 0, mode
    if token == _END:
        return "continue", len(buffer), mode
    if token == _DELETE:
        if pos < len(buffer):
            del buffer[pos]
        return "continue", pos, mode
    if token in ("\x7f", "\b"):
        if pos > 0:
            del buffer[pos - 1]
            pos -= 1
        return "continue", pos, mode
    if len(token) == 1 and token >= " " and token != "\x7f":
        buffer.insert(pos, token)
        return "continue", pos + 1, mode
    return "continue", pos, mode


# CSI sequences end on a "final byte" in this inclusive range (ECMA-48).
_CSI_FINAL_LO, _CSI_FINAL_HI = "\x40", "\x7e"


def _decode_csi(params: str, final: str) -> Optional[str]:
    """Map one CSI sequence to a nav token, or ``None`` for keys we ignore."""
    if final == "~":
        return _CSI_TILDE_KEYS.get(params.split(";", 1)[0])
    return _CSI_FINAL_KEYS.get(final)


def _iter_keys(chunk: str) -> Iterator[str]:
    """Yield key tokens (single chars or nav names) from a raw input chunk.

    Escape *sequences* (arrow keys, Home/End, F-keys, Alt+chords) arrive as
    multi-byte bursts starting with ESC. Recognized navigation sequences are
    translated to symbolic tokens; everything else is swallowed whole — the
    old code fed the bytes through one at a time, saw the leading ESC, and
    cancelled the prompt the moment you pressed a left arrow. A *lone* ESC
    (nothing after it in the chunk) is still yielded so the caller can treat
    it as cancel.
    """
    i, n = 0, len(chunk)
    while i < n:
        ch = chunk[i]
        if ch != "\x1b":
            yield ch
            i += 1
            continue
        if i + 1 >= n:
            yield "\x1b"  # lone ESC → cancel
            return
        nxt = chunk[i + 1]
        if nxt == "[":  # CSI: ESC [ <params/intermediates> <final byte>
            i += 2
            start = i
            while i < n and not (_CSI_FINAL_LO <= chunk[i] <= _CSI_FINAL_HI):
                i += 1
            if i < n:
                token = _decode_csi(chunk[start:i], chunk[i])
                if token is not None:
                    yield token
            i += 1  # consume the final byte (or run off the end — fine)
        elif nxt == "O":  # SS3: application-mode arrows / Home / End
            if i + 2 < n:
                token = _CSI_FINAL_KEYS.get(chunk[i + 2])
                if token is not None:
                    yield token
            i += 3
        else:  # Alt+<char> chord — swallow both
            i += 2


def _finish_submit(buffer: list[str], mode: SteerMode) -> SteerResult:
    """Build the public result for an Enter submit."""
    text = "".join(buffer).strip()
    return (text, mode) if text else None


def _collect_via_posix_raw() -> SteerResult:
    """Collect steering text using POSIX cbreak mode. Always restores TTY.

    Input is read in chunks via ``os.read`` (not ``sys.stdin.read(1)``):
    a keypress that produces an escape sequence arrives as one atomic burst,
    which lets :func:`_iter_keys` tell "left arrow" apart from a lone ESC.
    The text-IO wrapper would slurp the whole sequence into its private
    buffer and make that distinction impossible.
    """
    import codecs
    import os
    import termios
    import tty

    fd = sys.stdin.fileno()
    original_attrs = termios.tcgetattr(fd)
    buffer: list[str] = []
    pos = 0
    mode: SteerMode = "now"
    state = make_render_state()
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    try:
        tty.setcbreak(fd)
        _render_prompt(buffer, pos, mode, state)
        while True:
            raw = os.read(fd, 1024)
            if not raw:  # EOF
                _exit_prompt(buffer, mode, state)
                return None
            for token in _iter_keys(decoder.decode(raw)):
                action, pos, mode = _handle_key(token, buffer, pos, mode)
                if action == "submit":
                    _exit_prompt(buffer, mode, state)
                    return _finish_submit(buffer, mode)
                if action == "cancel":
                    _exit_prompt(buffer, mode, state)
                    return None
                _render_prompt(buffer, pos, mode, state)
    except KeyboardInterrupt:
        _exit_prompt(buffer, mode, state)
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original_attrs)


def _collect_via_windows_raw() -> SteerResult:
    """Collect steering text using ``msvcrt.getwch()`` on Windows."""
    import msvcrt

    buffer: list[str] = []
    pos = 0
    mode: SteerMode = "now"
    state = make_render_state()
    _render_prompt(buffer, pos, mode, state)
    while True:
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            token = _WIN_SCAN_KEYS.get(msvcrt.getwch())
            if token is None:
                continue  # F-keys, up/down, etc. — ignore
        else:
            token = ch
        action, pos, mode = _handle_key(token, buffer, pos, mode)
        if action == "submit":
            _exit_prompt(buffer, mode, state)
            return _finish_submit(buffer, mode)
        if action == "cancel":
            _exit_prompt(buffer, mode, state)
            return None
        _render_prompt(buffer, pos, mode, state)


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
