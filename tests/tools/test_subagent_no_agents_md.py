"""Regression: AGENTS.md (puppy rules) must NOT be injected into sub-agents.

A global AGENTS.md rule like "always invoke the xyz agent to do abc" would,
if fed to the xyz sub-agent itself, make an ``invoke_agent``-capable agent
re-invoke itself forever (recursion trap). Sub-agents therefore get only
their own authored prompt plus the sub-agent identity note.

The test poisons ``load_puppy_rules`` with a sentinel rule and asserts the
sentinel never reaches the instructions handed to the temp pydantic agent.
"""

from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.tools.agent_tools import register_invoke_agent

POISON_RULE = "ALWAYS invoke the xyz agent to do abc"


def _capture_registered_tool(register_func):
    """Grab the function that ``register_func`` registers on an agent."""
    mock_agent = MagicMock()
    captured = {}

    def capture_tool(func):
        captured["func"] = func
        return func

    mock_agent.tool = capture_tool
    register_func(mock_agent)
    return captured["func"]


@pytest.mark.asyncio
async def test_subagent_instructions_exclude_agents_md():
    invoke_agent = _capture_registered_tool(register_invoke_agent)
    mock_context = MagicMock()

    mock_agent_config = MagicMock()

    @contextmanager
    def temporary_override(model_name):
        yield

    mock_agent_config.temporary_model_name_override.side_effect = temporary_override
    mock_agent_config.get_model_name.return_value = "default-model"
    mock_agent_config.get_full_system_prompt.return_value = "You are xyz."
    mock_agent_config.get_available_tools.return_value = ["list_files"]
    mock_agent_config.get_message_history.return_value = []

    mock_result = MagicMock()
    mock_result.output = "subagent response"
    mock_result.all_messages.return_value = []

    mock_temp_agent = MagicMock()
    mock_temp_agent.run = AsyncMock(return_value=mock_result)

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "code_puppy.tools.subagent_invocation.generate_group_id",
                return_value="test-group",
            )
        )
        mock_bus = stack.enter_context(
            patch("code_puppy.tools.subagent_invocation.get_message_bus")
        )
        stack.enter_context(
            patch(
                "code_puppy.tools.subagent_invocation.get_session_context",
                return_value="parent",
            )
        )
        stack.enter_context(
            patch("code_puppy.tools.subagent_invocation.set_session_context")
        )
        stack.enter_context(patch("code_puppy.tools.subagent_invocation.emit_info"))
        stack.enter_context(patch("code_puppy.tools.subagent_invocation.emit_success"))
        stack.enter_context(
            patch("code_puppy.tools.subagent_invocation._save_session_history")
        )
        stack.enter_context(
            patch(
                "code_puppy.agents.agent_manager.load_agent",
                return_value=mock_agent_config,
            )
        )
        stack.enter_context(
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={"default-model": {}},
            )
        )
        stack.enter_context(patch("code_puppy.model_factory.ModelFactory.get_model"))
        stack.enter_context(patch("code_puppy.model_factory.make_model_settings"))
        # Poison pill: if ANY code path folds AGENTS.md into the sub-agent's
        # instructions, the assertion below catches it.
        stack.enter_context(
            patch(
                "code_puppy.agents._builder.load_puppy_rules",
                return_value=POISON_RULE,
            )
        )
        stack.enter_context(
            patch("code_puppy.callbacks.on_load_prompt", return_value=[])
        )
        mock_prepare = stack.enter_context(
            patch("code_puppy.model_utils.prepare_prompt_for_model")
        )
        stack.enter_context(
            patch(
                "code_puppy.agents._builder.autostart_bound_servers_async",
                new=AsyncMock(),
            )
        )
        stack.enter_context(patch("code_puppy.config.get_value", return_value="true"))
        stack.enter_context(
            patch(
                "code_puppy.agents._compaction.make_history_processor",
                return_value=lambda messages: messages,
            )
        )
        stack.enter_context(
            patch(
                "code_puppy.tools.subagent_invocation.Agent",
                return_value=mock_temp_agent,
            )
        )
        stack.enter_context(patch("code_puppy.tools.register_tools_for_agent"))
        stack.enter_context(
            patch(
                "code_puppy.tools.subagent_invocation.on_wrap_pydantic_agent",
                side_effect=lambda _cfg, agent, **_kwargs: agent,
            )
        )
        stack.enter_context(
            patch(
                "code_puppy.tools.subagent_invocation.on_agent_run_context",
                return_value=[],
            )
        )
        stack.enter_context(
            patch(
                "code_puppy.tools.subagent_invocation._load_session_history",
                return_value=[],
            )
        )
        stack.enter_context(
            patch(
                "code_puppy.tools.subagent_invocation._generate_session_hash_suffix",
                return_value="abc123",
            )
        )

        mock_bus.return_value.emit = MagicMock()
        mock_prepare.return_value = MagicMock(
            instructions="prepared instructions", user_prompt="prepared prompt"
        )

        result = await invoke_agent(
            mock_context,
            agent_name="xyz",
            prompt="Hello",
            session_id=None,
        )

    assert result.error is None
    mock_prepare.assert_called_once()
    assembled_instructions = mock_prepare.call_args.args[1]

    # The sub-agent keeps its own authored prompt...
    assert "You are xyz." in assembled_instructions
    # ...but AGENTS.md rules must never leak in (recursion-trap guard).
    assert POISON_RULE not in assembled_instructions
