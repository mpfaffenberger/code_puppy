"""Phase 3 kit: FormScreen multi-field form."""

import pytest
from textual.widgets import Input, Label

from code_puppy.tui.app import build_app
from code_puppy.tui.screens.form import FormField, FormScreen


def _fields():
    return [
        FormField("name", "Name", required=True),
        FormField("token", "Token", kind="password"),
        FormField("enabled", "Enabled", kind="bool", default=True),
        FormField("kind", "Kind", kind="select", options=["a", "b"], default="a"),
    ]


@pytest.mark.asyncio
async def test_form_submit_collects_values():
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        result = []
        app.push_screen(FormScreen("Test", _fields()), lambda r: result.append(r))
        await pilot.pause(0.1)
        assert isinstance(app.screen, FormScreen)
        app.screen.query_one("#field-name", Input).value = "cooper"
        app.screen.query_one("#field-token", Input).value = "secret"
        await pilot.click("#submit")
        await pilot.pause(0.1)
    assert result == [
        {"name": "cooper", "token": "secret", "enabled": True, "kind": "a"}
    ]


@pytest.mark.asyncio
async def test_form_required_validation_blocks_submit():
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        result = []
        app.push_screen(FormScreen("Test", _fields()), lambda r: result.append(r))
        await pilot.pause(0.1)
        # name is required and empty -> submit must not dismiss
        await pilot.click("#submit")
        await pilot.pause(0.1)
        assert result == []  # not dismissed
        assert isinstance(app.screen, FormScreen)
        error = str(app.screen.query_one("#error", Label).render())
        assert "Required" in error and "Name" in error


@pytest.mark.asyncio
async def test_form_cancel_returns_none():
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        result = []
        app.push_screen(FormScreen("Test", _fields()), lambda r: result.append(r))
        await pilot.pause(0.1)
        await pilot.press("escape")
        await pilot.pause(0.1)
    assert result == [None]


@pytest.mark.asyncio
async def test_form_cancel_button_returns_none():
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        result = []
        app.push_screen(FormScreen("Test", _fields()), lambda r: result.append(r))
        await pilot.pause(0.1)
        await pilot.click("#cancel")
        await pilot.pause(0.1)
    assert result == [None]
