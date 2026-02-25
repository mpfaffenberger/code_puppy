"""Interactive TUI for browsing and installing E2E Open Skills.

Launch with /skill-market to browse the catalog in a split-panel interface.
Built with prompt_toolkit, matching the /skills TUI style.
"""

import sys
import time
from pathlib import Path
from typing import List, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.tools.command_runner import set_awaiting_user_input

from . import api_client

PAGE_SIZE = 12


class SkillMarketplaceMenu:
    """Split-panel TUI for browsing and downloading marketplace skills."""

    def __init__(self):
        self.skills: List[dict] = []
        self.filtered_skills: List[dict] = []
        self.search_query: str = ""
        self.selected_idx: int = 0
        self.current_page: int = 0
        self.result: Optional[str] = None
        self.status_message: str = ""
        self.status_style: str = ""
        self.loading: bool = True

        # UI controls
        self.menu_control: Optional[FormattedTextControl] = None
        self.preview_control: Optional[FormattedTextControl] = None

    def _load_skills(self) -> None:
        """Fetch skills from the marketplace API."""
        self.loading = True
        try:
            resp = api_client.run_async(api_client.fetch_skills())
            if resp.get("success"):
                self.skills = resp.get("data", [])
                self.filtered_skills = list(self.skills)
                self.status_message = f"Loaded {len(self.skills)} skills"
                self.status_style = "fg:ansigreen"
            else:
                self.skills = []
                self.filtered_skills = []
                self.status_message = f"Error: {resp.get('error', 'unknown')}"
                self.status_style = "fg:ansired"
        except Exception as e:
            self.skills = []
            self.filtered_skills = []
            self.status_message = f"Failed: {e}"
            self.status_style = "fg:ansired"
        finally:
            self.loading = False

    def _apply_filter(self) -> None:
        """Filter skills by the current search query."""
        if not self.search_query:
            self.filtered_skills = list(self.skills)
        else:
            q = self.search_query.lower()
            self.filtered_skills = [
                s
                for s in self.skills
                if q in s.get("name", "").lower()
                or q in s.get("description", "").lower()
                or q in s.get("tags", "").lower()
            ]
        self.selected_idx = 0
        self.current_page = 0

    def _get_current_skill(self) -> Optional[dict]:
        if 0 <= self.selected_idx < len(self.filtered_skills):
            return self.filtered_skills[self.selected_idx]
        return None

    # ── Left Panel ─────────────────────────────────────────────

    def _render_skill_list(self) -> List:
        lines: List = []

        # Header
        lines.append(("bold fg:ansicyan", " 🐶 E2E Open Skills Marketplace"))
        lines.append(("", "\n"))
        lines.append((self.status_style, f"  {self.status_message}"))
        lines.append(("", "\n\n"))

        # Search bar
        if self.search_query:
            lines.append(("fg:ansiyellow", f'  🔍 "{self.search_query}"'))
            lines.append(("", "\n\n"))

        if self.loading:
            lines.append(("fg:ansiyellow", "  Loading skills..."))
            return lines

        if not self.filtered_skills:
            lines.append(("fg:ansiyellow", "  No skills found."))
            lines.append(("", "\n"))
            if self.search_query:
                lines.append(("fg:ansibrightblack", "  Press Esc to clear search."))
            return lines

        # Pagination
        total_pages = max(1, (len(self.filtered_skills) + PAGE_SIZE - 1) // PAGE_SIZE)
        start = self.current_page * PAGE_SIZE
        end = min(start + PAGE_SIZE, len(self.filtered_skills))

        for i in range(start, end):
            skill = self.filtered_skills[i]
            is_selected = i == self.selected_idx
            installed = api_client.is_skill_installed(skill["name"])

            icon = "✓" if installed else "○"
            icon_style = "fg:ansigreen" if installed else "fg:ansibrightblack"

            prefix = " ▸ " if is_selected else "   "
            name = skill.get("name", "?")

            if is_selected:
                lines.append(("bold", prefix))
                lines.append((icon_style + " bold", icon))
                lines.append(("bold", f" {name}"))
            else:
                lines.append(("", prefix))
                lines.append((icon_style, icon))
                lines.append(("fg:ansibrightblack", f" {name}"))

            lines.append(("", "\n"))

        # Page info
        lines.append(("", "\n"))
        lines.append(
            (
                "fg:ansibrightblack",
                f" Page {self.current_page + 1}/{total_pages}"
                f"  ({len(self.filtered_skills)} skills)",
            )
        )
        lines.append(("", "\n"))

        self._render_nav_hints(lines)
        return lines

    def _render_nav_hints(self, lines: List) -> None:
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  ↑/↓ j/k  "))
        lines.append(("", "Navigate  "))
        lines.append(("fg:ansibrightblack", "←/→  "))
        lines.append(("", "Page\n"))
        lines.append(("fg:ansigreen", "  Enter  "))
        lines.append(("", "Install  "))
        lines.append(("fg:ansicyan", "  /  "))
        lines.append(("", "Search\n"))
        lines.append(("fg:ansiyellow", "  r  "))
        lines.append(("", "Refresh  "))
        lines.append(("fg:ansired", "  q  "))
        lines.append(("", "Exit"))

    # ── Right Panel ────────────────────────────────────────────

    def _render_skill_details(self) -> List:
        lines: List = []
        lines.append(("dim cyan", " SKILL DETAILS"))
        lines.append(("", "\n\n"))

        skill = self._get_current_skill()
        if not skill:
            lines.append(("fg:ansiyellow", "  Select a skill to view details."))
            return lines

        name = skill.get("name", "?")
        desc = skill.get("description", "No description")
        tags = skill.get("tags", "")
        installed = api_client.is_skill_installed(name)

        # Name
        lines.append(("bold", f"  {name}"))
        lines.append(("", "\n\n"))

        # Status
        if installed:
            lines.append(("fg:ansigreen bold", "  ✓ Installed"))
        else:
            lines.append(("fg:ansiyellow", "  ○ Not installed"))
        lines.append(("", "\n\n"))

        # Description
        lines.append(("bold", "  Description:"))
        lines.append(("", "\n"))
        for line in self._wrap_text(desc, 48):
            lines.append(("fg:ansibrightblack", f"    {line}"))
            lines.append(("", "\n"))
        lines.append(("", "\n"))

        # Tags
        if tags:
            lines.append(("bold", "  Tags:"))
            lines.append(("", "\n"))
            lines.append(("fg:ansicyan", f"    {tags}"))
            lines.append(("", "\n\n"))

        # Install path
        dest = api_client.SKILLS_DIR / name / "SKILL.md"
        path_str = str(dest)
        home = str(Path.home())
        if path_str.startswith(home):
            path_str = "~" + path_str[len(home) :]
        lines.append(("bold", "  Install path:"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", f"    {path_str}"))
        lines.append(("", "\n\n"))

        # URL
        url = skill.get("url", "")
        if url:
            lines.append(("bold", "  URL:"))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", f"    {url}"))
            lines.append(("", "\n"))

        return lines

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _wrap_text(text: str, width: int) -> List[str]:
        words = text.split()
        lines: List[str] = []
        current: List[str] = []
        length = 0
        for word in words:
            if length + len(word) + 1 <= width:
                current.append(word)
                length += len(word) + 1
            else:
                if current:
                    lines.append(" ".join(current))
                current = [word]
                length = len(word)
        if current:
            lines.append(" ".join(current))
        return lines or [""]

    def _install_current_skill(self) -> None:
        """Download and install the currently selected skill."""
        skill = self._get_current_skill()
        if not skill:
            return

        name = skill["name"]
        self.status_message = f"Installing {name}..."
        self.status_style = "fg:ansicyan"
        self.update_display()

        try:
            resp = api_client.run_async(api_client.fetch_skill_md(name))
            if resp.get("success"):
                content = resp["data"]
                api_client.install_skill(name, content)
                self.status_message = f"✓ Installed {name}"
                self.status_style = "fg:ansigreen"
            else:
                self.status_message = f"Failed: {resp.get('error', '?')}"
                self.status_style = "fg:ansired"
        except Exception as e:
            self.status_message = f"Error: {e}"
            self.status_style = "fg:ansired"

        self.update_display()

    def update_display(self) -> None:
        if self.menu_control:
            self.menu_control.text = self._render_skill_list()
        if self.preview_control:
            self.preview_control.text = self._render_skill_details()

    # ── Run ────────────────────────────────────────────────────

    def run(self) -> Optional[str]:
        """Run the interactive marketplace browser."""
        self._load_skills()

        self.menu_control = FormattedTextControl(text="")
        self.preview_control = FormattedTextControl(text="")

        menu_window = Window(
            content=self.menu_control, wrap_lines=True, width=Dimension(weight=38)
        )
        preview_window = Window(
            content=self.preview_control, wrap_lines=True, width=Dimension(weight=62)
        )

        menu_frame = Frame(menu_window, width=Dimension(weight=38), title="Marketplace")
        preview_frame = Frame(
            preview_window, width=Dimension(weight=62), title="Details"
        )

        root = VSplit([menu_frame, preview_frame])
        kb = self._build_keybindings()

        layout = Layout(root)
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
            try:
                import termios

                termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
            except (ImportError, OSError):
                pass
            time.sleep(0.1)
            set_awaiting_user_input(False)

        return self.result

    def _build_keybindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("up")
        @kb.add("k")
        def _move_up(event):
            if self.selected_idx > 0:
                self.selected_idx -= 1
                self.current_page = self.selected_idx // PAGE_SIZE
            self.update_display()

        @kb.add("down")
        @kb.add("j")
        def _move_down(event):
            if self.selected_idx < len(self.filtered_skills) - 1:
                self.selected_idx += 1
                self.current_page = self.selected_idx // PAGE_SIZE
            self.update_display()

        @kb.add("left")
        def _page_prev(event):
            if self.current_page > 0:
                self.current_page -= 1
                self.selected_idx = self.current_page * PAGE_SIZE
                self.update_display()

        @kb.add("right")
        def _page_next(event):
            total_pages = max(
                1, (len(self.filtered_skills) + PAGE_SIZE - 1) // PAGE_SIZE
            )
            if self.current_page < total_pages - 1:
                self.current_page += 1
                self.selected_idx = self.current_page * PAGE_SIZE
                self.update_display()

        @kb.add("enter")
        def _install(event):
            self._install_current_skill()

        @kb.add("r")
        def _refresh(event):
            self.status_message = "Refreshing..."
            self.status_style = "fg:ansicyan"
            self.update_display()
            self._load_skills()
            self._apply_filter()
            self.update_display()

        @kb.add("/")
        def _search(event):
            self.result = "search"
            event.app.exit()

        @kb.add("escape")
        def _clear_or_quit(event):
            if self.search_query:
                self.search_query = ""
                self._apply_filter()
                self.update_display()
            else:
                self.result = "quit"
                event.app.exit()

        @kb.add("q")
        def _quit(event):
            self.result = "quit"
            event.app.exit()

        @kb.add("c-c")
        def _force_quit(event):
            self.result = "quit"
            event.app.exit()

        return kb


def _prompt_search_query() -> Optional[str]:
    """Prompt for a search string outside the TUI."""
    from code_puppy.command_line.utils import safe_input

    try:
        print("\n" + "─" * 50)
        print("🔍  Search E2E Open Skills")
        print("─" * 50)
        query = safe_input("  Search: ").strip()
        return query if query else None
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return None


def show_skill_marketplace() -> bool:
    """Launch the interactive skill marketplace TUI.

    Returns True if any skills were installed.
    """
    installed_any = False
    search_query = ""

    while True:
        menu = SkillMarketplaceMenu()
        menu.search_query = search_query
        if search_query:
            menu._apply_filter()

        result = menu.run()

        if result == "search":
            query = _prompt_search_query()
            search_query = query or ""
            continue

        if "✓" in menu.status_message:
            installed_any = True

        break

    return installed_any
