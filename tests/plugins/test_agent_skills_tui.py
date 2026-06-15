"""Tests for the Textual /skills ModalScreen (SkillsScreen + open_skills)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from code_puppy.plugins.agent_skills.skills_tui import SkillsScreen, open_skills
from code_puppy.tui.app import build_app


def _skills():
    return [
        SimpleNamespace(name="alpha", path=Path("/tmp/alpha"), has_skill_md=True),
        SimpleNamespace(name="beta", path=Path("/tmp/beta"), has_skill_md=True),
    ]


def _meta(name):
    return SimpleNamespace(
        name=name,
        description=f"{name} does things",
        version="1.0",
        author="luc",
        tags=["x"],
    )


def _patches(disabled=frozenset(), enabled=True):
    return (
        patch(
            "code_puppy.plugins.agent_skills.discovery.discover_skills",
            return_value=_skills(),
        ),
        patch(
            "code_puppy.plugins.agent_skills.metadata.parse_skill_metadata",
            side_effect=lambda path: _meta(path.name),
        ),
        patch(
            "code_puppy.plugins.agent_skills.config.get_disabled_skills",
            return_value=set(disabled),
        ),
        patch(
            "code_puppy.plugins.agent_skills.config.get_skills_enabled",
            return_value=enabled,
        ),
    )


@pytest.mark.asyncio
async def test_skills_screen_lists_skills():
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            app.push_screen(SkillsScreen())
            await pilot.pause()
            from textual.widgets import OptionList

            items = app.screen.query_one("#items", OptionList)
            assert items.option_count == 2


@pytest.mark.asyncio
async def test_skills_screen_toggle_disables_skill():
    captured = {}

    def _set(name, disabled):
        captured["name"] = name
        captured["disabled"] = disabled

    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        p1, p2, p3, p4 = _patches()
        with (
            p1,
            p2,
            p3,
            p4,
            patch(
                "code_puppy.plugins.agent_skills.config.set_skill_disabled",
                _set,
            ),
        ):
            app.push_screen(SkillsScreen())
            await pilot.pause()
            app.screen.action_toggle()  # first row = alpha (enabled -> disabled)
            await pilot.pause(0.1)

    assert captured == {"name": "alpha", "disabled": True}


@pytest.mark.asyncio
async def test_skills_screen_toggle_global():
    captured = {}
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        p1, p2, p3, p4 = _patches(enabled=True)
        with (
            p1,
            p2,
            p3,
            p4,
            patch(
                "code_puppy.plugins.agent_skills.config.set_skills_enabled",
                lambda v: captured.setdefault("enabled", v),
            ),
        ):
            app.push_screen(SkillsScreen())
            await pilot.pause()
            app.screen.action_toggle_global()
            await pilot.pause(0.1)

    assert captured["enabled"] is False  # was enabled -> toggled off


@pytest.mark.asyncio
async def test_open_skills_pushes_screen():
    app = build_app()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        p1, p2, p3, p4 = _patches()
        with p1, p2, p3, p4:
            open_skills(app)
            await pilot.pause(0.1)
            assert isinstance(app.screen, SkillsScreen)
