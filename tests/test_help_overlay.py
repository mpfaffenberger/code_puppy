"""Tests for the fullscreen help overlay renderer/launcher (PUP-352)."""

from unittest.mock import AsyncMock, patch

from code_puppy.command_line import help_overlay
from code_puppy.command_line.help_catalog import HelpEntry, HelpSection
from code_puppy.command_line.help_overlay import (
    _build_application,
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


def test_column_width_scales_with_longest_label_but_is_capped():
    sections = [
        HelpSection("S", [HelpEntry("x" * 200, "desc")]),
    ]
    assert _column_width(sections) == 60


def test_column_width_has_a_sane_floor():
    sections = [HelpSection("S", [HelpEntry("x", "desc")])]
    assert _column_width(sections) == 12


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


def test_build_application_does_not_crash_and_wires_close_keys():
    from prompt_toolkit.keys import Keys

    app = _build_application(_sections())
    # Building the Application object must not require a live terminal.
    assert app.full_screen is True
    bindings = app.key_bindings.bindings
    bound_keys = {tuple(b.keys) for b in bindings}
    # "tab" normalizes to Ctrl-I and "escape" to Keys.Escape under the hood.
    assert (Keys.ControlI,) in bound_keys
    assert (Keys.Escape,) in bound_keys
    assert ("q",) in bound_keys
    assert (Keys.ControlC,) in bound_keys


def test_show_help_overlay_builds_sections_and_runs_the_application():
    # AsyncMock, not a plain Mock: show_help_overlay does
    # asyncio.run(_run_help_overlay_async(sections)), which requires a real
    # coroutine. A plain Mock's return value (None) would make asyncio.run
    # raise -- silently swallowed by show_help_overlay's own broad except,
    # letting the test pass without ever proving the launch path works.
    with (
        patch(
            "code_puppy.command_line.help_overlay.build_help_sections",
            return_value=_sections(),
        ) as mock_build,
        patch(
            "code_puppy.command_line.help_overlay._run_help_overlay_async",
            new_callable=AsyncMock,
        ) as mock_run,
    ):
        show_help_overlay()

    mock_build.assert_called_once()
    mock_run.assert_awaited_once_with(_sections())


def test_show_help_overlay_swallows_exceptions_never_crashes_the_repl():
    with patch(
        "code_puppy.command_line.help_overlay.build_help_sections",
        side_effect=RuntimeError("boom"),
    ):
        show_help_overlay()  # must not raise


def test_show_help_overlay_is_a_noop_while_already_running():
    """Guards the launch race: two Tab presses in quick succession (key
    repeat, a fast double-tap, a pasted double-tab) must not spin up a
    second competing fullscreen Application on top of the first."""
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
    with (
        patch(
            "code_puppy.command_line.help_overlay.build_help_sections",
            return_value=_sections(),
        ),
        patch(
            "code_puppy.command_line.help_overlay._run_help_overlay_async",
            new_callable=AsyncMock,
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
            "code_puppy.command_line.help_overlay._run_help_overlay_async",
            new_callable=AsyncMock,
        ),
    ):
        show_help_overlay()
    mock_build.assert_called_once()


def test_show_help_overlay_releases_the_lock_even_if_catalog_build_fails():
    with patch(
        "code_puppy.command_line.help_overlay.build_help_sections",
        side_effect=RuntimeError("boom"),
    ):
        show_help_overlay()

    acquired = help_overlay._launch_lock.acquire(blocking=False)
    assert acquired, "lock must be released even when catalog build raises"
    help_overlay._launch_lock.release()
