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

    # Compatibility field names; values are shared prompt-toolkit semantic roles.
    header_bold: str = "class:tui.header"
    header_dim: str = "class:tui.help"

    cursor_active: str = "class:tui.success"
    cursor_inactive: str = "class:tui.body"
    selected: str = "class:tui.selected"
    selected_check: str = "class:tui.success"

    text_normal: str = "class:tui.body"
    text_dim: str = "class:tui.muted"
    text_warning: str = "class:tui.warning"

    help_key: str = "class:tui.help-key"
    help_text: str = "class:tui.help"

    error: str = "class:tui.error"


# Create defaults after class definitions
_DEFAULT_TUI = TUIColors()


def get_tui_colors() -> TUIColors:
    """Return shared semantic roles for prompt-toolkit rendering.

    The active theme resolves these classes centrally. Legacy per-tool color
    configuration must not override that shared palette.
    """
    return _DEFAULT_TUI


# Rich console color mappings for the right panel
class RichColors(NamedTuple):
    """Rich markup colors for the question panel."""

    # Header colors (Rich markup format)
    header: str = "bold cyan"
    progress: str = "italic"

    # Question text
    question: str = "bold"
    question_hint: str = "italic"

    # Option colors
    cursor: str = "green bold"
    selected: str = "cyan"
    normal: str = ""
    description: str = "italic"

    # Input field
    input_label: str = "bold yellow"
    input_text: str = "green"
    input_hint: str = "italic"

    # Help overlay
    help_border: str = "bold cyan"
    help_title: str = "bold cyan"
    help_section: str = "bold"
    help_key: str = "green"
    help_close: str = "italic"

    # Timeout warning
    timeout_warning: str = "bold yellow"


_DEFAULT_RICH = RichColors()


def get_rich_colors() -> RichColors:
    """Return Rich styles backed by the shared prompt-toolkit palette."""
    from code_puppy.plugins.theme.prompt_toolkit_theme import get_style_rules

    muted_rule = get_style_rules().get("tui.muted", "").removeprefix("fg:")
    if not muted_rule:
        return _DEFAULT_RICH
    muted = muted_rule.split(maxsplit=1)[0]

    muted_style = f"{muted} italic"
    return _DEFAULT_RICH._replace(
        progress=muted_style,
        question_hint=muted_style,
        description=muted_style,
        input_hint=muted_style,
        help_close=muted_style,
    )
