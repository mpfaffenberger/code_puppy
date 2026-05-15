"""Tiny raw-terminal prompt for collecting a steering message + mode.

This deliberately avoids third-party terminal UI libraries. The Ctrl+T steering
prompt runs while agent streaming, spinner teardown, and key-listener machinery
are active; in real terminals CPR/raw-mode negotiation has caused instability
(``WARNING: your terminal doesn't support cursor position requests (CPR)``) and
left users unable to submit. This prompt is boring on purpose: stdlib-only,
single-line, no CPR, no full-screen UI, no bottom toolbar.
"""

from __future__ import annotations

import sys
from typing import Literal, Optional, Tuple

SteerMode = Literal["now", "queue"]
SteerResult = Optional[Tuple[str, SteerMode]]
KeyAction = Literal["continue", "submit", "cancel", "redraw"]


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


def _render_prompt(buffer: list[str], mode: SteerMode) -> None:
    """Redraw the single steering prompt line."""
    sys.stdout.write(f"\r\x1b[Ksteer [{mode}]> {''.join(buffer)}")
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
    try:
        tty.setcbreak(fd)
        _render_prompt(buffer, mode)
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
            if action == "redraw":
                _render_prompt(buffer, mode)
            elif buffer and ch == buffer[-1]:
                sys.stdout.write(ch)
                sys.stdout.flush()
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
    _render_prompt(buffer, mode)
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
        if action == "redraw":
            _render_prompt(buffer, mode)
        elif buffer and ch == buffer[-1]:
            sys.stdout.write(ch)
            sys.stdout.flush()


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
