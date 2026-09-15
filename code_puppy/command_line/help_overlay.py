"""Fullscreen, vi-cheat-sheet-style help overlay on the termflow Pager.

Opened on Tab when the input buffer is empty; both REPL input paths
(``line_editor.py`` and ``prompt_toolkit_completion.py``) call
``show_help_overlay()``. It closes on Tab, Esc, Enter, or q, so no
"is help open?" state lives outside this module for the two paths to
keep in sync.

Callers are responsible for freeing stdin first (both paths already
suspend their UI -- ``suspended_run_ui()`` / ``run_in_terminal`` --
before invoking this), so the Pager can own raw mode + the alt screen
for its blocking lifetime.
"""

from __future__ import annotations

import threading

from code_puppy.command_line.help_catalog import HelpSection, build_help_sections

_TITLE = "CODE PUPPY -- HELP"
_FOOTER = "Tab / Esc / q close - arrows or j/k scroll - g/G jump"


def _column_width(sections: list) -> int:
    widest = 0
    for section in sections:
        for entry in section.entries:
            widest = max(widest, len(entry.left))
    return min(max(widest, 12), 60)


def _render_sheet_text(sections: list) -> str:
    """Render sections into plain vi/vim-cheat-sheet-style text."""
    width = _column_width(sections)
    lines: list = []
    for section in sections:
        lines.append(section.title.upper())
        lines.append("-" * len(section.title))
        for entry in section.entries:
            label = entry.left.ljust(width)
            if entry.right:
                lines.append(f"  {label}  {entry.right}")
            else:
                lines.append(f"  {label}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _build_pager(sections: list, **overrides):
    """Assemble the Pager. ``overrides`` map onto PagerBuilder setters."""
    from termflow.tui import Key, PagerBuilder
    from termflow.tui.pager import PagerResult

    from code_puppy.command_line.tui_style import menu_style

    builder = (
        PagerBuilder(_TITLE)
        .text(_render_sheet_text(sections))
        .footer_hint(_FOOTER)
        .on_key(Key.TAB, lambda _pager: PagerResult(key=Key.TAB))
    )
    style = menu_style()
    if style is not None:
        builder.style(style)
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


_launch_lock = threading.Lock()


def show_help_overlay() -> None:
    """Show the fullscreen help overlay, blocking until the user closes it.

    Runs synchronously on the calling thread -- the Pager owns raw mode
    and the alt screen itself, so no worker thread or event loop is
    needed (the callers have already released stdin).

    The lock guards a launch race: the raw-terminal path hops through
    ``run_coroutine_threadsafe`` and an executor before arriving here, so
    two fast Tab presses can both be scheduled before the first overlay
    owns the terminal. A losing caller becomes a no-op rather than a
    second widget fighting for the same stdin.
    """
    if not _launch_lock.acquire(blocking=False):
        return
    try:
        try:
            sections: list[HelpSection] = build_help_sections()
        except Exception:
            # A broken plugin's help text must not take the Tab key down.
            return
        try:
            _build_pager(sections).run()
        except Exception:
            pass
    finally:
        _launch_lock.release()
