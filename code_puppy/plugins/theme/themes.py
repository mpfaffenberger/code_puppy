"""Theme definitions and application logic.

Pure module: no I/O beyond reading/writing config via code_puppy.config and
content_styles. Testable in isolation. Zen: simple is better than complex.
"""

from __future__ import annotations

import random
from itertools import cycle
from typing import Callable

from code_puppy.command_line.colors_menu import BANNER_COLORS, BANNER_DISPLAY_INFO
from code_puppy.config import set_banner_color

from . import bundled_palettes as bp
from . import content_styles as cs
from . import rich_themes as rt

# Palette = the Rich color values from /colors (deduped, sorted for determinism)
PALETTE: list[str] = sorted(set(BANNER_COLORS.values()))
BANNER_KEYS: list[str] = list(BANNER_DISPLAY_INFO.keys())


# A smaller palette suited to *foreground* text (the full PALETTE includes some
# very dark colors that are unreadable as text on a dark terminal, and a
# couple of names like ``cyan4`` / ``dark_orchid`` that Rich can't even parse
# as standalone Colors despite working as background tags).
def _parseable(name: str) -> bool:
    from rich.color import Color

    try:
        Color.parse(name)
        return True
    except Exception:
        return False


TEXT_PALETTE: list[str] = sorted(
    {
        c
        for c in PALETTE
        if _parseable(c)
        and not any(bad in c for bad in ("black", "navy_blue", "dark_red", "grey0"))
    }
)

# --- Curated themes ---------------------------------------------------------
# Each curated theme is just an ordered list of palette colors; we cycle
# through them to color every banner. Keep it small + opinionated.
CURATED_THEMES: dict[str, dict] = {
    "ocean": {
        "icon": "🌊",
        "label": "Ocean",
        "blurb": "cool blues, cyans & teals",
        "colors": [
            "deep_sky_blue4",
            "cyan4",
            "dodger_blue3",
            "dark_turquoise",
            "steel_blue",
            "blue",
            "navy_blue",
            "dark_cyan",
            "aquamarine1",
        ],
        "content_styles": {
            "info": "cyan",
            "warning": "yellow",
            "success": "bright_cyan",
            "error": "bold red",
            "debug": "dim cyan",
            "diff_add": "bright_cyan",
            "diff_remove": "red",
            "diff_context": "dim blue",
        },
        "color_remap": rt.make_remap(
            cyan="deep_sky_blue4",
            blue="dodger_blue3",
            magenta="dark_turquoise",
            bright_cyan="aquamarine1",
            bright_blue="steel_blue",
            bright_magenta="dark_cyan",
        ),
        "terminal_palette": bp.OCEAN,
    },
    "forest": {
        "icon": "🌲",
        "label": "Forest",
        "blurb": "earthy greens & olives",
        "colors": [
            "green4",
            "dark_green",
            "dark_sea_green4",
            "spring_green4",
            "chartreuse4",
            "dark_olive_green3",
            "dark_goldenrod",
        ],
        "content_styles": {
            "info": "green",
            "warning": "dark_goldenrod",
            "success": "bright_green",
            "error": "bold red",
            "debug": "dim green",
            "diff_add": "bright_green",
            "diff_remove": "red",
            "diff_context": "dim green",
        },
        "color_remap": rt.make_remap(
            cyan="spring_green4",
            blue="green4",
            magenta="dark_sea_green4",
            bright_cyan="chartreuse4",
            bright_blue="dark_green",
            bright_magenta="dark_olive_green3",
        ),
        "terminal_palette": bp.FOREST,
    },
    "sunset": {
        "icon": "🌅",
        "label": "Sunset",
        "blurb": "warm reds, oranges & gold",
        "colors": [
            "orange_red1",
            "dark_orange3",
            "gold3",
            "red3",
            "indian_red",
            "dark_red",
            "hot_pink3",
        ],
        "content_styles": {
            "info": "gold3",
            "warning": "dark_orange3",
            "success": "orange_red1",
            "error": "bold red",
            "debug": "dim yellow",
            "diff_add": "gold3",
            "diff_remove": "red3",
            "diff_context": "dim yellow",
        },
        "color_remap": rt.make_remap(
            cyan="gold3",
            blue="orange_red1",
            magenta="hot_pink3",
            bright_cyan="dark_orange3",
            bright_blue="indian_red",
            bright_magenta="hot_pink3",
        ),
        "terminal_palette": bp.SUNSET,
    },
    "vaporwave": {
        "icon": "🪩",
        "label": "Vaporwave",
        "blurb": "neon pinks & purples",
        "colors": [
            "hot_pink3",
            "dark_magenta",
            "purple",
            "dark_violet",
            "medium_purple4",
            "dark_orchid",
            "deep_pink4",
            "pale_violet_red1",
        ],
        "content_styles": {
            "info": "magenta",
            "warning": "hot_pink3",
            "success": "bright_magenta",
            "error": "bold red",
            "debug": "dim magenta",
            "diff_add": "bright_magenta",
            "diff_remove": "red",
            "diff_context": "dim magenta",
        },
        "color_remap": rt.make_remap(
            cyan="hot_pink3",
            blue="purple",
            magenta="dark_magenta",
            bright_cyan="pale_violet_red1",
            bright_blue="dark_violet",
            bright_magenta="medium_orchid",
        ),
        "terminal_palette": bp.VAPORWAVE,
    },
    # --- Mure-port "palette-first" themes ---------------------------------
    # These rely primarily on the OSC ANSI palette swap (slot 6 = cyan, etc.)
    # so Rich's own [cyan]/[blue]/[magenta] tags automatically render in the
    # new palette. Rich-level color_remap stays empty for these.
    "catppuccin-mocha": {
        "icon": "🐱",
        "label": "Catppuccin Mocha",
        "blurb": "soothing pastel dark",
        "colors": [
            "cyan",
            "magenta",
            "blue",
            "green",
            "yellow",
            "red",
            "bright_cyan",
            "bright_magenta",
        ],
        "content_styles": {
            "info": "cyan",
            "warning": "yellow",
            "success": "green",
            "error": "bold red",
            "debug": "dim white",
            "diff_add": "green",
            "diff_remove": "red",
            "diff_context": "dim white",
        },
        "color_remap": {},
        "terminal_palette": bp.CATPPUCCIN_MOCHA,
    },
    "catppuccin-latte": {
        "icon": "☕",
        "label": "Catppuccin Latte",
        "blurb": "soothing pastel light",
        "colors": [
            "blue",
            "magenta",
            "green",
            "yellow",
            "cyan",
            "red",
            "bright_blue",
            "bright_magenta",
        ],
        "content_styles": {
            "info": "blue",
            "warning": "yellow",
            "success": "green",
            "error": "bold red",
            "debug": "dim white",
            "diff_add": "green",
            "diff_remove": "red",
            "diff_context": "dim white",
        },
        "color_remap": {},
        "terminal_palette": bp.CATPPUCCIN_LATTE,
    },
    "tokyo-night": {
        "icon": "🌃",
        "label": "Tokyo Night",
        "blurb": "neon-on-navy night",
        "colors": [
            "blue",
            "cyan",
            "magenta",
            "green",
            "yellow",
            "red",
            "bright_blue",
            "bright_cyan",
        ],
        "content_styles": {
            "info": "cyan",
            "warning": "yellow",
            "success": "green",
            "error": "bold red",
            "debug": "dim white",
            "diff_add": "green",
            "diff_remove": "red",
            "diff_context": "dim white",
        },
        "color_remap": {},
        "terminal_palette": bp.TOKYO_NIGHT,
    },
    "gruvbox-dark": {
        "icon": "🍂",
        "label": "Gruvbox Dark",
        "blurb": "retro warm earth",
        "colors": [
            "yellow",
            "red",
            "green",
            "cyan",
            "magenta",
            "blue",
            "bright_yellow",
            "bright_red",
        ],
        "content_styles": {
            "info": "yellow",
            "warning": "bright_yellow",
            "success": "green",
            "error": "bold red",
            "debug": "dim white",
            "diff_add": "green",
            "diff_remove": "red",
            "diff_context": "dim white",
        },
        "color_remap": {},
        "terminal_palette": bp.GRUVBOX_DARK,
    },
    # --- Light-mode themes ------------------------------------------------
    # For light themes, `debug` uses dim *black* (not white) so dim text stays
    # visible against a light background.
    "solarized-light": {
        "icon": "☀️",
        "label": "Solarized Light",
        "blurb": "classic warm beige with calm accents",
        "colors": [
            "blue",
            "magenta",
            "green",
            "yellow",
            "cyan",
            "red",
            "bright_blue",
            "bright_magenta",
        ],
        "content_styles": {
            "info": "blue",
            "warning": "yellow",
            "success": "green",
            "error": "bold red",
            "debug": "dim black",
            "diff_add": "green",
            "diff_remove": "red",
            "diff_context": "dim black",
        },
        "color_remap": {},
        "terminal_palette": bp.SOLARIZED_LIGHT,
    },
    "github-light": {
        "icon": "📄",
        "label": "GitHub Light",
        "blurb": "crisp white, familiar code colors",
        "colors": [
            "blue",
            "magenta",
            "green",
            "yellow",
            "cyan",
            "red",
            "bright_blue",
            "bright_magenta",
        ],
        "content_styles": {
            "info": "blue",
            "warning": "yellow",
            "success": "green",
            "error": "bold red",
            "debug": "dim black",
            "diff_add": "green",
            "diff_remove": "red",
            "diff_context": "dim black",
        },
        "color_remap": {},
        "terminal_palette": bp.GITHUB_LIGHT,
    },
    "rose-pine-dawn": {
        "icon": "🌸",
        "label": "Rose Pine Dawn",
        "blurb": "soft pastel rose light",
        "colors": [
            "magenta",
            "blue",
            "cyan",
            "yellow",
            "green",
            "red",
            "bright_magenta",
            "bright_blue",
        ],
        "content_styles": {
            "info": "blue",
            "warning": "yellow",
            "success": "green",
            "error": "bold red",
            "debug": "dim black",
            "diff_add": "green",
            "diff_remove": "red",
            "diff_context": "dim black",
        },
        "color_remap": {},
        "terminal_palette": bp.ROSE_PINE_DAWN,
    },
}

# The 5th option: surprise me — special case, regenerated each preview/apply.
SURPRISE = {
    "icon": "🎲",
    "label": "Surprise Me",
    "blurb": "a fresh random remix every time",
    "colors": None,
    "content_styles": None,  # generated dynamically
    "color_remap": None,  # generated dynamically
    "terminal_palette": None,  # randomized at apply time
}

# The 6th option: restore Code Puppy defaults (banners + content).
DEFAULT = {
    "icon": "🔄",
    "label": "Restore Defaults",
    "blurb": "back to Code Puppy factory colors",
    "colors": None,
    "content_styles": None,  # handled specially
    "color_remap": None,  # handled specially (empty)
    "terminal_palette": None,  # handled specially (OSC reset)
}

# Ordered menu: 4 originals, 2 dark ports, 2 light themes, surprise, default.
# (Catppuccin Mocha, Solarized Light, Rose Pine Dawn removed by request -
# still resolvable by name as aliases for power users.)
MENU: list[tuple[str, dict]] = [
    ("ocean", CURATED_THEMES["ocean"]),
    ("forest", CURATED_THEMES["forest"]),
    ("sunset", CURATED_THEMES["sunset"]),
    ("vaporwave", CURATED_THEMES["vaporwave"]),
    ("catppuccin-latte", CURATED_THEMES["catppuccin-latte"]),
    ("github-light", CURATED_THEMES["github-light"]),
    ("surprise", SURPRISE),
    ("default", DEFAULT),
]
MENU_BY_NAME: dict[str, dict] = {name: theme for name, theme in MENU}
MENU_BY_INDEX: dict[str, str] = {str(i + 1): name for i, (name, _) in enumerate(MENU)}

# Friendly aliases (no spaces, alt names).
MENU_BY_NAME["random"] = SURPRISE
MENU_BY_NAME["reset"] = DEFAULT
MENU_BY_NAME["defaults"] = DEFAULT
MENU_BY_NAME["mocha"] = CURATED_THEMES["catppuccin-mocha"]
MENU_BY_NAME["latte"] = CURATED_THEMES["catppuccin-latte"]
MENU_BY_NAME["tokyo"] = CURATED_THEMES["tokyo-night"]
MENU_BY_NAME["gruvbox"] = CURATED_THEMES["gruvbox-dark"]
MENU_BY_NAME["solarized"] = CURATED_THEMES["solarized-light"]
MENU_BY_NAME["github"] = CURATED_THEMES["github-light"]
MENU_BY_NAME["rose-pine"] = CURATED_THEMES["rose-pine-dawn"]
MENU_BY_NAME["dawn"] = CURATED_THEMES["rose-pine-dawn"]


def colors_for(theme_name: str, rng: random.Random | None = None) -> dict[str, str]:
    """Build a {banner: color} mapping for the named theme.

    For curated themes, cycles through the theme palette deterministically.
    For ``surprise``, samples randomly from the full PALETTE.
    For ``default``, returns the Code Puppy factory banner colors.
    """
    if theme_name not in MENU_BY_NAME:
        raise KeyError(f"Unknown theme: {theme_name!r}")

    if theme_name == "default":
        from code_puppy.config import DEFAULT_BANNER_COLORS

        return dict(DEFAULT_BANNER_COLORS)

    if theme_name in ("surprise", "random"):
        chooser = rng.choice if rng is not None else random.choice
        return {banner: chooser(PALETTE) for banner in BANNER_KEYS}

    palette = cycle(MENU_BY_NAME[theme_name]["colors"])
    return {banner: next(palette) for banner in BANNER_KEYS}


def content_styles_for(
    theme_name: str, rng: random.Random | None = None
) -> dict[str, str]:
    """Build a {content_key: style} mapping for the named theme.

    For curated themes, returns the hand-picked palette.
    For ``surprise``, generates a random remix (error stays red — it's a UX
    contract that errors look angry).
    For ``default``, returns the factory defaults.
    """
    if theme_name not in MENU_BY_NAME:
        raise KeyError(f"Unknown theme: {theme_name!r}")

    if theme_name == "default":
        return dict(cs.DEFAULT_CONTENT_STYLES)

    if theme_name in ("surprise", "random"):
        chooser = rng.choice if rng is not None else random.choice
        mapping = {key: chooser(TEXT_PALETTE) for key in cs.CONTENT_KEYS}
        # Errors should always be visually distinct + alarming.
        mapping["error"] = "bold red"
        return mapping

    return dict(MENU_BY_NAME[theme_name]["content_styles"])


def color_remap_for(
    theme_name: str, rng: random.Random | None = None
) -> dict[str, str]:
    """Build a Rich color remap dict for the named theme (Level 2 theming).

    For curated themes, returns the hand-picked remap.
    For ``surprise``, picks random replacements (semantic colors untouched).
    For ``default``, returns an empty dict (= no remap, restore).
    """
    if theme_name not in MENU_BY_NAME:
        raise KeyError(f"Unknown theme: {theme_name!r}")

    if theme_name == "default":
        return {}

    if theme_name in ("surprise", "random"):
        chooser = rng.choice if rng is not None else random.choice
        return rt.make_remap(
            cyan=chooser(TEXT_PALETTE),
            blue=chooser(TEXT_PALETTE),
            magenta=chooser(TEXT_PALETTE),
            bright_cyan=chooser(TEXT_PALETTE),
            bright_blue=chooser(TEXT_PALETTE),
            bright_magenta=chooser(TEXT_PALETTE),
        )

    return dict(MENU_BY_NAME[theme_name]["color_remap"])


def terminal_palette_for(
    theme_name: str, rng: random.Random | None = None
) -> dict | None:
    """Build an OSC terminal palette for the named theme.

    Returns None if the theme has no terminal palette (rare). For
    ``default``, returns None (caller is expected to call osc_palette.reset).
    For ``surprise``, generates a random bg/fg pair (no full ANSI swap).
    """
    if theme_name not in MENU_BY_NAME:
        raise KeyError(f"Unknown theme: {theme_name!r}")

    if theme_name == "default":
        return None

    if theme_name in ("surprise", "random"):
        chooser = rng.choice if rng is not None else random.choice
        # Random bg/fg pair with enough contrast to read text.
        LIGHT_BGS = [
            "#fdf6e3",
            "#ffffff",
            "#faf4ed",
            "#eff1f5",
            "#f5f5f5",
            "#f8f0e3",
        ]
        DARK_FGS = [
            "#657b83",
            "#24292e",
            "#575279",
            "#4c4f69",
            "#2d2d2d",
            "#3c3c3c",
        ]
        DARK_BGS = [
            "#0a1929",
            "#1a2310",
            "#2d1b0e",
            "#16002a",
            "#1e1e2e",
            "#1a1b26",
            "#282828",
            "#0e0e2c",
        ]
        LIGHT_FGS = [
            "#d6eaf8",
            "#e3eecc",
            "#ffe4cc",
            "#ffe0ff",
            "#cdd6f4",
            "#c0caf5",
            "#ebdbb2",
            "#f5f5f5",
        ]
        # 30% chance of a light surprise, 70% dark (most users prefer dark TUI).
        if (rng or random).random() < 0.3:
            return {"bg": chooser(LIGHT_BGS), "fg": chooser(DARK_FGS)}
        return {"bg": chooser(DARK_BGS), "fg": chooser(LIGHT_FGS)}

    return MENU_BY_NAME[theme_name].get("terminal_palette")


def apply(
    mapping: dict[str, str], setter: Callable[[str, str], None] = set_banner_color
) -> None:
    """Persist a banner→color mapping via the config layer.

    ``setter`` is injectable for tests.
    """
    for banner, color in mapping.items():
        setter(banner, color)


def resolve_theme_arg(arg: str) -> str | None:
    """Resolve '1'..'6' or a theme name to a canonical theme key.

    Returns None if the argument is not recognized.
    """
    if arg in MENU_BY_INDEX:
        return MENU_BY_INDEX[arg]
    if arg in MENU_BY_NAME:
        # Normalize aliases to canonical keys.
        if arg == "random":
            return "surprise"
        if arg in ("reset", "defaults"):
            return "default"
        return arg
    return None
