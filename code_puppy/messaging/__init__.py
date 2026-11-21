"""The 0.0.x ``emit_*`` functions, printing through the runtime's console.

0.0.x plugins report with ``emit_info`` and friends. 1.0 has no message bus:
the compat bridge hands over the session's console, and these print to it.
Before a session exists they print to stderr, which the splash defers.
"""

from __future__ import annotations

from rich.console import Console
from rich.errors import MarkupError

STYLES = {
    "info": None,
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "system": "dim",
}

_console: Console | None = None
_fallback: Console | None = None


def set_console(console: Console | None) -> None:
    """Route ``emit_*`` output to ``console``; ``None`` restores the stderr fallback."""
    global _console
    _console = console


def get_console() -> Console:
    global _fallback
    if _console is not None:
        return _console
    if _fallback is None:
        _fallback = Console(stderr=True)
    return _fallback


def _emit(kind: str, content: object) -> None:
    console, style = get_console(), STYLES[kind]
    if not isinstance(content, str):
        console.print(content, style=style)
        return
    # `highlight=False`: a message is prose, not a Python repr for Rich to recolour.
    try:
        console.print(content, style=style, highlight=False)
    except MarkupError:
        # Plain text that only looks like markup, such as "[/path]".
        console.print(content, style=style, markup=False, highlight=False)


def emit_info(content: object = "", *args: object, **metadata: object) -> None:
    _emit("info", content)


def emit_success(content: object = "", *args: object, **metadata: object) -> None:
    _emit("success", content)


def emit_warning(content: object = "", *args: object, **metadata: object) -> None:
    _emit("warning", content)


def emit_error(content: object = "", *args: object, **metadata: object) -> None:
    _emit("error", content)


def emit_system_message(
    content: object = "", *args: object, **metadata: object
) -> None:
    _emit("system", content)


def emit_debug(content: object = "", *args: object, **metadata: object) -> None:
    """Debug chatter from 0.0.x plugins is dropped."""


__all__ = [
    "emit_debug",
    "emit_error",
    "emit_info",
    "emit_success",
    "emit_system_message",
    "emit_warning",
    "get_console",
    "set_console",
]
