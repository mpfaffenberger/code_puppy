"""Phase 3: /uc tool browser screens."""

import pytest

from code_puppy.tui.app import build_app
from code_puppy.tui.screens.base import FilterableListScreen
from code_puppy.tui.screens.source_view import SourceViewScreen


class _Meta:
    def __init__(self, enabled):
        self.enabled = enabled


class _Tool:
    def __init__(self, full_name, enabled=True):
        self.full_name = full_name
        self.meta = _Meta(enabled)
        self.source_path = "/tmp/x.py"


def _patch_tools(monkeypatch, tools):
    monkeypatch.setattr(
        "code_puppy.command_line.uc_menu._get_tool_entries", lambda: tools
    )


@pytest.mark.asyncio
async def test_uc_opens_list(monkeypatch):
    _patch_tools(monkeypatch, [_Tool("alpha"), _Tool("beta", enabled=False)])
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/uc")
        await pilot.pause(0.2)
        assert isinstance(app.screen, FilterableListScreen)


@pytest.mark.asyncio
async def test_uc_empty_shows_no_modal(monkeypatch):
    _patch_tools(monkeypatch, [])
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/uc")
        await pilot.pause(0.2)
        assert not isinstance(app.screen, FilterableListScreen)


@pytest.mark.asyncio
async def test_uc_toggle(monkeypatch):
    _patch_tools(monkeypatch, [_Tool("alpha")])
    toggled = {}
    monkeypatch.setattr(
        "code_puppy.command_line.uc_menu._toggle_tool_enabled",
        lambda tool: toggled.setdefault("name", tool.full_name),
    )
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/uc")
        await pilot.pause(0.2)
        await pilot.press("enter")  # select the only tool -> action list
        await pilot.pause(0.1)
        await pilot.press("enter")  # first action = toggle
        await pilot.pause(0.1)
    assert toggled.get("name") == "alpha"


@pytest.mark.asyncio
async def test_uc_view_source(monkeypatch):
    _patch_tools(monkeypatch, [_Tool("alpha")])
    monkeypatch.setattr(
        "code_puppy.command_line.uc_menu._load_source_code",
        lambda tool: (["def x():", "    return 1"], None),
    )
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/uc")
        await pilot.pause(0.2)
        await pilot.press("enter")  # select tool -> action list
        await pilot.pause(0.1)
        await pilot.press(*"source")
        await pilot.pause(0.1)
        await pilot.press("enter")  # View source
        await pilot.pause(0.1)
        assert isinstance(app.screen, SourceViewScreen)
