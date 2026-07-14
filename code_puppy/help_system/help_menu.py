"""Interactive help menu TUI - Full screen panel.

Browse commands, categories, and search results in a split-panel interface.
"""

from __future__ import annotations

import asyncio
from typing import List, Optional

import shutil
import sys
from typing import Tuple

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.help_system.help_content import HELP_CATEGORIES, COMMAND_HELP


class _HelpEntry:
    """Lightweight struct for a help item."""

    __slots__ = ("name", "brief", "category", "is_command")

    def __init__(self, name: str, brief: str, category: str, is_command: bool = False):
        self.name = name
        self.brief = brief
        self.category = category
        self.is_command = is_command


class HelpMenu:
    """Interactive TUI for browsing help content."""

    def __init__(self):
        self.entries: List[_HelpEntry] = []
        self.selected_idx = 0
        self.current_page = 0
        self.page_size = 18
        self.result: Optional[str] = None

        self.menu_control: Optional[FormattedTextControl] = None
        self.detail_control: Optional[FormattedTextControl] = None

        # Dynamic dimensions (updated on terminal resize)
        self._menu_cols = 35
        self._detail_cols = 55
        self._pane_rows = 25
        self._last_size: Tuple[int, int] = (0, 0)

        self._refresh_data()

    def _measure_terminal(self) -> Tuple[int, int]:
        """Return (cols, rows) of the current terminal."""
        try:
            size = shutil.get_terminal_size(fallback=(120, 40))
            return max(60, size.columns), max(15, size.lines)
        except Exception:
            return 120, 40

    def _recompute_dimensions(self) -> bool:
        """Re-measure terminal and recompute pane widths."""
        cols, rows = self._measure_terminal()
        if self._last_size == (cols, rows):
            return False
        self._last_size = (cols, rows)
        # Two side-by-side Frames cost 4 columns of border
        usable_cols = max(40, cols - 4)
        # 35% / 65% split
        self._menu_cols = max(25, min(45, int(usable_cols * 0.35)))
        self._detail_cols = max(30, usable_cols - self._menu_cols)
        # Reserve 2 rows for Frame borders
        self._pane_rows = max(10, rows - 4)
        self.page_size = max(5, self._pane_rows - 6)
        return True

    def _refresh_data(self) -> None:
        """Load all help entries from registry and categories."""
        self.entries = []

        # Add categories
        for cat_name, cat_info in HELP_CATEGORIES.items():
            if isinstance(cat_info, dict) and "description" in cat_info:
                self.entries.append(
                    _HelpEntry(
                        name=cat_name.title(),
                        brief=cat_info["description"],
                        category="Category",
                        is_command=False,
                    )
                )

        # Add all registered commands from command_registry
        try:
            from code_puppy.command_line.command_registry import get_unique_commands

            for cmd_info in get_unique_commands():
                if cmd_info.name not in ("help", "h"):
                    brief = COMMAND_HELP.get(f"/{cmd_info.name}", {}).get(
                        "brief", cmd_info.description
                    )
                    self.entries.append(
                        _HelpEntry(
                            name=f"/{cmd_info.name}",
                            brief=brief,
                            category="Command",
                            is_command=True,
                        )
                    )
        except Exception:
            pass

    def _current(self) -> Optional[_HelpEntry]:
        if 0 <= self.selected_idx < len(self.entries):
            return self.entries[self.selected_idx]
        return None

    def _render_menu_fragment(self) -> FormattedText:
        """Build the left pane (list of entries)."""
        lines: list[tuple[str, str]] = []
        start = self.current_page * self.page_size
        end = min(start + self.page_size, len(self.entries))

        # Header
        lines.append(("bold cyan", " Browse"))
        lines.append(("", "\n\n"))

        for i in range(start, end):
            entry = self.entries[i]
            is_selected = i == self.selected_idx

            if is_selected:
                lines.append(("fg:white bg:ansibrightblack", f" > {entry.name}\n"))
            else:
                lines.append(("", f"   {entry.name}\n"))

        # Pad remaining lines
        lines_shown = end - start
        for _ in range(self.page_size - lines_shown):
            lines.append(("", "\n"))

        # Footer with pagination info
        total_pages = max(1, (len(self.entries) + self.page_size - 1) // self.page_size)
        lines.append(("", f"\n [{self.current_page + 1}/{total_pages}]"))

        return FormattedText(lines)

    def _render_detail_fragment(self) -> FormattedText:
        """Build the right pane (details for selected entry)."""
        entry = self._current()
        if not entry:
            return FormattedText([("", "\n\n\n\n     Select an item to view details")])

        lines: list[tuple[str, str]] = []

        # Header
        lines.append(("bold white", f" {entry.name}\n"))
        lines.append(("dim", " " + "=" * 44 + "\n\n"))

        if entry.is_command:
            cmd_info = COMMAND_HELP.get(entry.name, {})

            if cmd_info:
                lines.append(("bold", " Description\n"))
                lines.append(("", f"  {cmd_info.get('description', 'N/A')}\n\n"))

                lines.append(("bold", " Syntax\n"))
                lines.append(("fg:cyan", f"  {cmd_info.get('syntax', 'N/A')}\n\n"))

                if cmd_info.get("examples"):
                    lines.append(("bold", " Examples\n"))
                    for ex in cmd_info["examples"][:4]:
                        lines.append(("fg:green", f"    {ex}\n"))
                    lines.append(("", "\n"))

                if cmd_info.get("tips"):
                    lines.append(("bold", " Tips\n"))
                    for tip in cmd_info["tips"][:3]:
                        lines.append(("fg:yellow", f"  - {tip}\n"))
                    lines.append(("", "\n"))

                if cmd_info.get("related"):
                    lines.append(("bold", " Related\n"))
                    for rel in cmd_info["related"]:
                        lines.append(("fg:magenta", f"    {rel}\n"))
            else:
                # Fallback for commands not in COMMAND_HELP
                from code_puppy.command_line.command_registry import get_command

                cmd_name = entry.name.lstrip("/")
                cmd = get_command(cmd_name)
                if cmd:
                    lines.append(("", f"  {cmd.description}\n\n"))
                    lines.append(("bold", " Syntax\n"))
                    lines.append(("fg:cyan", f"  {cmd.usage}\n"))
                    if cmd.aliases:
                        lines.append(("", f"\n  Aliases: {', '.join(cmd.aliases)}\n"))
        else:
            # Category view
            cat_info = HELP_CATEGORIES.get(entry.name.lower(), {})
            if "items" in cat_info:
                lines.append(("", f"  {cat_info.get('description', '')}\n\n"))
                lines.append(("bold", " Items\n\n"))
                for item_name, item_info in cat_info["items"].items():
                    if isinstance(item_info, dict):
                        brief = item_info.get("brief", "")
                    else:
                        brief = str(item_info)
                    lines.append(("fg:cyan", f"    {item_name:<20}"))
                    lines.append(("", f" {brief}\n"))

        return FormattedText(lines)

    def _build_layout(self) -> Layout:
        """Build the split-panel layout with dynamic sizing."""
        self.menu_control = FormattedTextControl(self._render_menu_fragment)
        self.detail_control = FormattedTextControl(self._render_detail_fragment)

        footer_control = FormattedTextControl(
            lambda: FormattedText(
                [
                    ("bold fg:cyan", "  ↑↓ Navigate  "),
                    ("", "|"),
                    ("bold fg:green", "  Enter Select  "),
                    ("", "|"),
                    ("bold fg:yellow", "  q Esc Quit  "),
                    ("", "|"),
                    ("dim", "  PgUp/PgDn Page  "),
                ]
            )
        )

        def menu_width() -> Dimension:
            return Dimension(min=20, max=self._menu_cols, preferred=self._menu_cols)

        def detail_width() -> Dimension:
            return Dimension(min=25, max=self._detail_cols, preferred=self._detail_cols)

        def pane_height() -> Dimension:
            return Dimension(min=8, max=self._pane_rows, preferred=self._pane_rows)

        menu_window = Window(
            content=self.menu_control,
            wrap_lines=False,
            width=menu_width,
            height=pane_height,
        )
        detail_window = Window(
            content=self.detail_control,
            wrap_lines=False,
            width=detail_width,
            height=pane_height,
        )

        footer_window = Window(footer_control, height=1)

        left = Frame(menu_window, title="Commands")
        right = Frame(detail_window, title="Details")

        from prompt_toolkit.layout import HSplit

        return Layout(
            HSplit(
                [
                    VSplit([left, right]),
                    footer_window,
                ]
            )
        )

    def _build_key_bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("down")
        @kb.add("j")
        def _(event):
            if self.selected_idx < len(self.entries) - 1:
                self.selected_idx += 1
                new_page = self.selected_idx // self.page_size
                if new_page != self.current_page:
                    self.current_page = new_page
                event.app.invalidate()

        @kb.add("up")
        @kb.add("k")
        def _(event):
            if self.selected_idx > 0:
                self.selected_idx -= 1
                new_page = self.selected_idx // self.page_size
                if new_page != self.current_page:
                    self.current_page = new_page
                event.app.invalidate()

        @kb.add("pageup")
        @kb.add("c-p")
        def _(event):
            self.selected_idx = max(0, self.selected_idx - self.page_size)
            self.current_page = self.selected_idx // self.page_size
            event.app.invalidate()

        @kb.add("pagedown")
        @kb.add("c-n")
        def _(event):
            self.selected_idx = min(
                len(self.entries) - 1, self.selected_idx + self.page_size
            )
            self.current_page = self.selected_idx // self.page_size
            event.app.invalidate()

        @kb.add("enter")
        def _(event):
            entry = self._current()
            if entry:
                self.result = entry.name
                event.app.exit()

        @kb.add("escape")
        @kb.add("c-c")
        def _(event):
            self.result = None
            event.app.exit()

        return kb

    async def run_async(self) -> Optional[str]:
        """Run the interactive help menu asynchronously."""
        # Compute initial dimensions
        self._recompute_dimensions()

        kb = self._build_key_bindings()
        layout = self._build_layout()

        result: list[Optional[str]] = [None]

        app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=False,
            mouse_support=False,
        )

        original_exit = app.exit

        def _exit(result_value=None):
            result[0] = result_value if result_value is not None else self.result
            original_exit(result=result_value)

        app.exit = _exit

        # Enter alt screen
        sys.stdout.write("\033[?1049h\033[2J\033[H")
        sys.stdout.flush()

        try:
            await app.run_async()
        except Exception:
            return None
        finally:
            # Exit alt screen
            sys.stdout.write("\033[?1049l")
            sys.stdout.flush()

        return result[0]


async def interactive_help_async() -> Optional[str]:
    """Launch the interactive help menu asynchronously."""
    from code_puppy.tools.command_runner import set_awaiting_user_input

    set_awaiting_user_input(True)
    try:
        menu = HelpMenu()
        return await menu.run_async()
    except KeyboardInterrupt:
        return None
    finally:
        set_awaiting_user_input(False)


def interactive_help() -> Optional[str]:
    """Launch the interactive help menu (sync wrapper)."""
    try:
        return asyncio.run(interactive_help_async())
    except Exception:
        return None
