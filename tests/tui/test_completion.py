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


def test_model_arg_completion(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.command_line.model_picker_completion.load_model_names",
        lambda: ["alpha-1", "beta-2", "alpha-3"],
    )
    line = "/model alpha"
    result = compute_completions(line, len(line))
    assert result is not None
    assert result.start_col == len("/model ")
    inserts = sorted(i.insert for i in result.items)
    assert inserts == ["alpha-1", "alpha-3"]


def test_agent_arg_completion(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.agents.agent_manager.get_available_agents",
        lambda: {"code-puppy": "Code Puppy", "helios": "Helios"},
    )
    line = "/a hel"
    result = compute_completions(line, len(line))
    assert result is not None
    assert [i.insert for i in result.items] == ["helios"]


def test_mcp_subcommand_completion():
    line = "/mcp sta"
    result = compute_completions(line, len(line))
    assert result is not None
    inserts = {i.insert for i in result.items}
    assert "start" in inserts and "start-all" in inserts


def test_mcp_server_name_completion(monkeypatch):
    class _S:
        def __init__(self, name):
            self.name = name

    monkeypatch.setattr(
        "code_puppy.mcp_.manager.get_mcp_manager",
        lambda: type(
            "M", (), {"list_servers": lambda self: [_S("filesystem"), _S("github")]}
        )(),
    )
    line = "/mcp start fil"
    result = compute_completions(line, len(line))
    assert result is not None
    assert [i.insert for i in result.items] == ["filesystem"]


def test_mcp_no_server_completion_for_general_subcommand(monkeypatch):
    line = "/mcp help extra"
    # 'help' takes no server arg -> no completion for the second token
    assert compute_completions(line, len(line)) is None


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


@pytest.mark.asyncio
async def test_partial_menu_command_runs_on_single_enter(monkeypatch):
    """Typing a few letters of a no-arg menu command + Enter should open it in
    one keystroke (not complete-then-require-a-second-Enter)."""
    from code_puppy.tui.screens.diff_picker import DiffPickerScreen

    monkeypatch.setattr("code_puppy.config.get_diff_addition_color", lambda: "#000000")
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", PromptArea)
        prompt.text = "/dif"
        prompt.move_cursor((0, 4))
        app._refresh_completions()
        await pilot.pause(0.05)
        assert app.completion_visible()

        # One Enter: accept /diff AND open its modal.
        submitted = app.accept_completion(submit_if_terminal=True)
        await pilot.pause(0.1)
        assert submitted is True
        assert prompt.text == ""
        assert isinstance(app.screen, DiffPickerScreen)


@pytest.mark.asyncio
async def test_partial_arg_command_does_not_autorun_on_enter(monkeypatch):
    """Commands with argument completions (e.g. /model) should complete the
    name and surface argument completions instead of auto-running."""
    monkeypatch.setattr(
        "code_puppy.command_line.model_picker_completion.load_model_names",
        lambda: ["alpha-1", "beta-2"],
    )
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", PromptArea)
        prompt.text = "/mod"
        prompt.move_cursor((0, 4))
        app._refresh_completions()
        await pilot.pause(0.05)
        assert app.completion_visible()

        submitted = app.accept_completion(submit_if_terminal=True)
        await pilot.pause(0.05)
        # Did NOT submit; completed to "/model " and shows model-name args.
        assert submitted is False
        assert prompt.text.startswith("/model ")
        assert app.completion_visible()
