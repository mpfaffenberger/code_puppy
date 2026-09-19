"""Shared status-row styling: reserve room for a prominent pending badge."""

from rich.cells import cell_len
from .bar_rendering import clip_cells, sanitize


def render_status_line(body: str, suffix: str, width: int) -> str:
    """Clip status chrome before the suffix, not the other way around.

    The queue plugin owns the suffix's text and lifecycle. Both bar layouts
    share this painter so pending work stays visible even on narrow terminals.
    Only generated styles may emit escape sequences; input text is sanitized.
    """
    suffix = sanitize(suffix).strip()
    if not suffix:
        return f"\x1b[2m{clip_cells(sanitize(body), width)}\x1b[22m"
    badge = clip_cells(f" {suffix} ", max(0, width))
    remaining = max(0, width - cell_len(badge) - 1)
    text = clip_cells(sanitize(body), remaining)
    prefix = f"\x1b[2m{text}\x1b[22m " if text else ""
    # ANSI palette slot 5 follows the active theme. Reset intensity before
    # drawing the badge so a surrounding dim style cannot mute it.
    return f"{prefix}\x1b[22;1;7;35m{badge}\x1b[0m"
