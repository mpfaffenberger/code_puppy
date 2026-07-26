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


def _relative_luminance(color: str) -> float:
    """Return WCAG relative luminance for a ``#rrggbb`` color."""
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def _muted_foreground(ansi: list[str], foreground: str, background: str) -> str:
    """Choose the least-prominent candidate that still meets WCAG AA."""
    candidates = (ansi[8], ansi[14], ansi[15], foreground)
    readable = [
        color for color in candidates if _contrast_ratio(color, background) >= 4.5
    ]
    return min(
        readable,
        key=lambda color: _contrast_ratio(color, background),
        default=foreground,
    )


def get_style_rules() -> dict[str, str]:
    """Return semantic prompt-toolkit rules for the active theme."""
    palette = _active_palette()
    if palette is None:
        return {}

    ansi = palette["ansi"]
    foreground = palette.get("fg", ansi[7])
    background = palette.get("bg", ansi[0])
    muted = _muted_foreground(ansi, foreground, background)
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
        "tui.input.focused": f"fg:{background} bg:{ansi[12]} bold noreverse",
        # prompt_toolkit's defaults hard-code grey on white for completion
        # menus. Root semantic rules cannot beat those more-specific selectors,
        # so adapt the standard widget classes here as part of the shared theme.
        "completion-menu": f"fg:{muted} bg:{background} noreverse",
        "completion-menu.completion": f"fg:{muted} bg:{background} noreverse",
        "completion-menu.completion.current": (
            f"fg:{ansi[12]} bg:{background} bold noreverse"
        ),
        "completion-menu.meta.completion": (
            f"fg:{muted} bg:{background} italic noreverse"
        ),
        "completion-menu.meta.completion.current": (
            f"fg:{ansi[14]} bg:{background} italic noreverse"
        ),
        "completion-menu.multi-column-meta": f"bg:{background}",
        "scrollbar.background": f"fg:{muted} bg:{background}",
        "scrollbar.button": f"fg:{muted} bg:{background}",
    }


def get_style() -> Style:
    """Build the active semantic style, or an empty style without a theme."""
    return Style.from_dict(get_style_rules())


def merge_with_active_style(style: BaseStyle | None) -> BaseStyle:
    """Layer a menu's specialized style over the shared theme base."""
    themed = get_style()
    return merge_styles([themed, style]) if style is not None else themed


__all__ = ["get_style", "get_style_rules", "merge_with_active_style"]
