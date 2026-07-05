"""/history: searchable previous-prompt picker (classic Ctrl+R replacement)."""

import pytest
from textual.widgets import TextArea

from code_puppy.tui.app import build_app
from code_puppy.tui.completion import compute_completions
from code_puppy.tui.screens.history_picker import HistoryScreen


def _patch_history(monkeypatch, prompts):
    monkeypatch.setattr(
        "code_puppy.tui.screens.history_picker.load_prompt_history",
        lambda: list(prompts),
    )


def test_history_is_completable():
    res = compute_completions("/hi", 3)
    assert res is not None
    assert "/history" in [i.display for i in res.items]


@pytest.mark.asyncio
async def test_history_command_opens_modal(monkeypatch):
    _patch_history(monkeypatch, ["alpha prompt", "beta prompt"])
    app = build_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.submit_prompt("/history")
        await pilot.pause(0.2)
        assert isinstance(app.screen, HistoryScreen)


@pytest.mark.asyncio
async def test_ctrl_r_opens_history(monkeypatch):
    # Ctrl+R is the classic reverse-search key; it now opens /history.
    _patch_history(monkeypatch, ["alpha prompt", "beta prompt"])
    app = build_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+r")
        await pilot.pause(0.2)
        assert isinstance(app.screen, HistoryScreen)


@pytest.mark.asyncio
async def test_history_empty_does_not_open(monkeypatch):
    _patch_history(monkeypatch, [])
    app = build_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.submit_prompt("/history")
        await pilot.pause(0.2)
        assert not isinstance(app.screen, HistoryScreen)


@pytest.mark.asyncio
async def test_history_filter_and_select_fills_prompt(monkeypatch):
    _patch_history(
        monkeypatch,
        ["refactor the auth module", "write some tests", "do a barrel roll"],
    )
    app = build_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.submit_prompt("/history")
        await pilot.pause(0.2)
        assert isinstance(app.screen, HistoryScreen)
        await pilot.press(*"barrel")  # filter narrows to the matching prompt
        await pilot.pause(0.1)
        await pilot.press("enter")  # pick it
        await pilot.pause(0.2)
        # The chosen prompt lands in the input box, ready to edit/send.
        assert app.query_one("#prompt", TextArea).text == "do a barrel roll"


@pytest.mark.asyncio
async def test_history_dismiss_button_closes(monkeypatch):
    _patch_history(monkeypatch, ["one", "two"])
    app = build_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        app.submit_prompt("/history")
        await pilot.pause(0.2)
        assert isinstance(app.screen, HistoryScreen)
        await pilot.click("#dismiss")
        await pilot.pause(0.2)
        assert not isinstance(app.screen, HistoryScreen)


def test_load_prompt_history_dedupes(monkeypatch, tmp_path):
    # FileHistory format: '# ts' then '+line' per entry. Newest-first on load.
    hist = tmp_path / "command_history.txt"
    hist.write_text(
        "\n".join(
            [
                "# 2026-01-01T00:00:00",
                "+older",
                "",
                "# 2026-01-01T00:00:01",
                "+dupe",
                "",
                "# 2026-01-01T00:00:02",
                "+dupe",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("code_puppy.config.COMMAND_HISTORY_FILE", str(hist))
    from code_puppy.tui.screens.history_picker import load_prompt_history

    out = load_prompt_history()
    assert out == ["dupe", "older"]  # newest-first, deduped
