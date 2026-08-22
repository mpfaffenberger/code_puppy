"""Fullscreen, vi/vim-cheat-sheet-style help overlay.

Opened on Tab when the input buffer is empty (see ``line_editor.py`` and
``prompt_toolkit_completion.py`` -- both REPL input paths wire into
``show_help_overlay()`` below). Closes itself on a second Tab, Esc, or q --
there is no persistent "is help open?" state living outside this module,
so the two input paths never need to agree on shared toggle state.

A module-level lock guards against a *launch* race: the raw-terminal path
(``line_editor.py``) hops from the key-listener thread through
``asyncio.run_coroutine_threadsafe`` and an executor before this function
ever runs, so two Tab presses in quick succession (key repeat, a fast
double-tap, or a pasted ``\\t\\t``) can both get scheduled before the first
overlay has actually started reading the terminal. Without the lock that
races two fullscreen ``Application``s for the same stdin/stdout. Once the
first overlay is actually running it owns the terminal and its own Tab/Esc/
q bindings close it normally -- the lock only needs to cover that narrow
launch window.
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
    # Keep it sane even if some plugin registers a novel-length label.
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

    # Vi-style nav on top of TextArea's default cursor-movement bindings
    # (arrows / PageUp / PageDown / Home / End already work out of the box).
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
    """Show the fullscreen help overlay and block until the user closes it.

    Safe to call from any synchronous context (the raw line editor's
    key-listener thread, or a prompt_toolkit key binding handler) -- runs
    its own event loop on a worker thread, same house pattern as the other
    menus (see e.g. ``config_commands.py``'s ``interactive_*_picker`` calls).

    A non-blocking lock acquire makes a concurrent launch attempt (see the
    module docstring's "launch race" note) a silent no-op instead of a
    second competing fullscreen ``Application``. There is no timeout on
    ``future.result()`` -- this is a modal dialog the user closes on their
    own schedule, and killing it after an arbitrary duration would be a
    worse experience than just waiting for a real close key.
    """
    if not _launch_lock.acquire(blocking=False):
        return
    try:
        try:
            sections: list[HelpSection] = build_help_sections()
        except Exception:
            # A busted plugin's help text should never crash the REPL --
            # worst case, Tab silently does nothing instead of opening.
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
