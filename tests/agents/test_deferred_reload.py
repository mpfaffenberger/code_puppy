"""Tests for main-loop agent reload requests from worker threads."""

import threading
import json
from unittest.mock import MagicMock, patch

from code_puppy.agents import (
    DeferredReloadQueue,
    apply_agent_reloads,
    clear_pending_agent_reloads,
    request_agent_reload,
)
from code_puppy.agents.base_agent import BaseAgent
from code_puppy.agents.json_agent import JSONAgent


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


def _json_agent(tmp_path, name: str):
    """Return (agent, rewrite) for a real JSON agent backed by a temp file."""
    path = tmp_path / "agent.json"
    config = {
        "name": name,
        "description": "test",
        "system_prompt": "test",
        "tools": [],
    }
    path.write_text(json.dumps(config))

    def rewrite(**changes):
        config.update(changes)
        for key in [k for k, v in changes.items() if v is None]:
            del config[key]
        path.write_text(json.dumps(config))

    return JSONAgent(str(path)), rewrite


def test_renamed_agent_consumes_the_request_it_was_selected_by(tmp_path):
    queue = DeferredReloadQueue()
    agent, rewrite = _json_agent(tmp_path, "old")
    queue.request("old")
    rewrite(name="new")

    with patch.object(agent, "reload_code_generation_agent") as reload:
        queue.apply(lambda: agent)
    stale = _agent("old")  # an unrelated agent that happens to use the old name
    queue.apply(lambda: stale)

    reload.assert_called_once_with()
    stale.reload_code_generation_agent.assert_not_called()


def test_rename_does_not_consume_another_agents_request(tmp_path):
    queue = DeferredReloadQueue()
    agent, rewrite = _json_agent(tmp_path, "old")
    queue.request("old")
    queue.request("new")
    rewrite(name="new")

    with patch.object(agent, "reload_code_generation_agent") as reload:
        queue.apply(lambda: agent)  # serves "old"
        queue.apply(lambda: agent)  # agent is now "new": its request survived

    assert reload.call_count == 2


def test_failed_rename_follows_the_agent_for_bounded_retries(tmp_path):
    queue = DeferredReloadQueue()
    agent, rewrite = _json_agent(tmp_path, "old")
    queue.request("old")
    rewrite(name="new")

    broken = RuntimeError("broken")
    with (
        patch.object(
            agent, "reload_code_generation_agent", side_effect=broken
        ) as reload,
        patch("code_puppy.agents.deferred_reload.emit_warning") as warn,
    ):
        for _ in range(4):
            queue.apply(lambda: agent)

    assert reload.call_count == 3
    warn.assert_called_once()
    assert "new" in warn.call_args.args[0]


def test_agent_losing_its_name_never_escapes_the_queue(tmp_path):
    queue = DeferredReloadQueue()
    agent, rewrite = _json_agent(tmp_path, "helper")
    queue.request("helper")
    rewrite(name=None)  # refresh_config validation now rejects the config

    for _ in range(2):  # failure handling, then later drains of a broken agent
        queue.apply(lambda: agent)
