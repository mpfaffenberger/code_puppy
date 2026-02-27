"""Interactive terminal UI for browsing and installing remote agent skills.

Launched from `/skills install` (wiring may live elsewhere). Provides a
split-panel prompt_toolkit UI:
- Left: categories, then skills within a category
- Right: live details preview for the current selection

Installation happens after the TUI exits, with a confirmation prompt via
`safe_input()`, and uses `download_and_install_skill()` to fetch and extract
remote ZIPs.

This module is intentionally defensive: if the remote catalog isn't available,
it shows an empty menu and returns False.
"""

import logging
import sys
import time
from pathlib import Path
from typing import List, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.command_line.utils import safe_input
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.plugins.agent_skills.downloader import download_and_install_skill
from code_puppy.plugins.agent_skills.installer import InstallResult
from code_puppy.plugins.agent_skills.skill_catalog import SkillCatalogEntry, catalog
from code_puppy.tools.command_runner import set_awaiting_user_input

logger = logging.getLogger(__name__)

PAGE_SIZE = 12


def is_skill_installed(skill_id: str) -> bool:
    """Return True if the skill is already installed locally."""

    return (Path.home() / ".code_puppy" / "skills" / skill_id / "SKILL.md").is_file()


def _format_bytes(num_bytes: int) -> str:
    """Format bytes into a human-readable string."""

    try:
        size = float(max(0, int(num_bytes)))
    except Exception:
        return "0 B"

    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024.0 or unit == "GB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} GB"


def _wrap_text(text: str, width: int) -> List[str]:
    """Simple word-wrap for display in the details panel."""

    if not text:
        return []

    words = text.split()
    lines: list[str] = []
    current = ""

    for word in words:
        if not current:
            current = word
            continue

        if len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}"

    if current:
        lines.append(current)

    return lines


def _category_key(category: str) -> str:
    """Normalize a category string for icon lookup."""

    return "".join(ch for ch in (category or "").casefold() if ch.isalnum())


class SkillsInstallMenu:
    """Interactive TUI for browsing and installing remote skills."""

    def __init__(self):
        """Initialize the skills install menu with catalog data."""

        self.catalog = catalog
        self.categories: List[str] = []
        self.current_category: Optional[str] = None
        self.current_skills: List[SkillCatalogEntry] = []

        # State
        self.view_mode = "categories"  # categories | skills
        self.selected_category_idx = 0
        self.selected_skill_idx = 0
        self.current_page = 0
        self.result: Optional[str] = None
        self.pending_entry: Optional[SkillCatalogEntry] = None

        # UI controls
        self.menu_control: Optional[FormattedTextControl] = None
        self.preview_control: Optional[FormattedTextControl] = None

        self._initialize_catalog()

    def _initialize_catalog(self) -> None:
        """Load categories from the remote-backed catalog."""

        try:
            self.categories = self.catalog.list_categories() if self.catalog else []
        except Exception as e:
            emit_error(f"Skill catalog not available: {e}")
            self.categories = []

    def _get_category_icon(self, category: str) -> str:
        """Return an emoji icon for a skill category name."""

        icons = {
            "data": "📊",
            "finance": "💰",
            "legal": "⚖️",
            "office": "📄",
            "productmanagement": "📦",
            "sales": "💼",
            "biology": "🧬",
        }
        return icons.get(_category_key(category), "📁")

    def _get_current_category(self) -> Optional[str]:
        """Get the currently highlighted category name."""

        if 0 <= self.selected_category_idx < len(self.categories):
            return self.categories[self.selected_category_idx]
        return None

    def _get_current_skill(self) -> Optional[SkillCatalogEntry]:
        """Get the currently highlighted skill entry."""

        if self.view_mode == "skills" and self.current_skills:
            if 0 <= self.selected_skill_idx < len(self.current_skills):
                return self.current_skills[self.selected_skill_idx]
        return None

    def _render_navigation_hints(self, lines: List) -> None:
        """Render keyboard shortcut hints at the bottom."""

        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  ↑/↓ "))
        lines.append(("", "Navigate  "))
        lines.append(("fg:ansibrightblack", "←/→ "))
        lines.append(("", "Page\n"))

        if self.view_mode == "categories":
            lines.append(("fg:ansigreen", "  Enter  "))
            lines.append(("", "Browse Skills\n"))
        else:
            lines.append(("fg:ansigreen", "  Enter  "))
            lines.append(("", "Install Skill\n"))
            lines.append(("fg:ansibrightblack", "  Esc/Back  "))
            lines.append(("", "Back\n"))

        lines.append(("fg:ansired", "  Ctrl+C "))
        lines.append(("", "Cancel"))

    def _render_category_list(self) -> List:
        """Render the left panel with category navigation."""

        lines = []

        lines.append(("bold cyan", " 📂 CATEGORIES"))
        lines.append(("", "\n\n"))

        if not self.categories:
            lines.append(("fg:ansiyellow", "  No remote categories available."))
            lines.append(("", "\n"))
            lines.append(
                (
                    "fg:ansibrightblack",
                    "  (Remote catalog unavailable or empty)\n",
                )
            )
            self._render_navigation_hints(lines)
            return lines

        total_pages = (len(self.categories) + PAGE_SIZE - 1) // PAGE_SIZE
        start_idx = self.current_page * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, len(self.categories))

        for i in range(start_idx, end_idx):
            category = self.categories[i]
            is_selected = i == self.selected_category_idx
            icon = self._get_category_icon(category)
            count = 0
            try:
                count = (
                    len(self.catalog.get_by_category(category)) if self.catalog else 0
                )
            except Exception:
                count = 0

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
        """Render the middle panel with skills in the selected category."""

        lines = []

        if not self.current_category:
            lines.append(("fg:ansiyellow", "  No category selected."))
            lines.append(("", "\n\n"))
            self._render_navigation_hints(lines)
            return lines

        icon = self._get_category_icon(self.current_category)
        lines.append(("bold cyan", f" {icon} {self.current_category.upper()}"))
        lines.append(("", "\n\n"))

        if not self.current_skills:
            lines.append(("fg:ansiyellow", "  No skills in this category."))
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
            status_icon = "✓" if installed else "○"
            status_style = "fg:ansigreen" if installed else "fg:ansibrightblack"

            prefix = " > " if is_selected else "   "
            label = f"{prefix}{status_icon} {entry.display_name}"

            if is_selected:
                lines.append(("fg:ansibrightcyan bold", label))
            else:
                lines.append((status_style, label))

            lines.append(("", "\n"))

        lines.append(("", "\n"))
        if total_pages > 1:
            lines.append(
                ("fg:ansibrightblack", f" Page {self.current_page + 1}/{total_pages}")
            )
            lines.append(("", "\n"))

        self._render_navigation_hints(lines)
        return lines

    def _render_details(self) -> List:
        """Render the right panel with details for the selected skill."""

        lines = []

        lines.append(("bold cyan", " 📋 DETAILS"))
        lines.append(("", "\n\n"))

        if self.view_mode == "categories":
            category = self._get_current_category()
            if not category:
                lines.append(("fg:ansiyellow", "  No category selected."))
                return lines

            icon = self._get_category_icon(category)
            lines.append(("bold", f"  {icon} {category}"))
            lines.append(("", "\n\n"))

            skills = []
            try:
                skills = self.catalog.get_by_category(category) if self.catalog else []
            except Exception:
                skills = []

            lines.append(("fg:ansibrightblack", f"  {len(skills)} skills available"))
            lines.append(("", "\n\n"))

            # Show a preview of the first few skills
            if skills:
                lines.append(("bold", "  Preview:"))
                lines.append(("", "\n"))
                for entry in skills[:6]:
                    lines.append(("fg:ansibrightblack", f"    • {entry.display_name}"))
                    lines.append(("", "\n"))

            return lines

        entry = self._get_current_skill()
        if not entry:
            lines.append(("fg:ansiyellow", "  No skill selected."))
            return lines

        installed = is_skill_installed(entry.id)
        installed_text = "Installed" if installed else "Not installed"
        installed_style = "fg:ansigreen" if installed else "fg:ansiyellow"

        lines.append(("bold", f"  {entry.display_name}"))
        lines.append(("", "\n"))
        lines.append((installed_style, f"  {installed_text}"))
        lines.append(("", "\n\n"))

        lines.append(("bold", "  ID:"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", f"    {entry.id}"))
        lines.append(("", "\n\n"))

        lines.append(("bold", "  Description:"))
        lines.append(("", "\n"))
        desc = entry.description or "No description available"
        for line in _wrap_text(desc, 56):
            lines.append(("fg:ansibrightblack", f"    {line}"))
            lines.append(("", "\n"))
        lines.append(("", "\n"))

        lines.append(("bold", "  Category:"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", f"    {entry.category}"))
        lines.append(("", "\n\n"))

        lines.append(("bold", "  Tags:"))
        lines.append(("", "\n"))
        tags = entry.tags or []
        lines.append(("fg:ansicyan", f"    {', '.join(tags) if tags else '(none)'}"))
        lines.append(("", "\n\n"))

        lines.append(("bold", "  Contents:"))
        lines.append(("", "\n"))
        lines.append(
            (
                "fg:ansibrightblack",
                f"    scripts: {'yes' if entry.has_scripts else 'no'}",
            )
        )
        lines.append(("", "\n"))
        lines.append(
            (
                "fg:ansibrightblack",
                f"    references: {'yes' if entry.has_references else 'no'}",
            )
        )
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", f"    files: {entry.file_count}"))
        lines.append(("", "\n\n"))

        lines.append(("bold", "  Download:"))
        lines.append(("", "\n"))
        lines.append(
            (
                "fg:ansibrightblack",
                f"    size: {_format_bytes(entry.zip_size_bytes)}",
            )
        )
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", f"    url: {entry.download_url}"))
        lines.append(("", "\n"))

        return lines

    def update_display(self) -> None:
        """Refresh all three panels of the TUI display."""

        if self.view_mode == "categories":
            self.menu_control.text = self._render_category_list()
        else:
            self.menu_control.text = self._render_skill_list()

        self.preview_control.text = self._render_details()

    def _enter_category(self) -> None:
        """Enter the currently highlighted category to browse skills."""

        category = self._get_current_category()
        if not category or not self.catalog:
            return

        self.current_category = category
        try:
            self.current_skills = self.catalog.get_by_category(category)
        except Exception:
            self.current_skills = []

        self.view_mode = "skills"
        self.selected_skill_idx = 0
        self.current_page = 0
        self.update_display()

    def _go_back_to_categories(self) -> None:
        """Navigate back from skill list to category list."""

        self.view_mode = "categories"
        self.current_category = None
        self.current_skills = []
        self.selected_skill_idx = 0
        self.current_page = 0
        self.update_display()

    def _select_current_skill(self) -> None:
        """Download and install the currently highlighted skill."""

        entry = self._get_current_skill()
        if entry:
            self.pending_entry = entry
            self.result = "pending_install"

    def run(self) -> bool:
        """Run the skills install menu.

        Returns:
            True if a skill was installed, False otherwise.
        """

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

        kb = KeyBindings()

        @kb.add("up")
        def _(event):
            """Move cursor up."""

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
            """Move cursor down."""

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
            """Navigate to previous page."""

            if self.current_page > 0:
                self.current_page -= 1
                if self.view_mode == "categories":
                    self.selected_category_idx = self.current_page * PAGE_SIZE
                else:
                    self.selected_skill_idx = self.current_page * PAGE_SIZE
                self.update_display()

        @kb.add("right")
        def _(event):
            """Navigate to next page."""

            if self.view_mode == "categories":
                total_items = len(self.categories)
            else:
                total_items = len(self.current_skills)

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
            """Select/enter the current item."""

            if self.view_mode == "categories":
                self._enter_category()
            else:
                self._select_current_skill()
                event.app.exit()

        @kb.add("escape")
        def _(event):
            """Go back."""

            if self.view_mode == "skills":
                self._go_back_to_categories()

        @kb.add("backspace")
        def _(event):
            """Go back."""

            if self.view_mode == "skills":
                self._go_back_to_categories()

        @kb.add("c-c")
        def _(event):
            """Quit the menu."""

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
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

            app.run(in_thread=True)

        finally:
            sys.stdout.write("\033[?1049l")
            sys.stdout.flush()

            # Flush any buffered input to prevent stale keypresses
            try:
                import termios

                termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
            except Exception:
                pass  # ImportError on Windows, termios.error, or not a tty

            # Small delay to let terminal settle before any output
            time.sleep(0.1)
            set_awaiting_user_input(False)

        # Handle install after TUI exits
        if self.result == "pending_install" and self.pending_entry:
            return _prompt_and_install(self.pending_entry)

        emit_info("✓ Exited skills install browser")
        return False


def _prompt_and_install(entry: SkillCatalogEntry) -> bool:
    """Prompt for confirmation and install the given skill."""

    installed = is_skill_installed(entry.id)
    size_str = _format_bytes(entry.zip_size_bytes)

    try:
        if installed:
            answer = safe_input(
                f"Skill '{entry.display_name}' is already installed. Reinstall ({size_str})? [y/N] "
            )
            if answer.strip().lower() not in {"y", "yes"}:
                emit_info("Installation cancelled")
                return False
            force = True
        else:
            answer = safe_input(
                f"Install skill '{entry.display_name}' ({size_str})? [y/N] "
            )
            if answer.strip().lower() not in {"y", "yes"}:
                emit_info("Installation cancelled")
                return False
            force = False

    except (KeyboardInterrupt, EOFError):
        emit_warning("Installation cancelled")
        return False

    emit_info(f"Downloading: {entry.display_name} ({size_str})")

    result: InstallResult
    try:
        result = download_and_install_skill(
            skill_name=entry.id,
            download_url=entry.download_url,
            force=force,
        )
    except Exception as e:
        logger.exception(f"Unexpected error during skill install: {e}")
        emit_error(f"Installation error: {e}")
        return False

    if result.success:
        emit_success(result.message)
        if result.installed_path:
            emit_info(f"Installed to: {result.installed_path}")
        return True

    emit_error(result.message)
    return False


def run_skills_install_menu() -> bool:
    """Run the bundled skills install menu.

    Returns:
        True if a skill was installed, False otherwise.
    """

    menu = SkillsInstallMenu()
    return menu.run()
