"""Phase 2b: cancel + steer control plane.

Escape cancels a running turn; Ctrl+T pauses and injects a steering message.
"""

import asyncio

import pytest

from code_puppy.messaging import (
    PauseAgentCommand,
    ResumeAgentCommand,
    SteerAgentCommand,
    get_message_bus,
)
from code_puppy.tui.app import build_app
from code_puppy.tui.screens.interactive import TextInputModal


class _FakeAgent:
    def set_message_history(self, history):
        pass


def _stub_long_agent(monkeypatch):
    async def fake_run(_agent, _task, *, display_console=None, use_run_ui=True):
        await asyncio.sleep(30)  # long-running, cancellable
        return None, None

    monkeypatch.setattr("code_puppy.agents.get_current_agent", lambda: _FakeAgent())
    monkeypatch.setattr("code_puppy.cli_runner.run_prompt_with_attachments", fake_run)
    monkeypatch.setattr("code_puppy.config.auto_save_session_if_enabled", lambda: None)


async def _wait(pilot, cond, tries=80):
    for _ in range(tries):
        await pilot.pause(0.02)
        if cond():
            return True
    return False


@pytest.mark.asyncio
async def test_escape_cancels_running_turn(monkeypatch):
    _stub_long_agent(monkeypatch)
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("a long task")
        assert await _wait(pilot, lambda: app._busy), "never became busy"
        app.action_cancel_turn()
        assert await _wait(pilot, lambda: not app._busy), "busy never cleared"


@pytest.mark.asyncio
async def test_ctrl_x_kills_running_shells(monkeypatch):
    """Ctrl+X in the TUI kills in-flight shell processes directly (no raw
    stdin listener), and reports how many it interrupted."""
    calls = {}
    monkeypatch.setattr(
        "code_puppy.tools.command_runner.kill_all_running_shell_processes",
        lambda: calls.setdefault("n", 3),
    )
    emitted = []
    bus = get_message_bus()
    monkeypatch.setattr(bus, "emit", lambda m: emitted.append(m))

    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_interrupt_shell()
        await pilot.pause(0.05)

    assert calls.get("n") == 3
    assert any("Interrupted 3" in getattr(m, "text", "") for m in emitted)


@pytest.mark.asyncio
async def test_ctrl_x_quiet_when_no_shells(monkeypatch):
    """With nothing running, Ctrl+X stays silent (no warning noise)."""
    monkeypatch.setattr(
        "code_puppy.tools.command_runner.kill_all_running_shell_processes",
        lambda: 0,
    )
    emitted = []
    bus = get_message_bus()
    monkeypatch.setattr(bus, "emit", lambda m: emitted.append(m))

    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_interrupt_shell()
        await pilot.pause(0.05)

    assert not any("Interrupted" in getattr(m, "text", "") for m in emitted)


@pytest.mark.asyncio
async def test_steer_when_idle_does_nothing(monkeypatch):
    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_steer()
        await pilot.pause(0.1)
        assert not isinstance(app.screen, TextInputModal)


@pytest.mark.asyncio
async def test_steer_pauses_and_injects(monkeypatch):
    _stub_long_agent(monkeypatch)
    captured = []
    bus = get_message_bus()
    monkeypatch.setattr(bus, "provide_response", lambda cmd: captured.append(cmd))

    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("a long task")
        assert await _wait(pilot, lambda: app._busy), "never became busy"

        app.action_steer()
        assert await _wait(pilot, lambda: isinstance(app.screen, TextInputModal))
        # Pause was requested as soon as steering opened.
        assert any(isinstance(c, PauseAgentCommand) for c in captured)

        await pilot.press(*"use a dict instead")
        await pilot.press("enter")
        await pilot.pause(0.1)

        steers = [c for c in captured if isinstance(c, SteerAgentCommand)]
        assert len(steers) == 1
        assert steers[0].text == "use a dict instead"
        assert any(isinstance(c, ResumeAgentCommand) for c in captured)

        app.action_cancel_turn()  # clean up the long worker
        await _wait(pilot, lambda: not app._busy)


@pytest.mark.asyncio
async def test_steer_cancel_resumes_without_steer(monkeypatch):
    _stub_long_agent(monkeypatch)
    captured = []
    bus = get_message_bus()
    monkeypatch.setattr(bus, "provide_response", lambda cmd: captured.append(cmd))

    app = build_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.submit_prompt("a long task")
        assert await _wait(pilot, lambda: app._busy)

        app.action_steer()
        assert await _wait(pilot, lambda: isinstance(app.screen, TextInputModal))
        await pilot.press("escape")  # cancel the steer modal
        await pilot.pause(0.1)

        assert not any(isinstance(c, SteerAgentCommand) for c in captured)
        assert any(isinstance(c, ResumeAgentCommand) for c in captured)

        app.action_cancel_turn()
        await _wait(pilot, lambda: not app._busy)
