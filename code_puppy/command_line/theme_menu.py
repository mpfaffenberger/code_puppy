"""Interactive terminal UI for selecting color themes.

Provides a beautiful split-panel interface for browsing and previewing themes
with live preview of message colors and one-click theme application.
"""

import io
import sys
import time
from typing import List, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame
from rich.console import Console

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.themes import (
    get_all_themes,
    get_theme_info,
    get_theme_manager,
    is_preset_theme,
    set_theme_name,
)
from code_puppy.themes.theme import Theme
from code_puppy.tools.command_runner import set_awaiting_user_input

PAGE_SIZE = 12  # Themes per page


class ThemeMenu:
    """Interactive TUI for browsing and selecting themes."""

    def __init__(self):
        """Initialize the theme selection menu."""
        # Load all available themes (presets + custom)
        self.themes: List[str] = []
        self.theme_objects: dict = {}
        self._initialize_themes()

        # State management
        self.selected_theme_idx = 0
        self.current_page = 0
        self.result: Optional[str] = None  # Selected theme name or None if cancelled
        self.show_help = False  # Toggle help overlay
        self.status_message = ""  # Status message to display

    def _initialize_themes(self):
        """Load all available themes (presets and custom)."""
        try:
            manager = get_theme_manager()
            self.themes = manager.list_available_themes()
            self.theme_objects = get_all_themes()

            if not self.themes:
                emit_error("No themes found")
        except Exception as e:
            emit_error(f"Error loading themes: {e}")
            self.themes = []
            self.theme_objects = {}

    def _get_current_theme_name(self) -> Optional[str]:
        """Get the currently selected theme name."""
        if 0 <= self.selected_theme_idx < len(self.themes):
            return self.themes[self.selected_theme_idx]
        return None

    def _get_current_theme(self) -> Optional[Theme]:
        """Get the currently selected Theme object."""
        theme_name = self._get_current_theme_name()
        if theme_name:
            return self.theme_objects.get(theme_name)
        return None

    def _render_theme_list(self) -> List:
        """Render the theme list panel."""
        lines = []

        lines.append(("", " Select Theme"))
        lines.append(("", "\n\n"))

        if not self.themes:
            lines.append(("fg:yellow", "  No themes available."))
            lines.append(("", "\n\n"))
            self._render_navigation_hints(lines)
            return lines

        # Show themes for current page
        total_pages = (len(self.themes) + PAGE_SIZE - 1) // PAGE_SIZE
        start_idx = self.current_page * PAGE_SIZE
        end_idx = min(start_idx + PAGE_SIZE, len(self.themes))

        for i in range(start_idx, end_idx):
            theme_name = self.themes[i]
            is_selected = i == self.selected_theme_idx
            is_preset = is_preset_theme(theme_name)

            # Get theme info
            theme_info = get_theme_info(theme_name)
            description = theme_info["description"] if theme_info else ""

            # Shorten description if too long
            if len(description) > 45:
                description = description[:42] + "..."

            # Format: "> Theme Name" or "  Theme Name"
            prefix = " > " if is_selected else "   "
            icon = "⭐" if is_preset else "🎨"

            if is_selected:
                lines.append(
                    ("fg:ansibrightblack bold", f"{prefix}{icon} {theme_name}")
                )
            else:
                lines.append(("fg:ansibrightblack", f"{prefix}{icon} {theme_name}"))

            lines.append(("", "\n"))

            # Show description on next line (indented)
            if description:
                lines.append(("fg:ansibrightblack dim", f"     {description}"))
                lines.append(("", "\n"))

        lines.append(("", "\n"))
        lines.append(
            ("fg:ansibrightblack", f" Page {self.current_page + 1}/{total_pages}")
        )
        lines.append(("", "\n"))

        self._render_navigation_hints(lines)
        return lines

    def _render_navigation_hints(self, lines: List):
        """Render navigation hints at the bottom of the list panel."""
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  ↑/↓ "))
        lines.append(("", "Navigate  "))
        lines.append(("fg:ansibrightblack", "←/→ "))
        lines.append(("", "Page  "))
        lines.append(("fg:green", "Enter "))
        lines.append(("", "Select  "))
        lines.append(("fg:ansibrightblack", "Esc "))
        lines.append(("", "Cancel  "))
        lines.append(("fg:ansicyan", "? "))
        lines.append(("", "Help"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  Ctrl+C "))
        lines.append(("", "Exit"))

        # Show status message if available
        if self.status_message:
            lines.append(("", "\n"))
            lines.append(("fg:green", f"  ✓ {self.status_message}"))

    def _render_help_panel(self) -> ANSI:
        """Render the help panel with detailed instructions."""
        buffer = []

        buffer.append("[bold cyan]" + "=" * 50 + "[/bold cyan]")
        buffer.append("[bold cyan] HELP[/bold cyan]")
        buffer.append("[bold cyan]" + "=" * 50 + "[/bold cyan]")
        buffer.append("")

        buffer.append("[bold]Keyboard Shortcuts[/bold]")
        buffer.append("")
        buffer.append("[green]↑/↓[/green] Navigate up/down through themes")
        buffer.append("")
        buffer.append("[green]←/→[/green] Navigate between pages of themes")
        buffer.append("")
        buffer.append("[green]Enter[/green] Select and apply the highlighted theme")
        buffer.append("")
        buffer.append("[green]Esc[/green] Cancel and exit without selecting")
        buffer.append("")
        buffer.append("[green]Ctrl+C[/green] Exit immediately")
        buffer.append("")
        buffer.append("[green]?[/green] Toggle this help panel")
        buffer.append("")
        buffer.append("")

        buffer.append("[bold]Theme Icons[/bold]")
        buffer.append("")
        buffer.append("⭐ Preset theme (built-in)")
        buffer.append("")
        buffer.append("🎨 Custom theme (user-created)")
        buffer.append("")
        buffer.append("")

        buffer.append("[bold]Color Types[/bold]")
        buffer.append("")
        buffer.append("Error     - Error messages and failures")
        buffer.append("")
        buffer.append("Warning   - Warning messages and cautions")
        buffer.append("")
        buffer.append("Success   - Success confirmations")
        buffer.append("")
        buffer.append("Info      - General information")
        buffer.append("")
        buffer.append("Debug     - Debug output")
        buffer.append("")
        buffer.append("Tool      - Tool/command output")
        buffer.append("")
        buffer.append("Reasoning - Agent thought process")
        buffer.append("")
        buffer.append("Response  - Agent final responses")
        buffer.append("")
        buffer.append("System    - System messages")
        buffer.append("")
        buffer.append("")

        buffer.append("[cyan]Press ? to close help[/cyan]")
        buffer.append("")

        return self._render_to_ansi(buffer)

    def _render_message_preview(self) -> ANSI:
        """Render the message preview panel with theme colors using Rich's truecolor support."""
        if self.show_help:
            return self._render_help_panel()

        buffer = []

        # Header
        buffer.append("[bold cyan]" + "=" * 50 + "[/bold cyan]")
        buffer.append("[bold cyan] MESSAGE PREVIEW[/bold cyan]")
        buffer.append("[bold cyan]" + "=" * 50 + "[/bold cyan]")
        buffer.append("")

        theme_name = self._get_current_theme_name()
        theme = self._get_current_theme()
        if not theme:
            buffer.append("[yellow]No theme selected.[/yellow]")
            return self._render_to_ansi(buffer)

        # Get theme info
        theme_info = get_theme_info(theme_name) if theme_name else None

        # Display theme metadata
        if theme_info:
            # Theme name (title case)
            buffer.append(f"[bold cyan]{theme_info['name'].title()}[/bold cyan]")
            buffer.append("")

            # Description
            description = theme_info.get("description", "")
            if description:
                buffer.append(f"[bright_black]{description}[/bright_black]")
                buffer.append("")

            # Author and version
            author = theme_info.get("author")
            version = theme_info.get("version")
            if author or version:
                buffer.append("")
                buffer.append("[dim]──[/dim]")
                buffer.append("")
                meta_parts = []
                if author:
                    meta_parts.append(f"by {author}")
                if version:
                    meta_parts.append(f"v{version}")
                if meta_parts:
                    buffer.append(f"[dim]{' '.join(meta_parts)}[/dim]")
                    buffer.append("")

            # Tags (displayed as badges)
            tags = theme_info.get("tags", [])
            if tags:
                if author or version:
                    buffer.append("")
                buffer.append("[dim]Tags:[/dim]")
                buffer.append("")
                # Display tags as colored badges
                for i, tag in enumerate(tags[:5]):  # Show max 5 tags
                    tag_color = "cyan" if i % 2 == 0 else "magenta"
                    buffer.append(f"[{tag_color}][{tag}][/{tag_color}] ")
                buffer.append("")

            buffer.append("")

        # Display sample messages of each type with the theme's colors
        # Using Rich's markup syntax for truecolor support

        buffer.append("[bold]Message Type Samples[/bold]")
        buffer.append("")

        # Error message
        buffer.append(f"[{theme.error_color}]❌ Error:[/{theme.error_color}]")
        buffer.append(f"[{theme.error_color}]Something went wrong![/{theme.error_color}]")
        buffer.append("")

        # Warning message
        buffer.append(f"[{theme.warning_color}]⚠️  Warning:[/{theme.warning_color}]")
        buffer.append(f"[{theme.warning_color}]This is a warning message[/{theme.warning_color}]")
        buffer.append("")

        # Success message
        buffer.append(f"[{theme.success_color}]✅ Success:[/{theme.success_color}]")
        buffer.append(f"[{theme.success_color}]Operation completed successfully[/{theme.success_color}]")
        buffer.append("")

        # Info message
        buffer.append(f"[{theme.info_color}]ℹ️  Info:[/{theme.info_color}]")
        buffer.append(f"[{theme.info_color}]Informational message[/{theme.info_color}]")
        buffer.append("")

        # Debug message
        buffer.append(f"[{theme.debug_color}]🔍 Debug:[/{theme.debug_color}]")
        buffer.append(f"[{theme.debug_color}]Debug information[/{theme.debug_color}]")
        buffer.append("")

        # Tool output
        buffer.append(f"[{theme.tool_output_color}]🔧 Tool Output:[/{theme.tool_output_color}]")
        buffer.append(f"[{theme.tool_output_color}]File operations completed[/{theme.tool_output_color}]")
        buffer.append("")

        # Agent reasoning
        buffer.append(f"[{theme.agent_reasoning_color}]🧠 Agent Reasoning:[/{theme.agent_reasoning_color}]")
        buffer.append(f"[{theme.agent_reasoning_color}]Analyzing the request...[/{theme.agent_reasoning_color}]")
        buffer.append("")

        # Agent response
        buffer.append(f"[{theme.agent_response_color}]💬 Agent Response:[/{theme.agent_response_color}]")
        buffer.append(f"[{theme.agent_response_color}]Here's the solution[/{theme.agent_response_color}]")
        buffer.append("")

        # System message
        buffer.append(f"[{theme.system_color}]⚙️  System:[/{theme.system_color}]")
        buffer.append(f"[{theme.system_color}]System status update[/{theme.system_color}]")
        buffer.append("")

        return self._render_to_ansi(buffer)

    def _render_to_ansi(self, buffer: List[str]) -> ANSI:
        """Render buffer list to ANSI using Rich's Console with truecolor support.

        Args:
            buffer: List of Rich markup strings

        Returns:
            ANSI-formatted text for prompt_toolkit
        """
        output = io.StringIO()
        preview_console = Console(
            file=output,
            force_terminal=True,
            width=80,
            legacy_windows=False,
            color_system="truecolor",
            no_color=False,
        )
        preview_console.print("\n".join(buffer))

        return ANSI(output.getvalue())

    def update_display(self):
        """Update the display based on current state."""
        self.menu_control.text = self._render_theme_list()
        self.preview_control.text = self._render_message_preview()

    def _select_theme(self):
        """Select and apply the current theme."""
        theme_name = self._get_current_theme_name()
        if theme_name:
            self.result = theme_name

    def run(self) -> Optional[str]:
        """Run the interactive theme selection menu (synchronous).

        Returns:
            The selected theme name, or None if cancelled
        """
        if not self.themes:
            emit_warning("No themes available.")
            return None

        # Build UI
        self.menu_control = FormattedTextControl(text="")
        self.preview_control = FormattedTextControl(text="")

        menu_window = Window(
            content=self.menu_control, wrap_lines=True, width=Dimension(weight=40)
        )
        preview_window = Window(
            content=self.preview_control, wrap_lines=True, width=Dimension(weight=60)
        )

        menu_frame = Frame(menu_window, width=Dimension(weight=40), title="Themes")
        preview_frame = Frame(
            preview_window, width=Dimension(weight=60), title="Preview"
        )

        root_container = VSplit([menu_frame, preview_frame])

        # Key bindings
        kb = KeyBindings()

        @kb.add("up")
        def _(event):
            if self.selected_theme_idx > 0:
                self.selected_theme_idx -= 1
                self.current_page = self.selected_theme_idx // PAGE_SIZE
            self.update_display()

        @kb.add("down")
        def _(event):
            if self.selected_theme_idx < len(self.themes) - 1:
                self.selected_theme_idx += 1
                self.current_page = self.selected_theme_idx // PAGE_SIZE
            self.update_display()

        @kb.add("left")
        def _(event):
            """Previous page."""
            if self.current_page > 0:
                self.current_page -= 1
                self.selected_theme_idx = self.current_page * PAGE_SIZE
                self.update_display()

        @kb.add("right")
        def _(event):
            """Next page."""
            total_pages = (len(self.themes) + PAGE_SIZE - 1) // PAGE_SIZE
            if self.current_page < total_pages - 1:
                self.current_page += 1
                self.selected_theme_idx = self.current_page * PAGE_SIZE
                self.update_display()

        @kb.add("enter")
        def _(event):
            if self.show_help:
                self.show_help = False
                self.status_message = ""
                self.update_display()
            else:
                self._select_theme()
                self.status_message = f"Theme: {self._get_current_theme_name()}"
                self.update_display()
                time.sleep(0.3)  # Brief pause to show status
                event.app.exit()

        @kb.add("escape")
        def _(event):
            if self.show_help:
                self.show_help = False
                self.status_message = ""
                self.update_display()
            else:
                self.status_message = "Cancelled"
                self.result = None
                event.app.exit()

        @kb.add("c-c")
        def _(event):
            self.status_message = "Cancelled"
            self.result = None
            event.app.exit()

        @kb.add("?")
        def _(event):
            """Toggle help panel."""
            self.show_help = not self.show_help
            self.update_display()

        layout = Layout(root_container)
        app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=False,
            mouse_support=False,
        )

        set_awaiting_user_input(True)

        # Enter alternate screen buffer once for entire session
        sys.stdout.write("\033[?1049h")  # Enter alternate buffer
        sys.stdout.write("\033[2J\033[H")  # Clear and home
        sys.stdout.flush()
        time.sleep(0.05)

        try:
            # Initial display
            self.update_display()

            # Just clear the current buffer (don't switch buffers)
            sys.stdout.write("\033[2J\033[H")  # Clear screen within current buffer
            sys.stdout.flush()

            # Run application in a background thread to avoid event loop conflicts
            # This is needed because code_puppy runs in an async context
            app.run(in_thread=True)

        finally:
            # Exit alternate screen buffer once at end
            sys.stdout.write("\033[?1049l")  # Exit alternate buffer
            sys.stdout.flush()
            # Reset awaiting input flag
            set_awaiting_user_input(False)

        # Handle theme selection after TUI exits
        if self.result:
            try:
                # Save the selected theme to config
                set_theme_name(self.result)
                emit_success(f"✨ Theme '{self.result}' applied successfully!")
                emit_info(
                    "Restart Code Puppy or run /theme preview to see the changes."
                )
                return self.result
            except Exception as e:
                emit_error(f"Error applying theme: {e}")
                return None
        else:
            emit_info("Theme selection cancelled.")
            return None


def select_theme_interactive() -> Optional[str]:
    """Convenience function to run the theme selection menu.

    Returns:
        The selected theme name, or None if cancelled

    Example:
        >>> from code_puppy.command_line.theme_menu import select_theme_interactive
        >>> theme = select_theme_interactive()
        >>> if theme:
        ...     print(f"Selected: {theme}")
    """
    menu = ThemeMenu()
    return menu.run()
