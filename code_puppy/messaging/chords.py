"""Ctrl+X chord registry: one prefix, many bindings, zero modes.

Ctrl+X is ALWAYS a chord prefix — the line editor arms a pending state
on ``\\x18`` and resolves the NEXT key against this registry. Components
register bindings for exactly as long as they're meaningful:

* ``run_ui`` registers Ctrl+E (edit the prompt in $EDITOR) for the
  UI's lifetime.
* ``command_runner`` registers Ctrl+X (kill all shells) and Ctrl+B
  (background all shells) while shell commands are in flight.

This replaced the modal ``set_escape_handler`` design where a bare
Ctrl+X meant "kill shells IF a handler happened to be armed in that
microsecond, editor chord otherwise" — a mode switch distributed across
two modules whose arm/disarm lifecycle raced against keystrokes.

While the chord is armed, the bottom bar's status row shows a hint
built from the registered bindings; Esc (or any unbound key) cancels.
Everything here is best-effort and thread-safe — callbacks run on the
key-listener thread and must never block (hop to the loop's executor
like the $EDITOR handler does).
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

#: key char -> (callback, hint). Insertion order drives hint order.
_bindings: Dict[str, Tuple[Callable[[], None], str]] = {}
_lock = threading.Lock()

#: Status-row text displaced by the armed-chord hint (restored on clear
#: unless something newer painted over the hint in the meantime).
_painted_hint: Optional[str] = None
_saved_status: str = ""

_HINT_PREFIX = "Ctrl+X chord: "
_HINT_SUFFIX = " · Esc cancel"


def register_chord(key: str, callback: Callable[[], None], hint: str) -> None:
    """Bind ``Ctrl+X <key>`` to ``callback`` (replaces any existing bind).

    ``key`` is the raw follow-up character (e.g. ``"\\x05"`` for Ctrl+E);
    ``hint`` is the human-readable fragment shown while the chord is
    armed (e.g. ``"Ctrl+E edit in $EDITOR"``).
    """
    with _lock:
        _bindings[key] = (callback, hint)


def unregister_chord(key: str) -> None:
    """Remove a chord binding (no-op when absent)."""
    with _lock:
        _bindings.pop(key, None)


def get_chord(key: str) -> Optional[Callable[[], None]]:
    """Return the callback bound to ``Ctrl+X <key>``, or ``None``."""
    with _lock:
        entry = _bindings.get(key)
    return entry[0] if entry else None


def dispatch_chord(key: str) -> bool:
    """Fire the binding for ``key``. Returns True when one was bound.

    Callback failures are logged, never raised — a broken binding must
    not kill the key-listener thread.
    """
    with _lock:
        entry = _bindings.get(key)
    if entry is None:
        return False
    callback, _hint = entry
    try:
        callback()
    except Exception:
        logger.debug("chord callback failed for %r", key, exc_info=True)
    return True


def chord_hint() -> str:
    """Human-readable summary of the armed chord's bindings."""
    with _lock:
        hints = [hint for _cb, hint in _bindings.values()]
    if not hints:
        return ""
    return _HINT_PREFIX + " · ".join(hints) + _HINT_SUFFIX


def show_chord_hint() -> None:
    """Paint the chord hint on the bottom bar's status row (best-effort).

    The displaced text (mid-run token/context status) is remembered so
    ``clear_chord_hint`` can put it back — arming and cancelling a chord
    must not blank the status row until the next status tick.
    """
    global _painted_hint, _saved_status
    hint = chord_hint()
    if not hint:
        return
    try:
        from .bottom_bar import get_bottom_bar

        bar = get_bottom_bar()
        with _lock:
            _saved_status = bar.get_status()
            _painted_hint = hint
        bar.set_status(hint)
    except Exception:
        logger.debug("chord hint paint failed", exc_info=True)


def clear_chord_hint() -> None:
    """Restore whatever the chord hint displaced (best-effort).

    No-op when no hint was painted. If something newer painted over the
    hint while the chord was armed (the status display's periodic
    repaint), the newest text wins — restoring our stale snapshot would
    clobber it.
    """
    global _painted_hint, _saved_status
    with _lock:
        painted, saved = _painted_hint, _saved_status
        _painted_hint, _saved_status = None, ""
    if painted is None:
        return
    try:
        from .bottom_bar import get_bottom_bar

        bar = get_bottom_bar()
        if bar.get_status() == painted:  # nothing newer painted since
            bar.set_status(saved)
    except Exception:
        logger.debug("chord hint clear failed", exc_info=True)


__all__ = [
    "chord_hint",
    "clear_chord_hint",
    "dispatch_chord",
    "get_chord",
    "register_chord",
    "show_chord_hint",
    "unregister_chord",
]
