"""Tests for the bridge's `code_mode.*` speculation listeners (harness#699).

Same contract as the compaction listeners: each speculation event maps to a
messaging emission, listeners are fail-open, and the arguments preview stays
one-line-sized.
"""

from __future__ import annotations

from types import SimpleNamespace

from pydantic_ai_harness.code_mode import (
    SpeculativeCallClaimedEvent,
    SpeculativeCallEvictedEvent,
    SpeculativeCallLaunchedEvent,
    SpeculativeCallMissedEvent,
    SpeculativeCallSettledEvent,
)

from code_puppy.events.bridge import CapabilityEventBridge, _preview_arguments

_CTX = SimpleNamespace()


def _capture(monkeypatch, name: str):
    messages: list[str] = []

    import code_puppy.messaging as messaging

    monkeypatch.setattr(messaging, name, lambda text: messages.append(text))
    return messages


async def test_launched_renders_function_args_and_lines(monkeypatch):
    messages = _capture(monkeypatch, "emit_info")
    bridge = CapabilityEventBridge()

    await bridge._speculative_launched(
        _CTX,
        SpeculativeCallLaunchedEvent(
            tool_call_id="part1",
            launch_id="part1__spec_1",
            sandbox_function="grep",
            wrapped_tool_name="grep",
            arguments={"search_string": "SpeculationState"},
            line_start=3,
            line_end=3,
        ),
    )

    assert len(messages) == 1
    assert "speculating grep(search_string='SpeculationState')" in messages[0]
    assert "L3" in messages[0]


async def test_launched_renders_multiline_spans(monkeypatch):
    messages = _capture(monkeypatch, "emit_info")
    bridge = CapabilityEventBridge()

    await bridge._speculative_launched(
        _CTX,
        SpeculativeCallLaunchedEvent(
            tool_call_id="part1",
            launch_id="part1__spec_1",
            sandbox_function="grep",
            wrapped_tool_name="grep",
            arguments={},
            line_start=2,
            line_end=5,
        ),
    )

    assert "L2-5" in messages[0]


async def test_settled_ready_and_failed_render_distinctly(monkeypatch):
    messages = _capture(monkeypatch, "emit_info")
    bridge = CapabilityEventBridge()

    await bridge._speculative_settled(
        _CTX,
        SpeculativeCallSettledEvent(
            tool_call_id="part1",
            launch_id="part1__spec_1",
            outcome="ready",
            elapsed_ms=48.2,
        ),
    )
    await bridge._speculative_settled(
        _CTX,
        SpeculativeCallSettledEvent(
            tool_call_id="part1",
            launch_id="part1__spec_2",
            outcome="failed",
            elapsed_ms=12.0,
        ),
    )

    assert "ready in 48ms" in messages[0]
    assert "failed after 12ms" in messages[1]


async def test_claimed_renders_hit_with_hidden_latency(monkeypatch):
    messages = _capture(monkeypatch, "emit_success")
    bridge = CapabilityEventBridge()

    await bridge._speculative_claimed(
        _CTX,
        SpeculativeCallClaimedEvent(
            tool_call_id="part1",
            launch_id="part1__spec_1",
            nested_tool_call_id="part1__1",
            wrapped_tool_name="grep",
            ready_at_claim=True,
            elapsed_ms=48.0,
        ),
    )

    assert "speculation hit: grep" in messages[0]
    assert "result was already waiting" in messages[0]


async def test_missed_and_evicted_render(monkeypatch):
    messages = _capture(monkeypatch, "emit_info")
    bridge = CapabilityEventBridge()

    await bridge._speculative_missed(
        _CTX,
        SpeculativeCallMissedEvent(
            tool_call_id="part1",
            sandbox_function="read_file",
            wrapped_tool_name="read_file",
            nested_tool_call_id="part1__2",
        ),
    )
    await bridge._speculative_evicted(
        _CTX,
        SpeculativeCallEvictedEvent(
            tool_call_id="part1",
            launch_id="part1__spec_3",
            wrapped_tool_name="grep",
            state="pending",
        ),
    )

    assert "speculation miss: read_file runs cold" in messages[0]
    assert "speculation wasted: grep (pending)" in messages[1]


async def test_listeners_are_fail_open(monkeypatch):
    import code_puppy.messaging as messaging

    def explode(text):
        raise RuntimeError("messaging down")

    monkeypatch.setattr(messaging, "emit_info", explode)
    monkeypatch.setattr(messaging, "emit_success", explode)
    bridge = CapabilityEventBridge()

    await bridge._speculative_missed(
        _CTX,
        SpeculativeCallMissedEvent(
            tool_call_id="p",
            sandbox_function="grep",
            wrapped_tool_name="grep",
            nested_tool_call_id="p__1",
        ),
    )
    await bridge._speculative_claimed(
        _CTX,
        SpeculativeCallClaimedEvent(
            tool_call_id="p",
            launch_id="p__spec_1",
            nested_tool_call_id="p__1",
            wrapped_tool_name="grep",
            ready_at_claim=False,
            elapsed_ms=1.0,
        ),
    )


def test_preview_arguments_truncates():
    preview = _preview_arguments({"query": "x" * 200})
    assert len(preview) == 60
    assert preview.endswith("\u2026")


async def test_listeners_defer_to_an_active_panel(monkeypatch):
    """While a SpeculationPanel cycle owns the terminal, the bridge stays silent."""
    messages = _capture(monkeypatch, "emit_info")
    success = _capture(monkeypatch, "emit_success")

    class _ActivePanel:
        active = True

    monkeypatch.setattr(
        "code_puppy.messaging.speculation_panel.get_speculation_panel",
        lambda: _ActivePanel(),
    )

    bridge = CapabilityEventBridge()
    await bridge._speculative_launched(
        _CTX,
        SpeculativeCallLaunchedEvent(
            tool_call_id="p",
            launch_id="p__spec_1",
            sandbox_function="grep",
            wrapped_tool_name="grep",
            arguments={},
            line_start=1,
            line_end=1,
        ),
    )
    await bridge._speculative_claimed(
        _CTX,
        SpeculativeCallClaimedEvent(
            tool_call_id="p",
            launch_id="p__spec_1",
            nested_tool_call_id="p__1",
            wrapped_tool_name="grep",
            ready_at_claim=True,
            elapsed_ms=1.0,
        ),
    )
    await bridge._speculative_missed(
        _CTX,
        SpeculativeCallMissedEvent(
            tool_call_id="p",
            sandbox_function="grep",
            wrapped_tool_name="grep",
            nested_tool_call_id="p__1",
        ),
    )

    assert messages == []
    assert success == []
