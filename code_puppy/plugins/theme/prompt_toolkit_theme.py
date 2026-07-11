"""Central prompt-toolkit adapter for the active Code Puppy theme.

TUI applications pass their local style through the ``prompt_toolkit_style``
hook. The theme plugin layers this semantic base underneath it, so local menu
rules retain precedence and legacy fragments such as ``bold`` inherit a
readable foreground.
"""

from __future__ import annotations

from typing import Any

from prompt_toolkit.styles import BaseStyle, Style, merge_styles

from . import osc_palette


def _active_palette() -> dict[str, Any] | None:
    palette = osc_palette.get_saved_palette()
    ansi = palette.get("ansi") if palette else None
    if not palette or not isinstance(ansi, list) or len(ansi) < 16:
        return None
    return palette


def get_style_rules() -> dict[str, str]:
    """Return semantic prompt-toolkit rules for the active theme."""
    palette = _active_palette()
    if palette is None:
        return {}

    ansi = palette["ansi"]
    foreground = palette.get("fg", ansi[7])
    background = palette.get("bg", ansi[0])
    # Some light palettes reserve bright-black for their background. It is not
    # a usable muted foreground in that case (Solarized base3, hello again).
    muted = ansi[14] if ansi[8].lower() == background.lower() else ansi[8]
    return {
        "": f"fg:{foreground} bg:{background}",
        "tui": f"fg:{foreground} bg:{background}",
        "tui.header": f"fg:{ansi[12]} bold",
        "tui.title": f"fg:{ansi[14]} bold",
        "tui.body": f"fg:{foreground}",
        "tui.label": f"fg:{foreground} bold",
        "tui.muted": f"fg:{muted}",
        "tui.border": f"fg:{ansi[12]}",
        "tui.selected": f"fg:{background} bg:{ansi[12]} bold noreverse",
        "tui.help": f"fg:{muted}",
        "tui.help-key": f"fg:{ansi[10]} bold",
        "tui.success": f"fg:{ansi[10]} bold",
        "tui.warning": f"fg:{ansi[11]} bold",
        "tui.error": f"fg:{ansi[9]} bold",
        "tui.input": f"fg:{foreground}",
        "tui.input.focused": f"fg:{foreground} bg:{muted}",
    }


def get_style() -> Style:
    """Build the active semantic style, or an empty style without a theme."""
    return Style.from_dict(get_style_rules())


def merge_with_active_style(style: BaseStyle | None) -> BaseStyle:
    """Layer a menu's specialized style over the shared theme base."""
    themed = get_style()
    return merge_styles([themed, style]) if style is not None else themed


__all__ = ["get_style", "get_style_rules", "merge_with_active_style"]
