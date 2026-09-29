"""Tests for the fullscreen help overlay renderer/launcher (termflow Pager)."""

from io import StringIO
from unittest.mock import patch

import pytest

from code_puppy.command_line import help_overlay
from code_puppy.command_line.help_catalog import HelpEntry, HelpSection
from code_puppy.command_line.help_overlay import (
    _build_pager,
    _column_width,
    _render_sheet_text,
    show_help_overlay,
)


def _sections():
    return [
        HelpSection(
            "Keybindings",
            [HelpEntry("Tab", "Toggle help"), HelpEntry("Esc", "Close")],
        ),
        HelpSection("Commands", [HelpEntry("/help", "Show help")]),
    ]


def _drive(sections, keys):
    """Run the real Pager headlessly on a key script. Returns output."""
    script = iter(keys)
    out = StringIO()
    pager = _build_pager(
        sections,
        key_source=lambda: next(script),
        output=out,
        size=lambda: (80, 24),
        alt_screen=False,
    )
    result = pager.run()
    return result, out.getvalue()


@pytest.mark.parametrize(
    "label_len, expected",
    [(200, 60), (1, 12)],  # capped for absurd labels, floored for tiny ones
)
def test_column_width_is_clamped_between_a_floor_and_a_cap(label_len, expected):
    sections = [HelpSection("S", [HelpEntry("x" * label_len, "desc")])]
    assert _column_width(sections) == expected


def test_render_sheet_text_includes_every_section_title_and_entry():
    text = _render_sheet_text(_sections())

    assert "KEYBINDINGS" in text
    assert "COMMANDS" in text
    assert "Toggle help" in text
    assert "/help" in text
    assert "Show help" in text


def test_render_sheet_text_omits_trailing_column_for_entries_without_right():
    sections = [HelpSection("S", [HelpEntry("just-a-label")])]
    text = _render_sheet_text(sections)
    assert "just-a-label" in text
    # No dangling double-space column for an entry with no description.
    assert "just-a-label  \n" not in text.replace("\n\n", "\n")


def test_pager_paints_sheet_and_all_close_keys_work():
    for close_key in ("tab", "q", "escape", "enter", "ctrl-c"):
        result, out = _drive(_sections(), [close_key])
        assert "CODE PUPPY -- HELP" in out
        assert "KEYBINDINGS" in out


def test_pager_scrolls_long_sheets():
    sections = [
        HelpSection(f"Section {i}", [HelpEntry(f"key-{i}", f"desc {i}")])
        for i in range(30)
    ]
    _, out = _drive(sections, ["G", "q"])
    assert "SECTION 29" in out  # bottom reachable via G (titles are uppercased)
    first_frame = out.split("\x1b[H")[1]
    assert "SECTION 29" not in first_frame  # but not visible at the top


def test_show_help_overlay_builds_sections_and_runs_the_pager():
    ran = []

    class FakePager:
        def run(self):
            ran.append(True)

    with (
        patch(
            "code_puppy.command_line.help_overlay.build_help_sections",
            return_value=_sections(),
        ) as mock_build,
        patch(
            "code_puppy.command_line.help_overlay._build_pager",
            return_value=FakePager(),
        ) as mock_pager,
    ):
        show_help_overlay()

    mock_build.assert_called_once()
    mock_pager.assert_called_once_with(_sections())
    assert ran == [True]


def test_show_help_overlay_is_a_noop_while_already_running():
    """Two Tab presses in quick succession must not spin up a second
    fullscreen widget on top of the first."""
    acquired = help_overlay._launch_lock.acquire(blocking=False)
    assert acquired, "test setup: lock should have been free"
    try:
        with patch(
            "code_puppy.command_line.help_overlay.build_help_sections"
        ) as mock_build:
            show_help_overlay()  # lock is "held" -- must return immediately
        mock_build.assert_not_called()
    finally:
        help_overlay._launch_lock.release()


def test_show_help_overlay_releases_the_lock_after_a_normal_run():
    class FakePager:
        def run(self):
            pass

    with (
        patch(
            "code_puppy.command_line.help_overlay.build_help_sections",
            return_value=_sections(),
        ),
        patch(
            "code_puppy.command_line.help_overlay._build_pager",
            return_value=FakePager(),
        ),
    ):
        show_help_overlay()

    # A second call right after must be able to acquire the lock and run.
    with (
        patch(
            "code_puppy.command_line.help_overlay.build_help_sections",
            return_value=_sections(),
        ) as mock_build,
        patch(
            "code_puppy.command_line.help_overlay._build_pager",
            return_value=FakePager(),
        ),
    ):
        show_help_overlay()
    mock_build.assert_called_once()


def test_show_help_overlay_releases_the_lock_even_if_catalog_build_fails():
    """Also proves a raising catalog build never propagates out to the REPL."""
    with patch(
        "code_puppy.command_line.help_overlay.build_help_sections",
        side_effect=RuntimeError("boom"),
    ):
        show_help_overlay()

    acquired = help_overlay._launch_lock.acquire(blocking=False)
    assert acquired, "lock must be released even when catalog build raises"
    help_overlay._launch_lock.release()


def test_show_help_overlay_survives_a_crashing_pager():
    class ExplodingPager:
        def run(self):
            raise OSError("no tty")

    with (
        patch(
            "code_puppy.command_line.help_overlay.build_help_sections",
            return_value=_sections(),
        ),
        patch(
            "code_puppy.command_line.help_overlay._build_pager",
            return_value=ExplodingPager(),
        ),
    ):
        show_help_overlay()  # must not raise

    acquired = help_overlay._launch_lock.acquire(blocking=False)
    assert acquired
    help_overlay._launch_lock.release()
