"""Tests for the app-side CapabilityEventBridge.

The bridge is the ONLY seam between pure capability events and Code
Puppy behavior (legacy callbacks, spinner, messaging). These tests pin:

* each ``compaction.*`` event maps to the right legacy surface,
* the context-indicator compatibility path (late-bound
  ``_compaction.update_spinner_context``),
* fail-open listeners (a broken callback never breaks the run),
* the pure capability remains bridge-agnostic (no bridge imports).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List

from code_puppy.capabilities.compaction import (
    BeforeCompactionEvent,
    CompactionCompletedEvent,
    CompactionFailedEvent,
    ContextUsageMeasuredEvent,
    HistoryProcessingCompletedEvent,
    HistoryProcessingStartedEvent,
)
from code_puppy.events.bridge import CapabilityEventBridge

_CTX = SimpleNamespace()


class _FakeAgent:
    def __init__(self):
        self._message_history: List[Any] = ["m1", "m2"]


async def test_before_compaction_maps_to_on_pre_compact(monkeypatch):
    calls = []

    async def fake_pre_compact(agent_name, strategy, message_count, token_count):
        calls.append((agent_name, strategy, message_count, token_count))
        return []

    import code_puppy.callbacks as callbacks

    monkeypatch.setattr(callbacks, "on_pre_compact", fake_pre_compact)

    bridge = CapabilityEventBridge()
    await bridge._before_compaction(
        _CTX,
        BeforeCompactionEvent(
            strategy="summarization",
            message_count=42,
            total_tokens=9000,
            agent_name="test-agent",
        ),
    )
    assert calls == [("test-agent", "summarization", 42, 9000)]


async def test_history_processing_events_map_to_processor_callbacks(monkeypatch):
    seen = {}

    def fake_start(**kwargs):
        seen["start"] = kwargs
        return []

    def fake_end(**kwargs):
        seen["end"] = kwargs
        return []

    import code_puppy.callbacks as callbacks

    monkeypatch.setattr(callbacks, "on_message_history_processor_start", fake_start)
    monkeypatch.setattr(callbacks, "on_message_history_processor_end", fake_end)

    agent = _FakeAgent()
    bridge = CapabilityEventBridge(agent=agent)
    await bridge._history_processing_started(
        _CTX,
        HistoryProcessingStartedEvent(
            agent_name="a", session_id="s", history_count=2, incoming_count=1
        ),
    )
    await bridge._history_processing_completed(
        _CTX,
        HistoryProcessingCompletedEvent(
            agent_name="a",
            session_id="s",
            history_count=2,
            messages_added=1,
            messages_filtered=0,
        ),
    )
    assert seen["start"]["agent_name"] == "a"
    assert seen["start"]["message_history"] == ["m1", "m2"]
    assert seen["end"]["messages_added"] == 1
    assert seen["end"]["message_history"] == ["m1", "m2"]


async def test_context_usage_routes_through_compaction_module(monkeypatch):
    """Spinner updates go through ``_compaction.update_spinner_context`` so
    the context-indicator plugin's monkeypatch keeps intercepting them."""
    from code_puppy.agents import _compaction

    captured = []
    monkeypatch.setattr(
        _compaction, "update_spinner_context", lambda info: captured.append(info)
    )

    bridge = CapabilityEventBridge()
    await bridge._context_usage_measured(
        _CTX,
        ContextUsageMeasuredEvent(
            total_tokens=500, model_max_tokens=1000, proportion_used=0.5
        ),
    )
    assert len(captured) == 1


async def test_compaction_failed_maps_to_emit_error(monkeypatch):
    errors = []
    import code_puppy.events.bridge as bridge_module  # noqa: F401
    import code_puppy.messaging as messaging

    monkeypatch.setattr(messaging, "emit_error", lambda msg: errors.append(msg))

    bridge = CapabilityEventBridge()
    await bridge._compaction_failed(
        _CTX, CompactionFailedEvent(error_type="RuntimeError", error_message="boom")
    )
    assert errors == ["Compaction failed: [RuntimeError] boom"]


async def test_forced_compaction_completed_maps_to_emit_success(monkeypatch):
    messages = []
    import code_puppy.messaging as messaging

    monkeypatch.setattr(messaging, "emit_success", lambda msg: messages.append(msg))

    bridge = CapabilityEventBridge()
    # Unforced: silent.
    await bridge._compaction_completed(
        _CTX,
        CompactionCompletedEvent(
            messages_before=10,
            messages_after=5,
            total_tokens_before=1000,
            total_tokens_after=500,
            dropped_count=5,
        ),
    )
    assert messages == []
    # Forced with drops.
    await bridge._compaction_completed(
        _CTX,
        CompactionCompletedEvent(
            messages_before=10,
            messages_after=5,
            total_tokens_before=1000,
            total_tokens_after=500,
            dropped_count=5,
            forced=True,
        ),
    )
    # Forced no-op.
    await bridge._compaction_completed(
        _CTX,
        CompactionCompletedEvent(
            messages_before=10,
            messages_after=10,
            total_tokens_before=1000,
            total_tokens_after=1000,
            dropped_count=0,
            forced=True,
        ),
    )
    assert messages == [
        "Mid-run compaction complete.",
        "Mid-run compaction complete. History was already minimal.",
    ]


async def test_listeners_are_fail_open(monkeypatch):
    """A broken legacy callback must never propagate out of the bridge."""
    import code_puppy.callbacks as callbacks

    async def exploding(*args, **kwargs):
        raise RuntimeError("plugin bug")

    monkeypatch.setattr(callbacks, "on_pre_compact", exploding)

    bridge = CapabilityEventBridge()
    # Must not raise.
    await bridge._before_compaction(
        _CTX,
        BeforeCompactionEvent(strategy="s", message_count=1, total_tokens=1),
    )


def test_pure_capability_does_not_import_the_bridge():
    """Decoupling direction check: capability -> events only, never the
    bridge (or any code_puppy module) from the capability."""
    import inspect

    import code_puppy.capabilities.compaction as module

    source = inspect.getsource(module)
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    for line in import_lines:
        assert "events.bridge" not in line, line
        assert "code_puppy.callbacks" not in line, line
