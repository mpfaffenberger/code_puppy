"""Phase 2e: prompt completion (/command and @path)."""

import pytest

from code_puppy.tui.app import CompletionList, PromptArea, build_app
from code_puppy.tui.completion import compute_completions


def test_command_completion_lists_help():
    result = compute_completions("/he", 3)
    assert result is not None
    assert result.start_col == 0 and result.end_col == 3
    inserts = [i.insert for i in result.items]
    assert any(i.startswith("/help") for i in inserts)
    # accepted command insert carries a trailing space for args
    assert all(i.endswith(" ") for i in inserts)


def test_no_completion_after_command_space():
    # Once there's a space, the slash-command context is over.
    assert compute_completions("/help ", 6) is None


def test_path_completion_matches_repo_file():
    # cwd is the repo root under pytest; pyproject.toml should be found.
    result = compute_completions("look at @pyproj", len("look at @pyproj"))
    assert result is not None
    assert result.start_col == len("look at ")
    assert any(i.insert.startswith("@pyproject") for i in result.items)


def test_plain_text_has_no_completion():
    assert compute_completions("just some words", 15) is None


@pytest.mark.asyncio
async def test_dropdown_opens_and_accepts():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", PromptArea)
        prompt.text = "/he"
        prompt.move_cursor((0, 3))
        app._refresh_completions()
        await pilot.pause(0.05)

        assert app.completion_visible()
        completions = app.query_one("#completions", CompletionList)
        assert completions.option_count >= 1

        app.accept_completion()
        await pilot.pause(0.05)
        assert prompt.text.startswith("/help ")
        assert not app.completion_visible()


@pytest.mark.asyncio
async def test_escape_dismisses_dropdown():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", PromptArea)
        prompt.text = "/he"
        prompt.move_cursor((0, 3))
        app._refresh_completions()
        await pilot.pause(0.05)
        assert app.completion_visible()

        app.hide_completions()
        assert not app.completion_visible()
