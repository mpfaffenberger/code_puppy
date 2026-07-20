"""Phase 3: /uc two-panel tool browser screen."""

import pytest

from code_puppy.tui.app import build_app
from code_puppy.tui.screens.source_view import SourceViewScreen
from code_puppy.tui.screens.uc_tools import UCToolsScreen

_MOD = "code_puppy.tui.screens.uc_tools"


class _Meta:
    def __init__(self, name, enabled):
        self.name = name
        self.namespace = ""
        self.enabled = enabled
        self.version = "1.0.0"
        self.author = ""
        self.description = "A test tool."


class _Tool:
    def __init__(self, full_name, enabled=True):
        self._full = full_name
        self.meta = _Meta(full_name, enabled)
        self.signature = f"{full_name}() -> None"
        self.source_path = "/tmp/x.py"

    @property
    def full_name(self):
        return self._full


def _patch_tools(monkeypatch, tools):
    monkeypatch.setattr(f"{_MOD}._get_tool_entries", lambda: tools)


@pytest.mark.asyncio
async def test_uc_opens_list(monkeypatch):
    _patch_tools(monkeypatch, [_Tool("alpha"), _Tool("beta", enabled=False)])
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/uc")
        await pilot.pause(0.2)
        assert isinstance(app.screen, UCToolsScreen)


@pytest.mark.asyncio
async def test_uc_empty_still_opens_modal(monkeypatch):
    _patch_tools(monkeypatch, [])
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/uc")
        await pilot.pause(0.2)
        # Even with no tools, the friendly two-panel empty-state opens.
        assert isinstance(app.screen, UCToolsScreen)


@pytest.mark.asyncio
async def test_uc_toggle(monkeypatch):
    _patch_tools(monkeypatch, [_Tool("alpha")])
    toggled = {}
    monkeypatch.setattr(
        f"{_MOD}._toggle_tool_enabled",
        lambda tool: toggled.setdefault("name", tool.full_name),
    )
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/uc")
        await pilot.pause(0.2)
        assert isinstance(app.screen, UCToolsScreen)
        await pilot.press("e")  # toggle enabled
        await pilot.pause(0.1)
    assert toggled.get("name") == "alpha"


@pytest.mark.asyncio
async def test_uc_view_source(monkeypatch):
    _patch_tools(monkeypatch, [_Tool("alpha")])
    monkeypatch.setattr(
        f"{_MOD}._load_source_code",
        lambda tool: (["def x():", "    return 1"], None),
    )
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/uc")
        await pilot.pause(0.2)
        await pilot.press("enter")  # view source of highlighted tool
        await pilot.pause(0.1)
        assert isinstance(app.screen, SourceViewScreen)


@pytest.mark.asyncio
async def test_uc_delete_confirm(monkeypatch):
    _patch_tools(monkeypatch, [_Tool("alpha")])
    deleted = {}
    monkeypatch.setattr(
        f"{_MOD}._delete_tool",
        lambda tool: deleted.setdefault("name", tool.full_name),
    )
    app = build_app()
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        app.submit_prompt("/uc")
        await pilot.pause(0.2)
        await pilot.press("d")  # delete -> confirm modal
        await pilot.pause(0.1)
        await pilot.click("#opt-0")  # "Delete" (first option)
        await pilot.pause(0.1)
    assert deleted.get("name") == "alpha"
