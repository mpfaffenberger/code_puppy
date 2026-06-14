"""Phase 0: the CooperApp scaffold boots headlessly and the bus -> renderer
path works (no TTY required, CI-friendly).
"""

import pytest
from textual.widgets import RichLog

from code_puppy.tui.app import build_app
from code_puppy.tui.renderer import message_to_renderable
from code_puppy.messaging import MessageLevel, TextMessage


@pytest.mark.asyncio
async def test_app_boots_and_renders_startup_message():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.query_one("#log", RichLog)
        # Startup success message was buffered then drained by the renderer.
        assert len(log.lines) >= 1


@pytest.mark.asyncio
async def test_submit_prompt_round_trips_through_bus():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        log = app.query_one("#log", RichLog)
        before = len(log.lines)
        app.submit_prompt("hello puppy")
        for _ in range(50):
            await pilot.pause(0.05)
            if len(log.lines) > before:
                break
        assert len(log.lines) > before


@pytest.mark.asyncio
async def test_initial_command_is_submitted_on_mount():
    app = build_app(initial_command="do the thing")
    async with app.run_test() as pilot:
        for _ in range(50):
            await pilot.pause(0.05)
            if len(app.query_one("#log", RichLog).lines) > 1:
                break
        assert len(app.query_one("#log", RichLog).lines) > 1


def test_message_to_renderable_handles_text_and_fallback():
    from rich.text import Text

    r = message_to_renderable(TextMessage(level=MessageLevel.INFO, text="hi"))
    assert isinstance(r, Text)
    assert "hi" in r.plain

    # An unknown message type must not crash; it falls back to a dim repr.
    class _Weird:
        def __repr__(self):
            return "<weird>"

    fallback = message_to_renderable(_Weird())
    assert isinstance(fallback, Text)
