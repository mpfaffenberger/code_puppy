"""Observability span-naming contract for pydantic-ai agents.

pydantic-ai names the per-run OTel span ``invoke_agent {agent.name}`` (and the
Logfire message ``{agent.name} run``). When ``name=`` is omitted, pydantic-ai
*infers* a name from the caller's frame variables, which produced traces like
``invoke_agent temp_agent`` (every sub-agent!) and ``invoke_agent
pydantic_agent`` (the main agent). These tests pin the fix: both construction
paths must pass the *logical* agent name explicitly.

No Logfire/OTel wiring is needed here -- asserting ``.name`` on the built
pydantic-ai agent is exactly what instrumentation consumes
(``ctx.agent.name``), so it locks the span name without global tracer state.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic_ai.models.test import TestModel
from pydantic_ai.settings import ModelSettings


class _FakeAgentConfig:
    """Minimal BaseAgent-shaped config for driving the real build paths."""

    name = "web-retriever"
    display_name = "Web Retriever"

    def __init__(self):
        self._message_history = []
        self._compacted_message_hashes = set()
        self._puppy_rules = None

    @contextmanager
    def temporary_model_name_override(self, _model_name):
        yield

    def get_model_name(self):
        return "test-model"

    def get_full_system_prompt(self):
        return "You are a test agent."

    def get_available_tools(self):
        return []

    def get_message_history(self):
        return self._message_history

    def set_message_history(self, history):
        self._message_history = history

    def __getattr__(self, item):
        # Misc numeric config probes used by history processors.
        if item.startswith("__"):
            raise AttributeError(item)
        return lambda *a, **k: 0


def _fake_load_model_with_fallback(*_args, **_kwargs):
    return TestModel(custom_output_text="woof"), "test-model"


def test_build_pydantic_agent_sets_logical_agent_name():
    """Main agent path: spans must read 'invoke_agent code-puppy', not
    'invoke_agent pydantic_agent' (the inferred frame-variable name)."""
    from code_puppy.agents import _builder

    cfg = _FakeAgentConfig()
    cfg.name = "code-puppy"

    with (
        patch.object(
            _builder, "load_model_with_fallback", _fake_load_model_with_fallback
        ),
        patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
        patch.object(_builder, "load_mcp_servers", lambda **k: []),
        patch(
            "code_puppy.agents._model_settings.make_model_settings",
            lambda *a, **k: ModelSettings(),
        ),
        patch("code_puppy.tools.register_tools_for_agent", lambda *a, **k: None),
    ):
        built = _builder.build_pydantic_agent(cfg)

    assert built.name == "code-puppy"


@pytest.mark.asyncio
async def test_invoke_agent_impl_sets_subagent_name():
    """Sub-agent path: every delegate must carry its own logical name so
    parallel invocations don't all render as 'invoke_agent temp_agent'."""
    from code_puppy.tools import subagent_invocation as si

    cfg = _FakeAgentConfig()
    captured = {}

    def capture_wrap(_agent_config, pydantic_agent, **_kwargs):
        captured["agent"] = pydantic_agent
        return pydantic_agent

    with (
        patch("code_puppy.agents.agent_manager.load_agent", return_value=cfg),
        patch(
            "code_puppy.agents._builder.load_model_with_fallback",
            _fake_load_model_with_fallback,
        ),
        patch(
            "code_puppy.agents._model_settings.make_model_settings",
            lambda *a, **k: ModelSettings(),
        ),
        patch("code_puppy.config.get_value", return_value="true"),  # no MCP
        patch.object(si, "on_wrap_pydantic_agent", capture_wrap),
    ):
        out = await si._invoke_agent_impl(
            context=SimpleNamespace(),
            agent_name="web-retriever",
            prompt="fetch me a stick",
        )

    assert out.error is None
    assert captured["agent"].name == "web-retriever"
