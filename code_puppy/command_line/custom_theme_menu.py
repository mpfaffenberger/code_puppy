"""Interactive terminal UI for building custom color themes.

Provides a beautiful split-panel interface for configuring theme colors
with live preview of message colors and one-click theme saving.
"""

import io
import sys
import time
from typing import Optional

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.shortcuts import prompt
from prompt_toolkit.widgets import Frame
from rich.console import Console

from code_puppy.command_line.custom_theme_colors import (
    ALL_COLORS,
    MESSAGE_TYPES,
    STYLE_MODIFIERS,
)
from code_puppy.command_line.custom_theme_picker import arrow_select_async
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.themes.theme import Theme
from code_puppy.themes.theme_manager import get_theme_manager
from code_puppy.tools.command_runner import set_awaiting_user_input


# =============================================================================
# Custom Theme Builder
# =============================================================================


class CustomThemeBuilder:
    """Interactive TUI for building custom themes.

    The CustomThemeBuilder provides a split-panel interface where users can:
    - Navigate through 9 different message type color options
    - Select colors and style modifiers for each message type
    - See live preview of all message types with current colors
    - Save the custom theme to a JSON file

    Example:
        >>> from code_puppy.command_line.custom_theme_menu import CustomThemeBuilder
        >>> builder = CustomThemeBuilder()
        >>> theme = builder.run()
        >>> if theme:
        ...     print(f"Created theme: {theme.error_color}")
    """

    def __init__(self):
        """Initialize the custom theme builder."""
        # Start with default theme colors
        self.theme = Theme()
        self.selected_idx = 0
        self.result: Optional[Theme] = None  # Created theme or None if cancelled
        self.show_help = False  # Toggle help overlay
        self.status_message = ""  # Status message to display

        # Add action options at the end
        self.num_color_options = len(MESSAGE_TYPES)
        self.total_options = self.num_color_options + 2  # + Save and Cancel

    def _get_current_option(self) -> Optional[tuple]:
        """Get the currently selected option.

        Returns:
            (field_name, display_name, description) for color options
            or None for Save/Cancel options
        """
        if self.selected_idx < self.num_color_options:
            return MESSAGE_TYPES[self.selected_idx]
        return None

    def _get_current_color(self) -> Optional[str]:
        """Get the current color value for the selected option."""
        option = self._get_current_option()
        if option:
            field_name = option[0]
            return getattr(self.theme, field_name)
        return None

    def _render_option_list(self):
        """Render the color options list panel.

        Returns:
            FormattedText for the left panel showing all color options
        """
        lines = []

        if self.show_help:
            return self._render_help_panel()

        lines.append(("bold cyan", " Configure Theme Colors"))
        lines.append(("", "\n\n"))

        # Render color options
        for i, (field_name, display_name, description) in enumerate(MESSAGE_TYPES):
            is_selected = i == self.selected_idx
            current_color = getattr(self.theme, field_name)

            # Format: "> Display Name  [color]" or "  Display Name  [color]"
            prefix = " > " if is_selected else "   "

            if is_selected:
                lines.append(("fg:ansigreen bold", f"{prefix}{display_name}"))
            else:
                lines.append(("fg:ansibrightblack", f"{prefix}{display_name}"))

            lines.append(("", "\n"))

            # Show current color value
            if is_selected:
                lines.append(("fg:ansigreen", f"     [{current_color}]"))
            else:
                lines.append(("fg:gray dim", f"     [{current_color}]"))

            lines.append(("", "\n"))

            # Show description
            if is_selected:
                lines.append(("fg:ansiyellow", f"     {description}"))
            else:
                lines.append(("fg:gray dim", f"     {description}"))

            lines.append(("", "\n"))

        # Separator
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack dim", "─" * 40))
        lines.append(("", "\n\n"))

        # Save option
        save_idx = self.num_color_options
        if self.selected_idx == save_idx:
            lines.append(("fg:green bold", " > Save Theme"))
        else:
            lines.append(("fg:green", "   Save Theme"))
        lines.append(("", "\n\n"))

        # Cancel option
        cancel_idx = self.num_color_options + 1
        if self.selected_idx == cancel_idx:
            lines.append(("fg:red bold", " > Cancel"))
        else:
            lines.append(("fg:red", "   Cancel"))
        lines.append(("", "\n"))

        # Navigation hints
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  ↑/↓ "))
        lines.append(("", "Navigate  "))
        lines.append(("fg:green", "Enter "))
        lines.append(("", "Edit Color  "))
        lines.append(("fg:ansibrightblack", "Esc "))
        lines.append(("", "Cancel  "))
        lines.append(("fg:ansicyan", "? "))
        lines.append(("", "Help"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  Tab "))
        lines.append(("", "Jump to next option"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  Ctrl+C "))
        lines.append(("", "Exit"))

        # Show status message if available
        if self.status_message:
            lines.append(("", "\n"))
            lines.append(("fg:green", f"  ✓ {self.status_message}"))

        return lines

    def _render_preview(self) -> ANSI:
        """Render the live preview panel with current colors.

        Returns:
            ANSI-formatted text showing sample messages with current colors
        """
        buffer = []

        # Header
        buffer.append("[bold cyan]" + "═" * 50 + "[/bold cyan]")
        buffer.append("[bold cyan] LIVE PREVIEW[/bold cyan]")
        buffer.append("[bold cyan]" + "═" * 50 + "[/bold cyan]")
        buffer.append("")

        # Show sample messages with current colors
        samples = [
            (self.theme.error_color, "❌ Error:", "Something went wrong!", "error"),
            (
                self.theme.warning_color,
                "⚠️  Warning:",
                "This is a warning message",
                "warning",
            ),
            (
                self.theme.success_color,
                "✅ Success:",
                "Operation completed successfully",
                "success",
            ),
            (self.theme.info_color, "ℹ️  Info:", "Informational message", "info"),
            (self.theme.debug_color, "🔍 Debug:", "Debug information", "debug"),
            (
                self.theme.tool_output_color,
                "🔧 Tool Output:",
                "File operations completed",
                "tool",
            ),
            (
                self.theme.agent_reasoning_color,
                "🧠 Agent Reasoning:",
                "Analyzing the request...",
                "reasoning",
            ),
            (
                self.theme.agent_response_color,
                "💬 Agent Response:",
                "Here's the solution",
                "response",
            ),
            (self.theme.system_color, "⚙️  System:", "System status update", "system"),
        ]

        for color, icon, message, msg_type in samples:
            buffer.append(f"[{color}]{icon}[/] [{color}]{message}[/]")
            buffer.append("")

        buffer.append("")
        buffer.append("[bold cyan]" + "═" * 50 + "[/bold cyan]")

        # Render with Rich to get ANSI output
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

    def _render_help_panel(self):
        """Render the help panel with detailed instructions."""
        lines = []

        lines.append(("bold cyan", " HELP"))
        lines.append(("", "\n\n"))

        lines.append(("bold", "  Keyboard Shortcuts"))
        lines.append(("", "\n"))
        lines.append(("fg:green", "  ↑/↓"))
        lines.append(("", "  Navigate up/down through color options\n"))
        lines.append(("fg:green", "  Enter"))
        lines.append(("", "  Edit the selected color (opens color picker)\n"))
        lines.append(("fg:green", "  Tab"))
        lines.append(("", "  Jump to next color option\n"))
        lines.append(("fg:green", "  Esc"))
        lines.append(("", "  Cancel and exit without saving\n"))
        lines.append(("fg:green", "  Ctrl+C"))
        lines.append(("", "  Exit immediately\n"))
        lines.append(("fg:green", "  ?"))
        lines.append(("", "  Toggle this help panel\n"))

        lines.append(("", "\n"))
        lines.append(("bold", "  Color Picker"))
        lines.append(("", "\n"))
        lines.append(("", "  When editing a color, use:"))
        lines.append(("", "\n"))
        lines.append(("fg:green", "  ↑/↓"))
        lines.append(("", "  Navigate through color options\n"))
        lines.append(("fg:green", "  Enter"))
        lines.append(("", "  Select a color\n"))
        lines.append(("fg:green", "  Esc"))
        lines.append(("", "  Cancel color selection\n"))

        lines.append(("", "\n"))
        lines.append(("bold", "  Color Types"))
        lines.append(("", "\n"))
        lines.append(("", "  Error     - Error messages and failures\n"))
        lines.append(("", "  Warning   - Warning messages and cautions\n"))
        lines.append(("", "  Success   - Success confirmations\n"))
        lines.append(("", "  Info      - General information\n"))
        lines.append(("", "  Debug     - Debug output\n"))
        lines.append(("", "  Tool      - Tool/command output\n"))
        lines.append(("", "  Reasoning - Agent thought process\n"))
        lines.append(("", "  Response  - Agent final responses\n"))
        lines.append(("", "  System    - System messages\n"))

        lines.append(("", "\n"))
        lines.append(("bold", "  Style Modifiers"))
        lines.append(("", "\n"))
        lines.append(("", "  bold      - Bold text\n"))
        lines.append(("", "  dim       - Dimmed text\n"))
        lines.append(("", "  italic    - Italic text\n"))
        lines.append(("", "  underline - Underlined text\n"))
        lines.append(("", "  blink     - Blinking text\n"))
        lines.append(("", "  reverse   - Reversed colors\n"))

        lines.append(("", "\n"))
        lines.append(("fg:ansicyan", "  Press ? to close help"))

        return lines

    def update_display(self):
        """Update the display based on current state."""
        self.menu_control.text = self._render_option_list()
        self.preview_control.text = self._render_preview()

    def _open_color_picker(self) -> bool:
        """Open color picker for the currently selected option.

        This is a two-step process:
        1. Select a base color from available colors
        2. Select a style modifier (optional)

        Returns:
            True if color was changed, False if cancelled
        """
        option = self._get_current_option()
        if not option:
            return False

        field_name, display_name, description = option
        current_color = getattr(self.theme, field_name)

        # Parse current color into base color and style
        current_style = "(no style)"
        current_base = current_color

        # Check if color has a style modifier
        for style in STYLE_MODIFIERS[1:]:  # Skip "(no style)"
            if current_color.startswith(style + " "):
                current_style = style
                current_base = current_color[len(style) + 1 :]
                break

        # Step 1: Select base color
        try:
            selected_base = self._select_color_async(
                f"Select {display_name} - Base Color",
                ALL_COLORS,
                current_base,
            )
            if selected_base is None:
                return False  # Cancelled
        except KeyboardInterrupt:
            return False

        # Step 2: Select style modifier
        try:
            selected_style = self._select_style_async(
                f"Select {display_name} - Style",
                current_style,
            )
            if selected_style is None:
                return False  # Cancelled
        except KeyboardInterrupt:
            return False

        # Combine style and color
        if selected_style == "(no style)":
            new_color = selected_base
        else:
            new_color = f"{selected_style} {selected_base}"

        # Update the theme
        setattr(self.theme, field_name, new_color)
        return True

    def _select_color_async(
        self, title: str, colors: list[str], current: str
    ) -> Optional[str]:
        """Select a color from a list using arrow navigation.

        Args:
            title: Title for the selector
            colors: List of available colors
            current: Currently selected color

        Returns:
            Selected color or None if cancelled
        """
        import asyncio

        async def _select():
            return await arrow_select_async(title, colors, current, lambda c: None)

        return asyncio.run(_select())

    def _select_style_async(self, title: str, current: str) -> Optional[str]:
        """Select a style modifier using arrow navigation.

        Args:
            title: Title for the selector
            current: Currently selected style

        Returns:
            Selected style or None if cancelled
        """
        import asyncio

        async def _select():
            return await arrow_select_async(
                title, STYLE_MODIFIERS, current, lambda s: None
            )

        return asyncio.run(_select())

    def _save_theme(self) -> bool:
        """Prompt for theme name and save the theme.

        This method:
        1. Exits alternate screen buffer for prompt
        2. Prompts user for theme name
        3. Validates theme name (not empty, only alphanumeric/hyphen/underscore)
        4. Saves theme using theme_manager.save_theme()
        5. Re-enters alternate screen buffer

        Returns:
            True if saved successfully, False if cancelled or error
        """
        # Exit alternate buffer for prompt
        sys.stdout.write("\033[?1049l")  # Exit alternate buffer
        sys.stdout.flush()

        try:
            # Prompt for theme name
            theme_name = prompt(
                "\nEnter theme name: ",
                validator=lambda s: len(s.strip()) > 0,
                validate_while_typing=False,
            )

            if not theme_name or not theme_name.strip():
                emit_warning("Theme name cannot be empty.")
                return False

            theme_name = theme_name.strip()

            # Validate theme name (no special characters that could cause issues)
            import re

            if not re.match(r"^[a-zA-Z0-9_-]+$", theme_name):
                emit_warning(
                    "Theme name can only contain letters, numbers, hyphens, and underscores."
                )
                return False

            # Save the theme
            manager = get_theme_manager()
            manager.save_theme(self.theme, theme_name)

            self.result = self.theme
            emit_success(f"✨ Theme '{theme_name}' saved successfully!")
            return True

        except KeyboardInterrupt:
            emit_info("Save cancelled.")
            return False
        except Exception as e:
            emit_error(f"Error saving theme: {e}")
            return False
        finally:
            # Re-enter alternate buffer
            sys.stdout.write("\033[?1049h")  # Enter alternate buffer
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()

    def run(self) -> Optional[Theme]:
        """Run the interactive custom theme builder (synchronous).

        Creates a split-panel TUI with:
        - Left panel: List of 9 message type color options + Save/Cancel
        - Right panel: Live preview of all message types with current colors

        Returns:
            The created Theme instance, or None if cancelled

        Example:
            >>> builder = CustomThemeBuilder()
            >>> theme = builder.run()
            >>> if theme:
            ...     print(f"Created theme: {theme.error_color}")
        """
        # Build UI
        self.menu_control = FormattedTextControl(text="")
        self.preview_control = FormattedTextControl(text="")

        menu_window = Window(
            content=self.menu_control, wrap_lines=True, width=Dimension(weight=40)
        )
        preview_window = Window(
            content=self.preview_control, wrap_lines=True, width=Dimension(weight=60)
        )

        menu_frame = Frame(menu_window, width=Dimension(weight=40), title="Colors")
        preview_frame = Frame(
            preview_window, width=Dimension(weight=60), title="Preview"
        )

        root_container = VSplit([menu_frame, preview_frame])

        # Key bindings
        kb = KeyBindings()

        @kb.add("up")
        def _(event):
            """Move selection up."""
            if self.selected_idx > 0:
                self.selected_idx -= 1
            self.update_display()

        @kb.add("down")
        def _(event):
            """Move selection down."""
            if self.selected_idx < self.total_options - 1:
                self.selected_idx += 1
            self.update_display()

        @kb.add("enter")
        def _(event):
            """Handle Enter key - open color picker or save/cancel."""
            if self.show_help:
                self.show_help = False
                self.status_message = ""
                self.update_display()
                return

            option = self._get_current_option()
            if option:
                # Open color picker
                if self._open_color_picker():
                    self.status_message = "Color updated"
                    self.update_display()
            else:
                # Check if Save or Cancel
                if self.selected_idx == self.num_color_options:
                    # Save theme
                    if self._save_theme():
                        event.app.exit()
                    else:
                        # Re-entered buffer after save, update display
                        self.update_display()
                elif self.selected_idx == self.num_color_options + 1:
                    # Cancel
                    self.status_message = "Cancelled"
                    self.result = None
                    event.app.exit()

        @kb.add("escape")
        def _(event):
            """Cancel and exit."""
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
            """Cancel and exit on Ctrl-C."""
            self.status_message = "Cancelled"
            self.result = None
            event.app.exit()

        @kb.add("tab")
        def _(event):
            """Tab to next option."""
            if not self.show_help:
                if self.selected_idx < self.total_options - 1:
                    self.selected_idx += 1
                else:
                    self.selected_idx = 0  # Wrap to beginning
                self.update_display()

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

        return self.result


def build_custom_theme() -> Optional[Theme]:
    """Convenience function to run the custom theme builder.

    This function creates a CustomThemeBuilder instance and runs it,
    providing a simple interface for building custom themes.

    Returns:
        The created Theme instance, or None if cancelled

    Example:
        >>> from code_puppy.command_line.custom_theme_menu import build_custom_theme
        >>> theme = build_custom_theme()
        >>> if theme:
        ...     print(f"Created theme with error color: {theme.error_color}")
    """
    builder = CustomThemeBuilder()
    return builder.run()
