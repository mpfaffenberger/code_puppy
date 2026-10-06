"""Tests for main-loop agent reload requests from worker threads."""

import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from code_puppy.agents import (
    DeferredReloadQueue,
    apply_agent_reloads,
    clear_pending_agent_reloads,
    request_agent_reload,
)
from code_puppy.agents.base_agent import BaseAgent
from code_puppy.cli_runner import execute_single_prompt


def setup_function():
    clear_pending_agent_reloads()


def teardown_function():
    clear_pending_agent_reloads()


def _agent(name: str) -> MagicMock:
    agent = MagicMock(spec=BaseAgent)
    agent.name = name
    return agent


def test_base_agent_refresh_config_is_a_noop():
    class StaticAgent(BaseAgent):
        name = "static"
        display_name = "Static"
        description = "static test agent"

        def get_system_prompt(self):
            return ""

        def get_available_tools(self):
            return []

    assert StaticAgent().refresh_config() is None


def test_pending_reload_rebuilds_active_agent_on_main_loop():
    agent = _agent("helper")

    request_agent_reload("helper")
    apply_agent_reloads(lambda: agent)

    agent.refresh_config.assert_called_once_with()
    agent.reload_code_generation_agent.assert_called_once_with()


def test_pending_reload_waits_for_agent_to_become_active():
    queue = DeferredReloadQueue()
    inactive = _agent("other")
    active = _agent("helper")

    queue.request("helper")
    queue.apply(lambda: inactive)
    queue.apply(lambda: active)

    active.refresh_config.assert_called_once_with()
    active.reload_code_generation_agent.assert_called_once_with()


def test_completed_reload_is_not_repeated():
    queue = DeferredReloadQueue()
    agent = _agent("helper")

    queue.request("helper")
    queue.apply(lambda: agent)
    queue.apply(lambda: agent)

    agent.reload_code_generation_agent.assert_called_once_with()


def test_reload_failure_is_retried_then_evicted_with_user_warning():
    queue = DeferredReloadQueue()
    agent = _agent("helper")
    agent.reload_code_generation_agent.side_effect = RuntimeError("MCP not ready")

    queue.request("helper")
    with patch("code_puppy.agents.deferred_reload.emit_warning") as warn:
        for _ in range(2):
            queue.apply(lambda: agent)
        warn.assert_not_called()  # silent until attempts run out
        queue.apply(lambda: agent)
        queue.apply(lambda: agent)  # evicted: no fourth attempt

    assert agent.reload_code_generation_agent.call_count == 3
    warn.assert_called_once()
    assert "MCP not ready" in warn.call_args.args[0]


def test_fresh_request_resets_retry_budget():
    queue = DeferredReloadQueue()
    agent = _agent("helper")
    agent.reload_code_generation_agent.side_effect = RuntimeError("boom")

    queue.request("helper")
    queue.apply(lambda: agent)
    queue.apply(lambda: agent)  # two of three attempts used
    queue.request("helper")  # config changed again
    with patch("code_puppy.agents.deferred_reload.emit_warning"):
        for _ in range(4):
            queue.apply(lambda: agent)

    assert agent.reload_code_generation_agent.call_count == 2 + 3


def test_request_during_reload_is_not_lost():
    queue = DeferredReloadQueue()
    agent = _agent("helper")
    calls = []

    def reload_and_request_again():
        calls.append(1)
        if len(calls) == 1:
            queue.request("helper")  # config changed again mid-rebuild

    agent.reload_code_generation_agent.side_effect = reload_and_request_again

    queue.request("helper")
    queue.apply(lambda: agent)
    queue.apply(lambda: agent)

    assert agent.reload_code_generation_agent.call_count == 2


def test_concurrent_requests_are_not_lost():
    queue = DeferredReloadQueue()
    names = [f"agent-{index}" for index in range(12)]
    agents = {name: _agent(name) for name in names}

    threads = [threading.Thread(target=queue.request, args=(name,)) for name in names]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    for name in names:
        queue.apply(lambda name=name: agents[name])

    for agent in agents.values():
        agent.refresh_config.assert_called_once_with()
        agent.reload_code_generation_agent.assert_called_once_with()


def test_requests_racing_with_drain_leave_nothing_pending():
    queue = DeferredReloadQueue()
    agent = _agent("helper")
    producers_done = threading.Event()

    def produce():
        for _ in range(200):
            queue.request("helper")

    def drain():
        while not producers_done.is_set():
            queue.apply(lambda: agent)

    producers = [threading.Thread(target=produce) for _ in range(8)]
    drainer = threading.Thread(target=drain)
    drainer.start()
    for thread in producers:
        thread.start()
    for thread in producers:
        thread.join()
    producers_done.set()
    drainer.join()

    queue.apply(lambda: agent)  # drain whatever arrived after the last pass
    settled = agent.reload_code_generation_agent.call_count
    queue.apply(lambda: agent)

    assert settled >= 1
    assert agent.reload_code_generation_agent.call_count == settled


async def test_headless_prompt_drains_reloads_before_the_run():
    order = []
    agent = _agent("helper")
    agent.reload_code_generation_agent.side_effect = lambda: order.append("reload")
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
        patch("code_puppy.cli_runner.get_current_agent", return_value=agent),
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
