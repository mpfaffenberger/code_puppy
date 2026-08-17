"""Regression test for issue #338 — agent_run_start hook ordering.

The ``agent_run_start`` callback must complete **before** the agent task is
scheduled, otherwise plugins that perform pre-flight async work (token
refresh, credential minting, etc.) race against the agent's first HTTP
request and lose.

This test registers a slow async ``agent_run_start`` callback that flips a
flag *after* an ``await asyncio.sleep(...)``.  We then assert that by the
time the underlying pydantic-ai ``run()`` is invoked, the flag is already
``True`` — proving the hook finished before the agent task got going.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.agent_execution_context import get_executing_agent
from code_puppy.agents.agent_code_puppy import CodePuppyAgent
from code_puppy.callbacks import (
    clear_callbacks,
    register_callback,
    unregister_callback,
)


class TestAgentRunStartOrdering:
    """Issue #338 regression: agent_run_start fires before the agent task."""

    @pytest.fixture
    def agent(self):
        return CodePuppyAgent()

    @pytest.fixture(autouse=True)
    def _clean_callbacks(self):
        """Make sure no stray agent_run_start callbacks leak between tests."""
        clear_callbacks("agent_run_start")
        yield
        clear_callbacks("agent_run_start")

    @pytest.mark.asyncio
    async def test_hook_completes_before_agent_run(self, agent):
        """A slow async hook must finish before pydantic_agent.run() is called."""
        hook_finished = False

        async def slow_hook(agent_name, model_name, session_id=None):
            nonlocal hook_finished
            # Yield repeatedly: if the agent task were already scheduled, this is the
            # window where it would sneak ahead and call run() with stale credentials.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            hook_finished = True

        register_callback("agent_run_start", slow_hook)

        # Capture whether the flag was True at the moment run() was invoked.
        flag_at_run_time: dict[str, bool] = {}

        async def fake_run(*args, **kwargs):
            flag_at_run_time["value"] = hook_finished
            return MagicMock(data="response")

        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_agent.run = AsyncMock(side_effect=fake_run)

            await agent.run_with_mcp("hello")

        assert flag_at_run_time.get("value") is True, (
            "agent_run_start hook did NOT complete before pydantic_agent.run() "
            "was invoked — the race from issue #338 has regressed."
        )
        assert hook_finished is True

    @pytest.mark.asyncio
    async def test_agent_run_task_inherits_executing_agent_context(self, agent):
        """Plugins running in the pydantic task can resolve its actual agent."""
        observed_agent = None

        async def fake_run(*args, **kwargs):
            nonlocal observed_agent
            observed_agent = get_executing_agent()
            return MagicMock(data="response")

        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_agent.run = AsyncMock(side_effect=fake_run)
            await agent.run_with_mcp("hello")

        assert observed_agent is agent
        assert get_executing_agent() is None

    @pytest.mark.asyncio
    async def test_agent_run_lifecycle_hooks_resolve_executing_agent(self, agent):
        """agent_run_start/end fire outside the run task but see its agent."""
        observed = {}

        def capture_start(agent_name, model_name, session_id):
            observed["start"] = get_executing_agent()

        def capture_end(*args, **kwargs):
            _ = args, kwargs
            observed["end"] = get_executing_agent()

        register_callback("agent_run_start", capture_start)
        register_callback("agent_run_end", capture_end)
        try:
            with patch.object(agent, "_code_generation_agent") as mock_agent:
                mock_agent.run = AsyncMock(return_value=MagicMock(data="response"))
                await agent.run_with_mcp("hello")
        finally:
            unregister_callback("agent_run_start", capture_start)
            unregister_callback("agent_run_end", capture_end)

        assert observed["start"] is agent
        assert observed["end"] is agent
        assert get_executing_agent() is None

    @pytest.mark.asyncio
    async def test_hook_exception_does_not_block_agent(self, agent):
        """A failing hook must not prevent the agent from running."""

        async def broken_hook(agent_name, model_name, session_id=None):
            raise RuntimeError("boom")

        register_callback("agent_run_start", broken_hook)

        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_run = AsyncMock(return_value=MagicMock(data="response"))
            mock_agent.run = mock_run

            result = await agent.run_with_mcp("hello")

            assert mock_run.called
            assert result.data == "response"
