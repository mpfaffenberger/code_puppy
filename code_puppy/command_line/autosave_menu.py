"""Interactive terminal UI for loading autosave sessions.

Provides a beautiful split-panel interface for browsing and loading
autosave sessions with live preview of message content.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import List, Optional, Tuple

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame
from rich.console import Console
from rich.markdown import Markdown

from code_puppy.command_line.autosave_search import (
    SessionContentIndex,
    entry_matches,
    iter_alphabet_bindings,
)
from code_puppy.command_line.pagination import (
    ensure_visible_page,
    get_page_bounds,
    get_page_for_index,
    get_total_pages,
)
from code_puppy.callbacks import on_prompt_toolkit_style
from code_puppy.config import AUTOSAVE_DIR
from code_puppy.session_storage import (
    list_sessions,
    load_pins,
    load_session,
    toggle_pin,
)
from code_puppy.tools.command_runner import set_awaiting_user_input

logger = logging.getLogger(__name__)

PAGE_SIZE = 15  # Sessions per page


def _get_session_metadata(base_dir: Path, session_name: str) -> dict:
    """Load metadata for a session."""
    meta_path = base_dir / f"{session_name}_meta.json"
    try:
        with meta_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _order_entries(
    entries: List[Tuple[str, dict]],
) -> List[Tuple[str, dict]]:
    """Order entries for display: pinned first, then most-recent-first.

    Pin state is read from each entry's ``metadata['pinned']`` flag
    (populated by :func:`_get_session_entries`). Pulled out as a standalone
    helper so the initial load and the live pin-toggle share one ordering rule.
    """

    def sort_key(entry):
        _, metadata = entry
        timestamp = metadata.get("timestamp")
        if timestamp:
            try:
                return datetime.fromisoformat(timestamp)
            except ValueError:
                return datetime.min
        return datetime.min

    pinned = [e for e in entries if e[1].get("pinned")]
    rest = [e for e in entries if not e[1].get("pinned")]
    pinned.sort(key=sort_key, reverse=True)
    rest.sort(key=sort_key, reverse=True)
    return pinned + rest


def _get_session_entries(base_dir: Path) -> List[Tuple[str, dict]]:
    """Get all sessions with their metadata, most recent first."""
    try:
        sessions = list_sessions(base_dir)
    except (FileNotFoundError, PermissionError):
        return []

    entries = []
    pins = load_pins(base_dir)

    for name in sessions:
        try:
            metadata = _get_session_metadata(base_dir, name)
        except (FileNotFoundError, PermissionError):
            metadata = {}
        # Stash pin state in the (display-only) metadata dict so the renderer
        # can show a marker without re-reading the registry per row.
        metadata["pinned"] = name in pins
        entries.append((name, metadata))

    return _order_entries(entries)


def _extract_last_user_message(history: list) -> str:
    """Extract the most recent user message from history.

    Joins all content parts from the message since messages can have
    multiple parts (e.g., text + attachments, multi-part prompts).
    """
    # Walk backwards through history to find last user message
    for msg in reversed(history):
        content_parts = []
        for part in msg.parts:
            if hasattr(part, "content"):
                content = part.content
                if isinstance(content, str) and content.strip():
                    content_parts.append(content)
        if content_parts:
            return "\n\n".join(content_parts)
    return "[No messages found]"


def _extract_message_content(msg) -> Tuple[str, str]:
    """Extract role and content from a message.

    Returns:
        Tuple of (role, content) where role is 'user', 'assistant', or 'tool'
    """
    # Determine role based on message kind AND part types
    # tool-return comes in a 'request' message but it's not from the user
    part_kinds = [getattr(p, "part_kind", "unknown") for p in msg.parts]

    if msg.kind == "request":
        # Check if this is a tool return (not actually user input)
        if all(pk == "tool-return" for pk in part_kinds):
            role = "tool"
        else:
            role = "user"
    else:
        # Response from assistant
        if all(pk == "tool-call" for pk in part_kinds):
            role = "tool"  # Pure tool call, label as tool activity
        else:
            role = "assistant"

    # Extract content from parts, handling different part types
    content_parts = []
    for part in msg.parts:
        part_kind = getattr(part, "part_kind", "unknown")

        if part_kind == "tool-call":
            # Assistant is calling a tool - show tool name and args preview
            tool_name = getattr(part, "tool_name", "unknown")
            args = getattr(part, "args", {})
            # Create a condensed args preview
            if args:
                args_preview = str(args)[:100]
                if len(str(args)) > 100:
                    args_preview += "..."
                content_parts.append(f"Tool Call: {tool_name}\n   Args: {args_preview}")
            else:
                content_parts.append(f"Tool Call: {tool_name}")

        elif part_kind == "tool-return":
            # Tool result being returned - show tool name and truncated result
            tool_name = getattr(part, "tool_name", "unknown")
            result = getattr(part, "content", "")
            if isinstance(result, str) and result.strip():
                # Truncate long results
                preview = result[:200].replace("\n", " ")
                if len(result) > 200:
                    preview += "..."
                content_parts.append(f"📥 Tool Result: {tool_name}\n   {preview}")
            else:
                content_parts.append(f"📥 Tool Result: {tool_name}")

        elif hasattr(part, "content"):
            # Regular text content (user-prompt, text, thinking, etc.)
            content = part.content
            if isinstance(content, str) and content.strip():
                content_parts.append(content)

    content = "\n\n".join(content_parts) if content_parts else "[No content]"
    return role, content


def _render_menu_panel(
    entries: List[Tuple[str, dict]],
    page: int,
    selected_idx: int,
    browse_mode: bool = False,
    search_text: str = "",
    in_search_mode: bool = False,
    search_buffer: str = "",
    status_line: Optional[Tuple[str, str]] = None,
) -> List:
    """Render the left menu panel with pagination.

    ``status_line`` is an optional ``(style, text)`` pair that, when
    provided, replaces the normal search/filter indicator. The picker
    uses it to surface transient states like ``Filtering...`` (right
    after the user commits a search) and ``Indexing N/M...`` (while the
    background pre-warm task is still chewing through sessions).
    """
    lines = []
    total_pages = get_total_pages(len(entries), PAGE_SIZE)
    start_idx, end_idx = get_page_bounds(page, len(entries), PAGE_SIZE)

    lines.append(("", f" Session Page(s): ({page + 1}/{total_pages})"))
    if status_line is not None:
        lines.append(("", "\n"))
        lines.append(status_line)
    elif in_search_mode:
        lines.append(("", "\n"))
        lines.append(("class:tui.input.focused", f"  Searching: '{search_buffer}'"))
    elif search_text:
        lines.append(("", "\n"))
        lines.append(("class:tui.warning", f"  Filter: '{search_text}'"))
    lines.append(("", "\n\n"))

    if not entries:
        if search_text or in_search_mode:
            lines.append(("class:tui.warning", "  No sessions match your search."))
        else:
            lines.append(("class:tui.warning", "  No autosave sessions found."))
        lines.append(("", "\n\n"))
        # Navigation hints (always show)
        lines.append(("", "\n"))
        lines.append(("class:tui.muted", "  ↑/↓ "))
        lines.append(("", "Navigate\n"))
        lines.append(("class:tui.muted", "  ←/→ "))
        lines.append(("", "Page\n"))
        lines.append(("class:tui.help-key", "  Enter  "))
        lines.append(("", "Load\n"))
        lines.append(("class:tui.help-key", "  Ctrl+C "))
        lines.append(("", "Cancel"))
        return lines

    for i in range(start_idx, end_idx):
        session_name, metadata = entries[i]
        is_selected = i == selected_idx

        # Format timestamp
        timestamp = metadata.get("timestamp", "unknown")
        try:
            dt = datetime.fromisoformat(timestamp)
            time_str = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            time_str = "unknown time"

        # Format message count. auto_session_* names are opaque noise — hide them.
        # User-named sessions keep the parenthetical so they stay distinguishable.
        msg_count = metadata.get("message_count", "?")
        if session_name.startswith("auto_session_"):
            label = f"{time_str} \u2022 {msg_count} msgs"
        else:
            label = f"{time_str} \u2022 {msg_count} msgs ({session_name})"

        # Highlight selected item
        is_session_pinned = bool(metadata.get("pinned"))
        row_style = "class:tui.selected" if is_selected else "class:tui.muted"
        caret = " > " if is_selected else "   "
        lines.append((row_style, caret))
        # Pin marker column (keeps rows aligned when not pinned).
        if is_session_pinned:
            lines.append(("class:tui.success", "* "))
        else:
            lines.append(("", "  "))
        lines.append((row_style, label))

        lines.append(("", "\n"))

    # Navigation hints - change based on browse mode
    lines.append(("", "\n"))
    if browse_mode:
        lines.append(("class:tui.help-key", "  ↑/↓ "))
        lines.append(("", "Browse msgs\n"))
        lines.append(("class:tui.help-key", "  Esc "))
        lines.append(("", "Exit browser\n"))
    else:
        lines.append(("class:tui.muted", "  ↑/↓ "))
        lines.append(("", "Navigate\n"))
        lines.append(("class:tui.muted", "  ←/→ "))
        lines.append(("", "Page\n"))
        lines.append(("class:tui.help-key", "  e   "))
        lines.append(("", "Browse msgs\n"))
        lines.append(("class:tui.help-key", "  /   "))
        lines.append(("", "Search content\n"))
        lines.append(("class:tui.help-key", "  p   "))
        lines.append(("", "Pin/Unpin\n"))
    lines.append(("class:tui.help-key", "  Enter  "))
    lines.append(("", "Load\n"))
    lines.append(("class:tui.help-key", "  Ctrl+C "))
    lines.append(("", "Cancel"))

    return lines


def _render_message_browser_panel(
    history: list,
    message_idx: int,
    session_name: str,
) -> List:
    """Render the message browser panel showing a single message.

    Args:
        history: Full message history list
        message_idx: Index into history (0 = most recent)
        session_name: Name of the session being browsed
    """
    lines = []

    lines.append(("class:tui.header", " MESSAGE BROWSER"))
    lines.append(("", "\n\n"))

    total_messages = len(history)
    if total_messages == 0:
        lines.append(("class:tui.warning", "  No messages in this session."))
        lines.append(("", "\n"))
        return lines

    # Clamp index to valid range
    message_idx = max(0, min(message_idx, total_messages - 1))

    # Get message (reverse index so 0 = most recent)
    actual_idx = total_messages - 1 - message_idx
    msg = history[actual_idx]

    # Extract role and content
    role, content = _extract_message_content(msg)

    # Session info
    lines.append(("class:tui.muted", f"  Session: {session_name}"))
    lines.append(("", "\n"))

    # Message position indicator
    display_num = message_idx + 1  # 1-based for display
    lines.append(("class:tui.label", f"  Message {display_num} of {total_messages}"))
    lines.append(("", "\n\n"))

    # Role indicator with icon and color
    if role == "user":
        lines.append(("class:tui.title", "  \U0001f9d1 USER"))
    elif role == "tool":
        lines.append(("class:tui.warning", "  TOOL"))
    else:
        lines.append(("class:tui.success", "  \U0001f916 ASSISTANT"))
    lines.append(("", "\n"))

    # Separator line
    lines.append(("class:tui.muted", "  " + "─" * 40))
    lines.append(("", "\n"))

    # Render content - use markdown for user/assistant, plain text for tool
    try:
        if role == "tool":
            # Tool messages are already formatted, don't pass through markdown
            # Use yellow color for tool output
            rendered = content
            text_color = "class:tui.warning"
        else:
            # User and assistant messages should be rendered as markdown
            # Rich will handle the styling via ANSI codes
            console = Console(
                file=StringIO(),
                legacy_windows=False,
                no_color=False,
                force_terminal=False,
                width=72,
            )
            md = Markdown(content)
            console.print(md)
            rendered = console.file.getvalue()
            # Don't override Rich's ANSI styling - use empty style
            text_color = ""

        # Show full message without truncation
        message_lines = rendered.split("\n")

        for line in message_lines:
            lines.append((text_color, f"  {line}"))
            lines.append(("", "\n"))

    except Exception as e:
        lines.append(("class:tui.error", f"  Error rendering message: {e}"))
        lines.append(("", "\n"))

    # Navigation hint at bottom
    lines.append(("", "\n"))
    lines.append(("class:tui.help", "  ↑ older  ↓ newer  Esc exit"))
    lines.append(("", "\n"))

    return lines


def _render_preview_panel(base_dir: Path, entry: Optional[Tuple[str, dict]]) -> List:
    """Render the right preview panel with message content using rich markdown."""
    lines = []

    lines.append(("class:tui.title", " PREVIEW"))
    lines.append(("", "\n\n"))

    if not entry:
        lines.append(("class:tui.warning", "  No session selected."))
        lines.append(("", "\n"))
        return lines

    session_name, metadata = entry

    # Show metadata
    lines.append(("class:tui.label", "  Session: "))
    lines.append(("", session_name))
    lines.append(("", "\n"))

    if metadata.get("pinned"):
        lines.append(("class:tui.success", "  * Pinned"))
        lines.append(("", "\n"))

    timestamp = metadata.get("timestamp", "unknown")
    try:
        dt = datetime.fromisoformat(timestamp)
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        time_str = timestamp
    lines.append(("class:tui.muted", f"  Saved: {time_str}"))
    lines.append(("", "\n"))

    msg_count = metadata.get("message_count", 0)
    tokens = metadata.get("total_tokens", 0)
    lines.append(("class:tui.muted", f"  Messages: {msg_count} • Tokens: {tokens:,}"))
    lines.append(("", "\n\n"))

    lines.append(("class:tui.label", "  Last Message:"))
    lines.append(("class:tui.muted", "  (press 'e' to browse full history)"))
    lines.append(("", "\n"))

    # Try to load and preview the last message
    try:
        history = load_session(session_name, base_dir)
        last_message = _extract_last_user_message(history)

        # Render markdown with rich
        console = Console(
            file=StringIO(),
            legacy_windows=False,
            no_color=False,
            force_terminal=False,
            width=76,
        )
        md = Markdown(last_message)
        console.print(md)
        rendered = console.file.getvalue()

        # Show full message without truncation
        message_lines = rendered.split("\n")

        for line in message_lines:
            # Rich already rendered the markdown, just display it dimmed
            lines.append(("class:tui.muted", f"  {line}"))
            lines.append(("", "\n"))

    except Exception as e:
        lines.append(("class:tui.error", f"  Error loading preview: {e}"))
        lines.append(("", "\n"))

    return lines


# Default number of messages to display when resuming a session
# This is overridden by the user config 'resume_message_count'
DEFAULT_RESUME_DISPLAY_COUNT = 50


def display_resumed_history(
    history: list,
    num_messages: int | None = None,
) -> None:
    """Display recent message history after resuming a session.

    Shows the last N messages from the conversation so users have context
    about where they left off. Uses the same rendering style as normal chat.

    Args:
        history: The full message history list
        num_messages: Number of messages to display. If None, uses the
                      'resume_message_count' config value (default 50).
                      Configurable via: /set resume_message_count=50
    """
    from rich.console import Console
    from rich.rule import Rule

    from code_puppy.config import get_banner_color, get_resume_message_count
    from code_puppy.tools.display import render_markdown

    if not history:
        return

    # Use config value if num_messages not explicitly provided
    if num_messages is None:
        num_messages = get_resume_message_count()
    if num_messages <= 0:
        return
    console = Console()
    total_messages = len(history)

    # Skip if only system message exists
    if total_messages <= 1:
        return

    # Determine which messages to show (skip first system message)
    # We want to show the last N non-system messages
    displayable_history = history[1:]  # Skip system message
    total_displayable = len(displayable_history)

    if total_displayable == 0:
        return

    messages_to_show = (
        displayable_history[-num_messages:]
        if total_displayable > num_messages
        else displayable_history
    )
    hidden_count = total_displayable - len(messages_to_show)

    # Print header with hidden count if applicable
    console.print()
    if hidden_count > 0:
        console.print(
            Rule(
                f"{hidden_count} earlier messages",
                style="dim",
            )
        )
        console.print()

    # Get banner color for agent responses
    response_color = get_banner_color("agent_response")

    # Render each message in the same style as normal chat
    for msg in messages_to_show:
        role, content = _extract_message_content(msg)

        # Print banner matching normal chat style
        if role == "user":
            # User messages don't have a banner in normal chat,
            # but we add one for clarity in resumed history
            console.print("[dim]> [/dim]", end="")
            console.print(f"[bold]{content}[/bold]")
        elif role == "tool":
            # Tool output is typically dim/collapsed
            console.print(f"[dim]{content}[/dim]")
        else:  # assistant
            # Use the exact same banner format as normal AGENT RESPONSE
            banner = f"[bold white on {response_color}] AGENT RESPONSE [/bold white on {response_color}]"
            console.print(f"\n{banner}")
            # Resume uses the same Termflow pipeline as live agent output.
            render_markdown(content, console)

        console.print()  # Blank line between messages

    # Print footer separator
    console.print(Rule("Session Resumed", style="bold green"))
    console.print()


async def interactive_autosave_picker() -> Optional[str]:
    """Show interactive terminal UI to select an autosave session.

    Returns:
        Session name to load, or None if cancelled
    """
    base_dir = Path(AUTOSAVE_DIR)
    entries = _get_session_entries(base_dir)

    if not entries:
        from code_puppy.messaging import emit_info

        emit_info("No autosave sessions found.")
        return None

    # State
    selected_idx = [0]  # Current selection (index into visible_entries)
    current_page = [0]  # Current page
    result = [None]  # Selected session name

    # Browse mode state
    browse_mode = [False]  # Are we browsing messages within a session?
    message_idx = [0]  # Current message index (0 = most recent)
    cached_history = [None]  # Cached history for current session in browse mode

    # Search/filter state (mirrors set_menu.py's `/`-search UX)
    search_text = [""]  # Committed filter (drives visible_entries)
    in_search_mode = [False]  # Currently typing into the search buffer?
    search_buffer = [""]  # Live keystrokes before Enter commits them
    visible_entries: List[List[Tuple[str, dict]]] = [list(entries)]
    content_index = SessionContentIndex()  # Lazy content cache for THIS picker
    is_filtering = [False]  # True while the Enter-handler is doing the work
    total_to_index = len(entries)  # Denominator for the prewarm progress hint

    def get_current_entry() -> Optional[Tuple[str, dict]]:
        visible = visible_entries[0]
        if 0 <= selected_idx[0] < len(visible):
            return visible[selected_idx[0]]
        return None

    def _filter_entries(needle: str) -> List[Tuple[str, dict]]:
        """Pure filter: needle in, filtered list out. Safe to run off-thread.

        Reads ``entries``, ``content_index``, and ``base_dir`` from the
        enclosing closure -- ``entries`` is built once and never mutated,
        and ``content_index`` is protected by its own internal lock, so
        this is safe to invoke from an ``asyncio.to_thread`` worker.
        """
        if not needle:
            return _order_entries(list(entries))
        return _order_entries(
            [e for e in entries if entry_matches(e, needle, content_index, base_dir)]
        )

    def _apply_filter_result(filtered: List[Tuple[str, dict]]) -> None:
        """Apply a filter result to picker state. Must run on the main thread."""
        visible_entries[0] = filtered
        if not filtered:
            selected_idx[0] = 0
            current_page[0] = 0
            return
        selected_idx[0] = min(selected_idx[0], len(filtered) - 1)
        current_page[0] = get_page_for_index(selected_idx[0], PAGE_SIZE)

    def update_visible_entries() -> None:
        """Synchronous re-filter -- only safe when the cache is warm or empty.

        Used for the picker's initial setup (no filter active -> trivial)
        and as a fallback. The post-Enter path goes through
        :func:`asyncio.to_thread` instead so a cold-cache filter does not
        freeze the event loop.
        """
        _apply_filter_result(_filter_entries(search_text[0]))

    # Build UI
    menu_control = FormattedTextControl(text="")
    preview_control = FormattedTextControl(text="")

    def _compute_status_line() -> Optional[Tuple[str, str]]:
        """Resolve which transient indicator (if any) takes the header slot.

        Priority order:
          1. ``Filtering...`` -- user just hit Enter, filter is running.
          2. ``Searching: '...'`` / ``Filter: '...'`` -- normal search UX,
             handled by the renderer's own branches when this returns None.
          3. ``Indexing N/M...`` -- background pre-warm in progress and no
             other search activity to crowd out.
        """
        if is_filtering[0]:
            return ("class:tui.input.focused", "  Filtering...")
        if in_search_mode[0] or search_text[0]:
            return None  # Let the renderer show the search/filter line.
        cached = content_index.count()
        if 0 < cached < total_to_index:
            return (
                "class:tui.muted",
                f"  Indexing {cached}/{total_to_index}...",
            )
        return None

    def update_display():
        """Update both panels."""
        menu_control.text = _render_menu_panel(
            visible_entries[0],
            current_page[0],
            selected_idx[0],
            browse_mode[0],
            search_text=search_text[0],
            in_search_mode=in_search_mode[0],
            search_buffer=search_buffer[0],
            status_line=_compute_status_line(),
        )
        # Show message browser if in browse mode, otherwise show preview
        if browse_mode[0] and cached_history[0] is not None:
            entry = get_current_entry()
            session_name = entry[0] if entry else "unknown"
            preview_control.text = _render_message_browser_panel(
                cached_history[0], message_idx[0], session_name
            )
        else:
            preview_control.text = _render_preview_panel(base_dir, get_current_entry())

    menu_window = Window(
        content=menu_control, wrap_lines=True, width=Dimension(weight=30)
    )
    preview_window = Window(
        content=preview_control, wrap_lines=True, width=Dimension(weight=70)
    )

    menu_frame = Frame(menu_window, width=Dimension(weight=30), title="Sessions")
    preview_frame = Frame(preview_window, width=Dimension(weight=70), title="Preview")

    # Make left panel narrower (15% vs 85%)
    root_container = VSplit(
        [
            menu_frame,
            preview_frame,
        ]
    )

    # Key bindings
    kb = KeyBindings()

    @kb.add("up")
    @kb.add("c-p")  # Ctrl+P = previous (Emacs-style)
    def _(event):
        if in_search_mode[0]:
            return  # While typing the search buffer, arrows do nothing.
        if browse_mode[0]:
            # In browse mode: go to older message
            if cached_history[0] and message_idx[0] < len(cached_history[0]) - 1:
                message_idx[0] += 1
                update_display()
        else:
            # Normal mode: navigate sessions
            if selected_idx[0] > 0:
                selected_idx[0] -= 1
                current_page[0] = ensure_visible_page(
                    selected_idx[0],
                    current_page[0],
                    len(visible_entries[0]),
                    PAGE_SIZE,
                )
                update_display()

    @kb.add("down")
    @kb.add("c-n")  # Ctrl+N = next (Emacs-style)
    def _(event):
        if in_search_mode[0]:
            return
        if browse_mode[0]:
            # In browse mode: go to newer message
            if message_idx[0] > 0:
                message_idx[0] -= 1
                update_display()
        else:
            # Normal mode: navigate sessions
            if selected_idx[0] < len(visible_entries[0]) - 1:
                selected_idx[0] += 1
                current_page[0] = ensure_visible_page(
                    selected_idx[0],
                    current_page[0],
                    len(visible_entries[0]),
                    PAGE_SIZE,
                )
                update_display()

    @kb.add("left")
    def _(event):
        if in_search_mode[0]:
            return
        if current_page[0] > 0:
            current_page[0] -= 1
            selected_idx[0] = current_page[0] * PAGE_SIZE
            update_display()

    @kb.add("right")
    def _(event):
        if in_search_mode[0]:
            return
        # Recompute total_pages from visible_entries every call -- filtering
        # changes the list length and a stale captured value would let users
        # page past the end of a filtered result.
        total_pages = get_total_pages(len(visible_entries[0]), PAGE_SIZE)
        if current_page[0] < total_pages - 1:
            current_page[0] += 1
            selected_idx[0] = current_page[0] * PAGE_SIZE
            update_display()

    @kb.add("e")
    @kb.add("E")
    def _(event):
        """Enter message browse mode (or feed the search buffer)."""
        if in_search_mode[0]:
            search_buffer[0] += "e"
            update_display()
            return
        if browse_mode[0]:
            return  # Already in browse mode
        entry = get_current_entry()
        if entry:
            session_name = entry[0]
            try:
                cached_history[0] = load_session(session_name, base_dir)
                browse_mode[0] = True
                message_idx[0] = 0  # Start at most recent
                update_display()
            except Exception:
                # Can't load this session (e.g. unpicklable or missing).
                # Stay in list mode; log so the failure is debuggable.
                logger.warning(
                    "Failed to load session %r for browsing",
                    session_name,
                    exc_info=True,
                )

    @kb.add("escape")
    def _(event):
        """Exit search mode, browse mode, or cancel -- in that priority."""
        if in_search_mode[0]:
            in_search_mode[0] = False
            search_buffer[0] = ""
            update_display()
            return
        if browse_mode[0]:
            browse_mode[0] = False
            cached_history[0] = None
            message_idx[0] = 0
            update_display()
        else:
            # Not in any sub-mode - treat as cancel
            result[0] = None
            event.app.exit()

    @kb.add("q")
    @kb.add("Q")
    def _(event):
        """Feed the search buffer, or exit browse mode if not searching."""
        if in_search_mode[0]:
            search_buffer[0] += "q"
            update_display()
            return
        if browse_mode[0]:
            browse_mode[0] = False
            cached_history[0] = None
            message_idx[0] = 0
            update_display()

    @kb.add("enter")
    async def _(event):
        if in_search_mode[0]:
            # Commit the buffer as the active filter. Repaint "Filtering..."
            # BEFORE doing the work so users get feedback even when the
            # content index is cold and the lookup has to read pickles.
            search_text[0] = search_buffer[0]
            in_search_mode[0] = False
            search_buffer[0] = ""
            is_filtering[0] = True
            update_display()
            event.app.invalidate()
            # Run the (potentially blocking) filter on a worker thread
            # so the event loop stays responsive. ``await`` yields here,
            # which also gives prompt_toolkit the tick it needs to paint
            # the "Filtering..." indicator before the worker starts.
            try:
                filtered = await asyncio.to_thread(_filter_entries, search_text[0])
                _apply_filter_result(filtered)
            finally:
                is_filtering[0] = False
            update_display()
            event.app.invalidate()
            return
        entry = get_current_entry()
        if entry:
            result[0] = entry[0]  # Store session name
        event.app.exit()

    @kb.add("/")
    def _(event):
        """Enter search mode. Disabled inside browse mode (focus is on msgs)."""
        if browse_mode[0]:
            return
        in_search_mode[0] = True
        search_buffer[0] = ""
        update_display()

    @kb.add("backspace")
    def _(event):
        if in_search_mode[0]:
            search_buffer[0] = search_buffer[0][:-1]
            update_display()

    for _key, _append in iter_alphabet_bindings():

        @kb.add(_key)
        def _alpha(event, _c=_append):
            if in_search_mode[0]:
                search_buffer[0] += _c
                update_display()

    @kb.add("p")
    def _(event):
        """Pin/unpin the selected session -- unless we're typing a search."""
        # While typing a search query, 'p' is just a character. This binding
        # is registered after the alphabet loop so it owns the 'p' key.
        if in_search_mode[0]:
            search_buffer[0] += "p"
            update_display()
            return
        if browse_mode[0]:
            return  # Pinning only makes sense in the session list
        entry = get_current_entry()
        if not entry:
            return
        session_name, metadata = entry
        try:
            new_state = toggle_pin(base_dir, session_name)
        except Exception:
            # Don't crash the picker on a write hiccup; log so it's debuggable.
            logger.warning(
                "Failed to toggle pin for session %r",
                session_name,
                exc_info=True,
            )
            return
        # Reflect the new flag on the shared metadata dict, then re-order the
        # visible list (honoring any active search) and keep this session
        # selected so the cursor follows it to its new position.
        metadata["pinned"] = new_state
        update_visible_entries()
        for i, (name, _meta) in enumerate(visible_entries[0]):
            if name == session_name:
                selected_idx[0] = i
                current_page[0] = get_page_for_index(i, PAGE_SIZE)
                break
        update_display()

    @kb.add("c-c")
    def _(event):
        result[0] = None
        event.app.exit()

    layout = Layout(root_container)
    app = Application(
        style=on_prompt_toolkit_style(),
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )

    async def _prewarm_index() -> None:
        """Eagerly populate the content index in the background.

        Without this, the first content-search blocks the UI on N pickle
        reads. Running the loads on a worker thread keeps the event loop
        responsive; ``app.invalidate()`` after each one drives the
        ``Indexing N/M...`` progress hint in the menu header.
        """
        for name, _meta in entries:
            if name in content_index:
                continue
            try:
                await asyncio.to_thread(content_index.lookup, name, base_dir)
            except asyncio.CancelledError:
                raise
            except Exception:
                # SessionContentIndex.lookup already swallows + caches
                # load errors; we should never get here, but be paranoid.
                pass
            try:
                app.invalidate()
            except Exception:
                # If the app is tearing down, invalidate may explode --
                # not our problem, just stop pre-warming gracefully.
                return

    set_awaiting_user_input(True)

    # Enter alternate screen buffer once for entire session
    sys.stdout.write("\033[?1049h")  # Enter alternate buffer
    sys.stdout.write("\033[2J\033[H")  # Clear and home
    sys.stdout.flush()
    await asyncio.sleep(0.05)

    prewarm_task = asyncio.create_task(_prewarm_index())

    try:
        # Initial display
        update_display()

        # Just clear the current buffer (don't switch buffers)
        sys.stdout.write("\033[2J\033[H")  # Clear screen within current buffer
        sys.stdout.flush()

        # Run application (stays in same alternate buffer)
        await app.run_async()

    finally:
        # Cancel the background pre-warm if it hasn't finished; suppress
        # the resulting CancelledError so the picker exits cleanly.
        prewarm_task.cancel()
        try:
            await prewarm_task
        except (asyncio.CancelledError, Exception):
            pass
        # Exit alternate screen buffer once at end
        sys.stdout.write("\033[?1049l")  # Exit alternate buffer
        sys.stdout.flush()
        # Reset awaiting input flag
        set_awaiting_user_input(False)

    # Clear exit message
    from code_puppy.messaging import emit_info

    emit_info("✓ Exited session browser")

    return result[0]
