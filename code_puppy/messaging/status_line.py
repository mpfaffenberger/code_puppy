"""Shared status-row styling: reserve room for a colored pending text."""

import re

from code_puppy.i18n import t
from rich.cells import cell_len
from .bar_rendering import clip_cells, sanitize


def _render_body(body: str, width: int) -> str:
    """Accent the literal tool name, never interpret model-supplied ANSI."""
    safe = sanitize(body)
    template = sanitize(t("stream.activity.calling", tool="__TOOL__"))
    pattern = re.escape(template).replace("__TOOL__", r"(?P<tool>.+)")
    match = re.search(r"(?:^|\| )" + pattern + r"$", safe)
    spans = []
    if match:
        spans.append((*match.span("tool"), "35"))
    progress = sanitize(
        t("stream.progress", count="__COUNT__", activity="__ACTIVITY__")
    )
    count_pattern = re.escape(progress).replace("__COUNT__", r"(?P<count>[0-9][0-9,]*)")
    count_pattern = count_pattern.replace("__ACTIVITY__", r".*")
    count_match = re.search(r"(?:^|\| )" + count_pattern + r"$", safe)
    if count_match:
        # ANSI blue is the theme-mapped agent-name accent, not fixed RGB.
        spans.append((*count_match.span("count"), "1;34"))
    text = clip_cells(safe, width)
    output = ["\x1b[2m"]
    cursor = 0
    for start, end, color in sorted(spans):
        if start >= len(text):
            break
        end = min(end, len(text))
        output.extend(
            (text[cursor:start], f"\x1b[22;{color}m", text[start:end], "\x1b[22;39;2m")
        )
        cursor = end
    output.extend((text[cursor:], "\x1b[22m"))
    return "".join(output)


def render_status_line(body: str, suffix: str, width: int) -> str:
    """Clip status chrome before the suffix, not the other way around.

    The queue plugin owns the suffix's text and lifecycle. Both bar layouts
    share this painter so pending work stays visible even on narrow terminals.
    Only generated styles may emit escape sequences; input text is sanitized.
    """
    suffix = sanitize(suffix).strip()
    if not suffix:
        return _render_body(body, width)
    pending = clip_cells(suffix, max(0, width))
    remaining = max(0, width - cell_len(pending) - 1)
    text = clip_cells(sanitize(body), remaining)
    prefix = _render_body(body, remaining) + " " if text else ""
    # Foreground color only: no bold, reverse video, or background badge.
    return f"{prefix}\x1b[0;35m{pending}\x1b[0m"
