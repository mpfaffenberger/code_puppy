"""Tests for main-loop agent reload requests from worker threads."""

from unittest.mock import MagicMock, patch

from code_puppy.agents import deferred_reload


def setup_function():
    with deferred_reload._pending_lock:
        deferred_reload._pending_agent_reloads.clear()


def teardown_function():
    with deferred_reload._pending_lock:
        deferred_reload._pending_agent_reloads.clear()


def test_pending_reload_rebuilds_active_agent_on_main_loop():
    agent = MagicMock(name="helper")
    agent.name = "helper"

    deferred_reload.request_agent_reload("helper")
    with patch("code_puppy.agents.get_current_agent", return_value=agent):
        deferred_reload.apply_pending_agent_reloads()

    agent.refresh_config.assert_called_once_with()
    agent.reload_code_generation_agent.assert_called_once_with()
    with deferred_reload._pending_lock:
        assert not deferred_reload._pending_agent_reloads


def test_pending_reload_waits_for_agent_to_become_active():
    inactive = MagicMock(name="other")
    inactive.name = "other"
    active = MagicMock(name="helper")
    active.name = "helper"

    deferred_reload.request_agent_reload("helper")
    with patch("code_puppy.agents.get_current_agent", return_value=inactive):
        deferred_reload.apply_pending_agent_reloads()

    with deferred_reload._pending_lock:
        assert deferred_reload._pending_agent_reloads == {"helper"}

    with patch("code_puppy.agents.get_current_agent", return_value=active):
        deferred_reload.apply_pending_agent_reloads()

    active.refresh_config.assert_called_once_with()
    active.reload_code_generation_agent.assert_called_once_with()
    with deferred_reload._pending_lock:
        assert not deferred_reload._pending_agent_reloads


def test_reload_failure_is_retried_on_a_later_main_loop_turn():
    agent = MagicMock(name="helper")
    agent.name = "helper"
    agent.reload_code_generation_agent.side_effect = RuntimeError("MCP not ready")

    deferred_reload.request_agent_reload("helper")
    with patch("code_puppy.agents.get_current_agent", return_value=agent):
        deferred_reload.apply_pending_agent_reloads()

    with deferred_reload._pending_lock:
        assert deferred_reload._pending_agent_reloads == {"helper"}
