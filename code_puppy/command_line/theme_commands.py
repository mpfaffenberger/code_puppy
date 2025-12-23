"""Command handlers for Code Puppy - THEME commands.

This module contains @register_command decorated handlers for theme-related
commands that are automatically discovered by the command registry system.
"""

from code_puppy.command_line.command_registry import register_command


@register_command(
    name="theme",
    description="Open theme selection menu to choose color themes",
    usage="/theme",
    category="config",
)
def handle_theme_command(command: str) -> bool:
    """Open the interactive theme selection menu.

    This command launches a beautiful split-panel TUI for browsing
    and previewing available color themes. Users can select a theme
    and it will be automatically applied to the configuration.

    The ThemeMenu class handles:
    - Displaying all available themes (presets and custom)
    - Live preview of message colors
    - Theme selection and application
    - User feedback messages
    """
    from code_puppy.command_line.theme_menu import ThemeMenu
    from code_puppy.messaging import emit_error

    try:
        # Create and run the theme selection menu
        menu = ThemeMenu()
        _ = menu.run()  # Result ignored - ThemeMenu handles everything internally

        # The ThemeMenu.run() method already handles:
        # - Showing the interactive menu
        # - Applying the selected theme to config
        # - Displaying success/error/warning messages
        # - Returning the selected theme name or None if cancelled

        # We just need to return True to indicate the command was handled
        return True

    except Exception as e:
        emit_error(f"Failed to open theme menu: {e}")
        return True
