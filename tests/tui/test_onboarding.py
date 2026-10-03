"""Phase 3: TUI onboarding slide deck."""

import pytest

from code_puppy.tui.app import build_app
from code_puppy.tui.screens.base import FilterableListScreen
from code_puppy.tui.screens.onboarding import OnboardingScreen


@pytest.fixture(autouse=True)
def _no_real_mark(monkeypatch):
    # Never touch the real onboarding-complete file from tests.
    monkeypatch.setattr(
        "code_puppy.command_line.onboarding_wizard.mark_onboarding_complete",
        lambda: None,
    )


@pytest.mark.asyncio
async def test_tutorial_opens_onboarding():
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/tutorial")
        await pilot.pause(0.2)
        assert isinstance(app.screen, OnboardingScreen)


@pytest.mark.asyncio
async def test_onboarding_skip_marks_complete(monkeypatch):
    marked = {}
    monkeypatch.setattr(
        "code_puppy.command_line.onboarding_wizard.mark_onboarding_complete",
        lambda: marked.setdefault("done", True),
    )
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/tutorial")
        await pilot.pause(0.2)
        await pilot.press("escape")
        await pilot.pause(0.1)
    assert marked.get("done") is True


@pytest.mark.asyncio
async def test_onboarding_pick_model_opens_picker():
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/tutorial")
        await pilot.pause(0.2)
        assert isinstance(app.screen, OnboardingScreen)
        # advance to the last slide, then pick a model
        for _ in range(3):
            await pilot.press("right")
            await pilot.pause(0.05)
        await pilot.click("#model")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FilterableListScreen)


@pytest.mark.asyncio
async def test_first_run_auto_shows_onboarding(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.command_line.onboarding_wizard.should_show_onboarding",
        lambda: True,
    )
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause(0.2)
        assert isinstance(app.screen, OnboardingScreen)
