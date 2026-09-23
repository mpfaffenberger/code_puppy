"""Resolve the agent accent without ANSI bold or Rich name-remap ambiguity."""

import json
import re


def agent_accent() -> str:
    """Use the active palette's bright-blue agent slot, with an ANSI fallback."""
    from code_puppy.config import get_value

    try:
        palette = json.loads(get_value("osc_palette_json") or "{}")
        color = palette["ansi"][12]
        if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            return color
    except (ValueError, TypeError, KeyError, IndexError):
        pass
    return "bright_blue"


def agent_accent_sgr() -> str:
    color = agent_accent()
    if color.startswith("#"):
        channels = [str(int(color[index : index + 2], 16)) for index in (1, 3, 5)]
        return "38;2;" + ";".join(channels)
    return "94"
