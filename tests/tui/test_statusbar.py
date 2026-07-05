"""The TUI status bar mirrors the classic prompt exactly.

Both modes call ``get_prompt_with_active_model`` so any monkey-patches
(context_indicator, custom statusline command, …) automatically apply to both.
"""

import pytest
from prompt_toolkit.formatted_text import FormattedText
from textual.widgets import Static

from code_puppy.tui.app import build_app


def _status_text(app) -> str:
    bar = app.query_one("#statusbar", Static)
    return str(getattr(bar, "_cp_renderable", ""))


def _fake_prompt(frags: list[tuple[str, str]]):
    """Return a zero-arg lambda that returns FormattedText(frags)."""
    pt = FormattedText(frags)

    def _fn(base: str = ">>> "):  # noqa: ARG001
        return pt

    return _fn


@pytest.mark.asyncio
async def test_statusbar_renders_classic_prompt_fields(monkeypatch):
    """Status bar shows the same model/agent/cwd as the classic prompt."""
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_prompt_with_active_model",
        _fake_prompt(
            [
                ("bold", " "),
                ("class:puppy", "code-puppy"),
                ("", " "),
                ("class:agent", "[code-puppy] "),
                ("class:model", "[claude-test-8] "),
                ("class:cwd", "(~/workspace/code-puppy) "),
                ("class:arrow", ">>> "),
            ]
        ),
    )
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause(0.3)  # let the threaded refresh land
        text = _status_text(app)

    assert "[claude-test-8]" in text
    assert "code-puppy" in text
    assert "~/workspace/code-puppy" in text
    # arrow must NOT appear in the status bar
    assert ">>> " not in text


@pytest.mark.asyncio
async def test_statusbar_reflects_context_indicator(monkeypatch):
    """Context-indicator emoji (already injected by the classic patch) shows up."""
    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_prompt_with_active_model",
        _fake_prompt(
            [
                ("bold", " "),
                ("class:context-indicator", " "),
                ("class:puppy", "code-puppy"),
                ("", " "),
                ("class:model", "[fast-model] "),
                ("class:cwd", "(~/proj) "),
                ("class:arrow", ">>> "),
            ]
        ),
    )
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause(0.3)
        text = _status_text(app)

    assert "" in text
    assert "[fast-model]" in text


@pytest.mark.asyncio
async def test_statusbar_reflects_custom_statusline_command(monkeypatch):
    """Custom command output uses Text.from_ansi() — no lossy style conversion.

    When is_enabled()+get_command() are truthy, _build_status_text() calls
    get_status_text() and feeds the raw ANSI string straight to
    Text.from_ansi().  This is the lossless path that preserves colors.
    """
    import code_puppy.plugins.statusline.config as _cfg
    import code_puppy.plugins.statusline.runner as _runner

    monkeypatch.setattr(_cfg, "is_enabled", lambda: True)
    monkeypatch.setattr(_cfg, "get_command", lambda: "echo test")
    # Raw ANSI string exactly as a shell command would produce it.
    monkeypatch.setattr(
        _runner,
        "get_status_text",
        lambda: (
            "\033[36m[my-model]\033[0m \033[35m(main)\033[0m \033[33m1.2%ctx\033[0m"
        ),
    )
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause(0.3)
        text = _status_text(app)

    assert "[my-model]" in text
    assert "(main)" in text
    assert "1.2%ctx" in text
    assert ">>> " not in text


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
async def test_statusbar_degrades_gracefully_on_exception(monkeypatch):
    """If get_prompt_with_active_model raises, status bar doesn't crash."""

    def _boom(base: str = ">>> "):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(
        "code_puppy.command_line.prompt_toolkit_completion.get_prompt_with_active_model",
        _boom,
    )
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause(0.3)
        # just don't crash; status bar may be empty
        _status_text(app)
