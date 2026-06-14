"""Phase 2 polish: !shell passthrough runs captured and renders in the TUI."""

import pytest
from textual.widgets import RichLog

from code_puppy.tui.app import build_app


def _log_text(app) -> str:
    log = app.query_one("#log", RichLog)
    return " ".join(line.text for line in log.lines)


@pytest.mark.asyncio
async def test_shell_passthrough_renders_output():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("!echo cooper123")
        for _ in range(80):
            await pilot.pause(0.05)
            if "cooper123" in _log_text(app):
                break
        text = _log_text(app)
        assert "cooper123" in text
        assert "Done" in text
        # Shell passthrough must not flip the agent busy-state.
        assert app._busy is False


@pytest.mark.asyncio
async def test_shell_passthrough_nonzero_exit():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("!exit 3")
        for _ in range(80):
            await pilot.pause(0.05)
            if "Exit code 3" in _log_text(app):
                break
        assert "Exit code 3" in _log_text(app)


@pytest.mark.asyncio
async def test_bare_bang_is_rejected():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("!   ")
        await pilot.pause(0.1)
        assert "Usage: !<command>" in _log_text(app)
