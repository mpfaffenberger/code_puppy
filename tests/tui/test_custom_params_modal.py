"""Tests for the Custom Params editor (parity gap fix, 2026-08-01).

Main added user-defined custom request params per model (d08b6c97) with a
classic-menu UI; the Textual /model_settings screen didn't expose the
'custom' setting at all until this fix (see test_model_settings_routing.py
for the visibility-bypass regression tests). These tests cover the
add/edit/delete flow of the dedicated CustomParamsModal screen.
"""

import asyncio

import pytest
from textual.app import App

from code_puppy.tui.screens.custom_params import CustomParamsModal


class _Harness(App):
    def __init__(self, model_name: str) -> None:
        super().__init__()
        self._model_name = model_name

    async def on_mount(self) -> None:
        self.push_screen(CustomParamsModal(self._model_name))


@pytest.fixture(autouse=True)
def _clean_custom_settings(monkeypatch):
    """Route all custom-param persistence through an in-memory dict so tests
    never touch the real ~/.code_puppy config."""
    store: dict = {}

    def _get(model_name):
        return dict(store)

    def _set(model_name, key, value):
        if value is None:
            store.pop(key, None)
        else:
            store[key] = value

    monkeypatch.setattr(
        "code_puppy.tui.screens.custom_params.get_custom_model_settings", _get
    )
    monkeypatch.setattr(
        "code_puppy.tui.screens.custom_params.set_custom_model_setting", _set
    )
    yield store


async def _run(model_name="gpt-x"):
    app = _Harness(model_name)
    ctx = app.run_test(size=(80, 24))
    pilot = await ctx.__aenter__()
    await pilot.pause()
    return app, pilot, ctx


def test_shows_add_new_row_when_empty():
    async def go():
        app, pilot, ctx = await _run()
        try:
            screen = app.screen
            items = screen.query_one("#items")
            ids = [items.get_option_at_index(i).id for i in range(items.option_count)]
            assert ids == ["__add_new__"]
        finally:
            await ctx.__aexit__(None, None, None)

    asyncio.run(go())


def test_add_delete_roundtrip(_clean_custom_settings):
    async def go():
        app, pilot, ctx = await _run()
        try:
            screen = app.screen
            # Simulate what TextInputModal would feed back for "add new".
            screen._save_input(None, "chat_template_kwargs.thinking = medium")
            assert _clean_custom_settings == {"chat_template_kwargs.thinking": "medium"}

            items = screen.query_one("#items")
            ids = [items.get_option_at_index(i).id for i in range(items.option_count)]
            assert "chat_template_kwargs.thinking" in ids
            assert screen._changed is True

            screen.action_delete()
            assert _clean_custom_settings == {}
        finally:
            await ctx.__aexit__(None, None, None)

    asyncio.run(go())


def test_rename_drops_stale_key(_clean_custom_settings):
    async def go():
        app, pilot, ctx = await _run()
        try:
            screen = app.screen
            screen._save_input(None, "old_key = 1")
            assert "old_key" in _clean_custom_settings

            screen._save_input("old_key", "new_key = 2")
            assert "old_key" not in _clean_custom_settings
            assert _clean_custom_settings["new_key"] == 2
        finally:
            await ctx.__aexit__(None, None, None)

    asyncio.run(go())


def test_malformed_input_does_not_crash(_clean_custom_settings):
    async def go():
        app, pilot, ctx = await _run()
        try:
            screen = app.screen
            screen._save_input(None, "no equals sign here")
            assert _clean_custom_settings == {}
        finally:
            await ctx.__aexit__(None, None, None)

    asyncio.run(go())
