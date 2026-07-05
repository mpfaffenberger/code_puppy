"""TUI coverage for `/btw`: modal path instead of the classic raw-terminal one.

Regression test for the bug where `/btw <question>` + ENTER did nothing
visible in the Textual UI (it was blocking on a termios read that competes
with Textual's own input driver -- see tui_view.py docstring).
"""

from unittest.mock import patch

import pytest

from code_puppy.plugins.btw import side_query, tui_view
from code_puppy.plugins.btw.tui_view import BtwAnswerScreen
from code_puppy.tui.app import build_app


def test_is_textual_active_false_outside_app():
    assert tui_view.is_textual_active() is False


@pytest.mark.asyncio
async def test_btw_opens_modal_in_tui_and_renders_answer():
    with (
        patch.object(side_query, "resolve_model_name", return_value="gpt-5"),
        patch.object(side_query, "_ask", return_value="a monoid, obviously"),
    ):
        app = build_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.submit_prompt("/btw what is a monad?")
            await pilot.pause(0.1)
            assert isinstance(app.screen, BtwAnswerScreen)
            # Let the async worker resolve the (mocked) query.
            await pilot.pause(0.1)
            body = app.screen.query_one("#btw-body").content
            assert "monoid" in str(getattr(body, "markup", body))
            await pilot.press("escape")
            await pilot.pause(0.1)
            assert not isinstance(app.screen, BtwAnswerScreen)


@pytest.mark.asyncio
async def test_btw_no_model_still_errors_in_tui():
    with patch.object(side_query, "resolve_model_name", return_value=None):
        app = build_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.submit_prompt("/btw hi")
            await pilot.pause(0.1)
            # No model -> classic error path fires before the modal check,
            # so no modal should be pushed.
            assert not isinstance(app.screen, BtwAnswerScreen)
