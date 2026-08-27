"""Entry points for ``/resume``: the session browser + resumed-history echo.

The interactive picker is the two-pane project/session browser in
:mod:`code_puppy.command_line.session_browser`; this module keeps the
stable public seams (``interactive_autosave_picker``,
``display_resumed_history``) that ``cli_runner`` and the command layer
import.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Optional

from code_puppy.command_line.autosave_search import SessionContentIndex
from code_puppy.command_line.menu_session import menu_session
from code_puppy.command_line.session_browser import (
    _extract_message_content,
    _prewarm,
    build_session_browser,
)
from code_puppy.command_line.session_browser_data import (
    SessionEntry,
    _get_session_entries,
    _get_session_metadata,
)
from code_puppy.config import AUTOSAVE_DIR
from code_puppy.tools.command_runner import set_awaiting_user_input

__all__ = [
    "interactive_autosave_picker",
    "display_resumed_history",
    "_get_session_entries",
    "_get_session_metadata",
]


async def interactive_autosave_picker() -> Optional[str]:
    """Run the two-pane session browser; return the chosen session name."""
    base_dir = Path(AUTOSAVE_DIR)
    pairs = _get_session_entries(base_dir)
    if not pairs:
        from code_puppy.messaging import emit_info

        emit_info("No autosave sessions found.")
        return None
    entries = [SessionEntry.from_pair(name, meta) for name, meta in pairs]
    try:
        # Plugins enrich the LIVE metadata dicts (AI titles, tags) in the
        # background; the browser picks changes up on its next repaint.
        from code_puppy.callbacks import on_session_browser_open

        await on_session_browser_open(
            str(base_dir), [(entry.name, entry.meta) for entry in entries]
        )
    except Exception:
        pass  # decorative: the browser must open regardless
    index = SessionContentIndex()
    threading.Thread(
        target=_prewarm, args=(base_dir, entries, index), daemon=True
    ).start()
    browser = build_session_browser(entries, base_dir, index, use_alt_screen=False)
    set_awaiting_user_input(True)
    try:
        with menu_session():
            result = await asyncio.to_thread(browser.run)
    finally:
        set_awaiting_user_input(False)
    return result.session if not result.cancelled else None


DEFAULT_RESUME_DISPLAY_COUNT = 50


def display_resumed_history(history: list, num_messages: int | None = None) -> None:
    from rich.console import Console
    from rich.rule import Rule

    from code_puppy.config import get_banner_color, get_resume_message_count
    from code_puppy.tools.display import render_markdown

    if not history:
        return
    num_messages = get_resume_message_count() if num_messages is None else num_messages
    if num_messages <= 0 or len(history) <= 1:
        return
    console, displayable = Console(), history[1:]
    shown = displayable[-num_messages:]
    console.print()
    if len(displayable) > len(shown):
        console.print(
            Rule(f"{len(displayable) - len(shown)} earlier messages", style="dim")
        )
        console.print()
    color = get_banner_color("agent_response")
    for msg in shown:
        role, content = _extract_message_content(msg)
        if role == "user":
            console.print("[dim]> [/dim]", end="")
            console.print(f"[bold]{content}[/bold]")
        elif role == "tool":
            console.print(f"[dim]{content}[/dim]")
        else:
            console.print(
                f"\n[bold white on {color}] AGENT RESPONSE [/bold white on {color}]"
            )
            render_markdown(content, console)
        console.print()
    console.print(Rule("Session Resumed", style="bold green"))
    console.print()
