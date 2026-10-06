"""CLI wiring: deferred agent reloads are applied right before each run."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import code_puppy.cli_runner as runner
from code_puppy.agents import clear_pending_agent_reloads, request_agent_reload
from code_puppy.agents.base_agent import BaseAgent
from code_puppy.cli_runner import execute_single_prompt
from tests.test_cli_runner_persistent_prompt import _drive_interactive


@pytest.fixture(autouse=True)
def _clean_queue():
    clear_pending_agent_reloads()
    yield
    clear_pending_agent_reloads()


@pytest.fixture
def helper_agent(monkeypatch):
    agent = MagicMock(spec=BaseAgent)
    agent.name = "helper"
    agent.get_user_prompt.return_value = ""
    for target in (
        "code_puppy.agents.get_current_agent",
        "code_puppy.agents.agent_manager.get_current_agent",
        "code_puppy.cli_runner.get_current_agent",
    ):
        monkeypatch.setattr(target, lambda: agent)
    monkeypatch.setattr("code_puppy.config.auto_save_session_if_enabled", lambda: None)
    monkeypatch.setattr(runner, "save_command_to_history", lambda _: None)
    return agent


@pytest.fixture
def reloads_seen_by_runs(monkeypatch, helper_agent):
    """Record how many rebuilds had happened when each run started."""
    seen = []

    async def run(*_args, **_kwargs):
        seen.append(helper_agent.reload_code_generation_agent.call_count)
        result = MagicMock(output="done")
        result.all_messages.return_value = []
        return result, None

    monkeypatch.setattr(runner, "run_prompt_with_attachments", run)
    return seen


async def _interactive(initial_command=None):
    await asyncio.wait_for(
        runner.interactive_mode(MagicMock(), initial_command=initial_command), 10
    )


async def test_initial_command_drains_reloads_before_the_run(
    monkeypatch, reloads_seen_by_runs
):
    _drive_interactive(monkeypatch, ["/exit"])
    request_agent_reload("helper")

    await _interactive(initial_command="go")

    assert reloads_seen_by_runs == [1]


async def test_request_during_idle_wait_is_applied_before_that_prompt_runs(
    monkeypatch, reloads_seen_by_runs
):
    _drive_interactive(monkeypatch, [])
    submissions = ["do it", "/exit"]

    async def idle_wait():
        request_agent_reload("helper")  # a worker finishes while the user types
        return submissions.pop(0)

    monkeypatch.setattr(
        "code_puppy.messaging.run_ui.wait_for_idle_submission", idle_wait
    )

    await _interactive()

    assert reloads_seen_by_runs == [1]


async def test_plugin_continuation_drains_reloads_before_its_run(
    monkeypatch, reloads_seen_by_runs
):
    _drive_interactive(monkeypatch, ["first", "/exit"])

    async def turn_end(*_args, **_kwargs):
        if len(reloads_seen_by_runs) == 1:
            request_agent_reload("helper")
            return [{"prompt": "second"}]
        return []

    monkeypatch.setattr("code_puppy.callbacks.on_interactive_turn_end", turn_end)

    await _interactive()

    assert reloads_seen_by_runs == [0, 1]


async def test_headless_prompt_drains_reloads_before_the_run(helper_agent):
    order = []
    helper_agent.reload_code_generation_agent.side_effect = lambda: order.append(
        "reload"
    )
    result = MagicMock(output="done")
    result.all_messages.return_value = []

    async def fake_run(*_args, **_kwargs):
        order.append("run")
        return result, MagicMock()

    request_agent_reload("helper")
    with (
        patch(
            "code_puppy.command_line.shell_passthrough.is_shell_passthrough",
            return_value=False,
        ),
        patch(
            "code_puppy.cli_runner.parse_prompt_attachments",
            return_value=SimpleNamespace(prompt="do it"),
        ),
        patch(
            "code_puppy.cli_runner.run_prompt_with_attachments",
            new=AsyncMock(side_effect=fake_run),
        ),
        patch("code_puppy.messaging.get_message_bus"),
        patch("code_puppy.session_lifecycle.persist_named_session"),
        patch("code_puppy.config.record_quick_resume_sessions"),
    ):
        await execute_single_prompt("do it", MagicMock())

    assert order == ["reload", "run"]
