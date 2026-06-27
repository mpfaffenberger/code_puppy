"""Tests for ``_on_post_tool_call`` as the authoritative completion signal.

The primary completion path through ``SubAgentResponseMessage`` is silently
skipped in high-output mode when tokens have already streamed inline (see
``_invoke_agent_impl`` in ``tools/subagent_invocation.py``). Without a
fallback the panel row sits frozen on its last ``stream_event``-derived status
forever -- a parent blocked awaiting children emits no further events. The
``post_tool_call`` hook fires whenever the tool returns, so it's the durable
boundary we rely on here.

These tests drive ``_on_post_tool_call`` directly. ``_maybe_flush_group``
calls ``_render_console()`` which returns ``None`` when no spinner is active,
and ``_maybe_flush_group`` handles that gracefully -- so no Rich / spinner
mocking is needed.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from code_puppy.plugins.subagent_panel import register_callbacks, state


@pytest.fixture(autouse=True)
def _reset_panel_state(monkeypatch):
    """Isolate panel state per-test and pin the runtime gate to enabled.

    ``state._AGENTS`` is module-level; without a reset, test order would
    matter and a sixth test would eventually flake. Monkeypatching
    ``_runtime_enabled`` defends against a stray ``DISABLE_SUBAGENT_PANEL=1``
    in the developer's env silently no-op-ing the whole suite.
    """
    state.clear()
    monkeypatch.setattr(register_callbacks, "_runtime_enabled", lambda: True)
    yield
    state.clear()


@dataclass
class _StubInvokeResult:
    """Mirrors the attributes of ``AgentInvokeOutput`` that the hook reads."""

    session_id: str | None = None
    error: str | None = None


# Generic "this tool returns something with no session_id" stub.
class _StubGenericResult:
    pass


async def test_success_marks_done():
    state.register("agent-alpha-abc123", "alpha-agent", model="gpt-5.4")

    await register_callbacks._on_post_tool_call(
        tool_name="invoke_agent",
        tool_args={},
        result=_StubInvokeResult(session_id="agent-alpha-abc123"),
        duration_ms=42,
    )

    entry = state._AGENTS["agent-alpha-abc123"]
    assert entry["done"] is True
    assert entry["status"] == "completed"
    assert not entry.get("failed")


async def test_failure_marks_failed():
    """Regression guard: the existing failure-renders-as-red behavior must
    survive any future edit to ``_on_post_tool_call`` that sits next to the
    new success branch.
    """
    state.register("agent-beta-def456", "beta-agent", model="gpt-5.4")

    await register_callbacks._on_post_tool_call(
        tool_name="invoke_agent",
        tool_args={},
        result=_StubInvokeResult(session_id="agent-beta-def456", error="boom"),
        duration_ms=42,
    )

    entry = state._AGENTS["agent-beta-def456"]
    assert entry["done"] is True
    assert entry["failed"] is True
    assert entry["status"] == "failed"


async def test_unrelated_tool_is_noop():
    """Tools other than the two invoke variants must not touch panel state."""
    state.register("agent-gamma-ghi789", "gamma-agent", model="gpt-5.4")
    pre = dict(state._AGENTS["agent-gamma-ghi789"])

    await register_callbacks._on_post_tool_call(
        tool_name="read_file",
        tool_args={"file_path": "x"},
        result=_StubGenericResult(),
        duration_ms=1,
    )

    assert state._AGENTS["agent-gamma-ghi789"] == pre


async def test_unregistered_session_is_noop():
    """A completion for a session we never registered must silently no-op,
    matching the underlying ``state.mark_done`` / ``mark_failed`` contract.
    """
    await register_callbacks._on_post_tool_call(
        tool_name="invoke_agent",
        tool_args={},
        result=_StubInvokeResult(session_id="ghost-session-xyz"),
        duration_ms=1,
    )

    assert "ghost-session-xyz" not in state._AGENTS


async def test_invoke_agent_with_model_also_handled():
    """The model-override variant of the tool must be treated identically."""
    state.register("agent-delta-jkl012", "delta-agent", model="gpt-5.4-nano")

    await register_callbacks._on_post_tool_call(
        tool_name="invoke_agent_with_model",
        tool_args={},
        result=_StubInvokeResult(session_id="agent-delta-jkl012"),
        duration_ms=42,
    )

    entry = state._AGENTS["agent-delta-jkl012"]
    assert entry["done"] is True
    assert entry["status"] == "completed"


async def test_missing_session_id_is_noop():
    """If the result has no ``session_id`` we must short-circuit without
    touching state -- guards against generic tool results that happen to
    pass the tool-name guard via some future refactor.
    """
    state.register("agent-epsilon-mno345", "epsilon-agent", model="gpt-5.4")

    await register_callbacks._on_post_tool_call(
        tool_name="invoke_agent",
        tool_args={},
        result=_StubInvokeResult(session_id=None),
        duration_ms=1,
    )

    # Untouched -- still 'starting', not 'completed'.
    assert state._AGENTS["agent-epsilon-mno345"]["status"] == "starting"
