"""Tests for main-loop agent reload requests from worker threads."""

import json
import threading
from unittest.mock import MagicMock, patch

import pytest
from rich.text import Text

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
    with patch("code_puppy.agents.deferred_reload.emit_info") as info:
        queue.apply(lambda: inactive)
        info.assert_not_called()
        queue.apply(lambda: active)
        info.assert_called_once()

    active.refresh_config.assert_called_once_with()
    active.reload_code_generation_agent.assert_called_once_with()


def test_completed_reload_is_not_repeated():
    queue = DeferredReloadQueue()
    agent = _agent("[bold]helper[/bold]")

    queue.request(agent.name)
    with patch("code_puppy.agents.deferred_reload.emit_info") as info:
        queue.apply(lambda: agent)
        queue.apply(lambda: agent)

    agent.reload_code_generation_agent.assert_called_once_with()
    info.assert_called_once()
    message = info.call_args.args[0]
    assert isinstance(message, Text)
    assert message.plain == "Active agent '[bold]helper[/bold]' reloaded"
    assert message.spans == []


def test_no_pending_reload_does_not_emit_success():
    queue = DeferredReloadQueue()
    agent = _agent("helper")

    with patch("code_puppy.agents.deferred_reload.emit_info") as info:
        queue.apply(lambda: agent)

    agent.refresh_config.assert_not_called()
    agent.reload_code_generation_agent.assert_not_called()
    info.assert_not_called()


def test_failed_reload_is_retried_in_the_drain_then_evicted_with_user_warning():
    queue = DeferredReloadQueue()
    agent = _agent("helper")
    agent.reload_code_generation_agent.side_effect = RuntimeError("MCP not ready")

    queue.request("helper")
    with (
        patch("code_puppy.agents.deferred_reload.emit_warning") as warn,
        patch("code_puppy.agents.deferred_reload.emit_info") as info,
    ):
        queue.apply(lambda: agent)
        queue.apply(lambda: agent)  # evicted: no further attempts

    info.assert_not_called()

    assert agent.reload_code_generation_agent.call_count == 3
    warn.assert_called_once()
    assert "MCP not ready" in warn.call_args.args[0]


def test_transient_failure_recovers_within_the_drain_without_warning():
    queue = DeferredReloadQueue()
    agent = _agent("helper")
    agent.reload_code_generation_agent.side_effect = [RuntimeError("x"), None]

    queue.request("helper")
    with (
        patch("code_puppy.agents.deferred_reload.emit_warning") as warn,
        patch("code_puppy.agents.deferred_reload.emit_info") as info,
    ):
        queue.apply(lambda: agent)
        queue.apply(lambda: agent)

    assert agent.reload_code_generation_agent.call_count == 2
    warn.assert_not_called()
    info.assert_called_once()
    assert info.call_args.args[0].plain == "Active agent 'helper' reloaded"


def test_request_during_failing_rebuild_gets_its_own_full_budget():
    queue = DeferredReloadQueue()
    agent = _agent("helper")
    calls = []

    def fail_and_request_again():
        calls.append(1)
        if len(calls) == 1:
            queue.request("helper")  # config changed again mid-rebuild
        raise RuntimeError("boom")

    agent.reload_code_generation_agent.side_effect = fail_and_request_again

    queue.request("helper")
    with patch("code_puppy.agents.deferred_reload.emit_warning") as warn:
        queue.apply(lambda: agent)  # superseded: stops after one attempt
        assert len(calls) == 1
        warn.assert_not_called()
        queue.apply(lambda: agent)  # the fresh request spends three of its own

    assert len(calls) == 1 + 3
    warn.assert_called_once()


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
    with patch("code_puppy.agents.deferred_reload.emit_info") as info:
        queue.apply(lambda: agent)
        info.assert_not_called()  # successful rebuild, but superseded generation
        queue.apply(lambda: agent)
        queue.apply(lambda: agent)

    assert agent.reload_code_generation_agent.call_count == 2
    info.assert_called_once()


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


def test_failed_rebuild_of_a_renamed_agent_stays_bounded_and_quiet(tmp_path):
    queue = DeferredReloadQueue()
    agent, rewrite = _json_agent(tmp_path, "old")
    queue.request("old")
    rewrite(name="new")

    with (
        patch.object(
            agent, "reload_code_generation_agent", side_effect=RuntimeError("broken")
        ) as reload,
        patch("code_puppy.agents.deferred_reload.emit_warning") as warn,
    ):
        for _ in range(3):
            queue.apply(lambda: agent)

    assert reload.call_count == 3
    warn.assert_called_once()


def test_rename_collision_leaves_the_other_request_untouched(tmp_path):
    queue = DeferredReloadQueue()
    target = _agent("new")
    target.reload_code_generation_agent.side_effect = RuntimeError("earlier config")
    agent, rewrite = _json_agent(tmp_path, "old")
    with patch("code_puppy.agents.deferred_reload.emit_warning") as warn:
        queue.request("new")
        queue.apply(lambda: target)  # spends the whole budget of "new"
        queue.request("new")
        queue.request("old")
        rewrite(name="new")
        with patch.object(
            agent, "reload_code_generation_agent", side_effect=RuntimeError("old")
        ):
            queue.apply(lambda: agent)  # fails "old" three times
        target.reload_code_generation_agent.reset_mock()
        queue.apply(lambda: target)  # "new" still pending, full budget

    assert target.reload_code_generation_agent.call_count == 3
    assert warn.call_count == 3


def test_request_during_failing_renamed_rebuild_is_retried_for_its_own_name(
    tmp_path,
):
    queue = DeferredReloadQueue()
    agent, rewrite = _json_agent(tmp_path, "old")
    queue.request("old")
    rewrite(name="new")
    calls = []

    def fail_and_request_new():
        calls.append(1)
        if len(calls) == 1:
            queue.request("new")
        raise RuntimeError("failure")

    with (
        patch.object(
            agent, "reload_code_generation_agent", side_effect=fail_and_request_new
        ),
        patch("code_puppy.agents.deferred_reload.emit_warning"),
    ):
        for _ in range(5):
            queue.apply(lambda: agent)

    assert len(calls) == 3 + 3  # old: three attempts, then "new": its own three


def test_threaded_request_during_failing_rebuild_is_not_orphaned():
    queue = DeferredReloadQueue()
    agent = _agent("helper")
    started, requested = threading.Event(), threading.Event()
    calls = []

    def producer():
        started.wait()
        queue.request("helper")
        requested.set()

    def rebuild():
        calls.append(1)
        if len(calls) == 1:
            started.set()
            assert requested.wait(5)
        raise RuntimeError("failure")

    agent.reload_code_generation_agent.side_effect = rebuild
    thread = threading.Thread(target=producer)
    thread.start()
    queue.request("helper")
    with patch("code_puppy.agents.deferred_reload.emit_warning"):
        queue.apply(lambda: agent)
        thread.join()
        queue.apply(lambda: agent)

    assert len(calls) == 1 + 3


def test_missing_name_fails_quietly_and_recovers_after_the_file_is_repaired(
    tmp_path,
):
    queue = DeferredReloadQueue()
    agent, rewrite = _json_agent(tmp_path, "old")
    queue.request("old")
    rewrite(name=None)  # refresh_config validation rejects this edit

    with (
        patch.object(agent, "reload_code_generation_agent") as reload,
        patch("code_puppy.agents.deferred_reload.emit_warning") as warn,
    ):
        queue.apply(lambda: agent)  # rejected edit: bounded, warned, evicted
        warn.assert_called_once()
        reload.assert_not_called()
        rewrite(name="old")  # user repairs the file and asks again
        queue.request("old")
        queue.apply(lambda: agent)

    assert agent.name == "old"
    reload.assert_called_once_with()


@pytest.mark.parametrize("bad_name", [[], {}, 7, None, ""])
def test_unusable_agent_name_is_skipped_without_touching_the_queue(bad_name):
    queue = DeferredReloadQueue()
    agent = _agent("helper")
    agent.name = bad_name

    queue.request("helper")
    queue.apply(lambda: agent)  # must not raise (e.g. unhashable names)
    agent.name = "helper"
    queue.apply(lambda: agent)  # the real request is still there

    agent.reload_code_generation_agent.assert_called_once_with()


def test_malformed_name_written_into_the_config_never_escapes_the_queue(tmp_path):
    queue = DeferredReloadQueue()
    agent, rewrite = _json_agent(tmp_path, "old")
    queue.request("old")
    rewrite(name=[])  # passes JSONAgent validation but is not a usable name

    with (
        patch.object(
            agent, "reload_code_generation_agent", side_effect=RuntimeError("bad")
        ),
        patch("code_puppy.agents.deferred_reload.emit_warning") as warn,
    ):
        queue.apply(lambda: agent)  # failure handling must not use the new name
        queue.apply(lambda: agent)  # later drains skip the unusable name

    warn.assert_called_once()


def test_rejected_config_edit_leaves_the_live_json_agent_intact(tmp_path):
    agent, rewrite = _json_agent(tmp_path, "old")
    rewrite(name=None)

    with pytest.raises(ValueError, match="name"):
        agent.refresh_config()

    assert agent.name == "old"


def test_request_between_retries_stops_the_obsolete_drain():
    queue = DeferredReloadQueue()
    agent = _agent("helper")
    agent.reload_code_generation_agent.side_effect = RuntimeError("broken")
    release, requested = threading.Event(), threading.Event()
    real_lock = threading.Lock()

    class PausingLock:
        """After the first failed rebuild, let a producer slip in between
        the drain's last lock release and its next attempt."""

        paused = False

        def __enter__(self):
            real_lock.acquire()

        def __exit__(self, *exc_info):
            real_lock.release()
            calls = agent.reload_code_generation_agent.call_count
            if calls == 1 and not PausingLock.paused:
                PausingLock.paused = True
                release.set()
                assert requested.wait(5)

    def producer():
        assert release.wait(5)
        queue.request("helper")
        requested.set()

    queue.request("helper")
    queue._lock = PausingLock()
    thread = threading.Thread(target=producer)
    thread.start()
    with patch("code_puppy.agents.deferred_reload.emit_warning") as warn:
        queue.apply(lambda: agent)
        thread.join()

    assert agent.reload_code_generation_agent.call_count == 1
    warn.assert_not_called()
