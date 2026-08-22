"""Shared terminal ownership for full-screen TUI menus.

``menu_session()`` is the one context manager every interactive picker
wraps itself in (per the ``set_awaiting_user_input`` docstring rule that
components taking over the terminal are responsible for suspending the
run UI). It layers Code Puppy's app concerns on top of termflow's
``terminal_session`` (which owns raw mode + a single alternate screen
across chained menus):

1. ``suspended_run_ui()`` — releases the bottom bar's scroll region and
   the global key listener's grip on stdin.
2. ``PauseController.pause()`` — the message renderer buffers all
   ``emit_*`` output for the duration; the buffer flushes onto the
   primary screen at resume, instead of painting over (and flickering
   under) the menu in the alternate screen.

Menus inside a session must run with ``alt_screen=False``; the session
owns the screen. Reentrant: both layers are refcounted, so nested
pickers (pin-a-model inside the agent picker) share the outer session.
"""

from __future__ import annotations

import contextlib
import threading
from typing import Iterator

from termflow.tui import terminal_session

_lock = threading.Lock()
_depth = 0
_stack: contextlib.ExitStack | None = None


@contextlib.contextmanager
def menu_session() -> Iterator[None]:
    """Own the terminal for a (possibly nested) TUI menu session."""
    global _depth, _stack
    with _lock:
        _depth += 1
        if _depth == 1:
            from code_puppy.messaging.pause_controller import get_pause_controller
            from code_puppy.messaging.run_ui import suspended_run_ui

            stack = contextlib.ExitStack()
            try:
                stack.enter_context(suspended_run_ui())
                pc = get_pause_controller()
                pc.pause()
                # LIFO: resume fires after the terminal session closes, so
                # the buffered messages flush onto the primary screen.
                stack.callback(pc.resume)
                stack.enter_context(terminal_session())
            except Exception:
                _depth -= 1
                with contextlib.suppress(Exception):
                    stack.close()
                raise
            _stack = stack
    try:
        yield
    finally:
        with _lock:
            _depth -= 1
            if _depth == 0 and _stack is not None:
                stack, _stack = _stack, None
                with contextlib.suppress(Exception):
                    stack.close()
