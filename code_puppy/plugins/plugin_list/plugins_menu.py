"""Interactive TUI for managing plugins.

Launch with ``/plugins`` to browse and toggle plugins on/off.
Built with prompt_toolkit, following the same pattern as the skills menu.
"""

from __future__ import annotations

import sys
import time
from typing import List, Optional, Tuple

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.command_line.pagination import (
    ensure_visible_page,
    get_page_bounds,
    get_total_pages,
)
from code_puppy.tools.command_runner import set_awaiting_user_input

PAGE_SIZE = 20


class _PluginEntry:
    """Lightweight struct for a loaded plugin."""

    __slots__ = ("name", "tier")

    def __init__(self, name: str, tier: str) -> None:
        self.name = name
        self.tier = tier


class PluginsMenu:
    """Interactive TUI for enabling/disabling plugins."""

    def __init__(self) -> None:
        self.plugins: List[_PluginEntry] = []
        self.disabled: set[str] = set()

        self.selected_idx = 0
        self.current_page = 0
        self.result: Optional[str] = None
        self._changed = False

        self.menu_control: Optional[FormattedTextControl] = None
        self.detail_control: Optional[FormattedTextControl] = None

        self._refresh_data()

    # -- data helpers ------------------------------------------------------

    def _refresh_data(self) -> None:
        from code_puppy.plugins import get_loaded_plugins
        from code_puppy.plugins.config import get_disabled_plugins

        loaded = get_loaded_plugins()
        self.disabled = get_disabled_plugins()

        entries: List[_PluginEntry] = []
        for tier in ("builtin", "user", "project"):
            for name in sorted(loaded.get(tier, [])):
                entries.append(_PluginEntry(name, tier))
        self.plugins = entries

    def _current(self) -> Optional[_PluginEntry]:
        if 0 <= self.selected_idx < len(self.plugins):
            return self.plugins[self.selected_idx]
        return None

    def _toggle_current(self) -> None:
        entry = self._current()
        if not entry:
            return
        from code_puppy.plugins.config import set_plugin_disabled

        is_disabled = entry.name in self.disabled
        set_plugin_disabled(entry.name, not is_disabled)
        self._changed = True
        self._refresh_data()
        self.update_display()

    # -- rendering ---------------------------------------------------------

    def _render_list(self) -> List[Tuple[str, str]]:
        lines: List[Tuple[str, str]] = []

        lines.append(("bold", " Plugins"))
        lines.append(("", "\n\n"))

        if not self.plugins:
            lines.append(("fg:ansiyellow", "  No plugins loaded."))
            lines.append(("", "\n"))
            self._render_hints(lines)
            return lines

        total_pages = get_total_pages(len(self.plugins), PAGE_SIZE)
        start_idx, end_idx = get_page_bounds(
            self.current_page, len(self.plugins), PAGE_SIZE
        )

        for i in range(start_idx, end_idx):
            entry = self.plugins[i]
            is_selected = i == self.selected_idx
            is_disabled = entry.name in self.disabled

            icon = "x" if is_disabled else "+"
            icon_style = "fg:ansired" if is_disabled else "fg:ansigreen"
            prefix = " > " if is_selected else "   "

            if is_selected:
                lines.append(("bold", prefix))
                lines.append((icon_style + " bold", icon))
                lines.append(("bold", f" {entry.name}"))
            else:
                lines.append(("", prefix))
                lines.append((icon_style, icon))
                lines.append(("fg:ansibrightblack", f" {entry.name}"))

            lines.append(("", "\n"))

        lines.append(("", "\n"))
        lines.append(
            ("fg:ansibrightblack", f" Page {self.current_page + 1}/{total_pages}")
        )
        lines.append(("", "\n"))

        self._render_hints(lines)
        return lines

    def _render_hints(self, lines: List[Tuple[str, str]]) -> None:
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  up/down or j/k "))
        lines.append(("", "Navigate\n"))
        lines.append(("fg:ansibrightblack", "  left/right     "))
        lines.append(("", "Page\n"))
        lines.append(("fg:ansigreen", "  Enter          "))
        lines.append(("", "Toggle\n"))
        lines.append(("fg:ansired", "  q / Esc        "))
        lines.append(("", "Exit"))

    def _render_detail(self) -> List[Tuple[str, str]]:
        lines: List[Tuple[str, str]] = []

        lines.append(("dim cyan", " PLUGIN DETAILS"))
        lines.append(("", "\n\n"))

        entry = self._current()
        if not entry:
            lines.append(("fg:ansiyellow", "  No plugin selected."))
            return lines

        is_disabled = entry.name in self.disabled

        # Name
        lines.append(("bold", f"  {entry.name}"))
        lines.append(("", "\n\n"))

        # Tier
        lines.append(("bold", "  Tier: "))
        lines.append(("", entry.tier))
        lines.append(("", "\n\n"))

        # Status
        lines.append(("bold", "  Status: "))
        if is_disabled:
            lines.append(("fg:ansired bold", "Disabled"))
            lines.append(("", "\n"))
            lines.append(
                ("fg:ansibrightblack", "  Callbacks are skipped at dispatch time.")
            )
        else:
            lines.append(("fg:ansigreen bold", "Enabled"))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", "  All callbacks are active."))
        lines.append(("", "\n\n"))

        lines.append(("fg:ansibrightblack", "  Press Enter to toggle."))

        if self._changed:
            lines.append(("", "\n\n"))
            lines.append(("fg:ansiyellow bold", "  Restart Mist for"))
            lines.append(("", "\n"))
            lines.append(("fg:ansiyellow bold", "  changes to take effect."))

        return lines

    # -- display update ----------------------------------------------------

    def update_display(self) -> None:
        if self.menu_control:
            self.menu_control.text = self._render_list()
        if self.detail_control:
            self.detail_control.text = self._render_detail()

    # -- application -------------------------------------------------------

    def run(self) -> Optional[str]:
        self.menu_control = FormattedTextControl(text="")
        self.detail_control = FormattedTextControl(text="")

        menu_window = Window(
            content=self.menu_control, wrap_lines=True, width=Dimension(weight=40)
        )
        detail_window = Window(
            content=self.detail_control, wrap_lines=True, width=Dimension(weight=60)
        )

        menu_frame = Frame(menu_window, width=Dimension(weight=40), title="Plugins")
        detail_frame = Frame(detail_window, width=Dimension(weight=60), title="Details")

        root_container = VSplit([menu_frame, detail_frame])

        kb = KeyBindings()

        @kb.add("up")
        @kb.add("k")
        def _(event):
            if self.selected_idx > 0:
                self.selected_idx -= 1
                self.current_page = ensure_visible_page(
                    self.selected_idx,
                    self.current_page,
                    len(self.plugins),
                    PAGE_SIZE,
                )
            self.update_display()

        @kb.add("down")
        @kb.add("j")
        def _(event):
            if self.selected_idx < len(self.plugins) - 1:
                self.selected_idx += 1
                self.current_page = ensure_visible_page(
                    self.selected_idx,
                    self.current_page,
                    len(self.plugins),
                    PAGE_SIZE,
                )
            self.update_display()

        @kb.add("left")
        def _(event):
            if self.current_page > 0:
                self.current_page -= 1
                self.selected_idx = self.current_page * PAGE_SIZE
                self.update_display()

        @kb.add("right")
        def _(event):
            total_pages = get_total_pages(len(self.plugins), PAGE_SIZE)
            if self.current_page < total_pages - 1:
                self.current_page += 1
                self.selected_idx = self.current_page * PAGE_SIZE
                self.update_display()

        @kb.add("enter")
        def _(event):
            self._toggle_current()
            self.result = "changed"

        @kb.add("q")
        @kb.add("escape")
        def _(event):
            self.result = "quit"
            event.app.exit()

        @kb.add("c-c")
        def _(event):
            self.result = "quit"
            event.app.exit()

        layout = Layout(root_container)
        app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=False,
            mouse_support=False,
        )

        set_awaiting_user_input(True)

        sys.stdout.write("\033[?1049h")  # Enter alternate buffer
        sys.stdout.write("\033[2J\033[H")  # Clear and home
        sys.stdout.flush()
        time.sleep(0.05)

        try:
            self.update_display()

            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

            app.run(in_thread=True)

        finally:
            sys.stdout.write("\033[?1049l")  # Exit alternate buffer
            sys.stdout.flush()

            try:
                import termios

                termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
            except Exception:
                pass

            time.sleep(0.1)
            set_awaiting_user_input(False)

        return self.result


def run_plugins_menu() -> Optional[str]:
    """Entry point: create and run the plugins TUI, return the result."""
    from code_puppy.messaging import emit_warning

    menu = PluginsMenu()
    result = menu.run()

    if menu._changed:
        emit_warning("Restart Mist for plugin changes to take effect.")

    return result
