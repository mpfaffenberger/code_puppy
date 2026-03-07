"""Shared time-parsing utilities for the Code Puppy scheduler."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional


def parse_times_hhmm(
    raw: str,
    on_invalid: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """Parse a comma-separated string of HH:MM times into canonical form.

    Each entry is stripped of whitespace, validated with strptime, and
    normalised via strftime (so ``9:00`` becomes ``09:00``).  Duplicates
    are removed while preserving the first-occurrence order.

    Args:
        raw: Comma-separated time string, e.g. ``"09:00,17:30"``.
        on_invalid: Optional callback invoked with each entry that fails
            ``%H:%M`` parsing.  When *None*, invalid entries are silently
            dropped.

    Returns:
        Ordered, deduplicated list of canonical HH:MM strings.

    Examples:
        >>> parse_times_hhmm("09:00,17:30")
        ['09:00', '17:30']
        >>> parse_times_hhmm("9:0,09:00,bad")  # normalise + dedupe + skip
        ['09:00']
    """
    seen: set[str] = set()
    result: list[str] = []

    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            t = datetime.strptime(entry, "%H:%M")  # noqa: DTZ007
            normalised = t.strftime("%H:%M")
            if normalised not in seen:
                seen.add(normalised)
                result.append(normalised)
        except ValueError:
            if on_invalid is not None:
                on_invalid(entry)

    return result
