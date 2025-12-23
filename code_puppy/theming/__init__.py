"""Code Puppy Theming System.

Provides customizable color themes for the CLI interface.
"""

from .builtin_themes import BUILTIN_THEMES, DEFAULT_THEME
from .theme_manager import (
    apply_theme,
    clear_theme_cache,
    get_available_themes,
    get_current_theme,
    get_style,
    get_theme_by_name,
    save_custom_theme,
    set_current_theme,
)
from .theme_models import Theme, ThemeColors

__all__ = [
    "Theme",
    "ThemeColors",
    "get_current_theme",
    "set_current_theme",
    "get_available_themes",
    "get_theme_by_name",
    "apply_theme",
    "save_custom_theme",
    "clear_theme_cache",
    "get_style",
    "BUILTIN_THEMES",
    "DEFAULT_THEME",
]
