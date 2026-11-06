"""Callers can require the exact model and agent they asked for.

``load_model_with_fallback`` and ``load_agent`` quietly substitute another
model or ``code-puppy`` when the requested one is unavailable. That is the
right default for the TUI, but an embedder that reports which model and
agent a session runs on (an ACP client showing a model picker) would then
report one thing while running another. ``allow_fallback=False`` makes the
substitution an error instead.
"""

from unittest.mock import patch

import pytest
from pydantic_ai.models.test import TestModel

from code_puppy.agents import _builder
from code_puppy.agents.agent_manager import load_agent
from code_puppy.agents.base_agent import BaseAgent
from code_puppy.model_factory import ModelFactory

CONFIG = {"available": {"type": "test"}}


def _get_model(name, config):
    if name not in config:
        raise ValueError(f"Model '{name}' not found in configuration.")
    return TestModel(custom_output_text="woof")


@pytest.fixture(autouse=True)
def _models():
    _builder.reset_model_fallback_warnings()
    with (
        patch.object(ModelFactory, "get_model", staticmethod(_get_model)),
        patch.object(_builder, "get_global_model_name", lambda: "available"),
    ):
        yield
    _builder.reset_model_fallback_warnings()


class _Agent(BaseAgent):
    @property
    def name(self):
        return "test-agent"

    @property
    def display_name(self):
        return "Test Agent"

    @property
    def description(self):
        return "test"

    def get_system_prompt(self):
        return "You are a test agent."

    def get_available_tools(self):
        return []


def test_default_still_falls_back():
    _, name = _builder.load_model_with_fallback("missing", CONFIG, "g")

    assert name == "available"


def test_exact_load_raises_instead_of_falling_back():
    with patch.object(_builder, "emit_warning") as warn:
        with pytest.raises(ValueError, match="'missing' not found"):
            _builder.load_model_with_fallback(
                "missing", CONFIG, "g", allow_fallback=False
            )

    warn.assert_not_called()


def test_exact_load_returns_the_requested_model():
    _, name = _builder.load_model_with_fallback(
        "available", CONFIG, "g", allow_fallback=False
    )

    assert name == "available"


def test_agent_override_without_fallback_fails_the_build():
    agent = _Agent()
    agent.set_runtime_model_name_override("missing", allow_fallback=False)

    with (
        patch.object(_builder.ModelFactory, "load_config", lambda: CONFIG),
        patch("code_puppy.tools.register_tools_for_agent", lambda *a, **k: None),
        pytest.raises(ValueError, match="'missing' not found"),
    ):
        _builder.build_pydantic_agent(agent)


def test_agent_override_keeps_fallback_by_default():
    agent = _Agent()
    agent.set_runtime_model_name_override("missing")

    with (
        patch.object(_builder.ModelFactory, "load_config", lambda: CONFIG),
        patch.object(_builder, "make_model_settings", lambda *a, **k: None),
        patch("code_puppy.tools.register_tools_for_agent", lambda *a, **k: None),
    ):
        _builder.build_pydantic_agent(agent)

    assert agent._last_model_name == "available"


def test_temporary_override_restores_the_fallback_setting():
    agent = _Agent()

    with agent.temporary_model_name_override("missing", allow_fallback=False):
        assert agent.allows_runtime_model_fallback() is False

    assert agent.allows_runtime_model_fallback() is True
    assert agent.get_runtime_model_name_override() is None


def test_unknown_agent_falls_back_by_default():
    assert load_agent("no-such-agent").name == "code-puppy"


def test_unknown_agent_raises_without_fallback():
    with pytest.raises(ValueError, match="'no-such-agent' not found"):
        load_agent("no-such-agent", allow_fallback=False)
