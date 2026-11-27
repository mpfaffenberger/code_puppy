"""Code Puppy's default colours: the 0.0.x hues, toned to read on any terminal.

0.0.x painted with the terminal's named colours: a ``bright_blue`` accent,
``cyan`` info, ``green`` success, ``yellow`` warnings, ``red`` errors and a
blue → cyan → green banner. Named brights vanish on a light background
(``bright_cyan`` on white is 1.25:1), so each hue here is a mid-tone that
keeps at least 3.5:1 contrast on both a white and a near-black background.

pax's default theme speaks in Pydantic brand names (``LITHIUM``,
``CALCIUM``...). :data:`SHADES` says which puppy colour stands in for each;
``distribution`` installs them. Stdlib-only: the startup splash paints with
them before the runtime is imported.
"""

from __future__ import annotations

from typing import NamedTuple


class Shade(NamedTuple):
    colour: str
    """Truecolor hex, used as is by the default theme."""
    slot: int
    """The ANSI slot it maps to when a Termflow palette is selected."""
    sgr: int
    """The 16-colour SGR code for terminals without truecolor."""


BLUE = "#0087FF"
CYAN = "#0097A7"
GREEN = "#3A9A3A"
YELLOW = "#A88400"
RED = "#E5484D"
PURPLE = "#875FD7"
ORCHID = "#CC55CC"
GREY = "#808080"
SLATE = "#8080A8"
CHARCOAL = "#3A3A3A"
GRAPHITE = "#5F5F5F"

TEXT = (BLUE, CYAN, GREEN, YELLOW, RED, PURPLE, ORCHID, GREY, SLATE)
"""Colours painted as text, which must read on light and dark backgrounds."""

SHADES = {
    "LITHIUM": Shade(BLUE, 12, 94),
    "CALCIUM": Shade(RED, 1, 31),
    "PURPLE": Shade(PURPLE, 5, 35),
    "AQUA": Shade(GREEN, 2, 32),
    # Plain text in menus: 39 is the terminal's own foreground, never white on white.
    "SUGAR": Shade(SLATE, 7, 39),
    "LIGHT_PURPLE": Shade(ORCHID, 13, 95),
    "DARK_PURPLE": Shade(CHARCOAL, 0, 90),
    "GREY": Shade(GREY, 8, 90),
    "ELEMENT_PURPLE": Shade(GRAPHITE, 8, 90),
    "AI_CYAN": Shade(CYAN, 6, 36),
    "AI_YELLOW": Shade(YELLOW, 3, 33),
}
"""pax theme name → the puppy colour that replaces it."""

SLOTS = {shade.colour: shade.slot for shade in SHADES.values()}
"""Each colour's ANSI slot, for a Termflow palette."""
BASIC = {shade.colour: shade.sgr for shade in SHADES.values()}
"""Each colour's 16-colour SGR code, for terminals without truecolor."""

ROLES = {
    "ACCENT": f"bold {BLUE}",
    "INFO": CYAN,
    "SUCCESS": GREEN,
    "WARNING": YELLOW,
    "ERROR": RED,
    "MUTED": GREY,
    "THINKING": PURPLE,
    "LOGO": f"bold {BLUE}",
    # 0.0.x's banner gradient, top to bottom.
    "BANNER": (BLUE, CYAN, GREEN),
    # 0.0.x's diff backgrounds; the diff renderer paints its own text on them.
    "DIFF_ADDITION": "#0B1F0B",
    "DIFF_DELETION": "#390E1A",
}
"""pax theme roles, as 0.0.x coloured them."""
