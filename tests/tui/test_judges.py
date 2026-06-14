"""Phase 3 Wave C: /judges CRUD screens."""

import pytest

from code_puppy.plugins.wiggum.judge_config import JudgeConfig, JudgeRegistry
from code_puppy.tui.app import build_app
from code_puppy.tui.screens.base import FilterableListScreen
from code_puppy.tui.screens.form import FormScreen
from code_puppy.tui.screens.interactive import ConfirmModal


def _patch_models(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.command_line.model_picker_completion.load_model_names",
        lambda: ["m1", "m2"],
    )


@pytest.mark.asyncio
async def test_judges_lists_with_add_entry(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.plugins.wiggum.judge_config.load_judges",
        lambda: JudgeRegistry(judges=[JudgeConfig("strict", "m1")]),
    )
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/judges")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FilterableListScreen)


@pytest.mark.asyncio
async def test_judges_add_opens_form(monkeypatch):
    _patch_models(monkeypatch)
    monkeypatch.setattr(
        "code_puppy.plugins.wiggum.judge_config.load_judges",
        lambda: JudgeRegistry(judges=[]),
    )
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/judges")
        await pilot.pause(0.2)
        await pilot.press("enter")  # "+ Add a judge..." is first
        await pilot.pause(0.1)
        assert isinstance(app.screen, FormScreen)


@pytest.mark.asyncio
async def test_judge_select_then_delete_confirms(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.plugins.wiggum.judge_config.load_judges",
        lambda: JudgeRegistry(judges=[JudgeConfig("strict", "m1")]),
    )
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/judges")
        await pilot.pause(0.2)
        await pilot.press(*"strict")
        await pilot.pause(0.1)
        await pilot.press("enter")  # pick the judge -> action list
        await pilot.pause(0.1)
        assert isinstance(app.screen, FilterableListScreen)
        await pilot.press(*"delete")
        await pilot.pause(0.1)
        await pilot.press("enter")  # delete action -> confirm modal
        await pilot.pause(0.1)
        assert isinstance(app.screen, ConfirmModal)


def test_save_judge_persists(monkeypatch):
    saved = {}
    monkeypatch.setattr(
        "code_puppy.plugins.wiggum.judge_config.load_judges",
        lambda: JudgeRegistry(judges=[]),
    )
    monkeypatch.setattr(
        "code_puppy.plugins.wiggum.judge_config.save_judges",
        lambda reg: saved.update(judges=list(reg.judges)),
    )
    from code_puppy.tui.menu_judges import _save_judge

    _save_judge(
        None,
        {"name": "strict", "model": "m1", "prompt": "judge well", "enabled": True},
    )
    assert saved["judges"][0].name == "strict"
    assert saved["judges"][0].model == "m1"


def test_save_judge_rejects_bad_name(monkeypatch):
    errors = []
    monkeypatch.setattr(
        "code_puppy.messaging.emit_error", lambda msg, *a, **k: errors.append(msg)
    )
    from code_puppy.tui.menu_judges import _save_judge

    _save_judge(
        None, {"name": "bad name!", "model": "m1", "prompt": "", "enabled": True}
    )
    assert errors  # invalid name rejected
