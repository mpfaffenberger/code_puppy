"""Up/Down prompt-history recall in the Textual prompt box.

Mirrors the classic --interactive raw editor's Up=older/Down=newer behavior
(``HistoryNavigator`` in ``code_puppy/messaging/editor_history.py``), which
the TUI's ``PromptArea`` previously never wired up -- bare Up/Down just fell
through to TextArea's own (no-op, single-line) cursor movement.
"""

import pytest
from textual.widgets import TextArea

from code_puppy.tui.app import build_app


def _seed_history(monkeypatch, tmp_path, entries):
    """Write a FileHistory-format file and point COMMAND_HISTORY_FILE at it."""
    hist = tmp_path / "command_history.txt"
    lines = []
    for i, entry in enumerate(entries):
        lines.append(f"# 2026-01-01T00:00:0{i}")
        for line in entry.split("\n"):
            lines.append(f"+{line}")
        lines.append("")
    hist.write_text("\n".join(lines), encoding="utf-8")
    monkeypatch.setattr("code_puppy.config.COMMAND_HISTORY_FILE", str(hist))
    return hist


@pytest.mark.asyncio
async def test_up_recalls_previous_prompt(monkeypatch, tmp_path):
    _seed_history(monkeypatch, tmp_path, ["first prompt", "second prompt"])
    app = build_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", TextArea)
        prompt.focus()
        await pilot.press("up")
        await pilot.pause(0.1)
        assert prompt.text == "second prompt"


@pytest.mark.asyncio
async def test_up_up_walks_further_back(monkeypatch, tmp_path):
    _seed_history(monkeypatch, tmp_path, ["first prompt", "second prompt"])
    app = build_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", TextArea)
        prompt.focus()
        await pilot.press("up")
        await pilot.press("up")
        await pilot.pause(0.1)
        assert prompt.text == "first prompt"


@pytest.mark.asyncio
async def test_down_restores_working_text(monkeypatch, tmp_path):
    _seed_history(monkeypatch, tmp_path, ["first prompt", "second prompt"])
    app = build_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", TextArea)
        prompt.focus()
        for ch in "unsent draft":
            await pilot.press(ch)
        await pilot.pause(0.05)
        await pilot.press("up")  # -> "second prompt"
        await pilot.pause(0.05)
        await pilot.press("down")  # -> back to the working draft
        await pilot.pause(0.1)
        assert prompt.text == "unsent draft"


@pytest.mark.asyncio
async def test_submit_resets_history_browsing(monkeypatch, tmp_path):
    _seed_history(monkeypatch, tmp_path, ["first prompt"])
    app = build_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", TextArea)
        prompt.focus()
        app.submit_prompt("a brand new prompt")
        await pilot.pause(0.1)
        await pilot.press("up")
        await pilot.pause(0.1)
        # Fresh browse session: newest entry is the one just submitted.
        assert prompt.text == "a brand new prompt"


@pytest.mark.asyncio
async def test_up_at_empty_history_is_noop(monkeypatch, tmp_path):
    _seed_history(monkeypatch, tmp_path, [])
    app = build_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", TextArea)
        prompt.focus()
        await pilot.press("up")
        await pilot.pause(0.1)
        assert prompt.text == ""


@pytest.mark.asyncio
async def test_recalled_bare_command_does_not_open_completions(monkeypatch, tmp_path):
    """Regression: recalling a no-arg slash command (e.g. "/help") used to
    pop the completion dropdown open (it fully matches a command name), and
    the completion menu then swallowed the NEXT Up as menu navigation --
    getting the user stuck instead of continuing to walk further back.
    """
    _seed_history(monkeypatch, tmp_path, ["older prompt", "/help"])
    app = build_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt", TextArea)
        prompt.focus()
        await pilot.press("up")  # -> "/help"
        await pilot.pause(0.1)
        assert prompt.text == "/help"
        assert not app.completion_visible(), (
            "recalling a bare command should never open the completion menu"
        )
        await pilot.press("up")  # should keep walking back, not menu-navigate
        await pilot.pause(0.1)
        assert prompt.text == "older prompt"
