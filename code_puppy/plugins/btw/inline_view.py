"""Inline rendering for `/btw` answers (Claude Code style).

Why direct console writes instead of ``emit_info``: the `/btw` handler
blocks the main event loop while the side query runs, which starves the
async transcript renderer — queued messages would only paint *after*
the handler returns. Every slash command already executes under
``suspended_run_ui`` (idle and mid-run), so the terminal is ours for
the duration; printing straight to it is the same trick the TUI menus
use.

The dismiss-wait is load-bearing mid-run: the agent stays parked at its
pause boundary until the user dismisses (or the timeout fires), so the
resuming stream can't immediately scroll the answer away.
"""

from __future__ import annotations

import logging
import os
import sys
import time

logger = logging.getLogger(__name__)

DISMISS_TIMEOUT_S = 120.0
_DISMISS_KEYS = (b" ", b"\r", b"\n", b"\x1b")
_HINT = "Press Space, Enter, or Escape to dismiss"
_INDENT = (0, 0, 0, 2)  # answer block: two-cell left inset


def is_tty() -> bool:
    if os.getenv("CODE_PUPPY_NO_TUI") == "1":
        return False
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def _console():
    from rich.console import Console

    return Console()


def show_asking(question: str, model_name: str) -> None:
    """Echo the question and a progress line before the query blocks."""
    from rich.markup import escape

    console = _console()
    console.print()
    console.print(f"[bold yellow]/btw[/bold yellow] [dim]{escape(question)}[/dim]")
    console.print(f"  [dim]thinking ({escape(model_name)})...[/dim]")


def show_answer(answer: str) -> None:
    """Render the answer inline as Markdown, plus the dismiss hint."""
    from rich.markdown import Markdown
    from rich.padding import Padding

    console = _console()
    console.print()
    console.print(Padding(Markdown(answer), _INDENT))
    console.print()
    console.print(f"  [dim]{_HINT}[/dim]")


def wait_for_dismiss(timeout_s: float = DISMISS_TIMEOUT_S) -> None:
    """Block until Space / Enter / Esc, or auto-dismiss on timeout.

    Never raises. Skips waiting entirely when a raw key can't be read
    (no termios/msvcrt, weird stdin) — better to resume than to hang.
    """
    if not is_tty():
        return
    try:
        _wait_key_posix(timeout_s)
        return
    except ImportError:
        pass
    except Exception:
        logger.debug("btw: posix key wait failed", exc_info=True)
        return
    try:
        _wait_key_windows(timeout_s)
    except Exception:
        logger.debug("btw: windows key wait failed", exc_info=True)


def _wait_key_posix(timeout_s: float) -> None:
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            ready, _, _ = select.select([fd], [], [], min(remaining, 0.5))
            if ready and os.read(fd, 1) in _DISMISS_KEYS:
                return
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _wait_key_windows(timeout_s: float) -> None:
    import msvcrt

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if msvcrt.kbhit() and msvcrt.getch() in _DISMISS_KEYS:
            return
        time.sleep(0.05)


def emit_fallback(question: str, answer: str) -> None:
    """Non-TTY path: plain transcript message via the message queue."""
    from code_puppy.messaging import emit_info

    emit_info(f"/btw {question}\n\n{answer}")


__all__ = [
    "DISMISS_TIMEOUT_S",
    "emit_fallback",
    "is_tty",
    "show_answer",
    "show_asking",
    "wait_for_dismiss",
]
