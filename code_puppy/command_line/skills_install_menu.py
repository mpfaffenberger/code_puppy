"""Interactive terminal UI for browsing and installing bundled skills.

Modeled closely on `code_puppy/command_line/mcp/install_menu.py`.

This menu is used for `/skills install` to browse the bundled skill catalog
and install skills into the user's skill directory.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import List, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.plugins.agent_skills.installer import install_skill, is_skill_installed
from code_puppy.plugins.agent_skills.skill_catalog import SkillCatalogEntry
from code_puppy.tools.command_runner import set_awaiting_user_input

PAGE_SIZE = 12  # Items per page (match MCP install menu)


class SkillsInstallMenu:
    """Interactive TUI for browsing and installing bundled skills."""

    def __init__(self) -> None:
        self.catalog = None
        self.categories: List[str] = []

        # Current drill-down state
        self.current_category: Optional[str] = None
        self.current_skills: List[SkillCatalogEntry] = []

        # State management
        self.view_mode = "categories"  # "categories" or "skills"
        self.selected_category_idx = 0
        self.selected_skill_idx = 0
        self.current_page = 0
        self.result: Optional[str] = None

        # Pending install
        self.pending_skill: Optional[SkillCatalogEntry] = None

        # UI controls
        self.menu_control: Optional[FormattedTextControl] = None
        self.preview_control: Optional[FormattedTextControl] = None

        self._initialize_catalog()

    def _initialize_catalog(self) -> None:
        """Initialize bundled skills catalog with error handling."""
        try:
            from code_puppy.plugins.agent_skills.skill_catalog import catalog

            self.catalog = catalog
            self.categories = self.catalog.list_categories()
            if not self.categories:
                emit_warning("No bundled skills found in the catalog")
        except Exception as e:
            emit_error(f"Bundled skill catalog not available: {e}")
            self.catalog = None
            self.categories = []

    # -------------------------
    # Data helpers
    # -------------------------

    def _get_current_category(self) -> Optional[str]:
        if 0 <= self.selected_category_idx < len(self.categories):
            return self.categories[self.selected_category_idx]
        return None

    def _get_current_skill(self) -> Optional[SkillCatalogEntry]:
        if self.view_mode == "skills" and self.current_skills:
            if 0 <= self.selected_skill_idx < len(self.current_skills):
                return self.current_skills[self.selected_skill_idx]
        return None

    def _get_category_icon(self, category: str) -> str:
        icons = {
            "data": "📊",
            "finance": "💰",
            "legal": "⚖️",
            "office": "📄",
            "productmanagement": "📦",
            "product_management": "📦",
            "product management": "📦",
            "sales": "💼",
            "biology": "🧬",
        }
        return icons.get(category.strip().lower(), "📁")

    # -------------------------
    # Rendering
    # -------------------------

    def _wrap_text(self, text: str, width: int) -> List[str]:
        words = (text or "").split()
        if not words:
            return [""]

        lines: List[str] = []
        current: List[str] = []
        length = 0

        for word in words:
            extra = len(word) + (1 if current else 0)
            if length + extra <= width:
                current.append(word)
                length += extra
            else:
                lines.append(" ".join(current))
                current = [word]
                length = len(word)

        if current:
            lines.append(" ".join(current))

        return lines

    def _truncate_path(self, path: Path, max_len: int = 55) -> str:
        s = str(path)
        if len(s) <= max_len:
            return s
        return "..." + s[-(max_len - 3) :]

    def _render_navigation_hints(self, lines: List) -> None:
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  ↑/↓ "))
        lines.append(("", "Navigate  "))
        lines.append(("fg:ansibrightblack", "←/→ "))
        lines.append(("", "Page\n"))
        if self.view_mode == "categories":
            lines.append(("fg:green", "  Enter  "))
            lines.append(("", "Browse Skills\n"))
        else:
            lines.append(("fg:green", "  Enter  "))
            lines.append(("", "Install\n"))
            lines.append(("fg:ansibrightblack", "  Esc/Back  "))
            lines.append(("", "Back\n"))
        lines.append(("fg:ansired", "  Ctrl+C "))
        lines.append(("", "Cancel"))

    def _render_category_list(self) -> List:
        lines: List = []

        lines.append(("bold cyan", " 📂 CATEGORIES"))
        lines.append(("", "\n\n"))

        if not self.categories:
            lines.append(("fg:yellow", "  No categories available."))
            lines.append(("", "\n\n"))
            self._render_navigation_hints(lines)
            return lines

        total_pages = (len(self.categories) + PAGE_SIZE - 1) // PAGE_SIZE
        start_idx = self.current_page * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, len(self.categories))

        for i in range(start_idx, end_idx):
            category = self.categories[i]
            is_selected = i == self.selected_category_idx

            icon = self._get_category_icon(category)
            count = (
                len(self.catalog.get_by_category(category))
                if self.catalog is not None
                else 0
            )

            prefix = " > " if is_selected else "   "
            label = f"{prefix}{icon} {category} ({count})"

            if is_selected:
                lines.append(("fg:ansibrightcyan bold", label))
            else:
                lines.append(("fg:ansibrightblack", label))
            lines.append(("", "\n"))

        lines.append(("", "\n"))
        if total_pages > 1:
            lines.append(
                ("fg:ansibrightblack", f" Page {self.current_page + 1}/{total_pages}")
            )
            lines.append(("", "\n"))

        self._render_navigation_hints(lines)
        return lines

    def _render_skill_list(self) -> List:
        lines: List = []

        if not self.current_category:
            lines.append(("fg:yellow", "  No category selected."))
            lines.append(("", "\n\n"))
            self._render_navigation_hints(lines)
            return lines

        icon = self._get_category_icon(self.current_category)
        lines.append(("bold cyan", f" {icon} {self.current_category.upper()}"))
        lines.append(("", "\n\n"))

        if not self.current_skills:
            lines.append(("fg:yellow", "  No skills in this category."))
            lines.append(("", "\n\n"))
            self._render_navigation_hints(lines)
            return lines

        total_pages = (len(self.current_skills) + PAGE_SIZE - 1) // PAGE_SIZE
        start_idx = self.current_page * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, len(self.current_skills))

        for i in range(start_idx, end_idx):
            entry = self.current_skills[i]
            is_selected = i == self.selected_skill_idx
            installed = is_skill_installed(entry.id)

            prefix = " > " if is_selected else "   "
            badge = "✓" if installed else " "

            label = f"{prefix}{badge} {entry.id}"

            if is_selected:
                if installed:
                    lines.append(("fg:ansigreen bold", label))
                else:
                    lines.append(("fg:ansibrightcyan bold", label))
            else:
                if installed:
                    lines.append(("fg:ansigreen", label))
                else:
                    lines.append(("fg:ansibrightblack", label))

            lines.append(("", "\n"))

        lines.append(("", "\n"))
        if total_pages > 1:
            lines.append(
                ("fg:ansibrightblack", f" Page {self.current_page + 1}/{total_pages}")
            )
            lines.append(("", "\n"))

        self._render_navigation_hints(lines)
        return lines

    def _render_category_details(self, category: str) -> List:
        lines: List = []

        icon = self._get_category_icon(category)
        entries = self.catalog.get_by_category(category) if self.catalog else []

        lines.append(("bold", f"  {icon} {category}"))
        lines.append(("", "\n\n"))

        lines.append(("fg:ansibrightblack", f"  {len(entries)} skills available"))
        lines.append(("", "\n\n"))

        lines.append(("bold", "  Skills:"))
        lines.append(("", "\n"))

        for entry in entries[:12]:
            lines.append(("fg:ansibrightblack", f"    • {entry.id}"))
            lines.append(("", "\n"))

        if len(entries) > 12:
            lines.append(
                ("fg:ansibrightblack", f"    ... and {len(entries) - 12} more")
            )
            lines.append(("", "\n"))

        return lines

    def _render_skill_details(self, entry: SkillCatalogEntry) -> List:
        lines: List = []

        installed = is_skill_installed(entry.id)
        status = "✅ Installed" if installed else "📦 Available"
        status_style = "fg:ansigreen bold" if installed else "fg:ansiyellow bold"

        # Name
        lines.append(("bold", f"  {entry.display_name}"))
        lines.append(("fg:ansibrightblack", f"  ({entry.id})"))
        lines.append(("", "\n\n"))

        # Status
        lines.append((status_style, f"  {status}"))
        lines.append(("", "\n\n"))

        # Description
        lines.append(("bold", "  Description:"))
        lines.append(("", "\n"))
        desc = entry.description or "No description available"
        for line in self._wrap_text(desc, 50):
            lines.append(("fg:ansibrightblack", f"    {line}"))
            lines.append(("", "\n"))
        lines.append(("", "\n"))

        # Tags
        if entry.tags:
            lines.append(("bold", "  Tags:"))
            lines.append(("", "\n"))
            lines.append(("fg:ansicyan", f"    {', '.join(entry.tags)}"))
            lines.append(("", "\n\n"))

        # Resources
        lines.append(("bold", "  Resources:"))
        lines.append(("", "\n"))
        lines.append(
            (
                "fg:ansibrightblack",
                f"    📜 scripts: {'yes' if entry.has_scripts else 'no'}",
            )
        )
        lines.append(("", "\n"))
        lines.append(
            (
                "fg:ansibrightblack",
                f"    📚 references: {'yes' if entry.has_references else 'no'}",
            )
        )
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", f"    📄 file count: {entry.file_count}"))
        lines.append(("", "\n\n"))

        # Source
        lines.append(("bold", "  Source:"))
        lines.append(("", "\n"))
        lines.append(
            ("fg:ansibrightblack", f"    {self._truncate_path(entry.source_path)}")
        )
        lines.append(("", "\n"))

        return lines

    def _render_details(self) -> List:
        lines: List = []

        lines.append(("bold cyan", " 📋 DETAILS"))
        lines.append(("", "\n\n"))

        if self.view_mode == "categories":
            category = self._get_current_category()
            if not category:
                lines.append(("fg:yellow", "  No category selected."))
                return lines

            lines.extend(self._render_category_details(category))
            return lines

        entry = self._get_current_skill()
        if entry is None:
            lines.append(("fg:yellow", "  No skill selected."))
            return lines

        lines.extend(self._render_skill_details(entry))
        return lines

    # -------------------------
    # State transitions
    # -------------------------

    def update_display(self) -> None:
        if self.view_mode == "categories":
            self.menu_control.text = self._render_category_list()
        else:
            self.menu_control.text = self._render_skill_list()

        self.preview_control.text = self._render_details()

    def _enter_category(self) -> None:
        category = self._get_current_category()
        if not category or self.catalog is None:
            return

        self.current_category = category
        self.current_skills = self.catalog.get_by_category(category)
        self.view_mode = "skills"
        self.selected_skill_idx = 0
        self.current_page = 0
        self.update_display()

    def _go_back_to_categories(self) -> None:
        self.view_mode = "categories"
        self.current_category = None
        self.current_skills = []
        self.selected_skill_idx = 0
        self.current_page = 0
        self.update_display()

    def _select_current_skill(self) -> None:
        entry = self._get_current_skill()
        if entry is None:
            return

        self.pending_skill = entry
        self.result = "pending_install"

    # -------------------------
    # Run
    # -------------------------

    def run(self) -> bool:
        """Run the interactive skills install browser (synchronous).

        Returns:
            True if a skill was installed, False otherwise.
        """

        if not self.categories:
            emit_warning("No bundled skills catalog available.")
            return False

        self.result = None
        self.pending_skill = None

        # Build UI
        self.menu_control = FormattedTextControl(text="")
        self.preview_control = FormattedTextControl(text="")

        menu_window = Window(
            content=self.menu_control, wrap_lines=True, width=Dimension(weight=35)
        )
        preview_window = Window(
            content=self.preview_control, wrap_lines=True, width=Dimension(weight=65)
        )

        menu_frame = Frame(menu_window, width=Dimension(weight=35), title="Browse")
        preview_frame = Frame(
            preview_window, width=Dimension(weight=65), title="Details"
        )

        root_container = VSplit([menu_frame, preview_frame])

        # Key bindings (match MCP install menu)
        kb = KeyBindings()

        @kb.add("up")
        def _(event):
            if self.view_mode == "categories":
                if self.selected_category_idx > 0:
                    self.selected_category_idx -= 1
                    self.current_page = self.selected_category_idx // PAGE_SIZE
            else:
                if self.selected_skill_idx > 0:
                    self.selected_skill_idx -= 1
                    self.current_page = self.selected_skill_idx // PAGE_SIZE
            self.update_display()

        @kb.add("down")
        def _(event):
            if self.view_mode == "categories":
                if self.selected_category_idx < len(self.categories) - 1:
                    self.selected_category_idx += 1
                    self.current_page = self.selected_category_idx // PAGE_SIZE
            else:
                if self.selected_skill_idx < len(self.current_skills) - 1:
                    self.selected_skill_idx += 1
                    self.current_page = self.selected_skill_idx // PAGE_SIZE
            self.update_display()

        @kb.add("left")
        def _(event):
            """Previous page."""
            if self.current_page > 0:
                self.current_page -= 1
                if self.view_mode == "categories":
                    self.selected_category_idx = self.current_page * PAGE_SIZE
                else:
                    self.selected_skill_idx = self.current_page * PAGE_SIZE
                self.update_display()

        @kb.add("right")
        def _(event):
            """Next page."""
            total_items = (
                len(self.categories)
                if self.view_mode == "categories"
                else len(self.current_skills)
            )
            total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE
            if self.current_page < total_pages - 1:
                self.current_page += 1
                if self.view_mode == "categories":
                    self.selected_category_idx = self.current_page * PAGE_SIZE
                else:
                    self.selected_skill_idx = self.current_page * PAGE_SIZE
                self.update_display()

        @kb.add("enter")
        def _(event):
            if self.view_mode == "categories":
                self._enter_category()
            else:
                self._select_current_skill()
                event.app.exit()

        @kb.add("escape")
        def _(event):
            if self.view_mode == "skills":
                self._go_back_to_categories()

        @kb.add("backspace")
        def _(event):
            if self.view_mode == "skills":
                self._go_back_to_categories()

        @kb.add("c-c")
        def _(event):
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
            self.update_display()

            # Clear the current buffer
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

            app.run(in_thread=True)

        finally:
            # Exit alternate screen buffer
            sys.stdout.write("\033[?1049l")
            sys.stdout.flush()

            # Flush any buffered input (prevents stale keypresses after TUI)
            try:
                import termios

                termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
            except (ImportError, termios.error, OSError):
                pass

            time.sleep(0.1)
            set_awaiting_user_input(False)

        # If user just bailed, don't spam.
        if self.result != "pending_install":
            emit_info("✓ Exited skills installer")

        if self.result == "pending_install" and self.pending_skill is not None:
            return self._install_flow(self.pending_skill)

        return False

    # -------------------------
    # Install flow (post-TUI)
    # -------------------------

    def _install_flow(self, entry: SkillCatalogEntry) -> bool:
        from code_puppy.command_line.utils import safe_input

        already_installed = is_skill_installed(entry.id)

        print("\n" + "=" * 60)
        print("INSTALL SKILL")
        print("=" * 60)
        print(f"\nSkill: {entry.display_name} ({entry.id})")

        if already_installed:
            print("Status: already installed")
            confirm = (
                safe_input("Reinstall and overwrite existing files? (y/N): ")
                .strip()
                .lower()
            )
            if confirm not in ("y", "yes"):
                emit_info("Cancelled.")
                return False
            force = True
        else:
            confirm = safe_input("Install this skill? (y/N): ").strip().lower()
            if confirm not in ("y", "yes"):
                emit_info("Cancelled.")
                return False
            force = False

        result = install_skill(entry, force=force)
        if result.success:
            if result.was_update:
                emit_success(
                    f"✓ Reinstalled skill '{entry.id}' at {result.install_path}"
                )
            else:
                emit_success(f"✓ Installed skill '{entry.id}' at {result.install_path}")
            return True

        emit_error(result.error or f"Failed to install skill '{entry.id}'")
        return False


def run_skills_install_menu() -> bool:
    """Run the bundled skills install menu.

    Returns:
        True if a skill was installed, False otherwise.
    """

    menu = SkillsInstallMenu()
    return menu.run()
