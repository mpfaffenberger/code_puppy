"""Tests for the Textual /queue ModalScreen (QueueScreen + open_queue).

The classic prompt_toolkit /queue menu no-ops / corrupts the Textual screen,
so the TUI drives the SAME PauseController steer-queue via a native modal.
These tests lock that parity in place so the gap can't silently reopen.
"""

from __future__ import annotations

import pytest
from textual.widgets import OptionList

from code_puppy.messaging.pause_controller import reset_pause_controller
from code_puppy.plugins.steer_queue import register_callbacks as rc
from code_puppy.plugins.steer_queue.queue_tui import QueueScreen, open_queue
from code_puppy.tui.app import build_app


@pytest.fixture(autouse=True)
def fresh_controller():
    reset_pause_controller()
    yield
    reset_pause_controller()


def _seed(*prompts):
    from code_puppy.messaging.pause_controller import get_pause_controller

    pc = get_pause_controller()
    for p in prompts:
        pc.request_steer(p, mode="queue")
    return pc


def test_register_queue_screen_advertises_the_command():
    entries = rc._register_queue_screen()
    assert entries == [{"command": "queue", "open": open_queue}]


@pytest.mark.asyncio
async def test_queue_screen_lists_current_queue():
    _seed("first prompt", "second prompt")
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(QueueScreen())
        await pilot.pause()
        items = app.screen.query_one("#items", OptionList)
        assert items.option_count == 2
        # Newest-last ordering matches the controller's queue.
        assert app.screen._items == ["first prompt", "second prompt"]


@pytest.mark.asyncio
async def test_queue_screen_delete_removes_highlighted():
    pc = _seed("keep me", "delete me")
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(QueueScreen())
        await pilot.pause()
        items = app.screen.query_one("#items", OptionList)
        items.highlighted = 1  # "delete me"
        await pilot.pause()
        app.screen.action_delete()
        await pilot.pause()
        assert pc.peek_pending_steer_queued() == ["keep me"]
        assert app.screen.query_one("#items", OptionList).option_count == 1


@pytest.mark.asyncio
async def test_queue_screen_edit_applies_new_text():
    pc = _seed("typo prmpt")
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(QueueScreen())
        await pilot.pause()
        # Drive the edit path directly (bypassing the FormScreen dialog).
        app.screen._apply_edit(0, "fixed prompt")
        await pilot.pause()
    assert pc.peek_pending_steer_queued() == ["fixed prompt"]


@pytest.mark.asyncio
async def test_queue_screen_add_appends_through_controller():
    pc = _seed("existing")
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(QueueScreen())
        await pilot.pause()
        app.screen._apply_add("brand new")
        await pilot.pause()
    assert pc.peek_pending_steer_queued() == ["existing", "brand new"]


@pytest.mark.asyncio
async def test_queue_screen_empty_state_summary():
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(QueueScreen())
        await pilot.pause()
        from textual.widgets import Label

        summary = app.screen.query_one("#summary", Label)
        assert "empty" in str(summary.render()).lower()


@pytest.mark.asyncio
async def test_open_queue_pushes_screen():
    _seed("x")
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        open_queue(app)
        await pilot.pause()
        assert isinstance(app.screen, QueueScreen)


@pytest.mark.asyncio
async def test_queue_screen_shift_up_moves_item_earlier():
    pc = _seed("first", "second", "third")
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(QueueScreen())
        await pilot.pause()
        items = app.screen.query_one("#items", OptionList)
        items.highlighted = 1  # "second"
        await pilot.pause()
        app.screen.action_move_up()
        await pilot.pause()
        # Cursor follows the moved item — must check before app tears down.
        assert app.screen.query_one("#items", OptionList).highlighted == 0
    assert pc.peek_pending_steer_queued() == ["second", "first", "third"]


@pytest.mark.asyncio
async def test_queue_screen_shift_down_moves_item_later():
    pc = _seed("first", "second", "third")
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(QueueScreen())
        await pilot.pause()
        items = app.screen.query_one("#items", OptionList)
        items.highlighted = 1  # "second"
        await pilot.pause()
        app.screen.action_move_down()
        await pilot.pause()
        # Cursor follows the moved item — must check before app tears down.
        assert app.screen.query_one("#items", OptionList).highlighted == 2
    assert pc.peek_pending_steer_queued() == ["first", "third", "second"]


@pytest.mark.asyncio
async def test_queue_screen_shift_up_at_top_is_noop():
    pc = _seed("first", "second")
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(QueueScreen())
        await pilot.pause()
        app.screen.query_one("#items", OptionList).highlighted = 0
        await pilot.pause()
        app.screen.action_move_up()
        await pilot.pause()
    assert pc.peek_pending_steer_queued() == ["first", "second"]


@pytest.mark.asyncio
async def test_queue_screen_shift_down_at_bottom_is_noop():
    pc = _seed("first", "second")
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(QueueScreen())
        await pilot.pause()
        app.screen.query_one("#items", OptionList).highlighted = 1
        await pilot.pause()
        app.screen.action_move_down()
        await pilot.pause()
    assert pc.peek_pending_steer_queued() == ["first", "second"]
