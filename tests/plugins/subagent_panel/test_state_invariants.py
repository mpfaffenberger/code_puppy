"""Regression guards for ``state.py`` invariants the panel relies on.

These lock in semantics that are easy to break in a future refactor and
that the live-display logic in ``register_callbacks.py`` quietly depends
on. Tests here are intentionally tiny; they exist to fail loudly when an
invariant slips.
"""

from __future__ import annotations

import pytest

from code_puppy.plugins.subagent_panel import state


@pytest.fixture(autouse=True)
def _reset_panel_state():
    state.clear()
    yield
    state.clear()


def test_register_twice_preserves_start():
    """Re-registering the same session_id must keep the original ``start``.

    The panel computes elapsed mm:ss from ``start``. If a re-emit of
    ``SubAgentInvocationMessage`` clobbered ``start``, the displayed elapsed
    time would jump back to 00:00 mid-run.
    """
    state.register("agent-foo-abc", "foo-agent", model="gpt-5.4")
    original_start = state._AGENTS["agent-foo-abc"]["start"]

    # Manufactured re-register (e.g. a hypothetical message replay).
    state.register("agent-foo-abc", "foo-agent", model="gpt-5.4")

    assert state._AGENTS["agent-foo-abc"]["start"] == original_start


def test_record_event_for_unregistered_session_is_noop():
    """``record_event`` must be UPDATE-ONLY.

    This is the filter that keeps the main agent's stream events out of the
    panel (the main agent is never registered, sub-agents always are). If it
    started auto-creating entries, the panel would show the main agent's
    activity as a phantom sub-agent.
    """
    state.record_event("never-registered-sid", "part_start", {"part_type": "Text"})
    assert "never-registered-sid" not in state._AGENTS


def test_snapshot_does_not_idle_prune_done_entries(monkeypatch):
    """``mark_done`` rows must survive past ``IDLE_PRUNE_S``.

    Done rows are kept in the live tree (rendered as 'completed') until the
    whole swarm flushes, so a finished child never vanishes mid-run. The
    docstring on ``snapshot`` promises this; lock it.
    """
    state.register("agent-bar-xyz", "bar-agent", model="gpt-5.4")
    state.mark_done("agent-bar-xyz")

    # Force the entry's last_seen far into the past -- well beyond IDLE_PRUNE_S.
    state._AGENTS["agent-bar-xyz"]["last_seen"] = 0.0
    state._AGENTS["agent-bar-xyz"]["end"] = 0.0

    rows = state.snapshot()
    sids = [r["session_id"] for r in rows]
    assert "agent-bar-xyz" in sids
