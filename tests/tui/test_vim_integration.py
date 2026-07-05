"""Integration: vim mode driving a real PromptArea inside CooperApp.

Exercises the adapter (offset <-> row/col, Selection writeback) and the
`/vim` toggle through the actual Textual key pipeline.
"""

import pytest

from code_puppy.tui.app import PromptArea, build_app


def _prompt(app) -> PromptArea:
    return app.query_one("#prompt", PromptArea)


@pytest.mark.asyncio
async def test_vim_disabled_by_default(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda key: None)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.vim_enabled is False
        prompt = _prompt(app)
        prompt.focus()
        await pilot.press("h", "i")
        await pilot.pause()
        # Plain typing works when vim is off.
        assert prompt.text == "hi"


@pytest.mark.asyncio
async def test_toggle_vim_and_normal_mode_navigation(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda key: None)
    monkeypatch.setattr("code_puppy.config.set_config_value", lambda *a, **k: None)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.toggle_vim_mode() is True
        app.update_vim_indicator()
        prompt = _prompt(app)
        prompt.focus()
        # In INSERT mode typing flows straight through.
        await pilot.press("h", "e", "l", "l", "o")
        await pilot.pause()
        assert prompt.text == "hello"
        # ESC -> NORMAL, then 'x' deletes a char.
        await pilot.press("escape")
        await pilot.pause()
        assert app.vim_state.mode == "normal"
        await pilot.press("0", "x")
        await pilot.pause()
        assert prompt.text == "ello"


@pytest.mark.asyncio
async def test_border_title_reflects_mode(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda key: None)
    monkeypatch.setattr("code_puppy.config.set_config_value", lambda *a, **k: None)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.toggle_vim_mode()
        prompt = _prompt(app)
        prompt.focus()
        app.update_vim_indicator()
        assert "INSERT" in str(prompt.border_subtitle)
        await pilot.press("escape")
        await pilot.pause()
        assert "NORMAL" in str(prompt.border_subtitle)


@pytest.mark.asyncio
async def test_enter_still_submits_in_normal_mode(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda key: None)
    monkeypatch.setattr("code_puppy.config.set_config_value", lambda *a, **k: None)
    app = build_app()
    submitted = []
    async with app.run_test() as pilot:
        await pilot.pause()
        app.toggle_vim_mode()
        monkeypatch.setattr(app, "submit_prompt", lambda text: submitted.append(text))
        prompt = _prompt(app)
        prompt.focus()
        await pilot.press("h", "i")
        await pilot.press("escape")  # NORMAL
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert submitted == ["hi"]
        # Submitting resets to INSERT for the next prompt.
        assert app.vim_state.mode == "insert"


@pytest.mark.asyncio
async def test_vim_command_toggles(monkeypatch):
    monkeypatch.setattr("code_puppy.config.get_value", lambda key: None)
    monkeypatch.setattr("code_puppy.config.set_config_value", lambda *a, **k: None)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.vim_enabled is False
        handled = app._dispatch_command("/vim")
        assert handled is True
        assert app.vim_enabled is True
