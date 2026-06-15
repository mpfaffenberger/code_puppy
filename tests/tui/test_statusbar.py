"""The bottom status bar mirrors the classic status line (model/agent/branch/ctx)."""

import pytest
from textual.widgets import Static

from code_puppy.tui.app import build_app


def _status_text(app):
    bar = app.query_one("#statusbar", Static)
    return str(getattr(bar, "_cp_renderable", ""))


@pytest.mark.asyncio
async def test_statusbar_renders_model(monkeypatch):
    # Deterministic payload so the assertion doesn't depend on the environment.
    monkeypatch.setattr(
        "code_puppy.plugins.statusline.payload.build_payload",
        lambda: {
            "model": {"display_name": "claude-test-8"},
            "agent": {"name": "code-puppy"},
            "workspace": {"git_branch": "feature/add-tui"},
            "context_window": {"used_percentage": 1.7, "indicator": "\U0001f7e2"},
        },
    )
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause(0.3)  # let the threaded refresh land
        text = _status_text(app)
    assert "[claude-test-8]" in text
    assert "code-puppy" in text
    assert "(feature/add-tui)" in text
    assert "1.7%ctx" in text


@pytest.mark.asyncio
async def test_statusbar_sits_between_footer_keys_and_palette():
    from textual.widgets import Footer

    app = build_app()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        await pilot.pause(0.2)
        footer = app.query_one(Footer)
        sb = app.query_one("#statusbar", Static)
        palette = app.query_one("#palettehint", Static)
        # All on the same row: keys | palette hint | status (fills, right).
        assert footer.region.y == sb.region.y == palette.region.y
        assert footer.region.right <= palette.region.x
        assert palette.region.right <= sb.region.x


@pytest.mark.asyncio
async def test_statusbar_degrades_without_optional_fields(monkeypatch):
    # Only a model -> no agent/branch/ctx, but no crash and model still shows.
    monkeypatch.setattr(
        "code_puppy.plugins.statusline.payload.build_payload",
        lambda: {
            "model": {"display_name": "m1"},
            "workspace": {},
            "context_window": {},
        },
    )
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause(0.3)
        text = _status_text(app)
    assert "[m1]" in text
    assert "%ctx" not in text
