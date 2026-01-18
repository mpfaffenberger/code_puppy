"""Universal Constructor (UC) interactive TUI menu.

Provides a split-panel interface for browsing and managing UC tools
with live preview of tool details.
"""

import sys
import time
import unicodedata
from pathlib import Path
from typing import List, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.command_line.command_registry import register_command
from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.plugins.universal_constructor.models import UCToolInfo
from code_puppy.plugins.universal_constructor.registry import get_registry
from code_puppy.tools.command_runner import set_awaiting_user_input

PAGE_SIZE = 10  # Tools per page


def _sanitize_display_text(text: str) -> str:
    """Remove or replace characters that cause terminal rendering issues.

    Args:
        text: Text that may contain emojis or wide characters

    Returns:
        Sanitized text safe for prompt_toolkit rendering
    """
    result = []
    for char in text:
        cat = unicodedata.category(char)
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
            "Sk",  # Safe symbols
        )
        if cat in safe_categories:
            result.append(char)

    cleaned = " ".join("".join(result).split())
    return cleaned


def _get_tool_entries() -> List[UCToolInfo]:
    """Get all UC tools sorted by name.

    Returns:
        List of UCToolInfo sorted by full_name.
    """
    registry = get_registry()
    registry.scan()  # Force fresh scan
    return registry.list_tools(include_disabled=True)


def _toggle_tool_enabled(tool: UCToolInfo) -> bool:
    """Toggle a tool's enabled status by modifying its source file.

    Args:
        tool: The tool to toggle.

    Returns:
        True if successful, False otherwise.
    """
    try:
        source_path = Path(tool.source_path)
        content = source_path.read_text()

        # Find and flip the enabled flag in TOOL_META
        new_enabled = not tool.meta.enabled

        # Try to find and replace the enabled line
        import re

        # Match 'enabled': True/False or "enabled": True/False
        pattern = r'(["\']enabled["\']\s*:\s*)(True|False)'

        def replacer(m):
            return m.group(1) + str(new_enabled)

        new_content, count = re.subn(pattern, replacer, content)

        if count == 0:
            # No explicit enabled field - add it to TOOL_META
            # Find TOOL_META = { and add enabled after the opening brace
            meta_pattern = r"(TOOL_META\s*=\s*\{)"
            new_content = re.sub(
                meta_pattern, f'\\1\n    "enabled": {new_enabled},', content
            )

        source_path.write_text(new_content)

        status = "enabled" if new_enabled else "disabled"
        emit_success(f"Tool '{tool.full_name}' is now {status}")
        return True

    except Exception as e:
        emit_error(f"Failed to toggle tool: {e}")
        return False


def _render_menu_panel(
    tools: List[UCToolInfo],
    page: int,
    selected_idx: int,
) -> List:
    """Render the left menu panel with pagination.

    Args:
        tools: List of UCToolInfo objects
        page: Current page number (0-indexed)
        selected_idx: Currently selected index (global)

    Returns:
        List of (style, text) tuples for FormattedTextControl
    """
    lines = []
    total_pages = (len(tools) + PAGE_SIZE - 1) // PAGE_SIZE if tools else 1
    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, len(tools))

    lines.append(("bold", "UC Tools"))
    lines.append(("fg:ansibrightblack", f" (Page {page + 1}/{total_pages})"))
    lines.append(("", "\n\n"))

    if not tools:
        lines.append(("fg:yellow", "  No UC tools found.\n"))
        lines.append(("fg:ansibrightblack", "  Ask the LLM to create one!\n"))
        lines.append(("", "\n"))
    else:
        for i in range(start_idx, end_idx):
            tool = tools[i]
            is_selected = i == selected_idx

            safe_name = _sanitize_display_text(tool.full_name)

            # Selection indicator
            if is_selected:
                lines.append(("fg:ansigreen", "> "))
                lines.append(("fg:ansigreen bold", safe_name))
            else:
                lines.append(("", "  "))
                lines.append(("", safe_name))

            # Status indicator
            if tool.meta.enabled:
                lines.append(("fg:ansigreen", " [on]"))
            else:
                lines.append(("fg:ansired", " [off]"))

            # Namespace tag if present
            if tool.meta.namespace:
                lines.append(("fg:ansiblue", f" ({tool.meta.namespace})"))

            lines.append(("", "\n"))

    # Navigation hints
    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", "  [up]/[down] "))
    lines.append(("", "Navigate\n"))
    lines.append(("fg:ansibrightblack", "  [left]/[right] "))
    lines.append(("", "Page\n"))
    lines.append(("fg:green", "  Enter  "))
    lines.append(("", "View source\n"))
    lines.append(("fg:ansiyellow", "  E "))
    lines.append(("", "Toggle enabled\n"))
    lines.append(("fg:ansibrightred", "  Ctrl+C "))
    lines.append(("", "Exit"))

    return lines


def _render_preview_panel(tool: Optional[UCToolInfo]) -> List:
    """Render the right preview panel with tool details.

    Args:
        tool: UCToolInfo or None

    Returns:
        List of (style, text) tuples for FormattedTextControl
    """
    lines = []

    lines.append(("dim cyan", " TOOL DETAILS"))
    lines.append(("", "\n\n"))

    if not tool:
        lines.append(("fg:yellow", "  No tool selected.\n"))
        lines.append(("fg:ansibrightblack", "  Create some with the LLM!\n"))
        return lines

    safe_name = _sanitize_display_text(tool.meta.name)
    safe_desc = _sanitize_display_text(tool.meta.description)

    # Tool name
    lines.append(("bold", "Name: "))
    lines.append(("fg:ansicyan", safe_name))
    lines.append(("", "\n\n"))

    # Full name (with namespace)
    if tool.meta.namespace:
        lines.append(("bold", "Full Name: "))
        lines.append(("", tool.full_name))
        lines.append(("", "\n\n"))

    # Status
    lines.append(("bold", "Status: "))
    if tool.meta.enabled:
        lines.append(("fg:ansigreen bold", "ENABLED"))
    else:
        lines.append(("fg:ansired bold", "DISABLED"))
    lines.append(("", "\n\n"))

    # Version
    lines.append(("bold", "Version: "))
    lines.append(("", tool.meta.version))
    lines.append(("", "\n\n"))

    # Author (if present)
    if tool.meta.author:
        lines.append(("bold", "Author: "))
        lines.append(("", tool.meta.author))
        lines.append(("", "\n\n"))

    # Signature
    lines.append(("bold", "Signature: "))
    lines.append(("fg:ansiyellow", tool.signature))
    lines.append(("", "\n\n"))

    # Description (word-wrapped)
    lines.append(("bold", "Description:"))
    lines.append(("", "\n"))

    words = safe_desc.split()
    current_line = ""
    for word in words:
        if len(current_line) + len(word) + 1 > 50:
            lines.append(("fg:ansibrightblack", f"  {current_line}"))
            lines.append(("", "\n"))
            current_line = word
        else:
            current_line = word if not current_line else current_line + " " + word
    if current_line:
        lines.append(("fg:ansibrightblack", f"  {current_line}"))
        lines.append(("", "\n"))

    lines.append(("", "\n"))

    # Docstring preview (if available)
    if tool.docstring:
        lines.append(("bold", "Docstring:"))
        lines.append(("", "\n"))
        doc_preview = tool.docstring[:150]
        if len(tool.docstring) > 150:
            doc_preview += "..."
        lines.append(("fg:ansibrightblack", f"  {doc_preview}"))
        lines.append(("", "\n\n"))

    # Source path
    lines.append(("bold", "Source:"))
    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", f"  {tool.source_path}"))
    lines.append(("", "\n"))

    return lines


def _show_source_code(tool: UCToolInfo) -> None:
    """Display the full source code of a tool.

    Args:
        tool: The tool to show source for.
    """
    from rich.panel import Panel
    from rich.syntax import Syntax

    try:
        source_code = Path(tool.source_path).read_text()
        syntax = Syntax(
            source_code,
            "python",
            theme="monokai",
            line_numbers=True,
            word_wrap=True,
        )
        panel = Panel(
            syntax,
            title=f"[bold cyan]{tool.full_name}[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )
        emit_info(panel)
    except Exception as e:
        emit_error(f"Could not read source: {e}")


async def interactive_uc_picker() -> Optional[str]:
    """Show interactive TUI to browse UC tools.

    Returns:
        Tool name that was selected for viewing, or None if cancelled.
    """
    tools = _get_tool_entries()

    # State
    selected_idx = [0]
    current_page = [0]
    result = [None]  # Tool name to view
    pending_action = [None]  # 'toggle', 'view', or None

    total_pages = [max(1, (len(tools) + PAGE_SIZE - 1) // PAGE_SIZE)]

    def get_current_tool() -> Optional[UCToolInfo]:
        if 0 <= selected_idx[0] < len(tools):
            return tools[selected_idx[0]]
        return None

    def refresh_tools(selected_name: Optional[str] = None) -> None:
        nonlocal tools
        tools = _get_tool_entries()
        total_pages[0] = max(1, (len(tools) + PAGE_SIZE - 1) // PAGE_SIZE)

        if not tools:
            selected_idx[0] = 0
            current_page[0] = 0
            return

        if selected_name:
            for idx, t in enumerate(tools):
                if t.full_name == selected_name:
                    selected_idx[0] = idx
                    break
            else:
                selected_idx[0] = min(selected_idx[0], len(tools) - 1)
        else:
            selected_idx[0] = min(selected_idx[0], len(tools) - 1)

        current_page[0] = selected_idx[0] // PAGE_SIZE

    # Build UI
    menu_control = FormattedTextControl(text="")
    preview_control = FormattedTextControl(text="")

    def update_display():
        menu_control.text = _render_menu_panel(tools, current_page[0], selected_idx[0])
        preview_control.text = _render_preview_panel(get_current_tool())

    menu_window = Window(
        content=menu_control, wrap_lines=False, width=Dimension(weight=40)
    )
    preview_window = Window(
        content=preview_control, wrap_lines=False, width=Dimension(weight=60)
    )

    menu_frame = Frame(menu_window, width=Dimension(weight=40), title="UC Tools")
    preview_frame = Frame(preview_window, width=Dimension(weight=60), title="Preview")

    root_container = VSplit([menu_frame, preview_frame])

    # Key bindings
    kb = KeyBindings()

    @kb.add("up")
    def _(event):
        if selected_idx[0] > 0:
            selected_idx[0] -= 1
            current_page[0] = selected_idx[0] // PAGE_SIZE
            update_display()

    @kb.add("down")
    def _(event):
        if selected_idx[0] < len(tools) - 1:
            selected_idx[0] += 1
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
        if current_page[0] < total_pages[0] - 1:
            current_page[0] += 1
            selected_idx[0] = current_page[0] * PAGE_SIZE
            update_display()

    @kb.add("e")
    def _(event):
        if get_current_tool():
            pending_action[0] = "toggle"
            event.app.exit()

    @kb.add("enter")
    def _(event):
        tool = get_current_tool()
        if tool:
            result[0] = tool.full_name
            pending_action[0] = "view"
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

    # Enter alternate screen buffer
    sys.stdout.write("\033[?1049h")
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    time.sleep(0.05)

    try:
        while True:
            pending_action[0] = None
            result[0] = None
            update_display()

            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

            await app.run_async()

            if pending_action[0] == "toggle":
                tool = get_current_tool()
                if tool:
                    selected_name = tool.full_name
                    _toggle_tool_enabled(tool)
                    refresh_tools(selected_name=selected_name)
                continue

            if pending_action[0] == "view":
                tool = get_current_tool()
                if tool:
                    # Exit TUI first, then show source
                    sys.stdout.write("\033[?1049l")
                    sys.stdout.flush()
                    set_awaiting_user_input(False)
                    _show_source_code(tool)
                    return tool.full_name

            break

    finally:
        # Exit alternate screen buffer
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()
        set_awaiting_user_input(False)

    emit_info("Exited UC tool browser")
    return result[0]


@register_command(
    name="uc",
    description="Universal Constructor - browse and manage custom tools",
    usage="/uc",
    category="tools",
)
def handle_uc_command(command: str) -> bool:
    """Handle the /uc command - opens the interactive TUI.

    Args:
        command: The full command string.

    Returns:
        True always (command completed).
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're already in an async context - create a task
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, interactive_uc_picker())
                future.result()
        else:
            asyncio.run(interactive_uc_picker())
    except Exception as e:
        emit_error(f"Failed to open UC menu: {e}")

    return True
