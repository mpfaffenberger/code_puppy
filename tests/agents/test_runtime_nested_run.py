"""Tests for the nested-run guard in ``run_with_mcp``.

The shell_safety plugin (and any future plugin) may start a full
``run_with_mcp`` WHILE the primary agent run is in flight. Historically
that nested run trampled process-wide interactive state:

* ``reset_pause_state_at_run_start()`` drained the OUTER run's queued
  steering messages ("my steers vanish mid-run" bug).
* Its ``finally`` cleared the cancel hotkey + shell cancel bridge armed
  by the outer run.
* It swapped the SIGINT handler mid-run.

The fix: ``run_with_mcp`` tracks in-flight depth; nested runs skip all
interactive-state plumbing.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.agents import _runtime


@pytest.fixture(autouse=True)
def _reset_depth():
    _runtime._active_run_depth = 0
    yield
    _runtime._active_run_depth = 0


# =============================================================================
# Wrapper depth bookkeeping
# =============================================================================


@pytest.mark.asyncio
async def test_wrapper_marks_inner_runs_as_nested():
    seen: list[bool] = []

    async def fake_impl(agent, prompt, *, is_nested_run=False, **kwargs):
        seen.append(is_nested_run)
        if len(seen) == 1:
            # Simulate shell_safety kicking off a run mid-run.
            await _runtime.run_with_mcp(agent, "inner prompt")
        return "ok"

    with patch.object(_runtime, "_run_with_mcp_impl", fake_impl):
        result = await _runtime.run_with_mcp(MagicMock(), "outer prompt")

    assert result == "ok"
    assert seen == [False, True]


@pytest.mark.asyncio
async def test_depth_resets_after_exception():
    async def boom(agent, prompt, *, is_nested_run=False, **kwargs):
        raise RuntimeError("kaboom")

    with patch.object(_runtime, "_run_with_mcp_impl", boom):
        with pytest.raises(RuntimeError):
            await _runtime.run_with_mcp(MagicMock(), "x")

    assert _runtime._active_run_depth == 0


@pytest.mark.asyncio
async def test_sequential_runs_are_both_top_level():
    seen: list[bool] = []

    async def fake_impl(agent, prompt, *, is_nested_run=False, **kwargs):
        seen.append(is_nested_run)
        return "ok"

    with patch.object(_runtime, "_run_with_mcp_impl", fake_impl):
        await _runtime.run_with_mcp(MagicMock(), "first")
        await _runtime.run_with_mcp(MagicMock(), "second")

    assert seen == [False, False]


# =============================================================================
# Nested runs must not touch the PauseController
# =============================================================================


def _agent_that_explodes_at_build() -> MagicMock:
    """Fake agent whose pydantic build raises — the impl bails early,
    right AFTER the pause-reset decision we're testing."""
    agent = MagicMock()
    agent._code_generation_agent = None
    return agent


@pytest.mark.asyncio
async def test_top_level_run_resets_pause_state():
    agent = _agent_that_explodes_at_build()
    with (
        patch.object(_runtime, "reset_pause_state_at_run_start") as mock_reset,
        patch.object(
            _runtime, "build_pydantic_agent", side_effect=RuntimeError("boom")
        ),
    ):
        with pytest.raises(RuntimeError):
            await _runtime._run_with_mcp_impl(agent, "x", is_nested_run=False)

    mock_reset.assert_called_once()


@pytest.mark.asyncio
async def test_nested_run_never_drains_outer_runs_steers():
    agent = _agent_that_explodes_at_build()
    with (
        patch.object(_runtime, "reset_pause_state_at_run_start") as mock_reset,
        patch.object(
            _runtime, "build_pydantic_agent", side_effect=RuntimeError("boom")
        ),
    ):
        with pytest.raises(RuntimeError):
            await _runtime._run_with_mcp_impl(agent, "x", is_nested_run=True)

    mock_reset.assert_not_called()
