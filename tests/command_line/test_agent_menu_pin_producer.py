"""Regression coverage for the model-pin producer of the deferred reload queue.

``_apply_pinned_model`` is the only production caller that enqueues a deferred
reload. Without these tests the whole producer can be deleted and every
deferred-reload suite still passes, because those suites enqueue directly.

The load-bearing guarantee is negative: the picker runs in a worker thread on a
transient ``asyncio.run`` loop, so the producer must *persist and enqueue only*.
Rebuilding here is what deadlocked MCP autostart against anyio teardown, so
"no rebuild on the calling thread" is asserted explicitly, not implied.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.agents import (
    apply_agent_reloads,
    clear_pending_agent_reloads,
)
from code_puppy.agents.base_agent import BaseAgent
from code_puppy.command_line.agent_menu import _apply_pinned_model


@pytest.fixture(autouse=True)
def _clean_queue():
    clear_pending_agent_reloads()
    yield
    clear_pending_agent_reloads()


def _agent(name: str) -> MagicMock:
    agent = MagicMock(spec=BaseAgent)
    agent.name = name
    return agent


def _drain(agent: MagicMock) -> bool:
    """Drain for *agent*; True when a request was pending and applied."""
    apply_agent_reloads(lambda: agent)
    return agent.reload_code_generation_agent.called


def _json_agent_on_disk(tmp_path, name: str, **extra):
    path = tmp_path / f"{name}.json"
    path.write_text(
        json.dumps({"name": name, "description": "d", "system_prompt": "p", **extra}),
        encoding="utf-8",
    )
    return path


# --- built-in agents ------------------------------------------------------


def test_pinning_a_builtin_agent_persists_and_enqueues():
    with (
        patch("code_puppy.command_line.agent_menu.set_agent_pinned_model") as pin,
        patch("code_puppy.command_line.agent_menu.emit_success"),
    ):
        _apply_pinned_model("helper", "gpt-5")

    pin.assert_called_once_with("helper", "gpt-5")
    assert _drain(_agent("helper"))


def test_unpinning_a_builtin_agent_clears_and_enqueues():
    with (
        patch("code_puppy.command_line.agent_menu.clear_agent_pinned_model") as clear,
        patch("code_puppy.command_line.agent_menu.emit_success"),
    ):
        _apply_pinned_model("helper", "(unpin)")

    clear.assert_called_once_with("helper")
    assert _drain(_agent("helper"))


# --- JSON agents ----------------------------------------------------------


def test_pinning_a_json_agent_writes_the_file_and_enqueues(tmp_path):
    path = _json_agent_on_disk(tmp_path, "writer")

    with (
        patch(
            "code_puppy.agents.json_agent.discover_json_agents",
            return_value={"writer": str(path)},
        ),
        patch("code_puppy.command_line.agent_menu.emit_success"),
    ):
        _apply_pinned_model("writer", "gpt-5")

    assert json.loads(path.read_text(encoding="utf-8"))["model"] == "gpt-5"
    assert _drain(_agent("writer"))


def test_unpinning_a_json_agent_removes_the_key_and_enqueues(tmp_path):
    path = _json_agent_on_disk(tmp_path, "writer", model="gpt-5")

    with (
        patch(
            "code_puppy.agents.json_agent.discover_json_agents",
            return_value={"writer": str(path)},
        ),
        patch("code_puppy.command_line.agent_menu.emit_success"),
    ):
        _apply_pinned_model("writer", "(unpin)")

    assert "model" not in json.loads(path.read_text(encoding="utf-8"))
    assert _drain(_agent("writer"))


# --- the guarantees that justify the queue --------------------------------


def test_the_producer_never_rebuilds_on_the_calling_thread():
    """The picker's transient loop must not see agent construction."""
    agent = _agent("helper")

    with (
        patch("code_puppy.command_line.agent_menu.set_agent_pinned_model"),
        patch("code_puppy.command_line.agent_menu.emit_success"),
        patch("code_puppy.agents.agent_manager.get_current_agent", return_value=agent),
    ):
        _apply_pinned_model("helper", "gpt-5")

        agent.refresh_config.assert_not_called()
        agent.reload_code_generation_agent.assert_not_called()

    # The work happens later, on the main loop, when the drain runs.
    assert _drain(agent)
    agent.refresh_config.assert_called_once_with()


def test_the_request_targets_only_the_pinned_agent():
    with (
        patch("code_puppy.command_line.agent_menu.set_agent_pinned_model"),
        patch("code_puppy.command_line.agent_menu.emit_success"),
    ):
        _apply_pinned_model("helper", "gpt-5")

    assert not _drain(_agent("bystander"))
    assert _drain(_agent("helper"))


def test_failed_persistence_warns_and_enqueues_nothing():
    with (
        patch(
            "code_puppy.command_line.agent_menu.set_agent_pinned_model",
            side_effect=OSError("disk full"),
        ),
        patch("code_puppy.command_line.agent_menu.emit_success"),
        patch("code_puppy.command_line.agent_menu.emit_warning") as warn,
    ):
        _apply_pinned_model("helper", "gpt-5")

    warn.assert_called_once()
    assert not _drain(_agent("helper"))


def test_failed_json_write_warns_and_enqueues_nothing(tmp_path):
    path = _json_agent_on_disk(tmp_path, "writer")
    path.chmod(0o400)  # readable, not writable

    with (
        patch(
            "code_puppy.agents.json_agent.discover_json_agents",
            return_value={"writer": str(path)},
        ),
        patch("code_puppy.command_line.agent_menu.emit_success"),
        patch("code_puppy.command_line.agent_menu.emit_warning") as warn,
    ):
        try:
            _apply_pinned_model("writer", "gpt-5")
        finally:
            path.chmod(0o600)

    warn.assert_called_once()
    assert not _drain(_agent("writer"))
