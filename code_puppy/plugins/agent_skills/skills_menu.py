"""Interactive TUI for managing agent skills.

Launch with /skills to browse, enable, disable, and configure skills.
Built with prompt_toolkit for proper interactive split-panel interface.
"""

import os
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
from code_puppy.plugins.agent_skills.config import (
    add_skill_directory,
    get_disabled_skills,
    get_skill_directories,
    get_skills_enabled,
    remove_skill_directory,
    set_skill_disabled,
    set_skills_enabled,
)
from code_puppy.plugins.agent_skills.discovery import (
    SkillInfo,
    discover_skills,
    refresh_skill_cache,
)
from code_puppy.plugins.agent_skills.metadata import (
    SkillMetadata,
    get_skill_resources,
    parse_skill_metadata,
)
from code_puppy.tools.command_runner import set_awaiting_user_input

PAGE_SIZE = 15  # Items per page


class SkillsMenu:
    """Interactive TUI for managing agent skills."""

    def __init__(self):
        """Initialize the skills menu."""
        self.skills: List[SkillInfo] = []
        self.disabled_skills: List[str] = []
        self.skill_directories: List[Path] = []
        self.skills_enabled = False

        # State management
        self.selected_idx = 0
        self.current_page = 0
        self.result = None

        # UI controls (set during run)
        self.menu_control: Optional[FormattedTextControl] = None
        self.preview_control: Optional[FormattedTextControl] = None

        # Initialize data
        self._refresh_data()

    def _refresh_data(self) -> None:
        """Refresh skills data from disk."""
        try:
            self.skills = discover_skills()
            self.disabled_skills = get_disabled_skills()
            self.skill_directories = get_skill_directories()
            self.skills_enabled = get_skills_enabled()
        except Exception as e:
            emit_error(f"Failed to refresh skills data: {e}")

    def _get_current_skill(self) -> Optional[SkillInfo]:
        """Get the currently selected skill."""
        if 0 <= self.selected_idx < len(self.skills):
            return self.skills[self.selected_idx]
        return None

    def _get_skill_metadata(self, skill: SkillInfo) -> Optional[SkillMetadata]:
        """Get metadata for a skill."""
        try:
            return parse_skill_metadata(skill.path)
        except Exception:
            return None

    def _is_skill_disabled(self, skill: SkillInfo) -> bool:
        """Check if a skill is disabled."""
        metadata = self._get_skill_metadata(skill)
        if metadata:
            return metadata.name in self.disabled_skills
        return skill.name in self.disabled_skills

    def _toggle_current_skill(self) -> None:
        """Toggle the enabled/disabled state of the current skill."""
        skill = self._get_current_skill()
        if not skill:
            return

        metadata = self._get_skill_metadata(skill)
        skill_name = metadata.name if metadata else skill.name

        is_disabled = skill_name in self.disabled_skills
        set_skill_disabled(skill_name, not is_disabled)
        refresh_skill_cache()
        self._refresh_data()
        self.update_display()

    def _render_skill_list(self) -> List:
        """Render the skill list panel."""
        lines = []

        # Header with status
        status_color = "fg:ansigreen" if self.skills_enabled else "fg:ansired"
        status_text = "ENABLED" if self.skills_enabled else "DISABLED"
        lines.append((status_color, f" Skills: {status_text}"))
        lines.append(("", "\n\n"))

        if not self.skills:
            lines.append(("fg:ansiyellow", "  No skills found."))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", "  Create skills in:"))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", "    ~/.code_puppy/skills/"))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", "    ./skills/"))
            lines.append(("", "\n\n"))
            self._render_navigation_hints(lines)
            return lines

        # Calculate pagination
        total_pages = (len(self.skills) + PAGE_SIZE - 1) // PAGE_SIZE
        start_idx = self.current_page * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, len(self.skills))

        # Render skills
        for i in range(start_idx, end_idx):
            skill = self.skills[i]
            is_selected = i == self.selected_idx
            is_disabled = self._is_skill_disabled(skill)

            # Status icon
            status_icon = "✗" if is_disabled else "✓"
            status_style = "fg:ansired" if is_disabled else "fg:ansigreen"

            # Get skill name from metadata if available
            metadata = self._get_skill_metadata(skill)
            display_name = metadata.name if metadata else skill.name

            # Format line
            prefix = " > " if is_selected else "   "

            if is_selected:
                lines.append(("bold", prefix))
                lines.append((status_style + " bold", status_icon))
                lines.append(("bold", f" {display_name}"))
            else:
                lines.append(("", prefix))
                lines.append((status_style, status_icon))
                lines.append(("fg:ansibrightblack", f" {display_name}"))

            lines.append(("", "\n"))

        # Pagination info
        lines.append(("", "\n"))
        lines.append(
            ("fg:ansibrightblack", f" Page {self.current_page + 1}/{total_pages}")
        )
        lines.append(("", "\n"))

        self._render_navigation_hints(lines)
        return lines

    def _render_navigation_hints(self, lines: List) -> None:
        """Render navigation hints at the bottom."""
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  ↑/↓ or j/k "))
        lines.append(("", "Navigate  "))
        lines.append(("fg:ansibrightblack", "←/→ "))
        lines.append(("", "Page\n"))
        lines.append(("fg:ansigreen", "  Enter  "))
        lines.append(("", "Toggle  "))
        lines.append(("fg:ansicyan", "  t  "))
        lines.append(("", "Toggle System\n"))
        lines.append(("fg:ansimagenta", "  Ctrl+A  "))
        lines.append(("", "Add Dir  "))
        lines.append(("fg:ansiyellow", "  Ctrl+D  "))
        lines.append(("", "Show Dirs\n"))
        lines.append(("fg:ansimagenta", "  i  "))
        lines.append(("", "Install from catalog\n"))
        lines.append(("fg:ansiyellow", "  r  "))
        lines.append(("", "Refresh  "))
        lines.append(("fg:ansired", "  q  "))
        lines.append(("", "Exit"))

    def _render_skill_details(self) -> List:
        """Render the skill details panel."""
        lines = []

        lines.append(("dim cyan", " SKILL DETAILS"))
        lines.append(("", "\n\n"))

        skill = self._get_current_skill()
        if not skill:
            lines.append(("fg:ansiyellow", "  No skill selected."))
            lines.append(("", "\n\n"))
            lines.append(("fg:ansibrightblack", "  Select a skill from the list"))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", "  to view its details."))
            return lines

        metadata = self._get_skill_metadata(skill)
        is_disabled = self._is_skill_disabled(skill)

        # Status
        status_text = "Disabled" if is_disabled else "Enabled"
        status_style = "fg:ansired bold" if is_disabled else "fg:ansigreen bold"
        lines.append(("bold", "  Status: "))
        lines.append((status_style, status_text))
        lines.append(("", "\n\n"))

        if metadata:
            # Name
            lines.append(("bold", f"  {metadata.name}"))
            lines.append(("", "\n\n"))

            # Description
            if metadata.description:
                lines.append(("bold", "  Description:"))
                lines.append(("", "\n"))
                # Wrap description
                desc = metadata.description
                wrapped = self._wrap_text(desc, 50)
                for line in wrapped:
                    lines.append(("fg:ansibrightblack", f"    {line}"))
                    lines.append(("", "\n"))
                lines.append(("", "\n"))

            # Tags
            if metadata.tags:
                lines.append(("bold", "  Tags:"))
                lines.append(("", "\n"))
                tags_str = ", ".join(metadata.tags)
                lines.append(("fg:ansicyan", f"    {tags_str}"))
                lines.append(("", "\n\n"))

            # Resources
            resources = get_skill_resources(metadata.path)
            if resources:
                lines.append(("bold", "  Resources:"))
                lines.append(("", "\n"))
                for resource in resources[:5]:  # Show first 5
                    resource_name = getattr(resource, "name", str(resource))
                    lines.append(("fg:ansiyellow", f"    • {resource_name}"))
                    lines.append(("", "\n"))
                if len(resources) > 5:
                    lines.append(
                        ("fg:ansibrightblack", f"    ... and {len(resources) - 5} more")
                    )
                    lines.append(("", "\n"))
                lines.append(("", "\n"))

        else:
            # No metadata available
            lines.append(("bold", f"  {skill.name}"))
            lines.append(("", "\n\n"))
            lines.append(("fg:ansiyellow", "  No metadata available"))
            lines.append(("", "\n"))
            lines.append(("fg:ansibrightblack", "  Add a SKILL.md with frontmatter to"))
            lines.append(("", "\n"))
            lines.append(
                ("fg:ansibrightblack", "  define name, description, and tags.")
            )
            lines.append(("", "\n\n"))

        # Path
        lines.append(("bold", "  Path:"))
        lines.append(("", "\n"))
        path_str = str(skill.path)
        if len(path_str) > 45:
            path_str = "..." + path_str[-42:]
        lines.append(("fg:ansibrightblack", f"    {path_str}"))
        lines.append(("", "\n"))

        return lines

    def _wrap_text(self, text: str, width: int) -> List[str]:
        """Wrap text to specified width."""
        words = text.split()
        lines = []
        current_line = []
        current_length = 0

        for word in words:
            if current_length + len(word) + 1 <= width:
                current_line.append(word)
                current_length += len(word) + 1
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]
                current_length = len(word)

        if current_line:
            lines.append(" ".join(current_line))

        return lines or [""]

    def update_display(self) -> None:
        """Update the display based on current state."""
        if self.menu_control:
            self.menu_control.text = self._render_skill_list()
        if self.preview_control:
            self.preview_control.text = self._render_skill_details()

    def run(self) -> bool:
        """Run the interactive skills browser.

        Returns:
            True if changes were made, False otherwise.
        """
        # Reset per-run state
        self.result = None

        # Build UI
        self.menu_control = FormattedTextControl(text="")
        self.preview_control = FormattedTextControl(text="")

        menu_window = Window(
            content=self.menu_control, wrap_lines=True, width=Dimension(weight=35)
        )
        preview_window = Window(
            content=self.preview_control, wrap_lines=True, width=Dimension(weight=65)
        )

        menu_frame = Frame(menu_window, width=Dimension(weight=35), title="Skills")
        preview_frame = Frame(
            preview_window, width=Dimension(weight=65), title="Details"
        )

        root_container = VSplit([menu_frame, preview_frame])

        # Key bindings
        kb = KeyBindings()

        @kb.add("up")
        @kb.add("c-p")  # Ctrl+P
        @kb.add("k")
        def _(event):
            if self.selected_idx > 0:
                self.selected_idx -= 1
                self.current_page = self.selected_idx // PAGE_SIZE
            self.update_display()

        @kb.add("down")
        @kb.add("c-n")  # Ctrl+N
        @kb.add("j")
        def _(event):
            if self.selected_idx < len(self.skills) - 1:
                self.selected_idx += 1
                self.current_page = self.selected_idx // PAGE_SIZE
            self.update_display()

        @kb.add("left")
        def _(event):
            """Previous page."""
            if self.current_page > 0:
                self.current_page -= 1
                self.selected_idx = self.current_page * PAGE_SIZE
                self.update_display()

        @kb.add("right")
        def _(event):
            """Next page."""
            total_pages = (len(self.skills) + PAGE_SIZE - 1) // PAGE_SIZE
            if self.current_page < total_pages - 1:
                self.current_page += 1
                self.selected_idx = self.current_page * PAGE_SIZE
                self.update_display()

        @kb.add("enter")
        def _(event):
            """Toggle skill enabled/disabled."""
            self._toggle_current_skill()
            self.result = "changed"

        @kb.add("t")
        def _(event):
            """Toggle skills system on/off."""
            new_state = not self.skills_enabled
            set_skills_enabled(new_state)
            self.skills_enabled = new_state
            self.result = "changed"
            self.update_display()

        @kb.add("r")
        def _(event):
            """Refresh skills."""
            refresh_skill_cache()
            self._refresh_data()
            self.update_display()

        @kb.add("c-a")
        def _(event):
            """Add a skill directory."""
            self.result = "add_directory"
            event.app.exit()

        @kb.add("c-d")
        def _(event):
            """Show/manage directories."""
            self.result = "show_directories"
            event.app.exit()

        @kb.add("i")
        def _(event):
            """Install skills from catalog."""
            self.result = "install"
            event.app.exit()

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

        # Enter alternate screen buffer
        sys.stdout.write("\033[?1049h")  # Enter alternate buffer
        sys.stdout.write("\033[2J\033[H")  # Clear and home
        sys.stdout.flush()
        time.sleep(0.05)

        try:
            # Initial display
            self.update_display()

            # Clear the buffer
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

            # Run application in a background thread to avoid event loop conflicts
            app.run(in_thread=True)

        finally:
            # Exit alternate screen buffer
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

        return self.result


def _prompt_for_directory() -> Optional[str]:
    """Prompt user for a directory path to add."""
    from code_puppy.tools.common import safe_input

    try:
        print("\n" + "=" * 60)
        print("ADD SKILL DIRECTORY")
        print("=" * 60)
        print("\nEnter the path to a directory containing skills.")
        print("Examples:")
        print("  ~/.claude/skills")
        print("  /opt/shared-skills")
        print("  ./my-project-skills")
        print("\nPress Ctrl+C to cancel.\n")

        path = safe_input("Directory path: ").strip()
        if path:
            # Expand ~ to home directory
            expanded = os.path.expanduser(path)
            return expanded
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
    return None


def _show_directories_menu() -> Optional[str]:
    """Show current directories and allow removal."""
    from code_puppy.tools.common import safe_input

    try:
        dirs = get_skill_directories()

        print("\n" + "=" * 60)
        print("SKILL DIRECTORIES")
        print("=" * 60)
        print("\nCurrently configured directories:\n")

        if not dirs:
            print("  (no directories configured)")
        else:
            for i, d in enumerate(dirs, 1):
                exists = os.path.isdir(os.path.expanduser(d))
                status = "✓" if exists else "✗ (not found)"
                print(f"  {i}. {d}  {status}")

        print("\nOptions:")
        print("  Enter a number to remove that directory")
        print("  Press Enter or Ctrl+C to go back\n")

        choice = safe_input("Choice: ").strip()
        if choice and choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(dirs):
                dir_to_remove = dirs[idx]
                confirm = (
                    safe_input(f"Remove '{dir_to_remove}'? (y/N): ").strip().lower()
                )
                if confirm in ("y", "yes"):
                    remove_skill_directory(dir_to_remove)
                    print(f"Removed: {dir_to_remove}")
                    return "changed"
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
    return None


def show_skills_menu() -> bool:
    """Launch the interactive skills TUI menu.

    Returns:
        True if changes were made, False otherwise.
    """

    changes_made = False

    while True:
        menu = SkillsMenu()
        result = menu.run()

        if result == "add_directory":
            # Prompt for directory to add
            new_dir = _prompt_for_directory()
            if new_dir:
                if add_skill_directory(new_dir):
                    emit_success(f"Added skill directory: {new_dir}")
                    changes_made = True
                else:
                    emit_warning(f"Directory already configured: {new_dir}")
            # Re-run the menu
            continue

        elif result == "show_directories":
            # Show directories management
            dir_result = _show_directories_menu()
            if dir_result == "changed":
                changes_made = True
            # Re-run the menu
            continue

        elif result == "install":
            from code_puppy.plugins.agent_skills.skills_install_menu import (
                run_skills_install_menu,
            )

            install_result = run_skills_install_menu()
            if install_result:
                changes_made = True
            continue  # Re-run the skills menu after install

        elif result == "changed":
            changes_made = True
            break
        elif result == "quit":
            break
        else:
            # User quit or no-op
            break

    return changes_made


def list_skills() -> bool:
    """List all discovered skills in a simple format.

    Returns:
        True if successful, False otherwise.
    """
    try:
        skills = discover_skills()
        disabled_skills = get_disabled_skills()

        if not skills:
            emit_info(
                "No skills found. Create skills in ~/.code_puppy/skills/ or ./skills/"
            )
            return True

        emit_info(f"\nFound {len(skills)} skill(s):\n")

        for skill in skills:
            metadata = parse_skill_metadata(skill.path)
            if metadata:
                is_disabled = metadata.name in disabled_skills
                status = "enabled" if not is_disabled else "disabled"
                emit_info(f"  [{status}] {metadata.name}")
                if metadata.description:
                    emit_info(f"    {metadata.description}")
                resources = get_skill_resources(metadata.path)
                if resources:
                    emit_info(f"    Resources: {len(resources)}")
            else:
                is_disabled = skill.name in disabled_skills
                status = "enabled" if not is_disabled else "disabled"
                emit_info(f"  [{status}] {skill.name} (no metadata)")

        return True
    except Exception as e:
        emit_error(f"Failed to list skills: {e}")
        return False


def handle_skills_command(args: list[str]) -> bool:
    """Handle skills subcommands from the CLI.

    Args:
        args: List of command arguments (e.g., ['enable', 'my-skill'])

    Returns:
        True if successful, False otherwise.
    """
    if not args:
        # Show interactive TUI
        return show_skills_menu()

    command = args[0].lower()

    if command == "list":
        return list_skills()
    elif command == "enable":
        if len(args) < 2:
            emit_error("Usage: /skills enable <skill-name>")
            return False
        return _enable_skill(args[1])
    elif command == "disable":
        if len(args) < 2:
            emit_error("Usage: /skills disable <skill-name>")
            return False
        return _disable_skill(args[1])
    elif command == "toggle":
        return _toggle_skills_integration()
    elif command == "refresh":
        return _refresh_skills()
    elif command == "help":
        _show_help()
        return True
    else:
        emit_error(f"Unknown command: {command}")
        emit_info("Use '/skills help' to see available commands.")
        return False


def _enable_skill(skill_name: str) -> bool:
    """Enable a specific skill."""
    try:
        skills = discover_skills()
        skill_names = [s.name for s in skills]

        # Also check metadata names
        for skill in skills:
            metadata = parse_skill_metadata(skill.path)
            if metadata:
                skill_names.append(metadata.name)

        if skill_name not in skill_names:
            emit_error(f"Skill '{skill_name}' not found.")
            return False

        disabled = get_disabled_skills()
        if skill_name not in disabled:
            emit_info(f"Skill '{skill_name}' is already enabled.")
            return True

        set_skill_disabled(skill_name, False)
        refresh_skill_cache()
        emit_success(f"Skill '{skill_name}' has been enabled.")
        return True
    except Exception as e:
        emit_error(f"Failed to enable skill '{skill_name}': {e}")
        return False


def _disable_skill(skill_name: str) -> bool:
    """Disable a specific skill."""
    try:
        skills = discover_skills()
        skill_names = [s.name for s in skills]

        # Also check metadata names
        for skill in skills:
            metadata = parse_skill_metadata(skill.path)
            if metadata:
                skill_names.append(metadata.name)

        if skill_name not in skill_names:
            emit_error(f"Skill '{skill_name}' not found.")
            return False

        disabled = get_disabled_skills()
        if skill_name in disabled:
            emit_info(f"Skill '{skill_name}' is already disabled.")
            return True

        set_skill_disabled(skill_name, True)
        refresh_skill_cache()
        emit_success(f"Skill '{skill_name}' has been disabled.")
        return True
    except Exception as e:
        emit_error(f"Failed to disable skill '{skill_name}': {e}")
        return False


def _toggle_skills_integration() -> bool:
    """Toggle skills integration on/off."""
    try:
        current = get_skills_enabled()
        new_state = not current
        set_skills_enabled(new_state)

        if new_state:
            emit_success("Skills integration has been enabled.")
        else:
            emit_warning("Skills integration has been disabled.")

        return True
    except Exception as e:
        emit_error(f"Failed to toggle skills integration: {e}")
        return False


def _refresh_skills() -> bool:
    """Refresh the skill cache."""
    try:
        emit_info("Refreshing skill cache...")
        refresh_skill_cache()
        emit_success("Skill cache refreshed successfully.")
        return True
    except Exception as e:
        emit_error(f"Failed to refresh skill cache: {e}")
        return False


def _show_help() -> None:
    """Show help information."""
    emit_info("Available commands:")
    emit_info("  /skills                    - Show interactive TUI")
    emit_info("  /skills list              - List all skills")
    emit_info("  /skills enable <name>     - Enable a skill")
    emit_info("  /skills disable <name>    - Disable a skill")
    emit_info("  /skills toggle            - Toggle skills integration")
    emit_info("  /skills refresh           - Refresh skill cache")
    emit_info("  /skills help              - Show this help")
