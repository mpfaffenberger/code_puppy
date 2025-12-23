"""Pre-built color themes for Code Puppy's messaging system.

This module provides a collection of carefully crafted color themes for
Code Puppy's terminal output. Each theme defines colors for all 9 message
types (error, warning, success, info, debug, tool output, agent reasoning,
agent response, and system messages).

Example:
    >>> from code_puppy.themes.presets import get_preset_theme, list_preset_themes
    >>> list_preset_themes()
    ['default', 'midnight', 'forest', 'sunset', 'ocean', ...]
    >>> theme = get_preset_theme("midnight")
    >>> theme.error_color
    'bright_red'
"""

from __future__ import annotations

from typing import Dict, List

from code_puppy.themes.theme import Theme


# =============================================================================
# Pre-built Themes
# =============================================================================

# Theme 1: Default - Current Code Puppy colors (baseline)
# This is the original Code Puppy theme that users are familiar with
THEME_DEFAULT = Theme(
    error_color="bold red",
    warning_color="yellow",
    success_color="green",
    info_color="white",
    debug_color="dim",
    tool_output_color="cyan",
    agent_reasoning_color="magenta",
    agent_response_color="blue",
    system_color="bright_black",
    _name="default",
    _description="The original Code Puppy theme - familiar and balanced",
    _author="Code Puppy Team",
    _version="1.0.0",
    _tags=["classic", "balanced"],
)


# Theme 2: Midnight - Deep blues and purples (mysterious, elegant)
# Perfect for late-night coding sessions with a sophisticated dark palette
THEME_MIDNIGHT = Theme(
    error_color="bright_red",
    warning_color="bright_yellow",
    success_color="bright_green",
    info_color="bright_blue",
    debug_color="dim",
    tool_output_color="bright_cyan",
    agent_reasoning_color="bright_magenta",
    agent_response_color="blue",
    system_color="bright_black",
    _name="midnight",
    _description="Deep blues and purples - mysterious and elegant for night coding",
    _author="Code Puppy Team",
    _version="1.0.0",
    _tags=["dark", "elegant", "night"],
)


# Theme 3: Forest - Greens and earth tones (nature-inspired)
# A calming, nature-inspired palette that's easy on the eyes
THEME_FOREST = Theme(
    error_color="red",
    warning_color="yellow",
    success_color="green",
    info_color="bright_green",
    debug_color="dim",
    tool_output_color="cyan",
    agent_reasoning_color="green",
    agent_response_color="blue",
    system_color="black",
    _name="forest",
    _description="Greens and earth tones - nature-inspired and calming",
    _author="Code Puppy Team",
    _version="1.0.0",
    _tags=["nature", "green", "calm"],
)


# Theme 4: Sunset - Warm oranges, reds, and yellows (warm, energetic)
# Warm and energetic colors that feel like a beautiful sunset
THEME_SUNSET = Theme(
    error_color="bright_red",
    warning_color="yellow",
    success_color="bright_yellow",
    info_color="bright_yellow",
    debug_color="dim",
    tool_output_color="bright_red",
    agent_reasoning_color="yellow",
    agent_response_color="red",
    system_color="bright_black",
    _name="sunset",
    _description="Warm oranges, reds, and yellows - energetic and vibrant",
    _author="Code Puppy Team",
    _version="1.0.0",
    _tags=["warm", "energetic", "vibrant"],
)


# Theme 5: Ocean - Cool cyans, teals, and blues (calm, refreshing)
# Refreshing cool colors that evoke ocean waves and clear skies
THEME_OCEAN = Theme(
    error_color="bright_red",
    warning_color="yellow",
    success_color="cyan",
    info_color="bright_cyan",
    debug_color="dim",
    tool_output_color="blue",
    agent_reasoning_color="cyan",
    agent_response_color="bright_blue",
    system_color="bright_black",
    _name="ocean",
    _description="Cool cyans, teals, and blues - refreshing and calm",
    _author="Code Puppy Team",
    _version="1.0.0",
    _tags=["cool", "refreshing", "blue"],
)


# Theme 6: Retro Terminal - Classic amber/green monochrome (vintage tech)
# Nostalgic amber/green terminal colors reminiscent of classic computing
THEME_RETRO_TERMINAL = Theme(
    error_color="red",
    warning_color="yellow",
    success_color="green",
    info_color="yellow",
    debug_color="dim",
    tool_output_color="green",
    agent_reasoning_color="yellow",
    agent_response_color="green",
    system_color="yellow",
    _name="retro-terminal",
    _description="Classic amber/green monochrome - nostalgic vintage tech",
    _author="Code Puppy Team",
    _version="1.0.0",
    _tags=["vintage", "monochrome", "amber"],
)


# Theme 7: Neon Cyberpunk - Bright pinks, cyans, purples (futuristic, bold)
# Bold, vibrant neon colors for a futuristic cyberpunk aesthetic
THEME_NEON_CYBERPUNK = Theme(
    error_color="bold bright_red",
    warning_color="bold bright_yellow",
    success_color="bold bright_green",
    info_color="bold bright_cyan",
    debug_color="dim",
    tool_output_color="bold bright_magenta",
    agent_reasoning_color="bold bright_magenta",
    agent_response_color="bold bright_cyan",
    system_color="bold bright_white",
    _name="neon-cyberpunk",
    _description="Bright pinks, cyans, and purples - bold futuristic aesthetic",
    _author="Code Puppy Team",
    _version="1.0.0",
    _tags=["futuristic", "bold", "bright"],
)


# Theme 8: Minimalist - Clean grays and whites (modern, clean)
# Clean, professional grayscale palette for a modern look
THEME_MINIMALIST = Theme(
    error_color="red",
    warning_color="yellow",
    success_color="green",
    info_color="white",
    debug_color="dim",
    tool_output_color="bright_black",
    agent_reasoning_color="bright_black",
    agent_response_color="white",
    system_color="bright_black",
    _name="minimalist",
    _description="Clean grays and whites - modern and professional",
    _author="Code Puppy Team",
    _version="1.0.0",
    _tags=["clean", "modern", "grayscale"],
)


# Theme 9: Pastel - Soft, muted colors (gentle, pleasant)
# Soft, muted colors for a gentle and pleasant coding experience
THEME_PASTEL = Theme(
    error_color="dim red",
    warning_color="dim yellow",
    success_color="dim green",
    info_color="white",
    debug_color="dim",
    tool_output_color="dim cyan",
    agent_reasoning_color="dim magenta",
    agent_response_color="dim blue",
    system_color="bright_black",
    _name="pastel",
    _description="Soft muted colors - gentle and pleasant on the eyes",
    _author="Code Puppy Team",
    _version="1.0.0",
    _tags=["soft", "gentle", "muted"],
)


# Theme 10: Matrix - Classic hacker green (iconic, techy)
# The iconic green-on-black Matrix aesthetic for true hackers
THEME_MATRIX = Theme(
    error_color="bright_red",
    warning_color="bright_yellow",
    success_color="bright_green",
    info_color="green",
    debug_color="dim",
    tool_output_color="green",
    agent_reasoning_color="bright_green",
    agent_response_color="green",
    system_color="bright_black",
    _name="matrix",
    _description="Classic hacker green - iconic techy terminal look",
    _author="Code Puppy Team",
    _version="1.0.0",
    _tags=["hacker", "green", "tech"],
)


# =============================================================================
# Preset Theme Registry
# =============================================================================

PRESET_THEMES: Dict[str, Theme] = {
    "default": THEME_DEFAULT,
    "midnight": THEME_MIDNIGHT,
    "forest": THEME_FOREST,
    "sunset": THEME_SUNSET,
    "ocean": THEME_OCEAN,
    "retro-terminal": THEME_RETRO_TERMINAL,
    "neon-cyberpunk": THEME_NEON_CYBERPUNK,
    "minimalist": THEME_MINIMALIST,
    "pastel": THEME_PASTEL,
    "matrix": THEME_MATRIX,
}

# Descriptions for each preset theme
PRESET_THEME_DESCRIPTIONS: Dict[str, str] = {
    "default": "The original Code Puppy theme - familiar and balanced",
    "midnight": "Deep blues and purples - mysterious and elegant for night coding",
    "forest": "Greens and earth tones - nature-inspired and calming",
    "sunset": "Warm oranges, reds, and yellows - energetic and vibrant",
    "ocean": "Cool cyans, teals, and blues - refreshing and calm",
    "retro-terminal": "Classic amber/green monochrome - nostalgic vintage tech",
    "neon-cyberpunk": "Bright pinks, cyans, and purples - bold futuristic aesthetic",
    "minimalist": "Clean grays and whites - modern and professional",
    "pastel": "Soft muted colors - gentle and pleasant on the eyes",
    "matrix": "Classic hacker green - iconic techy terminal look",
}


# =============================================================================
# Helper Functions
# =============================================================================


def get_preset_theme(name: str) -> Theme:
    """Get a preset theme by name.

    Args:
        name: Name of the preset theme (case-insensitive)

    Returns:
        The Theme instance for the requested preset

    Raises:
        KeyError: If the preset name doesn't exist

    Example:
        >>> from code_puppy.themes.presets import get_preset_theme
        >>> theme = get_preset_theme("midnight")
        >>> print(theme.error_color)
        bright_red
    """
    normalized_name = name.lower().strip()
    if normalized_name not in PRESET_THEMES:
        available = ", ".join(sorted(PRESET_THEMES.keys()))
        raise KeyError(
            f"Preset theme '{name}' not found. Available themes: {available}"
        )
    return PRESET_THEMES[normalized_name]


def list_preset_themes() -> List[str]:
    """List all available preset theme names.

    Returns:
        Sorted list of preset theme names

    Example:
        >>> from code_puppy.themes.presets import list_preset_themes
        >>> list_preset_themes()
        ['default', 'forest', 'matrix', 'midnight', 'minimalist', ...]
    """
    return sorted(PRESET_THEMES.keys())


def get_preset_theme_description(name: str) -> str:
    """Get the description for a preset theme.

    Args:
        name: Name of the preset theme (case-insensitive)

    Returns:
        Description string for the theme

    Raises:
        KeyError: If the preset name doesn't exist

    Example:
        >>> from code_puppy.themes.presets import get_preset_theme_description
        >>> get_preset_theme_description("midnight")
        'Deep blues and purples - mysterious and elegant for night coding'
    """
    normalized_name = name.lower().strip()
    if normalized_name not in PRESET_THEME_DESCRIPTIONS:
        available = ", ".join(sorted(PRESET_THEME_DESCRIPTIONS.keys()))
        raise KeyError(
            f"Preset theme '{name}' not found. Available themes: {available}"
        )
    return PRESET_THEME_DESCRIPTIONS[normalized_name]


def list_preset_themes_with_descriptions() -> Dict[str, str]:
    """List all preset themes with their descriptions.

    Returns:
        Dictionary mapping theme names to their descriptions

    Example:
        >>> from code_puppy.themes.presets import list_preset_themes_with_descriptions
        >>> themes = list_preset_themes_with_descriptions()
        >>> for name, desc in themes.items():
        ...     print(f"{name}: {desc}")
    """
    return dict(sorted(PRESET_THEME_DESCRIPTIONS.items()))
