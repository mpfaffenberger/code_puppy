"""Contract tests for :class:`code_puppy.agents._resolved_model.ResolvedModel`.

The capability replaces the ``Agent(model=...)`` constructor kwarg at both
construction sites (``_builder.build_pydantic_agent`` and
``subagent_invocation``). These tests pin the parity contract documented in
the module docstring: identical wire behavior on the standard path, explicit
run/override models staying authoritative, and the one observable divergence
(the built agent's ``.model`` slot reads ``None``).
"""

from unittest.mock import patch

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from code_puppy.agents._resolved_model import ResolvedModel


def _wire_shape(messages: list[ModelMessage]) -> list[tuple]:
    """Project wire messages onto their model-visible content.

    Timestamps and request ids legitimately differ between two separate
    runs, so equality is asserted on everything the model actually sees:
    message type, instructions, and each part's type + content.
    """
    return [
        (
            type(message).__name__,
            getattr(message, "instructions", None),
            [
                (type(part).__name__, getattr(part, "content", None))
                for part in message.parts
            ],
        )
        for message in messages
    ]


def _capture_model(reply: str, seen: list[list[ModelMessage]]) -> FunctionModel:
    """A FunctionModel that records the wire messages of every request."""

    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        seen.append(messages)
        return ModelResponse(parts=[TextPart(reply)])

    return FunctionModel(respond)


def test_get_model_returns_exact_instance():
    seen: list[list[ModelMessage]] = []
    model = _capture_model("woof", seen)
    capability = ResolvedModel(model)
    assert capability.get_model() is model


def test_not_spec_constructible():
    # Holds a live Model instance -- deliberately opted out of spec-based
    # construction, like SteerInjection/HistoryCompaction.
    assert ResolvedModel.get_serialization_name() is None


async def test_kwarg_vs_capability_wire_parity():
    """Same prompt, same instructions: both delivery paths produce identical
    wire messages and identical output."""
    kwarg_seen: list[list[ModelMessage]] = []
    cap_seen: list[list[ModelMessage]] = []

    kwarg_agent = Agent(
        model=_capture_model("done", kwarg_seen),
        instructions="Be a good dog.",
    )
    cap_agent = Agent(
        instructions="Be a good dog.",
        capabilities=[ResolvedModel(_capture_model("done", cap_seen))],
    )

    kwarg_result = await kwarg_agent.run("fetch")
    cap_result = await cap_agent.run("fetch")

    assert kwarg_result.output == cap_result.output == "done"
    assert len(kwarg_seen) == len(cap_seen) == 1
    assert _wire_shape(kwarg_seen[0]) == _wire_shape(cap_seen[0])
    assert _wire_shape(kwarg_seen[0])[0][1] == "Be a good dog."


async def test_run_model_argument_stays_authoritative():
    """``run(model=...)`` short-circuits the capability contribution, exactly
    as it overrode the old constructor kwarg."""
    cap_seen: list[list[ModelMessage]] = []
    run_seen: list[list[ModelMessage]] = []

    agent = Agent(capabilities=[ResolvedModel(_capture_model("cap", cap_seen))])
    result = await agent.run("fetch", model=_capture_model("run", run_seen))

    assert result.output == "run"
    assert run_seen and not cap_seen


async def test_override_model_stays_authoritative_in_scope_only():
    """``Agent.override(model=...)`` wins inside the scope; the capability
    model is back in charge outside it -- same precedence as the old kwarg."""
    cap_seen: list[list[ModelMessage]] = []
    override_seen: list[list[ModelMessage]] = []

    agent = Agent(capabilities=[ResolvedModel(_capture_model("cap", cap_seen))])

    with agent.override(model=_capture_model("override", override_seen)):
        overridden = await agent.run("fetch")
    assert overridden.output == "override"
    assert override_seen and not cap_seen

    restored = await agent.run("fetch")
    assert restored.output == "cap"
    assert cap_seen


def test_agent_model_slot_reads_none():
    """Pinned divergence: the model no longer occupies the agent slot, so the
    built agent's ``.model`` property reads ``None``. No code_puppy call site
    reads it -- everything goes through ``BaseAgent.cur_model``."""
    seen: list[list[ModelMessage]] = []
    agent = Agent(capabilities=[ResolvedModel(_capture_model("woof", seen))])
    assert agent.model is None


class _AgentConfig:
    """Minimal BaseAgent stand-in for driving ``build_pydantic_agent``."""

    name = "test-agent"

    def __init__(self):
        self._message_history = []
        self._compacted_message_hashes = set()
        self._puppy_rules = None

    def get_model_name(self):
        return "test-model"

    def get_full_system_prompt(self):
        return "Test instructions"

    def get_available_tools(self):
        return []

    def get_message_history(self):
        return self._message_history

    def set_message_history(self, history):
        self._message_history = history

    def __getattr__(self, item):
        if item.startswith("__"):
            raise AttributeError(item)
        return lambda *_args, **_kwargs: 0


async def test_build_pydantic_agent_delivers_capability_model():
    """End-to-end: the built agent runs on the resolved model delivered via
    the capability, ``cur_model`` still tracks it, and the agent slot is
    empty."""
    from code_puppy.agents import _builder

    seen: list[list[ModelMessage]] = []
    model = _capture_model("built", seen)
    config = _AgentConfig()

    with (
        patch.object(
            _builder,
            "load_model_with_fallback",
            lambda *_args, **_kwargs: (model, "test-model"),
        ),
        patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
        patch.object(_builder, "load_mcp_servers", lambda **_kwargs: []),
        patch.object(_builder, "make_model_settings", lambda *_args, **_kwargs: None),
        patch(
            "code_puppy.tools.register_tools_for_agent", lambda *_args, **_kwargs: None
        ),
    ):
        built = _builder.build_pydantic_agent(config)
        result = await built.run("fetch")

    assert result.output == "built"
    assert seen, "the resolved model never received the request"
    assert config.cur_model is model
    assert built.model is None
