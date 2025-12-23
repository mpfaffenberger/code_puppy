"""Theme management for Code Puppy.

Handles loading, saving, and applying themes. Integrates with the config system
for persistence and supports both built-in and custom themes.
"""

import json
from pathlib import Path
from typing import Optional

from .builtin_themes import BUILTIN_THEMES, DEFAULT_THEME
from .theme_models import Theme, ThemeColors

# Custom theme file location (in user's config directory)
_CUSTOM_THEME_FILENAME = "custom_theme.json"

# Global cache for the current theme (avoids repeated config reads)
_current_theme_cache: Optional[Theme] = None


def _get_custom_theme_path() -> Path:
    """Get the path to the custom theme file.

    Returns:
        Path to ~/.code_puppy/custom_theme.json (or XDG equivalent)
    """
    # Import here to avoid circular imports
    from code_puppy.config import DATA_DIR

    return Path(DATA_DIR) / _CUSTOM_THEME_FILENAME


def _load_custom_theme() -> Optional[Theme]:
    """Load a custom theme from the user's config directory.

    Returns:
        Theme instance if custom theme exists and is valid, None otherwise
    """
    custom_path = _get_custom_theme_path()

    if not custom_path.exists():
        return None

    try:
        with open(custom_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Validate and parse the theme data
        colors = ThemeColors(**data.get("colors", {}))
        return Theme(
            name="custom",
            display_name=data.get("display_name", "Custom 🎨"),
            description=data.get("description", "Your personalized theme"),
            colors=colors,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        # Log the error but don't crash - fall back to default
        import sys

        sys.stderr.write(f"Warning: Failed to load custom theme: {e}\n")
        return None


def save_custom_theme(
    colors: ThemeColors,
    display_name: str = "Custom 🎨",
    description: str = "Your personalized theme",
) -> bool:
    """Save a custom theme to the user's config directory.

    Args:
        colors: ThemeColors instance with the custom color configuration
        display_name: Human-readable name for the theme
        description: Brief description of the theme

    Returns:
        True if save was successful, False otherwise
    """
    custom_path = _get_custom_theme_path()

    try:
        # Ensure directory exists
        custom_path.parent.mkdir(parents=True, exist_ok=True)

        theme_data = {
            "display_name": display_name,
            "description": description,
            "colors": colors.model_dump(),
        }

        with open(custom_path, "w", encoding="utf-8") as f:
            json.dump(theme_data, f, indent=2)

        # Clear cache so next get_current_theme() reflects changes
        global _current_theme_cache
        _current_theme_cache = None

        return True
    except (OSError, IOError) as e:
        import sys

        sys.stderr.write(f"Warning: Failed to save custom theme: {e}\n")
        return False


def get_available_themes() -> list[str]:
    """Get a list of all available theme names.

    Returns:
        List of theme names (built-in themes plus 'custom' if it exists)
    """
    themes = list(BUILTIN_THEMES.keys())

    # Add custom theme if it exists
    if _get_custom_theme_path().exists():
        themes.append("custom")

    return sorted(themes)


def get_theme_by_name(name: str) -> Optional[Theme]:
    """Get a theme by its name.

    Args:
        name: Theme name (e.g., "default", "dracula", "custom")

    Returns:
        Theme instance if found, None otherwise
    """
    # Check built-in themes first
    if name in BUILTIN_THEMES:
        return BUILTIN_THEMES[name]

    # Check for custom theme
    if name == "custom":
        return _load_custom_theme()

    return None


def get_current_theme() -> Theme:
    """Get the currently active theme.

    Reads the theme name from config and returns the corresponding Theme.
    Falls back to DEFAULT_THEME if the configured theme is not found.

    Returns:
        The currently active Theme instance
    """
    global _current_theme_cache

    # Return cached theme if available
    if _current_theme_cache is not None:
        return _current_theme_cache

    # Import here to avoid circular imports
    from code_puppy.config import get_value

    theme_name = get_value("theme")

    if theme_name:
        theme = get_theme_by_name(theme_name)
        if theme:
            _current_theme_cache = theme
            return theme

    # Fall back to default theme
    _current_theme_cache = DEFAULT_THEME
    return DEFAULT_THEME


def set_current_theme(theme_name: str) -> bool:
    """Set the current theme by name and persist to config.

    Args:
        theme_name: Name of the theme to activate

    Returns:
        True if theme was set successfully, False if theme not found
    """
    # Validate theme exists
    theme = get_theme_by_name(theme_name)
    if theme is None:
        return False

    # Import here to avoid circular imports
    from code_puppy.config import set_config_value

    # Persist to config
    set_config_value("theme", theme_name)

    # Clear cache so next get_current_theme() reflects the change
    global _current_theme_cache
    _current_theme_cache = theme

    # Apply the theme immediately
    apply_theme(theme)

    return True


def apply_theme(theme: Theme) -> None:
    """Apply a theme's styles to the global style mappings.

    This function updates the global style dictionaries used by the messaging
    system and other components. It should be called when the theme changes.

    Args:
        theme: The Theme to apply
    """
    # Update the global style cache
    global _current_theme_cache
    _current_theme_cache = theme

    # Update the DEFAULT_STYLES in rich_renderer if it's been imported
    # This allows the renderer to pick up theme changes dynamically
    try:
        from code_puppy.messaging.messages import MessageLevel
        from code_puppy.messaging.rich_renderer import DEFAULT_STYLES

        # Map theme colors to message levels
        DEFAULT_STYLES[MessageLevel.ERROR] = theme.colors.error_style
        DEFAULT_STYLES[MessageLevel.WARNING] = theme.colors.warning_style
        DEFAULT_STYLES[MessageLevel.SUCCESS] = theme.colors.success_style
        DEFAULT_STYLES[MessageLevel.INFO] = theme.colors.info_style
        DEFAULT_STYLES[MessageLevel.DEBUG] = theme.colors.debug_style
    except ImportError:
        # Messaging system not yet loaded, styles will be applied on first use
        pass

    # Update diff styles if available
    try:
        from code_puppy.messaging.rich_renderer import DIFF_STYLES

        DIFF_STYLES["add"] = theme.colors.diff_add_style
        DIFF_STYLES["remove"] = theme.colors.diff_remove_style
        DIFF_STYLES["context"] = theme.colors.diff_context_style
    except ImportError:
        pass


def clear_theme_cache() -> None:
    """Clear the theme cache.

    Call this when the config file changes externally or when you need
    to force a reload of the current theme.
    """
    global _current_theme_cache
    _current_theme_cache = None


def get_style(style_name: str) -> str:
    """Convenience function to get a style from the current theme.

    Args:
        style_name: Name of the style (e.g., "error_style", "header_style")

    Returns:
        The style string from the current theme, or empty string if not found
    """
    theme = get_current_theme()
    return theme.get_style(style_name) or ""
