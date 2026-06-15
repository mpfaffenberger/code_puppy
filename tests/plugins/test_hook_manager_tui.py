"""Tests for the Textual /hooks ModalScreen (HooksScreen + open_hooks)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from code_puppy.plugins.hook_manager.config import HookEntry
from code_puppy.plugins.hook_manager.hooks_tui import HooksScreen, open_hooks
from code_puppy.tui.app import build_app


def _entries():
    return [
        HookEntry(
            event_type="PreToolUse",
            matcher="*",
            hook_type="command",
            command="echo hi",
            enabled=True,
            source="project",
            group_index=0,
            hook_index=0,
        ),
        HookEntry(
            event_type="PostToolUse",
            matcher="Bash",
            hook_type="command",
            command="echo bye",
            enabled=False,
            source="global",
            group_index=0,
            hook_index=0,
        ),
    ]


@pytest.mark.asyncio
async def test_hooks_screen_lists_entries():
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        with patch(
            "code_puppy.plugins.hook_manager.config.flatten_all_hooks",
            return_value=_entries(),
        ):
            app.push_screen(HooksScreen())
            await pilot.pause()
            from textual.widgets import OptionList

            items = app.screen.query_one("#items", OptionList)
            assert items.option_count == 2


@pytest.mark.asyncio
async def test_hooks_screen_toggle_saves():
    saved = {}

    def _toggle(cfg, event_type, gi, hi, enabled):
        saved["enabled"] = enabled
        saved["event"] = event_type
        return cfg

    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        with (
            patch(
                "code_puppy.plugins.hook_manager.config.flatten_all_hooks",
                return_value=_entries(),
            ),
            patch(
                "code_puppy.plugins.hook_manager.config._load_project_hooks_config",
                return_value={},
            ),
            patch(
                "code_puppy.plugins.hook_manager.config.save_hooks_config"
            ) as mock_save,
            patch(
                "code_puppy.plugins.hook_manager.config.toggle_hook_enabled",
                _toggle,
            ),
        ):
            app.push_screen(HooksScreen())
            await pilot.pause()
            app.screen.action_toggle()  # toggles first (project, enabled->disabled)
            await pilot.pause(0.1)

    assert saved["event"] == "PreToolUse"
    assert saved["enabled"] is False
    assert mock_save.called


@pytest.mark.asyncio
async def test_open_hooks_pushes_screen():
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        with patch(
            "code_puppy.plugins.hook_manager.config.flatten_all_hooks",
            return_value=_entries(),
        ):
            open_hooks(app)
            await pilot.pause(0.1)
            assert isinstance(app.screen, HooksScreen)
