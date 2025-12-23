"""Code Puppy Theme System.

This package provides a theming system for Code Puppy's messaging output.
Themes control the colors and styling of different message types and categories.

Example:
    >>> from code_puppy.themes import ThemeManager, get_theme_manager
    >>> manager = get_theme_manager()
    >>> theme = manager.load_theme("default")
    >>> manager.apply_theme(theme)
    >>> manager.list_available_themes()
    ['default', 'dark', 'light']

    >>> from code_puppy.themes import get_preset_theme, list_preset_themes
    >>> list_preset_themes()
    ['default', 'midnight', 'forest', 'sunset', 'ocean', ...]
    >>> theme = get_preset_theme("midnight")
"""

from .presets import (
    PRESET_THEME_DESCRIPTIONS,
    PRESET_THEMES,
    get_preset_theme,
    get_preset_theme_description,
    list_preset_themes,
    list_preset_themes_with_descriptions,
)
from .theme import Theme, validate_theme_name
from .theme_manager import (
    DEFAULT_THEME,
    THEME_DIR,
    ThemeManager,
    get_all_themes,
    get_theme_info,
    get_theme_manager,
    get_theme_name,
    is_preset_theme,
    set_theme_name,
)

# =============================================================================
# Export all public symbols
# =============================================================================

__all__ = [
    # Core theme system
    "Theme",
    "ThemeManager",
    "get_theme_manager",
    "DEFAULT_THEME",
    "THEME_DIR",
    # Config integration
    "get_theme_name",
    "set_theme_name",
    # Helper functions
    "get_all_themes",
    "is_preset_theme",
    "get_theme_info",
    "validate_theme_name",
    # Preset themes
    "PRESET_THEMES",
    "PRESET_THEME_DESCRIPTIONS",
    "get_preset_theme",
    "get_preset_theme_description",
    "list_preset_themes",
    "list_preset_themes_with_descriptions",
]
