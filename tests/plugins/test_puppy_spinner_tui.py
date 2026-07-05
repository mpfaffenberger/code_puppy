"""Tests for the Textual /spinner ModalScreen (SpinnerScreen + open_spinner).

Closes the "half-fix" gap: the classic prompt_toolkit spinner picker (animated
preview) corrupts the Textual screen, so the TUI drives the SAME catalogue /
set_active data layer via a native live-preview modal. These tests lock the
parity in place so the gap can't quietly reopen.
"""

from __future__ import annotations

import pytest
from textual.widgets import OptionList

from code_puppy.plugins.puppy_spinner import register_callbacks as rc
from code_puppy.plugins.puppy_spinner import spinners as sp
from code_puppy.plugins.puppy_spinner.spinner_tui import SpinnerScreen, open_spinner
from code_puppy.tui.app import build_app


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    """Point config + user file at scratch space; reset the cache."""
    store: dict[str, str] = {}
    monkeypatch.setattr(sp, "get_value", store.get)
    monkeypatch.setattr(sp, "set_value", store.__setitem__)
    monkeypatch.setattr(sp, "USER_SPINNERS_FILE", str(tmp_path / "spinners.json"))
    monkeypatch.setattr(sp, "CONFIG_DIR", str(tmp_path))
    sp.invalidate_cache()
    yield store
    sp.invalidate_cache()


def test_register_spinner_screen_advertises_the_command():
    entries = rc._register_spinner_screen()
    assert entries == [{"command": "spinner", "open": open_spinner}]


@pytest.mark.asyncio
async def test_spinner_screen_lists_the_catalogue():
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(SpinnerScreen())
        await pilot.pause()
        items = app.screen.query_one("#items", OptionList)
        assert items.option_count == len(sp.get_catalogue())


@pytest.mark.asyncio
async def test_spinner_screen_apply_persists_selection(isolated_config):
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(SpinnerScreen())
        await pilot.pause()
        screen = app.screen
        # Highlight "zoomies" and apply.
        names = [s.name for s in screen._entries]
        screen.query_one("#items", OptionList).highlighted = names.index("zoomies")
        await pilot.pause()
        screen.action_apply()
        await pilot.pause()
    assert sp.get_active_spinner().name == "zoomies"


@pytest.mark.asyncio
async def test_spinner_screen_enter_key_applies(isolated_config):
    """Enter on the focused list applies (OptionSelected, not the swallowed
    screen-level `enter` binding)."""
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(SpinnerScreen())
        await pilot.pause()
        screen = app.screen
        names = [s.name for s in screen._entries]
        screen.query_one("#items", OptionList).highlighted = names.index("bone")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
    assert sp.get_active_spinner().name == "bone"


@pytest.mark.asyncio
async def test_spinner_screen_speed_dial_saves_custom_interval(isolated_config):
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(SpinnerScreen())
        await pilot.pause()
        screen = app.screen
        names = [s.name for s in screen._entries]
        screen.query_one("#items", OptionList).highlighted = names.index("dots")
        await pilot.pause()
        # Dial the speed a couple notches; that arms a custom interval.
        screen.action_slower()
        screen.action_slower()
        assert screen._custom_interval is not None
        dialed = screen._custom_interval
        screen.action_apply()
        await pilot.pause()
    active = sp.get_active_spinner()
    assert active.name == "dots"
    assert active.interval == pytest.approx(dialed)


@pytest.mark.asyncio
async def test_spinner_screen_highlight_resets_custom_speed():
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(SpinnerScreen())
        await pilot.pause()
        screen = app.screen
        screen.action_slower()
        assert screen._custom_interval is not None
        # Moving to another entry clears the dialed speed.
        items = screen.query_one("#items", OptionList)
        items.highlighted = (items.highlighted or 0) + 1
        await pilot.pause()
        assert screen._custom_interval is None


@pytest.mark.asyncio
async def test_spinner_screen_init_writes_starter_file(isolated_config):
    import os

    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(SpinnerScreen())
        await pilot.pause()
        screen = app.screen
        assert not os.path.isfile(sp.USER_SPINNERS_FILE)
        screen.action_init_file()
        await pilot.pause()
        assert os.path.isfile(sp.USER_SPINNERS_FILE)
        assert "written" in screen._notice.lower()


@pytest.mark.asyncio
async def test_open_spinner_pushes_screen():
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        open_spinner(app)
        await pilot.pause()
        assert isinstance(app.screen, SpinnerScreen)
