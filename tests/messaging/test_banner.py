"""Tests for the central banner formatter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from code_puppy.messaging import banner


# ---------------------------------------------------------------------------
# is_valid_strftime_format
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fmt,expected",
    [
        ("%Y-%m-%d %H:%M:%S", True),
        ("%H:%M:%S", True),
        ("%Y", True),
        ("%Q-bogus", False),  # silent literal pass-through
        ("hello world", False),  # pure literal
        ("%%", False),  # only literal percent
        ("", False),  # empty
    ],
)
def test_is_valid_strftime_format(fmt: str, expected: bool) -> None:
    assert banner.is_valid_strftime_format(fmt) is expected


# ---------------------------------------------------------------------------
# format_timestamp_suffix
# ---------------------------------------------------------------------------


def test_format_timestamp_suffix_returns_empty_when_disabled() -> None:
    with patch("code_puppy.config.get_banner_timestamps_enabled", return_value=False):
        assert banner.format_timestamp_suffix() == ""


def test_format_timestamp_suffix_uses_now_by_default() -> None:
    with (
        patch("code_puppy.config.get_banner_timestamps_enabled", return_value=True),
        patch("code_puppy.config.get_banner_timestamp_format", return_value="%H:%M:%S"),
    ):
        suffix = banner.format_timestamp_suffix()
    # Format: " [HH:MM:SS]"
    assert suffix.startswith(" [")
    assert suffix.endswith("]")
    assert len(suffix) == len(" [HH:MM:SS]")


def test_format_timestamp_suffix_uses_supplied_naive_datetime() -> None:
    when = datetime(2024, 1, 2, 3, 4, 5)
    with (
        patch("code_puppy.config.get_banner_timestamps_enabled", return_value=True),
        patch(
            "code_puppy.config.get_banner_timestamp_format",
            return_value="%Y-%m-%d %H:%M:%S",
        ),
    ):
        assert banner.format_timestamp_suffix(when) == " [2024-01-02 03:04:05]"


def test_format_timestamp_suffix_converts_aware_datetime_to_local() -> None:
    # 12:00 UTC should be rendered in local time when the input is aware.
    when = datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
    with (
        patch("code_puppy.config.get_banner_timestamps_enabled", return_value=True),
        patch(
            "code_puppy.config.get_banner_timestamp_format",
            return_value="%Y-%m-%dT%H:%M:%S",
        ),
    ):
        suffix = banner.format_timestamp_suffix(when)
    # Render the same instant directly with astimezone() to avoid hard-coding
    # any particular local timezone in the test environment.
    expected_local = (
        when.astimezone().replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")
    )
    assert suffix == f" [{expected_local}]"


def test_format_timestamp_suffix_falls_back_on_bad_format() -> None:
    # If somebody hand-edits puppy.cfg to a format that raises (the public
    # setter validates and rejects this, but get_banner_timestamp_format()
    # itself is permissive), the helper must still return *something*
    # sensible instead of propagating the exception into the renderer.
    when = datetime(2024, 1, 2, 3, 4, 5)
    with (
        patch("code_puppy.config.get_banner_timestamps_enabled", return_value=True),
        patch(
            "code_puppy.config.get_banner_timestamp_format",
            # %-Y is invalid on some platforms; fall through to default format.
            return_value="%-Y%-m%-d_completely_made_up_directive_%-q",
        ),
    ):
        result = banner.format_timestamp_suffix(when)
    assert result.startswith(" [")
    assert result.endswith("]")


# ---------------------------------------------------------------------------
# format_banner
# ---------------------------------------------------------------------------


def test_format_banner_default_behavior_is_unchanged() -> None:
    """With both opt-ins off, the output must match the historical format."""
    with (
        patch("code_puppy.config.get_banner_color", return_value="medium_purple4"),
        patch("code_puppy.config.get_banner_timestamps_enabled", return_value=False),
        patch("code_puppy.config.get_banner_newline_after_tag", return_value=False),
    ):
        result = banner.format_banner("agent_response", "AGENT RESPONSE")
    assert result == (
        "[bold white on medium_purple4] AGENT RESPONSE [/bold white on medium_purple4]"
    )


def test_format_banner_appends_dim_timestamp_outside_color_block() -> None:
    when = datetime(2024, 1, 2, 3, 4, 5)
    with (
        patch("code_puppy.config.get_banner_color", return_value="dark_orange3"),
        patch("code_puppy.config.get_banner_timestamps_enabled", return_value=True),
        patch(
            "code_puppy.config.get_banner_timestamp_format",
            return_value="%Y-%m-%d %H:%M:%S",
        ),
        patch("code_puppy.config.get_banner_newline_after_tag", return_value=False),
    ):
        result = banner.format_banner("shell_command", "SHELL COMMAND", when=when)
    assert result == (
        "[bold white on dark_orange3] SHELL COMMAND "
        "[/bold white on dark_orange3]"
        "[dim] [2024-01-02 03:04:05][/dim]"
    )


def test_format_banner_appends_trailing_newline_when_enabled() -> None:
    with (
        patch("code_puppy.config.get_banner_color", return_value="dark_goldenrod"),
        patch("code_puppy.config.get_banner_timestamps_enabled", return_value=False),
        patch("code_puppy.config.get_banner_newline_after_tag", return_value=True),
    ):
        result = banner.format_banner("replace_in_file", "EDIT FILE")
    assert result.endswith("\n")
    # The newline must be the very last character so callers building
    # `f"{banner} {extra}"` get the banner alone on its line.
    assert result.count("\n") == 1


def test_format_banner_combines_timestamp_and_newline() -> None:
    when = datetime(2024, 1, 2, 3, 4, 5)
    with (
        patch("code_puppy.config.get_banner_color", return_value="deep_sky_blue4"),
        patch("code_puppy.config.get_banner_timestamps_enabled", return_value=True),
        patch(
            "code_puppy.config.get_banner_timestamp_format",
            return_value="%H:%M:%S",
        ),
        patch("code_puppy.config.get_banner_newline_after_tag", return_value=True),
    ):
        result = banner.format_banner("thinking", "THINKING", when=when)
    assert result == (
        "[bold white on deep_sky_blue4] THINKING "
        "[/bold white on deep_sky_blue4]"
        "[dim] [03:04:05][/dim]\n"
    )
