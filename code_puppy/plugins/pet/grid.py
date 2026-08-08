"""The 'meet the breeds' list -- one tidy line per good boy.

Renders all 19 dogs as compact one-liners (snoot + name + stars + rarity),
each tinted by its rarity, as a Rich ``Text`` ready for ``emit_info``. Matches
the one-liner the pet shows in the prompt toolbar.
"""

from __future__ import annotations

from rich.text import Text

from code_puppy.plugins.pet.species import DOG_SPECIES, list_species

_FACE = "(\u00b7\u1d25\u00b7)"  # same compact snoot as the toolbar / picker

# Hex twins of species.RARITY_RGB, in Rich-friendly form.
RARITY_HEX = {
    "common": "#999999",
    "uncommon": "#4eba65",
    "rare": "#b1b9f9",
    "epic": "#af87ff",
    "legendary": "#ffc107",
}

_RARITY_ORDER = ["common", "uncommon", "rare", "epic", "legendary"]


def render_grid() -> Text:
    """Build the one-line-per-breed list + rarity legend as a Rich ``Text``."""
    names = list_species()
    out = Text()
    out.append("  The 19 Very Good Boys ", style="bold magenta")
    out.append("(/pet on to adopt)\n\n", style="dim")

    for name in names:
        dog = DOG_SPECIES[name]
        color = RARITY_HEX.get(dog.rarity, "#999999")
        out.append("  ")
        out.append(f"{_FACE} ", style="bold #5fd7ff")  # code-puppy cyan snoot
        out.append(f"{name:<11} ", style=color)
        out.append(f"{dog.stars:<5} ", style=color)
        out.append(dog.rarity, style="dim")
        out.append("\n")

    # ── Rarity legend ──────────────────────────────────────────────────────
    out.append("\n  Rarities  ", style="bold magenta")
    counts = {r: 0 for r in _RARITY_ORDER}
    for n in names:
        counts[DOG_SPECIES[n].rarity] += 1
    bits = []
    for r in _RARITY_ORDER:
        stars = "\u2605" * (_RARITY_ORDER.index(r) + 1)
        bits.append((f"{stars} {r} ({counts[r]})", RARITY_HEX[r]))
    for idx, (label, color) in enumerate(bits):
        out.append(label, style=color)
        if idx < len(bits) - 1:
            out.append("  ", style="dim")
    out.append("\n")
    return out
