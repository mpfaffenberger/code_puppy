"""Interactive terminal UI for loading autosave sessions.

Provides a beautiful split-panel interface for browsing and loading
autosave sessions with live preview of message content.
"""

import json
import sys
import time
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

from code_puppy.config import AUTOSAVE_DIR
from code_puppy.session_storage import list_sessions, load_session
from code_puppy.tools.command_runner import set_awaiting_user_input

PAGE_SIZE = 15  # Sessions per page


def _get_session_metadata(base_dir: Path, session_name: str) -> dict:
    """Load metadata for a session."""
    meta_path = base_dir / f"{session_name}_meta.json"
    try:
        with meta_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _get_session_entries(base_dir: Path) -> List[Tuple[str, dict]]:
    """Get all sessions with their metadata, sorted by timestamp."""
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

    # Sort by timestamp (most recent first)
    def sort_key(entry):
        _, metadata = entry
        timestamp = metadata.get("timestamp")
        if timestamp:
            try:
                return datetime.fromisoformat(timestamp)
            except ValueError:
                return datetime.min
        return datetime.min

    entries.sort(key=sort_key, reverse=True)
    return entries


def _extract_last_user_message(history: list) -> str:
    """Extract the most recent user message from history."""
    # Walk backwards through history to find last user message
    for msg in reversed(history):
        for part in msg.parts:
            if hasattr(part, "content"):
                return part.content
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
                content_parts.append(
                    f"🔧 Tool Call: {tool_name}\n   Args: {args_preview}"
                )
            else:
                content_parts.append(f"🔧 Tool Call: {tool_name}")

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
) -> List:
    """Render the left menu panel with pagination."""
    lines = []
    total_pages = (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE if entries else 1
    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, len(entries))

    lines.append(("", f" Session Page(s): ({page + 1}/{total_pages})"))
    lines.append(("", "\n\n"))

    if not entries:
        lines.append(("fg:yellow", "  No autosave sessions found."))
        lines.append(("", "\n\n"))
        # Navigation hints (always show)
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  ↑/↓ "))
        lines.append(("", "Navigate\n"))
        lines.append(("fg:ansibrightblack", "  ←/→ "))
        lines.append(("", "Page\n"))
        lines.append(("fg:green", "  Enter  "))
        lines.append(("", "Load\n"))
        lines.append(("fg:ansibrightred", "  Ctrl+C "))
        lines.append(("", "Cancel"))
        return lines

    # Show sessions for current page
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

        # Format message count
        msg_count = metadata.get("message_count", "?")

        # Highlight selected item
        if is_selected:
            lines.append(("fg:ansibrightblack", f" > {time_str} • {msg_count} msgs"))
        else:
            lines.append(("fg:ansibrightblack", f"   {time_str} • {msg_count} msgs"))

        lines.append(("", "\n"))

    # Navigation hints - change based on browse mode
    lines.append(("", "\n"))
    if browse_mode:
        lines.append(("fg:ansicyan", "  ↑/↓ "))
        lines.append(("", "Browse msgs\n"))
        lines.append(("fg:ansiyellow", "  Esc "))
        lines.append(("", "Exit browser\n"))
    else:
        lines.append(("fg:ansibrightblack", "  ↑/↓ "))
        lines.append(("", "Navigate\n"))
        lines.append(("fg:ansibrightblack", "  ←/→ "))
        lines.append(("", "Page\n"))
        lines.append(("fg:ansicyan", "  e   "))
        lines.append(("", "Browse msgs\n"))
    lines.append(("fg:green", "  Enter  "))
    lines.append(("", "Load\n"))
    lines.append(("fg:ansibrightred", "  Ctrl+C "))
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

    lines.append(("fg:ansicyan bold", " MESSAGE BROWSER"))
    lines.append(("", "\n\n"))

    total_messages = len(history)
    if total_messages == 0:
        lines.append(("fg:yellow", "  No messages in this session."))
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
    lines.append(("fg:ansibrightblack", f"  Session: {session_name}"))
    lines.append(("", "\n"))

    # Message position indicator
    display_num = message_idx + 1  # 1-based for display
    lines.append(("bold", f"  Message {display_num} of {total_messages}"))
    lines.append(("", "\n\n"))

    # Role indicator with icon and color
    if role == "user":
        lines.append(("fg:ansicyan bold", "  🧑 USER"))
    elif role == "tool":
        lines.append(("fg:ansiyellow bold", "  🔧 TOOL"))
    else:
        lines.append(("fg:ansigreen bold", "  🤖 ASSISTANT"))
    lines.append(("", "\n"))

    # Separator line
    lines.append(("fg:ansibrightblack", "  " + "─" * 40))
    lines.append(("", "\n"))

    # Render content - use markdown for user/assistant, plain text for tool
    try:
        if role == "tool":
            # Tool messages are already formatted, don't pass through markdown
            # Use yellow color for tool output
            rendered = content
            text_color = "fg:ansiyellow"
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

        # Truncate if too long (max 35 lines)
        message_lines = rendered.split("\n")[:35]
        is_truncated = len(rendered.split("\n")) > 35

        for line in message_lines:
            lines.append((text_color, f"  {line}"))
            lines.append(("", "\n"))

        if is_truncated:
            lines.append(("", "\n"))
            lines.append(("fg:yellow", "  ... truncated (message too long)"))
            lines.append(("", "\n"))

    except Exception as e:
        lines.append(("fg:red", f"  Error rendering message: {e}"))
        lines.append(("", "\n"))

    # Navigation hint at bottom
    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", "  ↑ older  ↓ newer  Esc exit"))
    lines.append(("", "\n"))

    return lines


def _render_preview_panel(base_dir: Path, entry: Optional[Tuple[str, dict]]) -> List:
    """Render the right preview panel with message content using rich markdown."""
    lines = []

    lines.append(("dim cyan", " PREVIEW"))
    lines.append(("", "\n\n"))

    if not entry:
        lines.append(("fg:yellow", "  No session selected."))
        lines.append(("", "\n"))
        return lines

    session_name, metadata = entry

    # Show metadata
    lines.append(("bold", "  Session: "))
    lines.append(("", session_name))
    lines.append(("", "\n"))

    timestamp = metadata.get("timestamp", "unknown")
    try:
        dt = datetime.fromisoformat(timestamp)
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        time_str = timestamp
    lines.append(("fg:ansibrightblack", f"  Saved: {time_str}"))
    lines.append(("", "\n"))

    msg_count = metadata.get("message_count", 0)
    tokens = metadata.get("total_tokens", 0)
    lines.append(
        ("fg:ansibrightblack", f"  Messages: {msg_count} • Tokens: {tokens:,}")
    )
    lines.append(("", "\n\n"))

    lines.append(("bold", "  Last Message:"))
    lines.append(("fg:ansibrightblack", "  (press 'e' to browse all)"))
    lines.append(("", "\n"))

    # Try to load and preview the last message
    try:
        history = load_session(session_name, base_dir)
        last_message = _extract_last_user_message(history)

        # Check if original message is long (before Rich processing)
        original_lines = last_message.split("\n") if last_message else []
        is_long = len(original_lines) > 30

        # Render markdown with rich but strip ANSI codes
        console = Console(
            file=StringIO(),
            legacy_windows=False,
            no_color=False,  # Disable ANSI color codes
            force_terminal=False,
            width=76,
        )
        md = Markdown(last_message)
        console.print(md)
        rendered = console.file.getvalue()

        # Truncate if too long (max 30 lines for bigger preview)
        message_lines = rendered.split("\n")[:30]

        for line in message_lines:
            # Rich already rendered the markdown, just display it dimmed
            lines.append(("fg:ansibrightblack", f"  {line}"))
            lines.append(("", "\n"))

        if is_long:
            lines.append(("", "\n"))
            lines.append(("fg:yellow", "  ... truncated"))
            lines.append(("", "\n"))

    except Exception as e:
        lines.append(("fg:red", f"  Error loading preview: {e}"))
        lines.append(("", "\n"))

    return lines


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
    selected_idx = [0]  # Current selection (global index)
    current_page = [0]  # Current page
    result = [None]  # Selected session name

    # Browse mode state
    browse_mode = [False]  # Are we browsing messages within a session?
    message_idx = [0]  # Current message index (0 = most recent)
    cached_history = [None]  # Cached history for current session in browse mode

    total_pages = (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE

    def get_current_entry() -> Optional[Tuple[str, dict]]:
        if 0 <= selected_idx[0] < len(entries):
            return entries[selected_idx[0]]
        return None

    # Build UI
    menu_control = FormattedTextControl(text="")
    preview_control = FormattedTextControl(text="")

    def update_display():
        """Update both panels."""
        menu_control.text = _render_menu_panel(
            entries, current_page[0], selected_idx[0], browse_mode[0]
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
    def _(event):
        if browse_mode[0]:
            # In browse mode: go to older message
            if cached_history[0] and message_idx[0] < len(cached_history[0]) - 1:
                message_idx[0] += 1
                update_display()
        else:
            # Normal mode: navigate sessions
            if selected_idx[0] > 0:
                selected_idx[0] -= 1
                # Update page if needed
                current_page[0] = selected_idx[0] // PAGE_SIZE
                update_display()

    @kb.add("down")
    def _(event):
        if browse_mode[0]:
            # In browse mode: go to newer message
            if message_idx[0] > 0:
                message_idx[0] -= 1
                update_display()
        else:
            # Normal mode: navigate sessions
            if selected_idx[0] < len(entries) - 1:
                selected_idx[0] += 1
                # Update page if needed
                current_page[0] = selected_idx[0] // PAGE_SIZE
                update_display()

    @kb.add("left")
    def _(event):
        if current_page[0] > 0:
            current_page[0] -= 1
            selected_idx[0] = current_page[0] * PAGE_SIZE
            update_display()

    @kb.add("right")
    def _(event):
        if current_page[0] < total_pages - 1:
            current_page[0] += 1
            selected_idx[0] = current_page[0] * PAGE_SIZE
            update_display()

    @kb.add("e")
    def _(event):
        """Enter message browse mode."""
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
                pass  # Silently fail if can't load

    @kb.add("escape")
    def _(event):
        """Exit browse mode or cancel."""
        if browse_mode[0]:
            browse_mode[0] = False
            cached_history[0] = None
            message_idx[0] = 0
            update_display()
        else:
            # Not in browse mode - treat as cancel
            result[0] = None
            event.app.exit()

    @kb.add("q")
    def _(event):
        """Exit browse mode (only when in browse mode)."""
        if browse_mode[0]:
            browse_mode[0] = False
            cached_history[0] = None
            message_idx[0] = 0
            update_display()

    @kb.add("enter")
    def _(event):
        entry = get_current_entry()
        if entry:
            result[0] = entry[0]  # Store session name
        event.app.exit()

    @kb.add("c-c")
    def _(event):
        result[0] = None
        event.app.exit()

    layout = Layout(root_container)
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )

    set_awaiting_user_input(True)

    # Enter alternate screen buffer once for entire session
    sys.stdout.write("\033[?1049h")  # Enter alternate buffer
    sys.stdout.write("\033[2J\033[H")  # Clear and home
    sys.stdout.flush()
    time.sleep(0.05)

    try:
        # Initial display
        update_display()

        # Just clear the current buffer (don't switch buffers)
        sys.stdout.write("\033[2J\033[H")  # Clear screen within current buffer
        sys.stdout.flush()

        # Run application (stays in same alternate buffer)
        await app.run_async()

    finally:
        # Exit alternate screen buffer once at end
        sys.stdout.write("\033[?1049l")  # Exit alternate buffer
        sys.stdout.flush()
        # Reset awaiting input flag
        set_awaiting_user_input(False)

    return result[0]
