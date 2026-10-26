"""Universal Constructor (UC) interactive TUI menu, on termflow.

A Menu over UC tools with a details preview pane; ``Enter`` opens the
tool's source in a Pager (theme-aware pygments highlighting via the
``termflow_highlighter`` callback), ``e`` toggles enabled, ``d``
deletes, ``Esc`` exits.
"""

from __future__ import annotations

import asyncio
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Tuple

from code_puppy.command_line.command_registry import register_command
from code_puppy.messaging import emit_error, emit_info, emit_success
from code_puppy.tools.command_runner import set_awaiting_user_input

if TYPE_CHECKING:
    UCToolInfo = Any

_TOGGLE = "__toggle_tool__"
_DELETE = "__delete_tool__"


def _sanitize_display_text(text: str) -> str:
    """Remove or replace characters that cause terminal rendering issues."""
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
            "Sm",
            "Sc",
            "Sk",  # Symbols (math, currency, modifier)
            "Zs",  # Space separator
        )
        if cat in safe_categories and (ord(char) < 0x1F000):
            result.append(char)
        elif cat == "So":
            # Other symbols (includes emojis) - replace with placeholder
            result.append("*")
    return "".join(result)


def _get_tool_entries() -> List[UCToolInfo]:
    """Get all UC tools sorted by name."""
    from code_puppy.universal_constructor_provider import (
        get_universal_constructor_provider,
    )

    provider = get_universal_constructor_provider()
    if provider is None:
        return []
    provider.reload()  # Force fresh scan
    return provider.list_tools(include_disabled=True)


def _toggle_tool_enabled(tool: UCToolInfo) -> bool:
    """Toggle a tool's enabled status by modifying its source file."""
    try:
        source_path = Path(tool.source_path)
        content = source_path.read_text()

        new_enabled = not tool.meta.enabled

        import re

        # Match 'enabled': True/False or "enabled": True/False
        pattern = r'(["\']enabled["\']\s*:\s*)(True|False)'

        def replacer(m):
            return m.group(1) + str(new_enabled)

        new_content, count = re.subn(pattern, replacer, content)

        if count == 0:
            # No explicit enabled field - add it to TOOL_META
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
    """Delete a UC tool by removing its source file."""
    try:
        source_path = Path(tool.source_path)
        if not source_path.exists():
            emit_error(f"Tool file not found: {source_path}")
            return False

        source_path.unlink()

        # Try to clean up empty parent directories (namespace folders)
        parent = source_path.parent
        from code_puppy.universal_constructor_provider import (
            get_universal_constructor_provider,
        )

        provider = get_universal_constructor_provider()
        tools_dir = provider.tools_dir if provider else parent
        while parent != tools_dir and parent.exists():
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
    """Load source code lines from a tool's file."""
    try:
        source_path = Path(tool.source_path)
        content = source_path.read_text()
        return content.splitlines(), None
    except Exception as e:
        return [], f"Could not read source: {e}"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _style():
    from termflow.render.style import RenderStyle

    from code_puppy.command_line.tui_style import menu_style

    return menu_style() or RenderStyle.default()


def _ansi(color: str, text: str) -> str:
    from termflow.ansi.codes import RESET
    from termflow.ansi.color import fg_color

    return f"{fg_color(color)}{text}{RESET}"


def tool_details(tool: Optional[UCToolInfo]) -> str:
    """Preview pane: tool metadata."""
    import textwrap

    s = _style()
    lines = [_ansi(s.bright, "TOOL DETAILS"), ""]
    if not tool:
        lines.append(_ansi(s.error, "No tool selected."))
        lines.append(_ansi(s.grey, "Create some with the LLM!"))
        return "\n".join(lines)

    lines.append(f"Name: {_ansi(s.head, _sanitize_display_text(tool.meta.name))}")
    if tool.meta.namespace:
        lines.append(f"Full Name: {tool.full_name}")
    status = (
        _ansi(s.head, "ENABLED") if tool.meta.enabled else _ansi(s.error, "DISABLED")
    )
    lines.append(f"Status: {status}")
    lines.append(f"Version: {tool.meta.version}")
    if tool.meta.author:
        lines.append(f"Author: {tool.meta.author}")
    lines.append(f"Signature: {_ansi(s.symbol, tool.signature)}")
    lines += ["", _ansi(s.head, "Description:")]
    for wrapped in textwrap.wrap(_sanitize_display_text(tool.meta.description), 50):
        lines.append(_ansi(s.grey, f"  {wrapped}"))
    if tool.docstring:
        doc_preview = tool.docstring[:150]
        if len(tool.docstring) > 150:
            doc_preview += "..."
        lines += ["", _ansi(s.head, "Docstring:")]
        for doc_line in doc_preview.splitlines():
            lines.append(_ansi(s.grey, f"  {doc_line}"))
    lines += ["", _ansi(s.head, "Source:"), _ansi(s.grey, f"  {tool.source_path}")]
    return "\n".join(lines)


def highlight_source_lines(source_lines: List[str]) -> List[str]:
    """Colorize Python source with the theme-aware termflow highlighter."""
    from termflow.syntax import Highlighter

    from code_puppy.callbacks import on_termflow_highlighter

    try:
        highlighter = on_termflow_highlighter(Highlighter())
        return [highlighter.highlight_line(line, "python") for line in source_lines]
    except Exception:
        return list(source_lines)


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


def build_tools_menu(tools: List[UCToolInfo], initial_index: int = 0, **overrides):
    """Tool list with preview; e/d exit with action sentinels."""
    from termflow.tui import MenuBuilder, MenuItem
    from termflow.tui.menu import MenuResult

    from code_puppy.command_line.tui_style import themed

    items = [
        MenuItem(
            f"{'+' if t.meta.enabled else '-'} {t.full_name}",
            value=t,
            description=_sanitize_display_text(t.meta.description)[:60],
        )
        for t in tools
    ]

    def action_handler(sentinel):
        def handler(_menu, item):
            return MenuResult(item=MenuItem("", value=(sentinel, item.value)))

        return handler

    builder = themed(
        MenuBuilder("UC Tools")
        .items(items)
        .list_width(40)
        .alt_screen(False)
        .initial_index(min(initial_index, max(len(items) - 1, 0)))
        .preview(
            lambda item: tool_details(
                item.value if not isinstance(item.value, tuple) else item.value[1]
            )
        )
        .footer_hint("Enter view source - e toggle - d delete - Esc exit")
        .on_key("e", action_handler(_TOGGLE))
        .on_key("d", action_handler(_DELETE))
    )
    for name, value in overrides.items():
        getattr(builder, name)(value)
    return builder.build()


def view_tool_source(tool: UCToolInfo, **overrides) -> None:
    """Show a tool's source in a Pager (blocking)."""
    from termflow.tui import PagerBuilder

    from code_puppy.command_line.tui_style import menu_style

    source_lines, error = _load_source_code(tool)
    lines = [error] if error else highlight_source_lines(source_lines)
    builder = (
        PagerBuilder(f"Source - {tool.full_name}")
        .lines(lines)
        .footer_hint("j/k scroll - g/G jump - q/Esc back")
        .alt_screen(False)
    )
    style = menu_style()
    if style is not None:
        builder.style(style)
    for name, value in overrides.items():
        getattr(builder, name)(value)
    builder.build().run()


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------


def run_uc_picker_flow(
    tools_menu_factory: Callable = build_tools_menu,
    source_viewer: Callable = view_tool_source,
    toggle_tool: Callable = _toggle_tool_enabled,
    delete_tool: Callable = _delete_tool,
) -> Optional[str]:
    """Browse loop. Returns the last-viewed tool name, or None."""
    result: Optional[str] = None
    cursor = 0
    while True:
        tools = _get_tool_entries()
        menu_result = tools_menu_factory(tools, initial_index=cursor).run()
        if menu_result.cancelled or menu_result.item is None:
            break
        value = menu_result.item.value
        if isinstance(value, tuple):
            action, tool = value
            cursor = next(
                (i for i, t in enumerate(tools) if t.full_name == tool.full_name), 0
            )
            if action == _TOGGLE:
                toggle_tool(tool)
            elif action == _DELETE:
                delete_tool(tool)
                cursor = 0
            continue
        tool = value
        cursor = next(
            (i for i, t in enumerate(tools) if t.full_name == tool.full_name), 0
        )
        result = tool.full_name
        source_viewer(tool)

    emit_info("Exited UC tool browser")
    return result


async def interactive_uc_picker() -> Optional[str]:
    """Show interactive TUI to browse UC tools."""
    from code_puppy.command_line.menu_session import menu_session

    set_awaiting_user_input(True)
    try:
        with menu_session():
            return await asyncio.to_thread(run_uc_picker_flow)
    finally:
        set_awaiting_user_input(False)


@register_command(
    name="uc",
    description="Universal Constructor - browse and manage custom tools",
    usage="/uc",
    category="tools",
)
def handle_uc_command(command: str) -> bool:
    """Handle the /uc command - opens the interactive TUI."""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, interactive_uc_picker())
                future.result()
        else:
            asyncio.run(interactive_uc_picker())
    except Exception as e:
        emit_error(f"Failed to open UC menu: {e}")

    return True
