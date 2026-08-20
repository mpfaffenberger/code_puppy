"""Tests for the ``model_select`` hook and per-run model resolution.

Covers ``callbacks.on_model_select`` and
``model_switching.resolve_run_model_selection`` -- the two new pieces that let
a plugin route each turn to a different model (small-vs-large auto mode, cost
caps, failover, ...).
"""

from __future__ import annotations

import pytest

from code_puppy.callbacks import (
    clear_callbacks,
    on_model_select,
    register_callback,
)
from code_puppy.model_switching import resolve_run_model_selection


@pytest.fixture(autouse=True)
def _clean_hook():
    clear_callbacks("model_select")
    yield
    clear_callbacks("model_select")


class FakeAgent:
    """Minimal stand-in exposing the model-override surface resolve() uses."""

    def __init__(self, base="global-model", runtime=None, pinned=None):
        self.name = "fake"
        self._base = base
        self._runtime = runtime
        self._auto = None
        self._code_generation_agent = object()  # non-None = "cached build"
        self._message_history = []

    def get_runtime_model_name_override(self):
        return self._runtime

    def get_auto_model_override(self):
        return self._auto

    def set_auto_model_override(self, name):
        self._auto = name

    def get_model_name(self):
        # Mirrors BaseAgent precedence: runtime > auto > base.
        return self._runtime or self._auto or self._base


# ---- on_model_select -------------------------------------------------------


def test_on_model_select_no_callbacks_returns_none():
    assert (
        on_model_select(
            agent_name="fake",
            current_model="m",
            prompt="hello",
            messages=[],
            session_id=None,
        )
        is None
    )


def test_on_model_select_returns_first_nonempty_without_running_lower_priority():
    lower_priority_calls = []
    register_callback("model_select", lambda **k: None)
    register_callback("model_select", lambda **k: "")
    register_callback("model_select", lambda **k: "small-model")
    register_callback(
        "model_select", lambda **k: lower_priority_calls.append(k) or "never-reached"
    )

    assert (
        on_model_select(
            agent_name="fake",
            current_model="big",
            prompt="fix the parser",
            messages=[],
            session_id="s",
        )
        == "small-model"
    )
    assert lower_priority_calls == []


def test_on_model_select_passes_context_to_callback():
    seen = {}

    def selector(**kwargs):
        seen.update(kwargs)
        return None

    register_callback("model_select", selector)
    on_model_select(
        agent_name="orch",
        current_model="big",
        prompt="current turn",
        messages=[1, 2],
        session_id="x",
    )
    assert seen["agent_name"] == "orch"
    assert seen["current_model"] == "big"
    assert seen["prompt"] == "current turn"
    assert seen["messages"] == [1, 2]
    assert seen["session_id"] == "x"


# ---- resolve_run_model_selection ------------------------------------------


def test_resolve_applies_hook_choice_and_invalidates_cache():
    register_callback("model_select", lambda **k: "small-model")
    agent = FakeAgent(base="big-model")
    chosen = resolve_run_model_selection(agent, "current prompt", [], "s")
    assert chosen == "small-model"
    assert agent.get_auto_model_override() == "small-model"
    assert agent._code_generation_agent is None  # forced rebuild


def test_resolve_noop_when_hook_picks_same_model():
    register_callback("model_select", lambda **k: "big-model")
    agent = FakeAgent(base="big-model")
    assert resolve_run_model_selection(agent, "current prompt", [], "s") is None
    assert agent.get_auto_model_override() is None
    assert agent._code_generation_agent is not None  # no rebuild


def test_explicit_runtime_override_beats_hook():
    register_callback("model_select", lambda **k: "small-model")
    agent = FakeAgent(base="big-model", runtime="user-picked")
    assert resolve_run_model_selection(agent, "current prompt", [], "s") is None
    assert agent.get_auto_model_override() is None  # hook never consulted


def test_prior_auto_choice_is_reset_each_run():
    # No hook registered this run; a stale auto choice must be cleared.
    agent = FakeAgent(base="big-model")
    agent.set_auto_model_override("stale-small")
    assert resolve_run_model_selection(agent, "current prompt", [], "s") is None
    assert agent.get_auto_model_override() is None
    assert agent._code_generation_agent is None  # invalidated on reset


def test_broken_selector_never_raises():
    def boom(**k):
        raise RuntimeError("selector exploded")

    register_callback("model_select", boom)
    agent = FakeAgent(base="big-model")
    # Must swallow the error and leave the run on its normal model.
    assert resolve_run_model_selection(agent, "current prompt", [], "s") is None
    assert agent.get_auto_model_override() is None
