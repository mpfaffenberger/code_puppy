"""The thinking spinner mirrors the classic ConsoleSpinner in the TUI."""

import pytest
from textual.widgets import Static

from code_puppy.messaging.spinner import SpinnerBase, update_spinner_context
from code_puppy.tui.app import build_app


@pytest.mark.asyncio
async def test_spinner_shows_while_busy_with_thinking_text_and_tokens():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        spinner = app.query_one("#spinner", Static)
        assert not spinner.has_class("visible")

        update_spinner_context(SpinnerBase.format_context_info(1000, 10000, 0.1))
        app._set_busy(True)
        await pilot.pause(0.3)  # let a couple of frames tick
        assert spinner.has_class("visible")
        rendered = spinner.render()
        text = rendered.plain if hasattr(rendered, "plain") else str(rendered)
        assert "thinking" in text
        assert "Tokens: 1,000/10,000" in text

        app._set_busy(False)
        await pilot.pause()
        assert not spinner.has_class("visible")


@pytest.mark.asyncio
async def test_spinner_frame_advances_while_busy():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app._set_busy(True)
        first = app._spinner_frame
        await pilot.pause(0.3)
        assert app._spinner_frame != first
        app._set_busy(False)
