"""Extension seam: BaseAgent.transform_mcp_toolsets.

Covers the contract enforced in ``_builder.build_pydantic_agent``:

* default (no override) is a true identity no-op
* an override is invoked exactly once and its return value is what actually
  gets used for both agent construction and MCP lifecycle tracking
* a faulty override fails open (falls back to the original toolsets, warns,
  and still lets construction succeed)
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset

from code_puppy.agents import _builder
from code_puppy.agents.base_agent import BaseAgent


class _FakeAgentConfig(BaseAgent):
    """Minimal concrete BaseAgent for driving the real build path."""

    def __init__(self, transform=None):
        super().__init__()
        self._transform = transform

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

    def get_model_name(self):
        return "test-model"

    def transform_mcp_toolsets(self, toolsets):
        if self._transform is not None:
            return self._transform(toolsets)
        return super().transform_mcp_toolsets(toolsets)


def _fake_load_model_with_fallback(*_args, **_kwargs):
    return TestModel(custom_output_text="woof"), "test-model"


@contextmanager
def _patched_build(agent, mcp_servers):
    with (
        patch.object(
            _builder, "load_model_with_fallback", _fake_load_model_with_fallback
        ),
        patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
        patch.object(_builder, "load_mcp_servers", lambda **k: mcp_servers),
        patch.object(_builder, "make_model_settings", lambda *a, **k: None),
        patch("code_puppy.tools.register_tools_for_agent", lambda *a, **k: None),
    ):
        yield


def test_default_transform_is_identity_no_op():
    """No override: the exact same objects, same order, come back out."""
    toolsets = [FunctionToolset(), FunctionToolset()]
    agent = _FakeAgentConfig()

    result = agent.transform_mcp_toolsets(toolsets)

    assert result is toolsets
    assert result == toolsets


def test_default_build_uses_unmodified_toolsets():
    """End-to-end: with no override, the builder wires up the same toolsets."""
    toolsets = [FunctionToolset()]
    agent = _FakeAgentConfig()

    with _patched_build(agent, toolsets):
        _builder.build_pydantic_agent(agent)

    assert agent._mcp_servers == toolsets


def test_override_invoked_once_and_result_used_for_construction():
    """Override receives the post-filter list, not the raw mcp_servers."""
    original = [FunctionToolset()]
    filtered_sentinel = [FunctionToolset()]  # distinct object, asserted by identity
    replacement = [FunctionToolset(), FunctionToolset()]
    calls = []

    def _transform(toolsets):
        calls.append(toolsets)
        return replacement

    agent = _FakeAgentConfig(transform=_transform)

    with (
        _patched_build(agent, original),
        patch.object(
            _builder,
            "filter_conflicting_mcp_tools",
            lambda *_a, **_k: filtered_sentinel,
        ),
    ):
        built = _builder.build_pydantic_agent(agent)

    assert len(calls) == 1
    assert calls[0] is filtered_sentinel
    assert agent._mcp_servers is replacement
    assert built is not None


def test_faulty_override_fails_open_to_original_toolsets():
    """A raising override must not crash construction; it falls back."""
    original = [FunctionToolset()]

    def _transform(_toolsets):
        raise RuntimeError("boom")

    agent = _FakeAgentConfig(transform=_transform)

    with (
        _patched_build(agent, original),
        patch.object(_builder, "emit_warning") as mock_warn,
    ):
        built = _builder.build_pydantic_agent(agent)

    assert built is not None
    assert agent._mcp_servers == original
    mock_warn.assert_called_once()


@pytest.mark.parametrize("bad_result", [None, "nope", 42, "not-a-list"])
def test_various_non_list_returns_fail_open(bad_result):
    """An override that returns a non-list is treated as a fault, not used."""
    original = [FunctionToolset()]
    agent = _FakeAgentConfig(transform=lambda _toolsets: bad_result)

    with (
        _patched_build(agent, original),
        patch.object(_builder, "emit_warning") as mock_warn,
    ):
        _builder.build_pydantic_agent(agent)

    assert agent._mcp_servers == original
    mock_warn.assert_called_once()
