from unittest.mock import Mock, patch

from code_puppy.plugins.walmart_specific.agent_run_cleanup import (
    prune_interrupted_tool_calls_on_agent_run_start,
)


def test_prunes_current_agent_history_on_agent_run_start():
    agent = Mock()
    agent.name = "code-puppy"
    history = [Mock(), Mock(), Mock()]
    pruned_history = [history[0], history[2]]
    agent.get_message_history.return_value = history
    agent.prune_interrupted_tool_calls.return_value = pruned_history

    with patch(
        "code_puppy.agents.agent_manager.get_current_agent", return_value=agent
    ):
        prune_interrupted_tool_calls_on_agent_run_start(
            agent_name="code-puppy",
            model_name="gpt-whatever",
        )

    agent.prune_interrupted_tool_calls.assert_called_once_with(history)
    agent.set_message_history.assert_called_once_with(pruned_history)


def test_skips_cleanup_when_active_agent_does_not_match_hook_agent_name():
    agent = Mock()
    agent.name = "other-agent"

    with patch(
        "code_puppy.agents.agent_manager.get_current_agent", return_value=agent
    ):
        prune_interrupted_tool_calls_on_agent_run_start(
            agent_name="code-puppy",
            model_name="gpt-whatever",
        )

    agent.get_message_history.assert_not_called()
    agent.prune_interrupted_tool_calls.assert_not_called()
    agent.set_message_history.assert_not_called()


def test_skips_setting_history_when_nothing_was_pruned():
    agent = Mock()
    agent.name = "code-puppy"
    history = [Mock(), Mock()]
    agent.get_message_history.return_value = history
    agent.prune_interrupted_tool_calls.return_value = list(history)

    with patch(
        "code_puppy.agents.agent_manager.get_current_agent", return_value=agent
    ):
        prune_interrupted_tool_calls_on_agent_run_start(
            agent_name="code-puppy",
            model_name="gpt-whatever",
        )

    agent.prune_interrupted_tool_calls.assert_called_once_with(history)
    agent.set_message_history.assert_not_called()
