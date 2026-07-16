"""Cross-task cancel-scope corruption is teardown noise, not a run failure.

When an MCP server's lifecycle task dies mid-run (flaky ``npx`` stdio
subprocess, dropped SSE connection, ...), the agent run task ends up closing
an anyio cancel scope owned by a dead task and anyio raises::

    RuntimeError: Attempted to exit a cancel scope that isn't the current
    task's current cancel scope

By then the model's response has already streamed to the user. ``_runtime``
must swallow that specific error with a friendly warning instead of vomiting
an exception group — while still propagating *real* RuntimeErrors.

Also covers ``MCPManager.wait_for_pending_starts``, which closes the
fire-and-forget autostart race on the main agent path (mirror of the
sub-agent fix in ``subagent_invocation.py``).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.agents._runtime import _is_cancel_scope_corruption
from code_puppy.agents.agent_code_puppy import CodePuppyAgent
from code_puppy.mcp_.manager import MCPManager

_CANCEL_SCOPE_MSG = (
    "Attempted to exit a cancel scope that isn't the current task's "
    "current cancel scope"
)


class TestIsCancelScopeCorruption:
    def test_matches_anyio_cross_task_error(self):
        assert _is_cancel_scope_corruption(RuntimeError(_CANCEL_SCOPE_MSG))

    def test_matches_other_cancel_scope_phrasings(self):
        assert _is_cancel_scope_corruption(
            RuntimeError(
                "Attempted to exit cancel scope in a different task "
                "than it was entered in"
            )
        )

    def test_rejects_unrelated_runtime_error(self):
        assert not _is_cancel_scope_corruption(RuntimeError("event loop is closed"))

    def test_rejects_non_runtime_error(self):
        assert not _is_cancel_scope_corruption(ValueError(_CANCEL_SCOPE_MSG))


class TestRunWithMcpSwallowsCancelScopeNoise:
    @pytest.fixture
    def agent(self):
        return CodePuppyAgent()

    @pytest.mark.asyncio
    async def test_bare_cancel_scope_error_is_swallowed(self, agent):
        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_agent.run = AsyncMock(side_effect=RuntimeError(_CANCEL_SCOPE_MSG))
            with patch("code_puppy.agents._runtime.emit_warning") as mock_warn:
                result = await agent.run_with_mcp("hello")

        assert result is None
        warned = " ".join(str(c.args[0]) for c in mock_warn.call_args_list)
        assert "MCP server" in warned

    @pytest.mark.asyncio
    async def test_grouped_cancel_scope_error_is_swallowed(self, agent):
        group = ExceptionGroup("unwind", [RuntimeError(_CANCEL_SCOPE_MSG)])
        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_agent.run = AsyncMock(side_effect=group)
            with patch("code_puppy.agents._runtime.emit_warning") as mock_warn:
                result = await agent.run_with_mcp("hello")

        assert result is None
        assert mock_warn.called

    @pytest.mark.asyncio
    async def test_real_runtime_error_still_raises(self, agent):
        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_agent.run = AsyncMock(side_effect=RuntimeError("boom"))
            with pytest.raises(RuntimeError, match="boom"):
                await agent.run_with_mcp("hello")

    @pytest.mark.asyncio
    async def test_mixed_group_raises_real_error_only(self, agent):
        """Scope noise is filtered out; the genuine error still propagates."""
        group = ExceptionGroup(
            "unwind",
            [RuntimeError(_CANCEL_SCOPE_MSG), ValueError("genuine bug")],
        )
        with patch.object(agent, "_code_generation_agent") as mock_agent:
            mock_agent.run = AsyncMock(side_effect=group)
            with pytest.raises(ValueError, match="genuine bug"):
                await agent.run_with_mcp("hello")


class TestWaitForPendingStarts:
    """Exercise the unbound method against a minimal fake — constructing a
    real MCPManager drags in config sync, which this logic doesn't need."""

    @staticmethod
    def _fake_manager(tasks):
        fake = MagicMock(spec=[])
        fake._pending_start_tasks = tasks
        return fake

    @pytest.mark.asyncio
    async def test_no_pending_tasks_returns_immediately(self):
        fake = self._fake_manager({})
        await MCPManager.wait_for_pending_starts(fake)

    @pytest.mark.asyncio
    async def test_missing_attribute_is_fine(self):
        fake = MagicMock(spec=[])
        await MCPManager.wait_for_pending_starts(fake)

    @pytest.mark.asyncio
    async def test_waits_for_in_flight_start(self):
        entered = asyncio.Event()

        async def _start():
            entered.set()

        task = asyncio.create_task(_start())
        fake = self._fake_manager({"srv": task})
        await MCPManager.wait_for_pending_starts(fake)
        assert entered.is_set()
        assert task.done()

    @pytest.mark.asyncio
    async def test_timeout_does_not_cancel_start_task(self):
        task = asyncio.create_task(asyncio.sleep(30))
        fake = self._fake_manager({"srv": task})
        await MCPManager.wait_for_pending_starts(fake, timeout=0.05)
        assert not task.done()
        assert not task.cancelled()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
