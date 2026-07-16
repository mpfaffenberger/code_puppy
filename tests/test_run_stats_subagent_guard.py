"""Tests for the sub-agent guard on ``_on_post_tool_call``.

``code_puppy/agents/run_stats.py`` registers three callbacks with the
global callback registry:

- ``_on_stream_event``     — already guarded on ``is_subagent()``
- ``_on_agent_run_end``    — already guarded on ``is_subagent()``
- ``_on_post_tool_call``   — the one this test file covers

Without a guard on ``_on_post_tool_call``, every tool return from a
sub-agent leaks into the main agent's TUI in ``high`` output mode via
``_render_high_mode_tool_result``. Sub-agents have their own rendering
path (``tools/subagent_invocation.py``), so the global callback firing
for them is unintended bleed-through, not the intended UX.

These tests lock in the guard.
"""

from __future__ import annotations

import pytest

from code_puppy.agents.run_stats import _on_post_tool_call
from code_puppy.tools.subagent_context import subagent_context


@pytest.mark.asyncio
async def test_on_post_tool_call_renders_by_default(monkeypatch):
    """Baseline: outside any sub-agent context, the renderer is invoked."""
    render_calls = []

    def _record(*args, **kwargs):
        render_calls.append((args, kwargs))

    monkeypatch.setattr(
        "code_puppy.agents.run_stats._render_high_mode_tool_result",
        _record,
    )

    await _on_post_tool_call(
        tool_name="some_tool",
        tool_args={"foo": "bar"},
        result={"ok": True},
        duration_ms=1.5,
    )
    assert len(render_calls) == 1


@pytest.mark.asyncio
async def test_on_post_tool_call_skips_inside_subagent_context(monkeypatch):
    """The load-bearing guard: sub-agent context suppresses the renderer.

    Sub-agents render through their own path; this global callback
    firing for them would leak internal tool traffic into the main
    agent's TUI in high output mode.
    """
    render_calls = []

    def _record(*args, **kwargs):
        render_calls.append((args, kwargs))

    monkeypatch.setattr(
        "code_puppy.agents.run_stats._render_high_mode_tool_result",
        _record,
    )

    with subagent_context("test-subagent"):
        await _on_post_tool_call(
            tool_name="some_internal_tool",
            tool_args={"summary": "..."},
            result={"summary": "..."},
            duration_ms=0.1,
        )
    assert render_calls == [], (
        "sub-agent tool returns must not reach the user-facing renderer; "
        f"got {render_calls!r}"
    )


@pytest.mark.asyncio
async def test_on_post_tool_call_resumes_rendering_after_subagent_exits(
    monkeypatch,
):
    """ContextVar token restore: after the sub-agent scope exits,
    rendering resumes for the main agent's tool calls."""
    render_calls = []

    def _record(*args, **kwargs):
        render_calls.append((args, kwargs))

    monkeypatch.setattr(
        "code_puppy.agents.run_stats._render_high_mode_tool_result",
        _record,
    )

    with subagent_context("test-subagent"):
        await _on_post_tool_call(
            tool_name="some_internal_tool",
            tool_args={},
            result={},
            duration_ms=0.1,
        )
    # Outside the scope again: main-agent tool calls should render.
    await _on_post_tool_call(
        tool_name="read_file",
        tool_args={"path": "x"},
        result="content",
        duration_ms=2.0,
    )
    assert len(render_calls) == 1
    assert render_calls[0][0][0] == "read_file"
