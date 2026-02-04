"""Theme configuration for ask_user_question TUI.

This module provides theming support that integrates with code-puppy's
color configuration system. It allows the TUI to inherit colors from
the global configuration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping, NamedTuple, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["TUIColors", "RichColors", "get_tui_colors", "get_rich_colors"]

# Cached config getter to avoid repeated imports
_config_getter: "Callable[[str], str | None] | None" = None


def _get_config_value(key: str) -> str | None:
    """Safely get a config value, caching the import for performance."""
    global _config_getter
    if _config_getter is None:
        try:
            from code_puppy.config import get_value

            _config_getter = get_value
        except ImportError:
            _config_getter = lambda _: None  # noqa: E731
    return _config_getter(key)


_T = TypeVar("_T", bound=NamedTuple)


def _apply_config_overrides(default: _T, config_map: Mapping[str, str]) -> _T:
    """Apply config overrides to a color scheme.

    Args:
        default: Default NamedTuple instance
        config_map: Mapping of field names to config keys

    Returns:
        New NamedTuple with overrides applied
    """
    overrides = {}
    for field, config_key in config_map.items():
        value = _get_config_value(config_key)
        if value:
            overrides[field] = value
    return default._replace(**overrides) if overrides else default


class TUIColors(NamedTuple):
    """Color scheme for the ask_user_question TUI."""

    # Header and title colors
    header_bold: str = "bold cyan"
    header_dim: str = "fg:ansicyan dim"

    # Cursor and selection colors
    cursor_active: str = "fg:ansigreen bold"
    cursor_inactive: str = "fg:ansiwhite"
    selected: str = "fg:ansicyan"
    selected_check: str = "fg:ansigreen"

    # Text colors
    text_normal: str = ""
    text_dim: str = "fg:ansiwhite dim"
    text_warning: str = "fg:ansiyellow bold"

    # Help text colors
    help_key: str = "fg:ansigreen"
    help_text: str = "fg:ansiwhite dim"

    # Error colors
    error: str = "fg:ansired"


# Create defaults after class definitions
_DEFAULT_TUI = TUIColors()

# Mapping of configurable TUI color fields to config keys
_TUI_CONFIG_MAP: dict[str, str] = {
    "header_bold": "tui_header_color",
    "cursor_active": "tui_cursor_color",
    "selected": "tui_selected_color",
}


def get_tui_colors() -> TUIColors:
    """Get the current TUI color scheme.

    Loads colors from code-puppy's configuration system for custom theming.
    Falls back to defaults for any missing config values.

    Returns:
        TUIColors instance with the current theme.
    """
    return _apply_config_overrides(_DEFAULT_TUI, _TUI_CONFIG_MAP)


# Rich console color mappings for the right panel
class RichColors(NamedTuple):
    """Rich markup colors for the question panel."""

    # Header colors (Rich markup format)
    header: str = "bold cyan"
    progress: str = "dim"

    # Question text
    question: str = "bold"
    question_hint: str = "dim"

    # Option colors
    cursor: str = "green bold"
    selected: str = "cyan"
    normal: str = ""
    description: str = "dim"

    # Input field
    input_label: str = "bold yellow"
    input_text: str = "green"
    input_hint: str = "dim"

    # Help overlay
    help_border: str = "bold cyan"
    help_title: str = "bold cyan"
    help_section: str = "bold"
    help_key: str = "green"
    help_close: str = "dim"

    # Timeout warning
    timeout_warning: str = "bold yellow"


_DEFAULT_RICH = RichColors()

# Mapping of configurable Rich color fields to config keys
_RICH_CONFIG_MAP: dict[str, str] = {
    "header": "tui_rich_header_color",
    "cursor": "tui_rich_cursor_color",
}


def get_rich_colors() -> RichColors:
    """Get Rich console colors for the question panel.

    Falls back to defaults for any missing config values.

    Returns:
        RichColors instance with current theme.
    """
    return _apply_config_overrides(_DEFAULT_RICH, _RICH_CONFIG_MAP)
