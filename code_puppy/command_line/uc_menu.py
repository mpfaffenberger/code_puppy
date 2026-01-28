"""Universal Constructor (UC) interactive TUI menu.

Provides a split-panel interface for browsing and managing UC tools
with live preview of tool details and inline source code viewing.
"""

import sys
import time
import unicodedata
from pathlib import Path
from typing import List, Optional, Tuple

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.command_line.command_registry import register_command
from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.plugins.universal_constructor.models import UCToolInfo
from code_puppy.plugins.universal_constructor.registry import get_registry
from code_puppy.tools.command_runner import set_awaiting_user_input

PAGE_SIZE = 10  # Tools per page
SOURCE_PAGE_SIZE = 30  # Lines of source per page


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
            new_content, meta_count = re.subn(
                meta_pattern, f'\\1\n    "enabled": {new_enabled},', content
            )
            if meta_count == 0:
                emit_error("TOOL_META not found; cannot toggle enabled flag.")
                return False

        source_path.write_text(new_content)

        status = "enabled" if new_enabled else "disabled"
        emit_success(f"Tool '{tool.full_name}' is now {status}")
        return True

    except Exception as e:
        emit_error(f"Failed to toggle tool: {e}")
        return False


def _delete_tool(tool: UCToolInfo) -> bool:
    """Delete a UC tool by removing its source file.

    Args:
        tool: The tool to delete.

    Returns:
        True if successful, False otherwise.
    """
    try:
        source_path = Path(tool.source_path)
        if not source_path.exists():
            emit_error(f"Tool file not found: {source_path}")
            return False

        # Delete the file
        source_path.unlink()

        # Try to clean up empty parent directories (namespace folders)
        parent = source_path.parent
        from code_puppy.plugins.universal_constructor import USER_UC_DIR

        while parent != USER_UC_DIR and parent.exists():
            try:
                if not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
                else:
                    break
            except OSError:
                break

        emit_success(f"Deleted tool '{tool.full_name}'")
        return True

    except Exception as e:
        emit_error(f"Failed to delete tool: {e}")
        return False


def _load_source_code(tool: UCToolInfo) -> Tuple[List[str], Optional[str]]:
    """Load source code lines from a tool's file.

    Args:
        tool: The tool to load source for.

    Returns:
        Tuple of (lines list, error message or None)
    """
    try:
        source_path = Path(tool.source_path)
        content = source_path.read_text()
        return content.splitlines(), None
    except Exception as e:
        return [], f"Could not read source: {e}"


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
    lines.append(("fg:ansired", "  D "))
    lines.append(("", "Delete tool\n"))
    lines.append(("fg:ansibrightblack", "  Esc "))
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


def _render_source_panel(
    tool: UCToolInfo,
    source_lines: List[str],
    scroll_offset: int,
    error: Optional[str] = None,
) -> List:
    """Render source code panel with syntax highlighting.

    Args:
        tool: The tool being viewed
        source_lines: List of source code lines
        scroll_offset: Current scroll position (line number)
        error: Error message if source couldn't be loaded

    Returns:
        List of (style, text) tuples for FormattedTextControl
    """
    lines = []

    # Header
    lines.append(("bold cyan", f" SOURCE: {tool.full_name}"))
    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", f" {tool.source_path}"))
    lines.append(("", "\n"))
    lines.append(("fg:ansibrightblack", "─" * 70))
    lines.append(("", "\n"))

    if error:
        lines.append(("fg:ansired", f"  Error: {error}\n"))
        return lines

    if not source_lines:
        lines.append(("fg:yellow", "  (empty file)\n"))
        return lines

    # Calculate visible range
    total_lines = len(source_lines)
    visible_lines = SOURCE_PAGE_SIZE
    end_offset = min(scroll_offset + visible_lines, total_lines)

    # Line number width for padding
    line_num_width = len(str(total_lines))

    # Render visible source lines with basic syntax highlighting
    for i in range(scroll_offset, end_offset):
        line_num = i + 1
        line_content = source_lines[i]

        # Line number
        lines.append(("fg:ansibrightblack", f" {line_num:>{line_num_width}} │ "))

        # Basic syntax highlighting
        highlighted = _highlight_python_line(line_content)
        lines.extend(highlighted)
        lines.append(("", "\n"))

    # Footer with scroll info
    lines.append(("fg:ansibrightblack", "─" * 70))
    lines.append(("", "\n"))

    # Scroll position indicator
    current_page = scroll_offset // SOURCE_PAGE_SIZE + 1
    total_pages = (total_lines + SOURCE_PAGE_SIZE - 1) // SOURCE_PAGE_SIZE
    lines.append(
        (
            "fg:ansibrightblack",
            f" Lines {scroll_offset + 1}-{end_offset} of {total_lines}",
        )
    )
    lines.append(("fg:ansibrightblack", f" (Page {current_page}/{total_pages})"))
    lines.append(("", "\n\n"))

    # Navigation hints for source view
    lines.append(("fg:ansibrightblack", "  [up]/[down] "))
    lines.append(("", "Scroll\n"))
    lines.append(("fg:ansibrightblack", "  [PgUp]/[PgDn] "))
    lines.append(("", "Page\n"))
    lines.append(("fg:ansiyellow", "  Esc/Q "))
    lines.append(("", "Back to list\n"))
    lines.append(("fg:ansibrightred", "  Ctrl+C "))
    lines.append(("", "Exit"))

    return lines


def _highlight_python_line(line: str) -> List[Tuple[str, str]]:
    """Apply basic Python syntax highlighting to a line.

    Args:
        line: A single line of Python code

    Returns:
        List of (style, text) tuples
    """
    result = []

    # Keywords
    keywords = {
        "def",
        "class",
        "return",
        "if",
        "else",
        "elif",
        "for",
        "while",
        "try",
        "except",
        "finally",
        "with",
        "as",
        "import",
        "from",
        "True",
        "False",
        "None",
        "and",
        "or",
        "not",
        "in",
        "is",
        "lambda",
        "yield",
        "raise",
        "pass",
        "break",
        "continue",
        "async",
        "await",
    }

    # Simple tokenization
    if not line.strip():
        result.append(("", line))
        return result

    # Check for comments
    if line.lstrip().startswith("#"):
        result.append(("fg:ansibrightblack italic", line))
        return result

    # Check for strings (simplified)
    stripped = line.lstrip()
    if stripped.startswith('"""') or stripped.startswith("'''"):
        result.append(("fg:ansigreen", line))
        return result

    # Word-by-word highlighting
    import re

    tokens = re.split(r"(\s+|[()\[\]{}:,=.])", line)

    in_string = False
    string_char = None

    for token in tokens:
        if not token:
            continue

        # Track string state
        if not in_string and (token.startswith('"') or token.startswith("'")):
            in_string = True
            string_char = token[0]
            result.append(("fg:ansigreen", token))
            if (
                len(token) > 1
                and token.endswith(string_char)
                and not token.endswith("\\" + string_char)
            ):
                in_string = False
            continue

        if in_string:
            result.append(("fg:ansigreen", token))
            if token.endswith(string_char) and not token.endswith("\\" + string_char):
                in_string = False
            continue

        # Keywords
        if token in keywords:
            result.append(("fg:ansimagenta bold", token))
        # Numbers
        elif token.isdigit():
            result.append(("fg:ansicyan", token))
        # Function/class names (after def/class)
        elif result and len(result) >= 1:
            prev_text = result[-1][1].strip() if result[-1][1] else ""
            if prev_text in ("def", "class"):
                result.append(("fg:ansiyellow bold", token))
            else:
                result.append(("", token))
        else:
            result.append(("", token))

    return result


def _show_source_code(tool: UCToolInfo) -> None:
    """Display the full source code of a tool (legacy, for external use).

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
    view_mode = ["list"]  # 'list' or 'source'
    source_scroll = [0]  # Scroll offset in source view
    source_lines = [[]]  # Cached source lines
    source_error = [None]  # Error loading source

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

    # Build UI controls
    menu_control = FormattedTextControl(text="")
    preview_control = FormattedTextControl(text="")
    source_control = FormattedTextControl(text="")

    def update_list_display():
        """Update the list view panels."""
        menu_control.text = _render_menu_panel(tools, current_page[0], selected_idx[0])
        preview_control.text = _render_preview_panel(get_current_tool())

    def update_source_display():
        """Update the source view panel."""
        tool = get_current_tool()
        if tool:
            source_control.text = _render_source_panel(
                tool, source_lines[0], source_scroll[0], source_error[0]
            )

    # Windows for list view
    menu_window = Window(
        content=menu_control, wrap_lines=False, width=Dimension(weight=40)
    )
    preview_window = Window(
        content=preview_control, wrap_lines=False, width=Dimension(weight=60)
    )

    # Window for source view (full width)
    source_window = Window(
        content=source_control, wrap_lines=True, width=Dimension(weight=100)
    )

    # Frames
    menu_frame = Frame(menu_window, width=Dimension(weight=40), title="UC Tools")
    preview_frame = Frame(preview_window, width=Dimension(weight=60), title="Preview")
    source_frame = Frame(
        source_window, width=Dimension(weight=100), title="Source Code"
    )

    # Containers
    list_container = VSplit([menu_frame, preview_frame])
    source_container = HSplit([source_frame])

    # Key bindings for LIST mode
    list_kb = KeyBindings()

    @list_kb.add("up")
    def _list_up(event):
        if selected_idx[0] > 0:
            selected_idx[0] -= 1
            current_page[0] = selected_idx[0] // PAGE_SIZE
            update_list_display()

    @list_kb.add("down")
    def _list_down(event):
        if selected_idx[0] < len(tools) - 1:
            selected_idx[0] += 1
            current_page[0] = selected_idx[0] // PAGE_SIZE
            update_list_display()

    @list_kb.add("left")
    def _list_left(event):
        if current_page[0] > 0:
            current_page[0] -= 1
            selected_idx[0] = current_page[0] * PAGE_SIZE
            update_list_display()

    @list_kb.add("right")
    def _list_right(event):
        if current_page[0] < total_pages[0] - 1:
            current_page[0] += 1
            selected_idx[0] = current_page[0] * PAGE_SIZE
            update_list_display()

    @list_kb.add("e")
    def _list_toggle(event):
        if get_current_tool():
            pending_action[0] = "toggle"
            event.app.exit()

    @list_kb.add("d")
    def _list_delete(event):
        if get_current_tool():
            pending_action[0] = "delete"
            event.app.exit()

    @list_kb.add("escape")
    def _list_escape(event):
        result[0] = None
        pending_action[0] = "exit"
        event.app.exit()

    @list_kb.add("enter")
    def _list_enter(event):
        tool = get_current_tool()
        if tool:
            # Switch to source view
            view_mode[0] = "source"
            source_scroll[0] = 0
            source_lines[0], source_error[0] = _load_source_code(tool)
            pending_action[0] = "switch_to_source"
            event.app.exit()

    @list_kb.add("c-c")
    def _list_exit(event):
        result[0] = None
        pending_action[0] = "exit"
        event.app.exit()

    # Key bindings for SOURCE mode
    source_kb = KeyBindings()

    @source_kb.add("up")
    def _source_up(event):
        if source_scroll[0] > 0:
            source_scroll[0] -= 1
            update_source_display()

    @source_kb.add("down")
    def _source_down(event):
        max_scroll = max(0, len(source_lines[0]) - SOURCE_PAGE_SIZE)
        if source_scroll[0] < max_scroll:
            source_scroll[0] += 1
            update_source_display()

    @source_kb.add("pageup")
    def _source_pageup(event):
        source_scroll[0] = max(0, source_scroll[0] - SOURCE_PAGE_SIZE)
        update_source_display()

    @source_kb.add("pagedown")
    def _source_pagedown(event):
        max_scroll = max(0, len(source_lines[0]) - SOURCE_PAGE_SIZE)
        source_scroll[0] = min(max_scroll, source_scroll[0] + SOURCE_PAGE_SIZE)
        update_source_display()

    @source_kb.add("escape")
    def _source_escape(event):
        view_mode[0] = "list"
        pending_action[0] = "switch_to_list"
        event.app.exit()

    @source_kb.add("q")
    def _source_q(event):
        view_mode[0] = "list"
        pending_action[0] = "switch_to_list"
        event.app.exit()

    @source_kb.add("c-c")
    def _source_exit(event):
        result[0] = None
        pending_action[0] = "exit"
        event.app.exit()

    set_awaiting_user_input(True)

    # Enter alternate screen buffer
    sys.stdout.write("\033[?1049h")
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    time.sleep(0.05)

    try:
        while True:
            # Clear screen
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

            if view_mode[0] == "list":
                # List view
                update_list_display()
                layout = Layout(list_container)
                app = Application(
                    layout=layout,
                    key_bindings=list_kb,
                    full_screen=False,
                    mouse_support=False,
                )
            else:
                # Source view
                update_source_display()
                layout = Layout(source_container)
                app = Application(
                    layout=layout,
                    key_bindings=source_kb,
                    full_screen=False,
                    mouse_support=False,
                )

            await app.run_async()

            # Handle actions
            if pending_action[0] == "toggle":
                tool = get_current_tool()
                if tool:
                    selected_name = tool.full_name
                    _toggle_tool_enabled(tool)
                    refresh_tools(selected_name=selected_name)
                pending_action[0] = None
                continue

            if pending_action[0] == "delete":
                tool = get_current_tool()
                if tool:
                    _delete_tool(tool)
                    refresh_tools()  # Don't try to keep selection on deleted tool
                pending_action[0] = None
                continue

            if pending_action[0] == "switch_to_source":
                pending_action[0] = None
                continue

            if pending_action[0] == "switch_to_list":
                pending_action[0] = None
                continue

            if pending_action[0] == "exit":
                break

            # Default: exit
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
