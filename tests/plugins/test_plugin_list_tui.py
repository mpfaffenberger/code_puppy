"""Tests for the Textual /plugins ModalScreen (PluginsScreen + open_plugins)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from code_puppy.plugins.plugin_list.plugins_tui import PluginsScreen, open_plugins
from code_puppy.tui.app import build_app

_LOADED = {"builtin": ["alpha", "beta"], "user": ["gamma"], "project": []}


@pytest.mark.asyncio
async def test_plugins_screen_lists_all_tiers():
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        with (
            patch(
                "code_puppy.plugins.get_loaded_plugins",
                return_value=_LOADED,
            ),
            patch(
                "code_puppy.plugins.config.get_disabled_plugins",
                return_value={"beta"},
            ),
        ):
            app.push_screen(PluginsScreen())
            await pilot.pause()
            from textual.widgets import OptionList

            items = app.screen.query_one("#items", OptionList)
            assert items.option_count == 3  # alpha, beta, gamma


def _row_texts(app):
    from textual.widgets import OptionList

    items = app.screen.query_one("#items", OptionList)
    return [items.get_option_at_index(i).prompt for i in range(items.option_count)]


@pytest.mark.asyncio
async def test_plugins_screen_row_labels_use_markers():
    loaded = {"builtin": ["alpha"], "user": ["mine"], "project": []}
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        with (
            patch("code_puppy.plugins.get_loaded_plugins", return_value=loaded),
            patch(
                "code_puppy.plugins.config.get_disabled_plugins",
                return_value={"alpha"},
            ),
        ):
            app.push_screen(PluginsScreen())
            await pilot.pause()
            labels = [t.plain for t in _row_texts(app)]
    # No truncated tier noise.
    assert all("[buil" not in label for label in labels)
    # Disabled builtin row -> 'x' marker, no inline tier tag.
    assert any(
        label.startswith("x alpha") and "builtin" not in label for label in labels
    )
    # Enabled user row -> '+' marker WITH the (user) tier tag.
    assert any(label.startswith("+ mine") and "(user)" in label for label in labels)


@pytest.mark.asyncio
async def test_plugins_screen_toggle_calls_config():
    calls = {}

    def _set(name, *, disabled):
        calls["name"] = name
        calls["disabled"] = disabled
        return True

    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        with (
            patch(
                "code_puppy.plugins.get_loaded_plugins",
                return_value=_LOADED,
            ),
            patch(
                "code_puppy.plugins.config.get_disabled_plugins",
                return_value=set(),
            ),
            patch(
                "code_puppy.plugins.config.set_plugin_disabled",
                _set,
            ),
        ):
            app.push_screen(PluginsScreen())
            await pilot.pause()
            # Highlight first row (alpha) and toggle.
            app.screen.action_toggle()
            await pilot.pause(0.1)

    assert calls == {"name": "alpha", "disabled": True}


@pytest.mark.asyncio
async def test_open_plugins_pushes_screen():
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        with (
            patch("code_puppy.plugins.get_loaded_plugins", return_value=_LOADED),
            patch(
                "code_puppy.plugins.config.get_disabled_plugins",
                return_value=set(),
            ),
        ):
            open_plugins(app)
            await pilot.pause(0.1)
            assert isinstance(app.screen, PluginsScreen)
