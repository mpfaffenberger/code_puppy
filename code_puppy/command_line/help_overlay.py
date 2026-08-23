"""Fullscreen, vi-cheat-sheet-style help overlay.

Opened on Tab when the input buffer is empty; both REPL input paths
(``line_editor.py`` and ``prompt_toolkit_completion.py``) call
``show_help_overlay()``. It closes on Tab, Esc, or q, so no "is help open?"
state lives outside this module for the two paths to keep in sync.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea

from code_puppy.callbacks import on_prompt_toolkit_style
from code_puppy.command_line.help_catalog import HelpSection, build_help_sections

_HEADER = "CODE PUPPY -- HELP  (Tab / Esc / q to close, arrows or j/k to scroll)"


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


def _build_application(sections: list) -> Application:
    body_text = _render_sheet_text(sections)

    kb = KeyBindings()

    @kb.add("tab")
    @kb.add("escape")
    @kb.add("q")
    @kb.add("c-c")
    def _close(event) -> None:
        event.app.exit()

    # TextArea already handles arrows / PageUp / PageDown / Home / End.
    @kb.add("j")
    def _down(event) -> None:
        event.current_buffer.cursor_down()

    @kb.add("k")
    def _up(event) -> None:
        event.current_buffer.cursor_up()

    @kb.add("g", "g")
    def _top(event) -> None:
        event.current_buffer.cursor_position = 0

    @kb.add("G")
    def _bottom(event) -> None:
        event.current_buffer.cursor_position = len(event.current_buffer.text)

    header = Window(
        content=FormattedTextControl(FormattedText([("bold reverse", _HEADER)])),
        height=1,
    )
    body = TextArea(
        text=body_text,
        read_only=True,
        scrollbar=True,
        line_numbers=False,
        wrap_lines=False,
        focus_on_click=True,
    )

    layout = Layout(HSplit([header, body]), focused_element=body)

    return Application(
        layout=layout,
        key_bindings=kb,
        full_screen=True,
        mouse_support=True,
        color_depth="DEPTH_24_BIT",
        style=on_prompt_toolkit_style(),
    )


async def _run_help_overlay_async(sections: list) -> None:
    app = _build_application(sections)
    await app.run_async()


_launch_lock = threading.Lock()


def show_help_overlay() -> None:
    """Show the fullscreen help overlay, blocking until the user closes it.

    Safe to call from any synchronous context -- the raw editor's
    key-listener thread or a prompt_toolkit key binding -- since it runs
    its own event loop on a worker thread.

    The lock guards a launch race: the raw-terminal path hops through
    ``run_coroutine_threadsafe`` and an executor before arriving here, so
    two fast Tab presses can both be scheduled before the first overlay
    owns the terminal. A losing caller becomes a no-op rather than a second
    ``Application`` fighting for the same stdin. ``future.result()`` is
    deliberately untimed -- the user closes this on their own schedule.
    """
    if not _launch_lock.acquire(blocking=False):
        return
    try:
        try:
            sections: list[HelpSection] = build_help_sections()
        except Exception:
            # A broken plugin's help text must not take the Tab key down.
            return
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(
                lambda: asyncio.run(_run_help_overlay_async(sections))
            )
            try:
                future.result()
            except Exception:
                pass
    finally:
        _launch_lock.release()
