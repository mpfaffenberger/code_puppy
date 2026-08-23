"""Termflow session browser used by ``/resume``."""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import List, Optional, Tuple

from rich.console import Console
from rich.markdown import Markdown
from termflow.ansi.codes import BOLD_ON, DIM_ON, RESET
from termflow.tui import MenuBuilder, MenuItem
from termflow.tui.menu import MenuResult

from code_puppy.command_line.autosave_search import (
    SessionContentIndex,
    entry_matches,
    iter_alphabet_bindings,
)
from code_puppy.command_line.menu_session import menu_session
from code_puppy.command_line.tui_style import themed
from code_puppy.config import AUTOSAVE_DIR
from code_puppy.session_storage import compute_scope_key, list_sessions, load_session
from code_puppy.tools.command_runner import set_awaiting_user_input


def _get_session_metadata(base_dir: Path, session_name: str) -> dict:
    try:
        with (base_dir / f"{session_name}_meta.json").open(encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def _get_session_entries(base_dir: Path) -> List[Tuple[str, dict]]:
    try:
        sessions = list_sessions(base_dir)
    except (FileNotFoundError, PermissionError):
        return []
    entries = []
    for name in sessions:
        try:
            metadata = _get_session_metadata(base_dir, name)
        except (FileNotFoundError, PermissionError):
            metadata = {}
        entries.append((name, metadata))

    def key(entry):
        try:
            return datetime.fromisoformat(entry[1].get("timestamp", ""))
        except (TypeError, ValueError):
            return datetime.min

    return sorted(entries, key=key, reverse=True)


def _extract_last_user_message(history: list) -> str:
    for msg in reversed(history):
        parts = [
            part.content
            for part in msg.parts
            if isinstance(getattr(part, "content", None), str) and part.content.strip()
        ]
        if parts:
            return "\n\n".join(parts)
    return "[No messages found]"


def _extract_message_content(msg) -> Tuple[str, str]:
    kinds = [getattr(part, "part_kind", "unknown") for part in msg.parts]
    if msg.kind == "request":
        role = "tool" if all(kind == "tool-return" for kind in kinds) else "user"
    else:
        role = "tool" if all(kind == "tool-call" for kind in kinds) else "assistant"
    content = []
    for part in msg.parts:
        kind = getattr(part, "part_kind", "unknown")
        if kind == "tool-call":
            name, args = (
                getattr(part, "tool_name", "unknown"),
                getattr(part, "args", {}),
            )
            suffix = (
                f"\n   Args: {str(args)[:100]}{'...' if len(str(args)) > 100 else ''}"
                if args
                else ""
            )
            content.append(f"Tool Call: {name}{suffix}")
        elif kind == "tool-return":
            name, result = (
                getattr(part, "tool_name", "unknown"),
                getattr(part, "content", ""),
            )
            preview = result[:200].replace("\n", " ") if isinstance(result, str) else ""
            if isinstance(result, str) and len(result) > 200:
                preview += "..."
            content.append(
                f"\U0001f4e5 Tool Result: {name}"
                + (f"\n   {preview}" if preview else "")
            )
        elif isinstance(getattr(part, "content", None), str) and part.content.strip():
            content.append(part.content)
    return role, "\n\n".join(content) if content else "[No content]"


def _markdown(text: str, width: int = 72) -> str:
    stream = StringIO()
    Console(file=stream, force_terminal=False, width=width).print(Markdown(text))
    return stream.getvalue().rstrip()


def _render_message_browser_panel(
    history: list, message_idx: int, session_name: str
) -> list:
    if not history:
        return [
            ("class:tui.warning", "MESSAGE BROWSER\n\nNo messages in this session.")
        ]
    message_idx = max(0, min(message_idx, len(history) - 1))
    role, content = _extract_message_content(history[-1 - message_idx])
    rendered = content if role == "tool" else _markdown(content)
    return [
        (
            "class:tui.header",
            f"MESSAGE BROWSER\n\nSession: {session_name}\nMessage {message_idx + 1} of {len(history)}\n\n{role.upper()}\n{'─' * 40}\n{rendered}\n\nUp older  Down newer  Esc exit",
        )
    ]


def _render_preview_panel(base_dir: Path, entry: Optional[Tuple[str, dict]]) -> list:
    if not entry:
        return [("class:tui.warning", "PREVIEW\n\nNo session selected.")]
    name, metadata = entry
    timestamp = metadata.get("timestamp", "unknown")
    try:
        timestamp = datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        pass
    try:
        message = _markdown(
            _extract_last_user_message(load_session(name, base_dir)), 76
        )
    except Exception as exc:
        message = f"Error loading preview: {exc}"
    text = f"PREVIEW\n\nSession: {name}\nSaved: {timestamp}\nMessages: {metadata.get('message_count', 0)} • Tokens: {metadata.get('total_tokens', 0):,}\n\nLast Message:\n(press 'e' to browse full history)\n{message}"
    return [("class:tui.muted", text)]


def _fragments_to_ansi(fragments: list) -> str:
    styles = {
        "class:tui.header": BOLD_ON,
        "class:tui.title": BOLD_ON,
        "class:tui.label": BOLD_ON,
        "class:tui.muted": DIM_ON,
    }
    return "".join(
        f"{styles.get(style, '')}{text}{RESET if style else ''}"
        for style, text in fragments
    )


def _description(metadata: dict) -> str:
    try:
        when = datetime.fromisoformat(metadata.get("timestamp", "")).strftime(
            "%Y-%m-%d %H:%M"
        )
    except (TypeError, ValueError):
        when = "unknown time"
    return f"{metadata.get('message_count', '?')} msgs - {when}"


def _items(entries: List[Tuple[str, dict]]) -> list[MenuItem]:
    return [
        MenuItem(name, value=name, description=_description(meta))
        for name, meta in entries
    ]


def build_resume_menu(entries=None, base_dir=None, content_index=None, **overrides):
    """Build a headlessly driveable termflow resume menu."""
    base_dir = Path(AUTOSAVE_DIR) if base_dir is None else Path(base_dir)
    entries = _get_session_entries(base_dir) if entries is None else list(entries)
    content_index = content_index or SessionContentIndex()
    state = {
        "all": entries,
        "search_filtered": list(entries),
        "visible": list(entries),
        "search": "",
        "buffer": "",
        "mode": "list",
        "scope": False,
        "history": None,
        "message": 0,
        "indexed": len(entries),
    }
    by_name = {name: (name, meta) for name, meta in entries}
    scope_key = compute_scope_key(Path.cwd())

    def current(item):
        return by_name.get(item.value)

    def apply(menu, filtered):
        state["search_filtered"] = filtered
        state["visible"] = [
            e
            for e in filtered
            if not state["scope"] or e[1].get("scope_key") == scope_key
        ]
        menu.replace_items(_items(state["visible"]))
        refresh(menu)

    def refresh(menu):
        progress = content_index.count()
        if state["mode"] == "search":
            menu._title = f"Sessions - Searching: '{state['buffer']}'"
        elif state["search"]:
            menu._title = f"Sessions - Filter: '{state['search']}'"
        else:
            menu._title = "Sessions"
        scope = " - this folder only" if state["scope"] else ""
        indexing = (
            f" - Indexing {progress}/{len(entries)}..."
            if progress < len(entries)
            else ""
        )
        menu._footer_hint = f"Up/Down navigate - Left/Right page - E browse - / search - Ctrl+T scope - Enter load - Esc cancel{scope}{indexing}"

    def preview(item):
        entry = current(item)
        fragments = (
            _render_message_browser_panel(
                state["history"] or [], state["message"], item.value
            )
            if state["mode"] == "browse"
            else _render_preview_panel(base_dir, entry)
        )
        return _fragments_to_ansi(fragments)

    def move(delta):
        def handler(menu, _item):
            if state["mode"] == "search":
                return None
            if state["mode"] == "browse":
                limit = len(state["history"] or []) - 1
                state["message"] = max(0, min(state["message"] + (-delta), limit))
            else:
                menu._move_cursor(menu._filtered(), delta)
            refresh(menu)
            return None

        return handler

    def page(direction):
        def handler(menu, _item):
            if state["mode"] == "list":
                menu.page_up() if direction < 0 else menu.page_down()
            return None

        return handler

    def browse(menu, item):
        if state["mode"] == "search":
            state["buffer"] += "e"
        elif state["mode"] == "list":
            try:
                state["history"] = load_session(item.value, base_dir)
                state["message"], state["mode"] = 0, "browse"
            except Exception:
                pass
        refresh(menu)
        return None

    def escape(menu, _item):
        if state["mode"] == "search":
            state["mode"], state["buffer"] = "list", ""
            refresh(menu)
            return None
        if state["mode"] == "browse":
            state["mode"], state["history"], state["message"] = "list", None, 0
            refresh(menu)
            return None
        return MenuResult(cancelled=True)

    def enter(menu, item):
        if state["mode"] != "search":
            return MenuResult(item=item)
        state["search"], state["buffer"], state["mode"] = state["buffer"], "", "list"
        filtered = [
            e
            for e in entries
            if entry_matches(e, state["search"], content_index, base_dir)
        ]
        apply(menu, filtered)
        return None

    def search(menu, _item):
        if state["mode"] == "list":
            state["mode"], state["buffer"] = "search", ""
            refresh(menu)
        return None

    def scope(menu, _item):
        if state["mode"] == "list":
            state["scope"] = not state["scope"]
            apply(menu, state["search_filtered"])
        return None

    def backspace(menu, _item):
        if state["mode"] == "search":
            state["buffer"] = state["buffer"][:-1]
            refresh(menu)
        return None

    def char_handler(char):
        def handler(menu, _item):
            if state["mode"] == "search":
                state["buffer"] += char
                refresh(menu)
            elif state["mode"] == "browse" and char == "q":
                escape(menu, _item)
            return None

        return handler

    builder = themed(
        MenuBuilder("Sessions")
        .items(_items(entries))
        .list_width(36)
        .preview(preview)
        .on_key("up", move(-1))
        .on_key("ctrl-p", move(-1))
        .on_key("down", move(1))
        .on_key("ctrl-n", move(1))
        .on_key("left", page(-1))
        .on_key("right", page(1))
        .on_key("e", browse)
        .on_key("E", browse)
        .on_key("/", search)
        .on_key("ctrl-t", scope)
        .on_key("backspace", backspace)
        .on_key("escape", escape)
        .on_key("enter", enter)
        .on_key("q", char_handler("q"))
        .on_key("Q", char_handler("q"))
        .footer_hint(
            "Up/Down navigate - Left/Right page - E browse - / search - Ctrl+T scope - Enter load - Esc cancel"
        )
    )
    for key, char in iter_alphabet_bindings():
        builder.on_key(key, char_handler(char))
    for name, value in overrides.items():
        getattr(builder, name)(value)
    menu = builder.build()
    menu.resume_state = state
    return menu


def _prewarm(index: SessionContentIndex, entries, base_dir: Path) -> None:
    for name, _ in entries:
        if name not in index:
            index.lookup(name, base_dir)


async def interactive_autosave_picker() -> Optional[str]:
    base_dir = Path(AUTOSAVE_DIR)
    entries = _get_session_entries(base_dir)
    if not entries:
        from code_puppy.messaging import emit_info

        emit_info("No autosave sessions found.")
        return None
    index = SessionContentIndex()
    threading.Thread(
        target=_prewarm, args=(index, entries, base_dir), daemon=True
    ).start()
    menu = build_resume_menu(entries, base_dir, index, alt_screen=False)
    set_awaiting_user_input(True)
    try:
        with menu_session():
            result = await asyncio.to_thread(menu.run)
    finally:
        set_awaiting_user_input(False)
    return result.item.value if result.item and not result.cancelled else None


DEFAULT_RESUME_DISPLAY_COUNT = 50


def display_resumed_history(history: list, num_messages: int | None = None) -> None:
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
