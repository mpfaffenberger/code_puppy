"""Live pet, rendered the *right* way: as a prompt_toolkit bottom toolbar.

A background thread scribbling raw ANSI fights prompt_toolkit's renderer and
loses (escapes get echoed as literal text). Instead we let prompt_toolkit draw
the pet itself via ``bottom_toolbar`` + ``refresh_interval`` -- right-aligned so
it lounges in the bottom-right corner, animating and rotating quips while you
think. It gets out of the way the moment the agent starts working.

Styled to match Code Puppy's prompt palette: bright cyan / blue / green.
"""

from __future__ import annotations

import time
from typing import List, Optional, Tuple

from code_puppy.plugins.pet.species import DOG_SPECIES, QUIPS

REFRESH_INTERVAL = 0.8  # seconds; how often prompt_toolkit re-asks for the pet
_QUIP_PERIOD = 5.0  # seconds each quip stays up
_BLINK_PERIOD = 6  # blink roughly every N ticks

# Rarity -> prompt_toolkit style string for the stars (Code Puppy ANSI palette).
_RARITY_STYLE = {
    "common": "fg:ansiwhite",
    "uncommon": "fg:ansigreen",
    "rare": "fg:ansibrightblue",
    "epic": "fg:ansimagenta",
    "legendary": "fg:ansiyellow",
}

# Style classes merged into the prompt's Style so the toolbar bar isn't a
# chunky reverse-video block but blends with Code Puppy's look.
PET_STYLE = {
    "bottom-toolbar": "noreverse bg:default",
    "bottom-toolbar.text": "noreverse bg:default",
}

FormattedText = List[Tuple[str, str]]


def _state():
    """Return (enabled, species, name) without importing config at module load."""
    from code_puppy.plugins.pet import config as pet_config

    return pet_config.is_enabled(), pet_config.get_species(), pet_config.get_name()


def _active_model() -> str:
    try:
        from code_puppy.command_line.model_picker_completion import get_active_model

        return get_active_model() or ""
    except Exception:
        return ""


# A nudge offset so "/pet quip" can force a fresh line immediately.
_quip_offset = 0


def reroll_quip() -> None:
    """Advance to a new quip on the next refresh (used by /pet quip)."""
    global _quip_offset
    _quip_offset += 1


def current_quip() -> str:
    enabled, species, name = _state()
    idx = (int(time.time() // _QUIP_PERIOD) + _quip_offset) % len(QUIPS)
    return QUIPS[idx].replace("{model}", _active_model() or "your model")


def _columns(default: int = 80) -> int:
    try:
        from prompt_toolkit.application import get_app

        return get_app().output.get_size().columns
    except Exception:
        import shutil

        return shutil.get_terminal_size(fallback=(default, 24)).columns


def render_toolbar() -> Optional[FormattedText]:
    """prompt_toolkit ``bottom_toolbar`` callback. Returns tokens or None."""
    enabled, species, name = _state()
    if not enabled:
        return None

    dog = DOG_SPECIES[species]
    tick = int(time.time() / REFRESH_INTERVAL)
    eye = "-" if tick % _BLINK_PERIOD == 0 else "\u00b7"
    snoot = "\u1d25"  # doge nose
    face = f"({eye}{snoot}{eye})"
    model = _active_model()
    quip = current_quip()

    rarity_style = _RARITY_STYLE.get(dog.rarity, "fg:ansiwhite")

    tokens: FormattedText = [
        ("fg:ansibrightcyan", f"{face} "),
        ("bold fg:ansibrightcyan", f"{name} "),
        (rarity_style, f"{dog.stars}  "),
        ("fg:ansibrightblack", "\u2502 "),
        ("italic fg:ansibrightblack", f"\u201c{quip}\u201d "),
    ]
    if model:
        tokens.append(("fg:ansibrightgreen", f"\u00b7 {model}"))

    # Right-align: pad the left so the pet hugs the bottom-right corner.
    visible = sum(len(t) for _, t in tokens)
    pad = max(1, _columns() - visible - 1)
    return [("", " " * pad)] + tokens


def toolbar_kwargs() -> dict:
    """Kwargs to splat into ``prompt_async`` only when a pet is adopted."""
    enabled, _, _ = _state()
    if not enabled:
        return {}
    return {"bottom_toolbar": render_toolbar, "refresh_interval": REFRESH_INTERVAL}
