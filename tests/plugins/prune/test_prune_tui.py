"""Tests for the Textual /prune ModalScreen (PruneScreen + open_prune)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.plugins.prune.prune_model import ContextBudget, build_message_entries
from code_puppy.plugins.prune.prune_tui import PruneScreen, open_prune
from code_puppy.tui.app import build_app

from ._helpers import _assistant_text, _system_plus_user_msg, _user_msg


def _entries():
    history = [
        _system_plus_user_msg(),
        _assistant_text("first answer"),
        _user_msg("second question"),
        _assistant_text("second answer"),
    ]
    return build_message_entries(history)


def test_prune_screen_excludes_locked_rows():
    screen = PruneScreen(_entries(), ContextBudget())
    # System bundle is locked -> not offered as a prunable row.
    assert all(not e.is_locked for e in screen._rows)
    assert screen._rows  # but the real messages are present


@pytest.mark.asyncio
async def test_prune_screen_lists_and_prunes_selection():
    entries = _entries()
    captured = {}

    def _fake_perform(indices):
        captured["indices"] = set(indices)

    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        with patch(
            "code_puppy.plugins.prune.register_callbacks._perform_prune",
            _fake_perform,
        ):
            app.push_screen(PruneScreen(entries, ContextBudget()))
            await pilot.pause()
            from textual.widgets import SelectionList

            sel = app.screen.query_one("#items", SelectionList)
            assert sel.option_count == len(
                [e for e in entries if not e.is_locked and not e.is_pure_tool_return]
            )
            # Select everything and prune.
            app.screen.action_select_all()
            await pilot.pause()
            app.screen.action_prune()
            await pilot.pause(0.1)

    assert "indices" in captured
    assert len(captured["indices"]) == sel.option_count


@pytest.mark.asyncio
async def test_prune_screen_empty_selection_no_perform():
    captured = {}
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        with patch(
            "code_puppy.plugins.prune.register_callbacks._perform_prune",
            lambda idx: captured.setdefault("called", True),
        ):
            app.push_screen(PruneScreen(_entries(), ContextBudget()))
            await pilot.pause()
            app.screen.action_prune()  # nothing selected
            await pilot.pause(0.1)
    assert "called" not in captured


@pytest.mark.asyncio
async def test_open_prune_pushes_screen():
    agent = MagicMock()
    agent.get_message_history.return_value = [
        _system_plus_user_msg(),
        _assistant_text("a"),
        _user_msg("q"),
    ]
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        with (
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=agent,
            ),
            patch(
                "code_puppy.plugins.prune.prune_model.annotate_context_window",
                return_value=ContextBudget(),
            ),
        ):
            open_prune(app)
            await pilot.pause(0.1)
            assert isinstance(app.screen, PruneScreen)
