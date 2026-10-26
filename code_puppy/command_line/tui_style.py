"""Theme-aware styling for termflow TUI menus.

The theme plugin persists the applied terminal palette (bg/fg + 16 ANSI
hexes) into config under ``osc_palette_json`` when it remaps the
terminal via OSC. Menus derive their accent colors from that palette so
the selected-row/title highlights match the active theme instead of
termflow's hardcoded defaults.

Core reads only the config value -- no plugin import. With no palette
applied (or an unparseable value) menus keep termflow's defaults.
"""

from __future__ import annotations

import json
from typing import Optional

from termflow.render.style import RenderStyle

from code_puppy.config import get_value

_PALETTE_CONFIG_KEY = "osc_palette_json"


def menu_style() -> Optional[RenderStyle]:
    """Return a RenderStyle for the active theme palette, or None."""
    try:
        raw = get_value(_PALETTE_CONFIG_KEY)
        if not raw:
            return None
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        return RenderStyle.from_palette(data)
    except Exception:
        return None


def themed(builder):
    """Apply the active theme's style to a MenuBuilder (fluent helper)."""
    style = menu_style()
    if style is not None:
        builder.style(style)
    return builder
