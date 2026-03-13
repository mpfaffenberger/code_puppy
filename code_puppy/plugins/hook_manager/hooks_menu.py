"""
Interactive TUI for managing Claude Code hooks.

Launch with /hooks to browse, enable/disable, inspect, and delete hooks
from both global (~/.code_puppy/hooks.json) and project (.claude/settings.json) sources.

Built with prompt_toolkit to match the existing skills_menu aesthetic exactly
(VSplit, FormattedTextControl, Frame).
"""

import sys
import time
from typing import List, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.messaging import emit_error

from .config import (
    HookEntry,
    _load_global_hooks_config,
    _load_project_hooks_config,
    delete_hook,
    flatten_all_hooks,
    save_global_hooks_config,
    save_hooks_config,
    toggle_hook_enabled,
)

PAGE_SIZE = 12

# Colour palette (matches skills_menu palette)
_C_ENABLED = "fg:ansigreen"
_C_DISABLED = "fg:ansired"
_C_SELECTED_BG = "bold"
_C_DIM = "fg:ansibrightblack"
_C_CYAN = "fg:ansicyan"
_C_YELLOW = "fg:ansiyellow"
_C_MAGENTA = "fg:ansimagenta"
_C_HEADER = "dim cyan"
_C_GLOBAL = "fg:ansiblue"
_C_PROJECT = "fg:ansigreen"


class HooksMenu:
    """Interactive TUI for managing hooks from both global and project sources."""

    def __init__(self) -> None:
        self.entries: List[HookEntry] = []
        self.selected_idx: int = 0
        self.current_page: int = 0
        self.result: Optional[str] = None
        self.status_message: str = ""

        # prompt_toolkit controls (set during run())
        self.list_control: Optional[FormattedTextControl] = None
        self.detail_control: Optional[FormattedTextControl] = None

        self._refresh_data()

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------

    def _refresh_data(self) -> None:
        """Reload hooks from both global and project sources."""
        try:
            self.entries = flatten_all_hooks()
            # Clamp selection
            if self.entries:
                self.selected_idx = min(self.selected_idx, len(self.entries) - 1)
            else:
                self.selected_idx = 0
        except Exception as exc:
            emit_error(f"Failed to refresh hooks data: {exc}")
            self.entries = []

    def _current_entry(self) -> Optional[HookEntry]:
        if 0 <= self.selected_idx < len(self.entries):
            return self.entries[self.selected_idx]
        return None

    def _save_current_entry(
        self, entry: HookEntry, new_enabled: Optional[bool] = None
    ) -> None:
        """Persist changes to the current entry's source file."""
        if entry.source == "global":
            global_config = _load_global_hooks_config()
            if new_enabled is not None:
                global_config = toggle_hook_enabled(
                    global_config,
                    entry.event_type,
                    entry._group_index,
                    entry._hook_index,
                    new_enabled,
                )
            save_global_hooks_config(global_config)
        else:  # project
            project_config = _load_project_hooks_config()
            if new_enabled is not None:
                project_config = toggle_hook_enabled(
                    project_config,
                    entry.event_type,
                    entry._group_index,
                    entry._hook_index,
                    new_enabled,
                )
            save_hooks_config(project_config)

    # ------------------------------------------------------------------
    # Actions triggered by key bindings
    # ------------------------------------------------------------------

    def _toggle_current(self) -> None:
        """Toggle enabled/disabled on the selected hook."""
        entry = self._current_entry()
        if entry is None:
            return
        new_enabled = not entry.enabled
        self._save_current_entry(entry, new_enabled)
        self._refresh_data()
        self.status_message = (
            f"Hook {'enabled' if new_enabled else 'disabled'}: {entry.display_command}"
        )
        self.update_display()

    def _delete_current(self) -> None:
        """Delete the selected hook (with guard against empty config)."""
        entry = self._current_entry()
        if entry is None:
            return

        if entry.source == "global":
            global_config = _load_global_hooks_config()
            global_config = delete_hook(
                global_config,
                entry.event_type,
                entry._group_index,
                entry._hook_index,
            )
            save_global_hooks_config(global_config)
        else:  # project
            project_config = _load_project_hooks_config()
            project_config = delete_hook(
                project_config,
                entry.event_type,
                entry._group_index,
                entry._hook_index,
            )
            save_hooks_config(project_config)

        self._refresh_data()
        self.status_message = f"Deleted hook: {entry.display_command}"
        self.update_display()

    def _enable_all(self) -> None:
        """Enable every hook in both project and global configs."""
        import copy

        # Enable all project hooks
        project_config = _load_project_hooks_config()
        project_cfg = copy.deepcopy(project_config)
        for groups in project_cfg.values():
            if not isinstance(groups, list):
                continue
            for group in groups:
                for hook in group.get("hooks", []):
                    hook["enabled"] = True
        save_hooks_config(project_cfg)

        # Enable all global hooks
        global_config = _load_global_hooks_config()
        global_cfg = copy.deepcopy(global_config)
        for groups in global_cfg.values():
            if not isinstance(groups, list):
                continue
            for group in groups:
                for hook in group.get("hooks", []):
                    hook["enabled"] = True
        save_global_hooks_config(global_cfg)

        self._refresh_data()
        self.status_message = "All hooks enabled."
        self.update_display()

    def _disable_all(self) -> None:
        """Disable every hook in both project and global configs."""
        import copy

        # Disable all project hooks
        project_config = _load_project_hooks_config()
        project_cfg = copy.deepcopy(project_config)
        for groups in project_cfg.values():
            if not isinstance(groups, list):
                continue
            for group in groups:
                for hook in group.get("hooks", []):
                    hook["enabled"] = False
        save_hooks_config(project_cfg)

        # Disable all global hooks
        global_config = _load_global_hooks_config()
        global_cfg = copy.deepcopy(global_config)
        for groups in global_cfg.values():
            if not isinstance(groups, list):
                continue
            for group in groups:
                for hook in group.get("hooks", []):
                    hook["enabled"] = False
        save_global_hooks_config(global_cfg)

        self._refresh_data()
        self.status_message = "All hooks disabled."
        self.update_display()

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _render_list(self) -> List:
        """Render the left-hand hooks list panel."""
        lines: List = []

        total = len(self.entries)
        enabled_count = sum(1 for e in self.entries if e.enabled)
        project_count = sum(1 for e in self.entries if e.source == "project")
        global_count = sum(1 for e in self.entries if e.source == "global")

        header_color = _C_ENABLED if enabled_count > 0 else _C_DISABLED
        lines.append((header_color, f" Hooks: {enabled_count}/{total} enabled"))
        lines.append(("", f"  ({project_count} project, {global_count} global)\n\n"))

        if not self.entries:
            lines.append((_C_YELLOW, "  No hooks configured."))
            lines.append(("", "\n"))
            lines.append((_C_DIM, "  Add hooks to .claude/settings.json (project)"))
            lines.append(("", "\n"))
            lines.append((_C_DIM, "  or ~/.code_puppy/hooks.json (global)"))
            lines.append(("", "\n\n"))
            self._render_nav_hints(lines)
            return lines

        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        start = self.current_page * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        for i in range(start, end):
            entry = self.entries[i]
            is_selected = i == self.selected_idx
            status_icon = "✓" if entry.enabled else "✗"
            status_style = _C_ENABLED if entry.enabled else _C_DISABLED
            source_indicator = "🌍" if entry.source == "global" else "📁"
            prefix = " > " if is_selected else "   "

            if is_selected:
                lines.append((_C_SELECTED_BG, prefix))
                lines.append((status_style + " bold", status_icon))
                lines.append(
                    (_C_SELECTED_BG, f" {source_indicator} [{entry.event_type}]")
                )
                lines.append((_C_SELECTED_BG, f" {entry.display_matcher}"))
            else:
                lines.append(("", prefix))
                lines.append((status_style, status_icon))
                source_color = _C_GLOBAL if entry.source == "global" else _C_PROJECT
                lines.append((source_color, f" {source_indicator}"))
                lines.append((_C_DIM, f" [{entry.event_type}]"))
                lines.append(("", f" {entry.display_matcher}"))
            lines.append(("", "\n"))

        lines.append(("", "\n"))
        lines.append((_C_DIM, f" Page {self.current_page + 1}/{total_pages}"))
        lines.append(("", "\n"))

        # Status message (shows result of last action)
        if self.status_message:
            lines.append(("", "\n"))
            lines.append((_C_CYAN, f" {self.status_message}"))
            lines.append(("", "\n"))

        self._render_nav_hints(lines)
        return lines

    def _render_nav_hints(self, lines: List) -> None:
        """Append keyboard shortcut hints to lines."""
        lines.append(("", "\n"))
        lines.append((_C_DIM, "  ↑/↓ j/k "))
        lines.append(("", "Navigate\n"))
        lines.append((_C_ENABLED, "  Enter   "))
        lines.append(("", "Toggle enable/disable\n"))
        lines.append((_C_DISABLED, "  d       "))
        lines.append(("", "Delete hook\n"))
        lines.append((_C_YELLOW, "  A       "))
        lines.append(("", "Enable all\n"))
        lines.append((_C_MAGENTA, "  D       "))
        lines.append(("", "Disable all\n"))
        lines.append((_C_YELLOW, "  r       "))
        lines.append(("", "Refresh\n"))
        lines.append((_C_DISABLED, "  q/Esc   "))
        lines.append(("", "Exit"))

    def _render_detail(self) -> List:
        """Render the right-hand hook detail panel."""
        lines: List = []
        lines.append((_C_HEADER, " HOOK DETAILS"))
        lines.append(("", "\n\n"))

        entry = self._current_entry()
        if entry is None:
            lines.append((_C_YELLOW, "  No hook selected."))
            lines.append(("", "\n\n"))
            lines.append((_C_DIM, "  Select a hook from the list"))
            lines.append(("", "\n"))
            lines.append((_C_DIM, "  to view its details."))
            return lines

        # Status badge
        status_text = "Enabled" if entry.enabled else "Disabled"
        status_style = _C_ENABLED + " bold" if entry.enabled else _C_DISABLED + " bold"
        lines.append(("bold", "  Status:  "))
        lines.append((status_style, status_text))
        lines.append(("", "\n\n"))

        # Source indicator
        source_label = (
            "Global (~/.code_puppy/hooks.json)"
            if entry.source == "global"
            else "Project (.claude/settings.json)"
        )
        source_color = _C_GLOBAL if entry.source == "global" else _C_PROJECT
        lines.append(("bold", "  Source:  "))
        lines.append((source_color, source_label))
        lines.append(("", "\n\n"))

        # Event type
        lines.append(("bold", "  Event:   "))
        lines.append((_C_CYAN, entry.event_type))
        lines.append(("", "\n\n"))

        # Matcher
        lines.append(("bold", "  Matcher: "))
        lines.append(("", "\n"))
        for chunk in _wrap(entry.matcher, 50):
            lines.append((_C_YELLOW, f"    {chunk}"))
            lines.append(("", "\n"))
        lines.append(("", "\n"))

        # Type
        lines.append(("bold", "  Type:    "))
        lines.append((_C_DIM, entry.hook_type))
        lines.append(("", "\n\n"))

        # Command / prompt
        label = "Command:" if entry.hook_type == "command" else "Prompt: "
        lines.append(("bold", f"  {label}"))
        lines.append(("", "\n"))
        for chunk in _wrap(entry.command, 50):
            lines.append((_C_DIM, f"    {chunk}"))
            lines.append(("", "\n"))
        lines.append(("", "\n"))

        # Timeout
        lines.append(("bold", "  Timeout: "))
        lines.append((_C_DIM, f"{entry.timeout} ms"))
        lines.append(("", "\n\n"))

        # Hook ID
        if entry.hook_id:
            lines.append(("bold", "  ID:      "))
            lines.append((_C_DIM, entry.hook_id))
            lines.append(("", "\n\n"))

        # Config location hint
        lines.append((_C_DIM, f"  Stored in {source_label}"))
        lines.append(("", "\n"))
        lines.append(
            (_C_DIM, f"  group #{entry._group_index}  hook #{entry._hook_index}")
        )
        lines.append(("", "\n"))

        return lines

    def update_display(self) -> None:
        """Push freshly rendered text into the prompt_toolkit controls."""
        if self.list_control:
            self.list_control.text = self._render_list()
        if self.detail_control:
            self.detail_control.text = self._render_detail()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self) -> Optional[str]:
        """Launch the interactive TUI.  Returns the exit reason string."""
        self.result = None

        self.list_control = FormattedTextControl(text="")
        self.detail_control = FormattedTextControl(text="")

        list_window = Window(
            content=self.list_control, wrap_lines=True, width=Dimension(weight=40)
        )
        detail_window = Window(
            content=self.detail_control, wrap_lines=True, width=Dimension(weight=60)
        )

        list_frame = Frame(list_window, width=Dimension(weight=40), title="Hooks")
        detail_frame = Frame(detail_window, width=Dimension(weight=60), title="Details")

        root_container = VSplit([list_frame, detail_frame])
        kb = KeyBindings()

        # --- Navigation ---
        @kb.add("up")
        @kb.add("c-p")
        @kb.add("k")
        def _move_up(event):
            if self.selected_idx > 0:
                self.selected_idx -= 1
                self.current_page = self.selected_idx // PAGE_SIZE
            self.update_display()

        @kb.add("down")
        @kb.add("c-n")
        @kb.add("j")
        def _move_down(event):
            if self.selected_idx < len(self.entries) - 1:
                self.selected_idx += 1
                self.current_page = self.selected_idx // PAGE_SIZE
            self.update_display()

        @kb.add("left")
        def _prev_page(event):
            if self.current_page > 0:
                self.current_page -= 1
                self.selected_idx = self.current_page * PAGE_SIZE
            self.update_display()

        @kb.add("right")
        def _next_page(event):
            total_pages = max(1, (len(self.entries) + PAGE_SIZE - 1) // PAGE_SIZE)
            if self.current_page < total_pages - 1:
                self.current_page += 1
                self.selected_idx = self.current_page * PAGE_SIZE
            self.update_display()

        # --- Actions ---
        @kb.add("enter")
        def _toggle(event):
            self._toggle_current()
            self.result = "changed"

        @kb.add("d")
        def _delete(event):
            self._delete_current()
            self.result = "changed"

        @kb.add("A")  # capital A = enable ALL
        def _enable_all(event):
            self._enable_all()
            self.result = "changed"

        @kb.add("D")  # capital D = disable ALL
        def _disable_all(event):
            self._disable_all()
            self.result = "changed"

        @kb.add("r")
        def _refresh(event):
            self._refresh_data()
            self.status_message = "Refreshed."
            self.update_display()

        # --- Exit ---
        @kb.add("q")
        @kb.add("escape")
        def _quit(event):
            self.result = "quit"
            event.app.exit()

        @kb.add("c-c")
        def _quit_ctrl_c(event):
            self.result = "quit"
            event.app.exit()

        layout = Layout(root_container)
        app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=False,
            mouse_support=False,
        )

        try:
            from code_puppy.tools.command_runner import set_awaiting_user_input

            set_awaiting_user_input(True)
        except Exception:
            pass

        # Enter alternate screen buffer
        sys.stdout.write("\033[?1049h")
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
        time.sleep(0.05)

        try:
            self.update_display()
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
            app.run(in_thread=True)
        finally:
            sys.stdout.write("\033[?1049l")
            sys.stdout.flush()
            try:
                import termios

                termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
            except Exception:
                pass  # ImportError on Windows, termios.error, or not a tty
            time.sleep(0.1)
            try:
                from code_puppy.tools.command_runner import set_awaiting_user_input

                set_awaiting_user_input(False)
            except Exception:
                pass

        return self.result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wrap(text: str, width: int) -> List[str]:
    """Wrap text to *width* characters, splitting on whitespace."""
    words = text.split()
    lines: List[str] = []
    current: List[str] = []
    length = 0
    for word in words:
        if length + len(word) + (1 if current else 0) <= width:
            current.append(word)
            length += len(word) + (1 if len(current) > 1 else 0)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
            length = len(word)
    if current:
        lines.append(" ".join(current))
    return lines or [""]


def show_hooks_menu() -> None:
    """Public entry point called from register_callbacks.py."""
    menu = HooksMenu()
    menu.run()
