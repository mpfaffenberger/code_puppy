"""Tests for main-loop agent reload requests from worker threads."""

import threading
from unittest.mock import MagicMock

from code_puppy.agents import (
    DeferredReloadQueue,
    apply_agent_reloads,
    clear_pending_agent_reloads,
    request_agent_reload,
)


def setup_function():
    clear_pending_agent_reloads()


def teardown_function():
    clear_pending_agent_reloads()


def test_pending_reload_rebuilds_active_agent_on_main_loop():
    agent = MagicMock(name="helper")
    agent.name = "helper"

    request_agent_reload("helper")
    apply_agent_reloads(lambda: agent)

    agent.refresh_config.assert_called_once_with()
    agent.reload_code_generation_agent.assert_called_once_with()


def test_pending_reload_waits_for_agent_to_become_active():
    queue = DeferredReloadQueue()
    inactive = MagicMock(name="other")
    inactive.name = "other"
    active = MagicMock(name="helper")
    active.name = "helper"

    queue.request("helper")
    queue.apply(lambda: inactive)
    queue.apply(lambda: active)

    active.refresh_config.assert_called_once_with()
    active.reload_code_generation_agent.assert_called_once_with()


def test_reload_failure_is_retried_and_then_evicted():
    queue = DeferredReloadQueue()
    agent = MagicMock(name="helper")
    agent.name = "helper"
    agent.reload_code_generation_agent.side_effect = RuntimeError("MCP not ready")

    queue.request("helper")
    for _ in range(3):
        queue.apply(lambda: agent)

    assert agent.reload_code_generation_agent.call_count == 3


def test_concurrent_requests_are_not_lost():
    queue = DeferredReloadQueue()
    names = [f"agent-{index}" for index in range(12)]
    agents = {name: MagicMock(name=name) for name in names}
    for name, agent in agents.items():
        agent.name = name

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
