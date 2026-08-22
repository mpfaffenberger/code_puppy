"""Contract tests for the ``AssembledInstructions`` capability.

Pins the parity claims made in ``code_puppy/agents/_instructions.py``: the
capability must deliver the same ``ModelRequest.instructions`` bytes the old
``Agent(instructions=...)`` constructor kwarg produced, collapse an empty
prompt to ``None`` identically, lose to ``Agent.override(instructions=...)``
identically, and stay spec-constructible via the inherited defaults.
"""

from contextlib import contextmanager
from unittest.mock import patch

from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from code_puppy.agents._instructions import AssembledInstructions

PROMPT_TEXT = "You are a helpful puppy.\n\nAlways fetch."


def _capture_model(captured: list):
    """FunctionModel that records each request's wire instructions."""

    def model_function(messages, info):
        requests = [m for m in messages if isinstance(m, ModelRequest)]
        captured.append(requests[-1].instructions if requests else None)
        return ModelResponse(parts=[TextPart("woof")])

    return FunctionModel(model_function)


def _run_and_capture(agent: Agent) -> str | None:
    captured: list = []
    agent.run_sync("hi", model=_capture_model(captured))
    assert len(captured) == 1
    return captured[0]


def test_get_instructions_returns_assembled_text():
    cap = AssembledInstructions(PROMPT_TEXT)
    assert cap.get_instructions() == PROMPT_TEXT


def test_wire_parity_with_constructor_kwarg():
    """Capability delivery must be byte-identical to the old kwarg path."""
    via_kwarg = Agent(model=TestModel(), instructions=PROMPT_TEXT)
    via_capability = Agent(
        model=TestModel(), capabilities=[AssembledInstructions(PROMPT_TEXT)]
    )

    kwarg_wire = _run_and_capture(via_kwarg)
    capability_wire = _run_and_capture(via_capability)

    assert kwarg_wire == PROMPT_TEXT
    assert capability_wire == kwarg_wire


def test_empty_instructions_collapse_to_none_on_wire():
    """Both paths strip an empty prompt down to ``instructions=None``."""
    via_kwarg = Agent(model=TestModel(), instructions="")
    via_capability = Agent(model=TestModel(), capabilities=[AssembledInstructions("")])

    assert _run_and_capture(via_kwarg) is None
    assert _run_and_capture(via_capability) is None


def test_override_replaces_capability_instructions():
    """``Agent.override(instructions=...)`` replaces capability contributions,
    exactly as it replaced the constructor kwarg -- no precedence divergence."""
    agent = Agent(model=TestModel(), capabilities=[AssembledInstructions(PROMPT_TEXT)])
    with agent.override(instructions="override wins"):
        assert _run_and_capture(agent) == "override wins"
    # Outside the override the snapshot is back in force.
    assert _run_and_capture(agent) == PROMPT_TEXT


def test_from_spec_constructs_capability():
    """The plain-string field keeps the inherited spec defaults working."""
    agent = Agent.from_spec(
        {"capabilities": [{"AssembledInstructions": {"instructions": PROMPT_TEXT}}]},
        custom_capability_types=[AssembledInstructions],
        model=TestModel(),
    )
    assert _run_and_capture(agent) == PROMPT_TEXT


class _FakeAgentConfig:
    """Minimal BaseAgent-shaped config for driving the real build path."""

    name = "code-puppy"
    display_name = "Code Puppy"

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


def test_build_pydantic_agent_delivers_assembled_prompt():
    """End-to-end: the built agent's wire instructions are the assembled
    prompt, now travelling via the capability instead of the kwarg."""
    from code_puppy.agents import _builder

    cfg = _FakeAgentConfig()
    captured: list = []

    def _fake_load_model_with_fallback(*_args, **_kwargs):
        return _capture_model(captured), "test-model"

    with (
        patch.object(
            _builder, "load_model_with_fallback", _fake_load_model_with_fallback
        ),
        patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
        patch.object(_builder, "load_mcp_servers", lambda **k: []),
        patch.object(_builder, "load_puppy_rules", lambda: None),
        patch.object(_builder, "make_model_settings", lambda *a, **k: None),
        patch("code_puppy.tools.register_tools_for_agent", lambda *a, **k: None),
    ):
        # Computed under the same patches, so ambient plugin prompt
        # fragments can't skew the exact-equality assertion below.
        expected = _builder._assemble_instructions(cfg, "test-model")
        built = _builder.build_pydantic_agent(cfg)
        built.run_sync("hi")

    assert len(captured) == 1
    assert "You are a test agent." in expected
    assert captured[0] == expected
