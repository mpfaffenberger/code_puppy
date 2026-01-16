"""Interactive terminal UI for selecting agents.

Provides a split-panel interface for browsing and selecting agents
with live preview of agent details.
"""

import sys
import time
import unicodedata
from typing import List, Optional, Tuple

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.agents import (
    get_agent_descriptions,
    get_available_agents,
    get_current_agent,
)
from code_puppy.tools.command_runner import set_awaiting_user_input

PAGE_SIZE = 10  # Agents per page


def _sanitize_display_text(text: str) -> str:
    """Remove or replace characters that cause terminal rendering issues.

    Args:
        text: Text that may contain emojis or wide characters

    Returns:
        Sanitized text safe for prompt_toolkit rendering
    """
    # Keep only characters that render cleanly in terminals
    # Be aggressive about stripping anything that could cause width issues
    result = []
    for char in text:
        # Get unicode category
        cat = unicodedata.category(char)
        # Categories to KEEP:
        # - L* (Letters): Lu, Ll, Lt, Lm, Lo
        # - N* (Numbers): Nd, Nl, No
        # - P* (Punctuation): Pc, Pd, Ps, Pe, Pi, Pf, Po
        # - Zs (Space separator)
        # - Sm (Math symbols like +, -, =)
        # - Sc (Currency symbols like $, €)
        # - Sk (Modifier symbols)
        #
        # Categories to SKIP (cause rendering issues):
        # - So (Symbol, other) - emojis
        # - Cf (Format) - ZWJ, etc.
        # - Mn (Mark, nonspacing) - combining characters
        # - Mc (Mark, spacing combining)
        # - Me (Mark, enclosing)
        # - Cn (Not assigned)
        # - Co (Private use)
        # - Cs (Surrogate)
        safe_categories = (
            "Lu",
            "Ll",
            "Lt",
            "Lm",
            "Lo",  # Letters
            "Nd",
            "Nl",
            "No",  # Numbers
            "Pc",
            "Pd",
            "Ps",
            "Pe",
            "Pi",
            "Pf",
            "Po",  # Punctuation
            "Zs",  # Space
            "Sm",
            "Sc",
            "Sk",  # Safe symbols (math, currency, modifier)
        )
        if cat in safe_categories:
            result.append(char)

    # Clean up any double spaces left behind and strip
    cleaned = " ".join("".join(result).split())
    return cleaned


def _get_agent_entries() -> List[Tuple[str, str, str]]:
    """Get all agents with their display names and descriptions.

    Returns:
        List of tuples (agent_name, display_name, description) sorted by name.
    """
    available = get_available_agents()
    descriptions = get_agent_descriptions()

    entries = []
    for name, display_name in available.items():
        description = descriptions.get(name, "No description available")
        entries.append((name, display_name, description))

    # Sort alphabetically by agent name
    entries.sort(key=lambda x: x[0].lower())
    return entries


def _render_menu_panel(
    entries: List[Tuple[str, str, str]],
    page: int,
    selected_idx: int,
    current_agent_name: str,
) -> List:
    """Render the left menu panel with pagination.

    Args:
        entries: List of (name, display_name, description) tuples
        page: Current page number (0-indexed)
        selected_idx: Currently selected index (global)
        current_agent_name: Name of the current active agent

    Returns:
        List of (style, text) tuples for FormattedTextControl
    """
    lines = []
    total_pages = (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE if entries else 1
    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, len(entries))

    lines.append(("bold", "Agents"))
    lines.append(("fg:ansibrightblack", f" (Page {page + 1}/{total_pages})"))
    lines.append(("", "\n\n"))

    if not entries:
        lines.append(("fg:yellow", "  No agents found."))
        lines.append(("", "\n\n"))
    else:
        # Show agents for current page
        for i in range(start_idx, end_idx):
            name, display_name, _ = entries[i]
            is_selected = i == selected_idx
            is_current = name == current_agent_name

            # Sanitize display name to avoid emoji rendering issues
            safe_display_name = _sanitize_display_text(display_name)

            # Build the line
            if is_selected:
                lines.append(("fg:ansigreen", "▶ "))
                lines.append(("fg:ansigreen bold", safe_display_name))
            else:
                lines.append(("", "  "))
                lines.append(("", safe_display_name))

            # Add current marker
            if is_current:
                lines.append(("fg:ansicyan", " ← current"))

            lines.append(("", "\n"))

    # Navigation hints
    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", "  ↑↓ "))
    lines.append(("", "Navigate\n"))
    lines.append(("fg:ansibrightblack", "  ←→ "))
    lines.append(("", "Page\n"))
    lines.append(("fg:green", "  Enter  "))
    lines.append(("", "Select\n"))
    lines.append(("fg:ansibrightred", "  Ctrl+C "))
    lines.append(("", "Cancel"))

    return lines


def _render_preview_panel(
    entry: Optional[Tuple[str, str, str]],
    current_agent_name: str,
) -> List:
    """Render the right preview panel with agent details.

    Args:
        entry: Tuple of (name, display_name, description) or None
        current_agent_name: Name of the current active agent

    Returns:
        List of (style, text) tuples for FormattedTextControl
    """
    lines = []

    lines.append(("dim cyan", " AGENT DETAILS"))
    lines.append(("", "\n\n"))

    if not entry:
        lines.append(("fg:yellow", "  No agent selected."))
        lines.append(("", "\n"))
        return lines

    name, display_name, description = entry
    is_current = name == current_agent_name

    # Sanitize text to avoid emoji rendering issues
    safe_display_name = _sanitize_display_text(display_name)
    safe_description = _sanitize_display_text(description)

    # Agent name (identifier)
    lines.append(("bold", "Name: "))
    lines.append(("", name))
    lines.append(("", "\n\n"))

    # Display name
    lines.append(("bold", "Display Name: "))
    lines.append(("fg:ansicyan", safe_display_name))
    lines.append(("", "\n\n"))

    # Description
    lines.append(("bold", "Description:"))
    lines.append(("", "\n"))

    # Wrap description to fit panel
    desc_lines = safe_description.split("\n")
    for desc_line in desc_lines:
        # Word wrap long lines
        words = desc_line.split()
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 > 55:
                lines.append(("fg:ansibrightblack", current_line))
                lines.append(("", "\n"))
                current_line = word
            else:
                if current_line == "":
                    current_line = word
                else:
                    current_line += " " + word
        if current_line.strip():
            lines.append(("fg:ansibrightblack", current_line))
            lines.append(("", "\n"))

    lines.append(("", "\n"))

    # Current status
    lines.append(("bold", "  Status: "))
    if is_current:
        lines.append(("fg:ansigreen bold", "✓ Currently Active"))
    else:
        lines.append(("fg:ansibrightblack", "Not active"))
    lines.append(("", "\n"))

    return lines


async def interactive_agent_picker() -> Optional[str]:
    """Show interactive terminal UI to select an agent.

    Returns:
        Agent name to switch to, or None if cancelled.
    """
    entries = _get_agent_entries()
    current_agent = get_current_agent()
    current_agent_name = current_agent.name if current_agent else ""

    if not entries:
        from code_puppy.messaging import emit_info

        emit_info("No agents found.")
        return None

    # State
    selected_idx = [0]  # Current selection (global index)
    current_page = [0]  # Current page
    result = [None]  # Selected agent name

    total_pages = (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE

    def get_current_entry() -> Optional[Tuple[str, str, str]]:
        if 0 <= selected_idx[0] < len(entries):
            return entries[selected_idx[0]]
        return None

    # Build UI
    menu_control = FormattedTextControl(text="")
    preview_control = FormattedTextControl(text="")

    def update_display():
        """Update both panels."""
        menu_control.text = _render_menu_panel(
            entries, current_page[0], selected_idx[0], current_agent_name
        )
        preview_control.text = _render_preview_panel(
            get_current_entry(), current_agent_name
        )

    menu_window = Window(
        content=menu_control, wrap_lines=False, width=Dimension(weight=35)
    )
    preview_window = Window(
        content=preview_control, wrap_lines=False, width=Dimension(weight=65)
    )

    menu_frame = Frame(menu_window, width=Dimension(weight=35), title="Agents")
    preview_frame = Frame(preview_window, width=Dimension(weight=65), title="Preview")

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
        if selected_idx[0] > 0:
            selected_idx[0] -= 1
            # Update page if needed
            current_page[0] = selected_idx[0] // PAGE_SIZE
            update_display()

    @kb.add("down")
    def _(event):
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

    @kb.add("enter")
    def _(event):
        entry = get_current_entry()
        if entry:
            result[0] = entry[0]  # Store agent name
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

        # Clear the current buffer
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

        # Run application
        await app.run_async()

    finally:
        # Exit alternate screen buffer once at end
        sys.stdout.write("\033[?1049l")  # Exit alternate buffer
        sys.stdout.flush()
        # Reset awaiting input flag
        set_awaiting_user_input(False)

    # Clear exit message
    from code_puppy.messaging import emit_info

    emit_info("✓ Exited agent picker")

    return result[0]
