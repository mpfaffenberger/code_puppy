"""MCP toolsets injected for one agent instance survive every build.

An embedder that brings its own MCP servers (an ACP client's ``mcpServers``)
attaches them with ``BaseAgent.set_runtime_mcp_toolsets``. Before this,
``build_pydantic_agent`` rebuilt ``_mcp_servers`` from ``mcp_servers.json``
alone, so injected servers were dropped on the first build and never became
toolsets.
"""

from contextlib import contextmanager
from unittest.mock import patch

from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import FunctionToolset

from code_puppy.agents import _builder
from code_puppy.agents.base_agent import BaseAgent


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

    def get_model_name(self):
        return "test-model"


@contextmanager
def _patched_build(configured):
    with (
        patch.object(
            _builder,
            "load_model_with_fallback",
            lambda *a, **k: (TestModel(custom_output_text="woof"), "test-model"),
        ),
        patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
        patch.object(_builder, "load_mcp_servers", lambda **k: list(configured)),
        patch.object(_builder, "make_model_settings", lambda *a, **k: None),
        patch("code_puppy.tools.register_tools_for_agent", lambda *a, **k: None),
    ):
        yield


def test_injected_toolsets_join_configured_ones_on_build():
    configured, injected = FunctionToolset(), FunctionToolset()
    agent = _Agent()
    agent.set_runtime_mcp_toolsets([injected])

    with _patched_build([configured]):
        _builder.build_pydantic_agent(agent)

    assert agent._mcp_servers == [configured, injected]


def test_injected_toolsets_survive_a_rebuild():
    injected = FunctionToolset()
    agent = _Agent()
    agent.set_runtime_mcp_toolsets([injected])

    with _patched_build([]):
        _builder.build_pydantic_agent(agent)
        _builder.build_pydantic_agent(agent)

    assert agent._mcp_servers == [injected]


def test_injected_toolsets_are_per_instance():
    agent, other = _Agent(), _Agent()
    agent.set_runtime_mcp_toolsets([FunctionToolset()])

    with _patched_build([]):
        _builder.build_pydantic_agent(other)

    assert other.get_runtime_mcp_toolsets() == []
    assert other._mcp_servers == []


def test_no_tools_still_means_no_mcp_toolsets(monkeypatch):
    monkeypatch.setattr("code_puppy.tools.tools_disabled", lambda: True)
    agent = _Agent()
    agent.set_runtime_mcp_toolsets([FunctionToolset()])

    with _patched_build([]):
        _builder.build_pydantic_agent(agent)

    assert agent._mcp_servers == []


def test_getter_returns_a_copy():
    agent = _Agent()
    agent.set_runtime_mcp_toolsets([FunctionToolset()])

    agent.get_runtime_mcp_toolsets().clear()

    assert len(agent.get_runtime_mcp_toolsets()) == 1
