"""Regression tests for BaseAgent.run_with_mcp async context handling."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.agents.base_agent import BaseAgent


class DummyAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "dummy-agent"

    @property
    def display_name(self) -> str:
        return "Dummy Agent"

    @property
    def description(self) -> str:
        return "test agent"

    def get_system_prompt(self) -> str:
        return "Be useful."

    def get_available_tools(self) -> list[str]:
        return []


@pytest.mark.asyncio
async def test_run_with_mcp_does_not_spawn_wrapper_task():
    """run_with_mcp should await inline to preserve contextvars state."""
    agent = DummyAgent()
    agent.get_message_history = MagicMock(return_value=[])
    agent.set_message_history = MagicMock()
    agent.prune_interrupted_tool_calls = MagicMock(
        side_effect=lambda messages: messages
    )
    agent.should_attempt_delayed_compaction = MagicMock(return_value=False)
    agent.get_model_name = MagicMock(return_value="test-model")
    agent.load_puppy_rules = MagicMock(return_value=None)

    mock_result = MagicMock()
    mock_result.output = "hello"

    mock_pydantic_agent = MagicMock()
    mock_pydantic_agent.run = AsyncMock(return_value=mock_result)
    agent.reload_code_generation_agent = MagicMock(return_value=mock_pydantic_agent)

    with (
        patch("code_puppy.agents.base_agent.get_message_limit", return_value=5),
        patch("code_puppy.agents.base_agent.get_use_dbos", return_value=False),
        patch(
            "code_puppy.agents.base_agent.cancel_agent_uses_signal", return_value=True
        ),
        patch("code_puppy.agents.base_agent.signal.signal", return_value="old-handler"),
        patch("code_puppy.agents.base_agent.on_agent_run_start", new=AsyncMock()),
        patch("code_puppy.agents.base_agent.on_agent_run_end", new=AsyncMock()),
        patch(
            "code_puppy.agents.base_agent.asyncio.create_task",
            side_effect=AssertionError(
                "run_with_mcp should not call asyncio.create_task"
            ),
        ),
        patch("code_puppy.model_utils.prepare_prompt_for_model") as mock_prepare,
    ):
        mock_prepare.return_value.user_prompt = "hello there"

        result = await agent.run_with_mcp("hello there")

    assert result is mock_result
    mock_pydantic_agent.run.assert_awaited_once()
