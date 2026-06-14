"""CooperApp boots headlessly and the bus -> renderer path works (no TTY).

Phase 2a tests stub the agent run so no model/network is touched.
"""

import pytest
from textual.containers import VerticalScroll

from code_puppy.tui.app import build_app
from code_puppy.tui.renderer import message_to_renderable
from code_puppy.messaging import MessageLevel, TextMessage


class _FakeResult:
    output = "All **done**!"

    def all_messages(self):
        return []


class _FakeAgent:
    def __init__(self):
        self.history = None

    def set_message_history(self, history):
        self.history = history


def _log_entries(app):
    """Number of mounted scrollback entries (Static / Markdown widgets)."""
    return len(app.query_one("#log", VerticalScroll).children)


def _stub_agent_run(monkeypatch):
    """Patch the lazy imports inside CooperApp._run_agent_turn."""
    agent = _FakeAgent()

    async def fake_run(_agent, _task, **_kwargs):
        return _FakeResult(), None

    monkeypatch.setattr("code_puppy.agents.get_current_agent", lambda: agent)
    monkeypatch.setattr("code_puppy.cli_runner.run_prompt_with_attachments", fake_run)
    monkeypatch.setattr("code_puppy.config.auto_save_session_if_enabled", lambda: None)
    return agent


@pytest.mark.asyncio
async def test_app_boots_and_renders_startup_message():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Startup success message was buffered then drained by the renderer.
        assert _log_entries(app) >= 1


@pytest.mark.asyncio
async def test_submit_prompt_runs_agent_and_renders_response(monkeypatch):
    agent = _stub_agent_run(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        before = _log_entries(app)
        app.submit_prompt("do a thing")
        for _ in range(60):
            await pilot.pause(0.05)
            if _log_entries(app) > before and not app._busy:
                break
        assert _log_entries(app) > before
        # The submitted prompt is echoed into the scrollback (so a scrolled-back
        # response still shows its question).
        assert ">>> do a thing" in app.log_text()
        # The agent's history was updated and busy state cleared.
        assert agent.history == []
        assert app._busy is False


@pytest.mark.asyncio
async def test_exit_command_quits():
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("/exit")
        await pilot.pause(0.1)
    # Exiting the run_test context without error is the assertion.


@pytest.mark.asyncio
async def test_slash_command_does_not_run_agent(monkeypatch):
    ran = {"agent": False}

    async def fake_run(_agent, _task, **_kwargs):
        ran["agent"] = True
        return None, None

    monkeypatch.setattr("code_puppy.cli_runner.run_prompt_with_attachments", fake_run)
    # /help is a registered command -> handled, must not reach the agent.
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("/help")
        await pilot.pause(0.2)
        assert ran["agent"] is False


@pytest.mark.asyncio
async def test_initial_command_is_submitted_on_mount(monkeypatch):
    _stub_agent_run(monkeypatch)
    app = build_app(initial_command="do the thing")
    async with app.run_test() as pilot:
        for _ in range(60):
            await pilot.pause(0.05)
            if _log_entries(app) > 1 and not app._busy:
                break
        assert _log_entries(app) > 1


def test_message_to_renderable_handles_text_and_fallback():
    from rich.text import Text

    r = message_to_renderable(TextMessage(level=MessageLevel.INFO, text="hi"))
    assert isinstance(r, Text)
    assert "hi" in r.plain

    # An unknown message type must not crash; it falls back to a dim repr.
    class _Weird:
        def __repr__(self):
            return "<weird>"

    fallback = message_to_renderable(_Weird())
    assert isinstance(fallback, Text)
