"""Terminal-level palette swap via OSC escape sequences.

This module reaches *past* Mist and recolors the whole terminal window
(bg, fg, ANSI palette slots) using widely-supported xterm OSC sequences:

    OSC 10 ; spec BEL    -> set default foreground
    OSC 11 ; spec BEL    -> set default background
    OSC  4 ; N ; spec BEL -> set ANSI palette slot N (0..15)
    OSC 110 BEL          -> reset foreground
    OSC 111 BEL          -> reset background
    OSC 104 BEL          -> reset whole palette

Supported by iTerm2, Terminal.app, Alacritty, kitty, VS Code, GNOME
Terminal, Windows Terminal. Unsupported terminals silently ignore them.

We always register an atexit handler so the terminal is restored when
Mist quits, even if the user forgets to /theme default first.
"""

from __future__ import annotations

import atexit
import json
import sys
from typing import Optional, Sequence

from code_puppy.config import get_value, set_config_value

BEL = "\007"
ESC = "\033"

_CONFIG_KEY = "osc_palette_json"
_atexit_registered = False


# --- Low-level emit ---------------------------------------------------------
def _emit(seq: str) -> None:
    """Write an escape sequence to stdout, ignoring failures (closed tty etc.)."""
    try:
        sys.stdout.write(seq)
        sys.stdout.flush()
    except Exception:
        pass


def _osc(code: str, *args: str) -> str:
    """Build an OSC escape: ESC ] code ; args... BEL"""
    payload = ";".join((code,) + args)
    return f"{ESC}]{payload}{BEL}"


# --- Public escape builders -------------------------------------------------
def set_bg(color: str) -> None:
    _emit(_osc("11", color))


def set_fg(color: str) -> None:
    _emit(_osc("10", color))


def set_ansi_slot(slot: int, color: str) -> None:
    if not 0 <= slot <= 15:
        return
    _emit(_osc("4", str(slot), color))


def reset_bg() -> None:
    _emit(_osc("111"))


def reset_fg() -> None:
    _emit(_osc("110"))


def reset_ansi() -> None:
    _emit(_osc("104"))


# --- High-level API ---------------------------------------------------------
def apply_palette(
    palette: dict, persist: bool = True, register_reset: bool = True
) -> None:
    """Apply a palette dict to the live terminal.

    Palette shape:
        {
            "bg":   "#rrggbb",                 # optional
            "fg":   "#rrggbb",                 # optional
            "ansi": ["#rrggbb", ...]           # optional, 0..16 entries
        }

    `persist=True` writes the palette to config so the next Mist
    session can replay it. `register_reset=True` ensures we always
    restore the terminal at process exit.
    """
    if not isinstance(palette, dict):
        return

    bg = palette.get("bg")
    fg = palette.get("fg")
    ansi: Sequence[str] = palette.get("ansi") or []

    if bg:
        set_bg(bg)
    if fg:
        set_fg(fg)
    for i, color in enumerate(ansi[:16]):
        if color:
            set_ansi_slot(i, color)

    if persist:
        try:
            set_config_value(_CONFIG_KEY, json.dumps(palette))
        except Exception:
            pass

    if register_reset:
        _ensure_atexit_registered()


def reset_palette(persist: bool = True) -> None:
    """Restore the terminal's original bg/fg/ANSI palette."""
    reset_ansi()
    reset_bg()
    reset_fg()
    if persist:
        try:
            set_config_value(_CONFIG_KEY, "")
        except Exception:
            pass


def get_saved_palette() -> Optional[dict]:
    """Read the persisted palette (or None if nothing saved)."""
    raw = get_value(_CONFIG_KEY)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def reapply_from_config() -> None:
    """On plugin load, re-fire any persisted palette into the terminal."""
    palette = get_saved_palette()
    if palette:
        apply_palette(palette, persist=False)


# --- Cleanup ----------------------------------------------------------------
def _at_exit_reset() -> None:
    """Best-effort terminal restore on Python exit.

    We DON'T touch persisted config here — if the user wants the palette
    next session, they get it; this just makes sure the live terminal
    doesn't stay stuck in a weird color after Mist dies.
    """
    try:
        reset_ansi()
        reset_bg()
        reset_fg()
    except Exception:
        pass


def _ensure_atexit_registered() -> None:
    global _atexit_registered
    if _atexit_registered:
        return
    try:
        atexit.register(_at_exit_reset)
        _atexit_registered = True
    except Exception:
        pass
