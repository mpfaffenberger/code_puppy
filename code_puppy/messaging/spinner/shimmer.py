"""Shimmer / shine animation effect for Rich Text.

Produces a bright highlight wave that sweeps left-to-right across a
string, then pauses briefly off-screen before looping.  Three tiers
of brightness create a soft gradient:

    base → mid → peak → mid → base
         ────shimmer zone────

Usage:
    text_obj = shimmer_text("Rolling back prices...", base="cyan")
"""

import time

from rich.text import Text

# ---- Defaults ---------------------------------------------------------------
_SPEED: float = 15.0  # chars / second
_WIDTH: int = 6  # total shimmer zone width (chars)
_PADDING: int = 12  # extra chars of "off-screen" pause between loops

# Style tiers per base colour
_STYLE_MAP: dict[str, tuple[str, str, str]] = {
    # base colour  →  (base_style,   mid_style,          peak_style)
    "cyan": ("cyan", "bold bright_cyan", "bold white"),
    "yellow": ("yellow", "bold bright_yellow", "bold white"),
    "green": ("green", "bold bright_green", "bold white"),
    "magenta": ("magenta", "bold bright_magenta", "bold white"),
    "blue": ("blue", "bold bright_blue", "bold white"),
}


def shimmer_text(
    message: str,
    base: str = "cyan",
    *,
    speed: float = _SPEED,
    width: int = _WIDTH,
    padding: int = _PADDING,
) -> Text:
    """Return a Rich ``Text`` with a travelling shimmer highlight.

    Parameters
    ----------
    message:
        The plain string to render.
    base:
        Colour family key (see ``_STYLE_MAP``).  Falls back to cyan.
    speed:
        How many character-positions the highlight moves per second.
    width:
        Width of the shimmer zone in characters.
    padding:
        Extra invisible distance the highlight travels off-screen
        before wrapping — creates a natural pause between sweeps.
    """
    text_len = len(message)
    if text_len == 0:
        return Text("")

    if speed <= 0:
        raise ValueError("speed must be > 0")
    if width <= 0:
        raise ValueError("width must be > 0")
    if padding < 0:
        raise ValueError("padding must be >= 0")

    base_style, mid_style, peak_style = _STYLE_MAP.get(base, _STYLE_MAP["cyan"])

    # The highlight travels across [0 … text_len + padding], giving it
    # room to fully exit the visible text before re-entering.
    total_travel = text_len + padding
    half_w = width / 2.0

    # Current centre of the shimmer (wraps continuously)
    centre = (time.monotonic() * speed) % total_travel

    result = Text()
    for i, char in enumerate(message):
        dist = abs(i - centre)
        if dist <= half_w * 0.35:
            style = peak_style
        elif dist <= half_w * 0.7:
            style = mid_style
        else:
            style = base_style
        result.append(char, style=style)

    return result
