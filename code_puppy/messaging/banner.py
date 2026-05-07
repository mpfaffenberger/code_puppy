"""Central banner formatting for Code Puppy.

This module is the single source of truth for how banner tags are turned into
Rich markup strings. Every code path that emits a banner -- the message-bus
renderer, the streaming event handler, and the resume-history display --
delegates here so the styling stays consistent and new behavior (timestamps,
trailing newlines, etc.) only has to be implemented in one place.

Behavior is config-driven:

    banner_timestamps_enabled   bool, default False
        When True, every banner is followed by a dim ``[timestamp]`` on the
        same line, just outside the colored block.

    banner_timestamp_format     str, default ``%H:%M:%S``
        ``strftime`` format used for the timestamp.

    banner_newline_after_tag    bool, default False
        When True, a trailing newline is appended to the banner string so the
        banner sits alone on its line and the following content drops to the
        next line. Only the AGENT RESPONSE banner did this historically;
        enabling this option makes every banner behave the same way.

All three options default to the previous behavior so this module is
strictly additive for users who do not opt in.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

# Two well-separated reference datetimes used to validate that a strftime
# format string actually consumes datetime info. Python's strftime is
# permissive -- ``%Q-bogus`` produces ``Q-bogus`` instead of raising -- so
# we detect uselessness by checking that the format yields *different*
# output for two clearly distinct datetimes.
_VALIDATION_DT_A = datetime(2001, 2, 3, 4, 5, 6)
_VALIDATION_DT_B = datetime(2099, 11, 22, 21, 33, 44)


def is_valid_strftime_format(fmt: str) -> bool:
    """Return True if ``fmt`` contains at least one working strftime directive.

    A useful strftime format must produce different output for different
    datetimes. Anything that returns the same string for both reference
    datetimes is either a literal or only contains unrecognized directives
    that Python silently passes through.

    Args:
        fmt: Candidate strftime format string.

    Returns:
        True if the format consumes datetime info, False otherwise.
    """
    if not fmt:
        return False
    try:
        a = _VALIDATION_DT_A.strftime(fmt)
        b = _VALIDATION_DT_B.strftime(fmt)
    except Exception:
        return False
    return a != b


def format_timestamp_suffix(when: Optional[datetime] = None) -> str:
    """Return ``" [TIMESTAMP]"`` (note the leading space) or ``""``.

    Empty string is returned when banner timestamps are disabled in config.

    Args:
        when: Optional datetime to render. Defaults to ``datetime.now()`` for
              live rendering. Timezone-aware inputs (e.g. UTC datetimes from
              pydantic-ai message metadata) are converted to local time before
              formatting so reloaded session timestamps display in the user's
              local timezone.

    Returns:
        ``" [HH:MM:SS]"`` style string ready to concatenate after the banner,
        or ``""`` if timestamps are disabled.
    """
    # Local import to avoid an import cycle (config imports nothing from us
    # but other modules may transitively).
    from code_puppy.config import (
        DEFAULT_BANNER_TIMESTAMP_FORMAT,
        get_banner_timestamp_format,
        get_banner_timestamps_enabled,
    )

    if not get_banner_timestamps_enabled():
        return ""

    if when is None:
        when = datetime.now()
    elif when.tzinfo is not None:
        # Convert aware datetimes to local naive time for strftime.
        when = when.astimezone().replace(tzinfo=None)

    fmt = get_banner_timestamp_format() or DEFAULT_BANNER_TIMESTAMP_FORMAT
    try:
        ts = when.strftime(fmt)
    except Exception:
        ts = when.strftime(DEFAULT_BANNER_TIMESTAMP_FORMAT)
    return f" [{ts}]"


def format_banner(
    banner_name: str,
    text: str,
    *,
    when: Optional[datetime] = None,
) -> str:
    """Build the Rich markup string for a banner tag.

    This is the canonical helper. All banner-emitting code paths should call
    it instead of constructing markup themselves.

    Args:
        banner_name: The banner identifier used to look up the configured
                     background color (e.g. ``"thinking"``, ``"shell_command"``).
        text: The visible label inside the banner (e.g. ``"THINKING"``).
        when: Optional datetime for the timestamp annotation. ``None`` means
              "use the current local time" (for live rendering); pass a stored
              timestamp (e.g. ``msg.timestamp``) when re-rendering history so
              the banner shows when the message *originally* happened.

    Returns:
        A Rich markup string. The banner itself sits inside a single
        ``[bold white on COLOR]`` block; an optional dim ``[HH:MM:SS]``
        annotation follows on the same line; an optional trailing newline
        forces the banner onto its own visual line.
    """
    from code_puppy.config import (
        get_banner_color,
        get_banner_newline_after_tag,
    )

    color = get_banner_color(banner_name)
    banner = f"[bold white on {color}] {text} [/bold white on {color}]"

    suffix = format_timestamp_suffix(when)
    if suffix:
        banner += f"[dim]{suffix}[/dim]"

    if get_banner_newline_after_tag():
        banner += "\n"

    return banner
