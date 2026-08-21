"""PerModelSettings: the ``model_settings=`` constructor kwarg as a capability."""

from unittest.mock import patch

from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.settings import ModelSettings

from code_puppy.agents import _model_settings
from code_puppy.agents._model_settings import PerModelSettings
from code_puppy.model_factory import make_model_settings

_MODEL_NAME = "capability-parity-model"


def test_snapshot_is_taken_at_construction_and_frozen():
    """Settings are computed once, at build time -- never re-read per run.

    The old kwarg path froze the payload when the agent was built; a config
    edit only landed on rebuild. ``get_model_settings`` re-extraction per run
    must observe the same freeze.
    """
    payloads = [ModelSettings(max_tokens=111), ModelSettings(max_tokens=222)]
    with patch.object(
        _model_settings, "make_model_settings", side_effect=payloads
    ) as factory:
        cap = PerModelSettings(_MODEL_NAME, max_tokens=111)

        first = cap.get_model_settings()
        second = cap.get_model_settings()

    factory.assert_called_once_with(_MODEL_NAME, 111)
    assert first is second
    assert first == ModelSettings(max_tokens=111)


def test_capability_matches_make_model_settings():
    """The capability is a pure carrier: same inputs, same payload."""
    cap = PerModelSettings(_MODEL_NAME)

    assert cap.get_model_settings() == make_model_settings(_MODEL_NAME)


async def test_wire_parity_with_model_settings_kwarg():
    """The model receives identical settings from the capability and the kwarg.

    Runs the same FunctionModel twice -- once with the historical
    ``Agent(model_settings=...)`` wiring, once with ``PerModelSettings`` in
    ``capabilities=[...]`` -- and asserts the merged settings that reach the
    model request are equal.
    """
    captured: list[ModelSettings | None] = []

    def model_fn(messages, info):
        captured.append(info.model_settings)
        return ModelResponse(parts=[TextPart(content="ok")])

    settings = make_model_settings(_MODEL_NAME)

    kwarg_agent = Agent(FunctionModel(model_fn), model_settings=settings)
    await kwarg_agent.run("hello")

    capability_agent = Agent(
        FunctionModel(model_fn),
        capabilities=[PerModelSettings(_MODEL_NAME)],
    )
    await capability_agent.run("hello")

    kwarg_settings, capability_settings = captured
    assert kwarg_settings is not None
    assert capability_settings == kwarg_settings


async def test_full_layering_base_then_capability_then_run():
    """Model base settings < capability snapshot < per-run settings.

    The per-run override path (``agent.run(model_settings=...)``) keeps its
    historical precedence over code_puppy's settings -- proven with all three
    layers populated and overlapping.
    """
    captured: list[ModelSettings | None] = []

    def model_fn(messages, info):
        captured.append(info.model_settings)
        return ModelResponse(parts=[TextPart(content="ok")])

    with patch.object(
        _model_settings,
        "make_model_settings",
        return_value=ModelSettings(max_tokens=100, temperature=0.1),
    ):
        cap = PerModelSettings(_MODEL_NAME)

    agent = Agent(
        FunctionModel(
            model_fn,
            # temperature overlaps with the capability layer so the
            # capability-over-base assertion below is unmasked: a base<->cap
            # ordering regression would surface as 0.9 winning.
            settings=ModelSettings(max_tokens=1, temperature=0.9, seed=42),
        ),
        capabilities=[cap],
    )
    await agent.run("hello", model_settings=ModelSettings(max_tokens=7))

    (settings,) = captured
    assert settings is not None
    assert settings["max_tokens"] == 7  # run layer wins
    assert settings["temperature"] == 0.1  # capability beats model base
    assert settings["seed"] == 42  # untouched model base survives


async def test_agent_override_merges_below_capability():
    """Pin the one deliberate divergence from the kwarg wiring.

    ``Agent.override(model_settings=...)`` replaces the agent-slot settings
    -- previously ours, now empty -- so the capability snapshot merges after
    it and wins conflicting keys. No code_puppy call site uses the seam;
    this test keeps the trade-off visible rather than accidental.
    """
    captured: list[ModelSettings | None] = []

    def model_fn(messages, info):
        captured.append(info.model_settings)
        return ModelResponse(parts=[TextPart(content="ok")])

    with patch.object(
        _model_settings,
        "make_model_settings",
        return_value=ModelSettings(max_tokens=100, temperature=0.1),
    ):
        cap = PerModelSettings(_MODEL_NAME)

    agent = Agent(FunctionModel(model_fn), capabilities=[cap])
    with agent.override(model_settings=ModelSettings(max_tokens=7)):
        await agent.run("hello")

    (settings,) = captured
    assert settings is not None
    assert settings["max_tokens"] == 100  # capability wins over override
    assert settings["temperature"] == 0.1


def test_stays_spec_constructible():
    """``from_spec`` builds a working instance from plain-data fields."""
    assert PerModelSettings.get_serialization_name() == "PerModelSettings"

    payload = ModelSettings(max_tokens=123)
    with patch.object(
        _model_settings, "make_model_settings", return_value=payload
    ) as factory:
        cap = PerModelSettings.from_spec(_MODEL_NAME, max_tokens=123)

    factory.assert_called_once_with(_MODEL_NAME, 123)
    assert isinstance(cap, PerModelSettings)
    assert cap.model_name == _MODEL_NAME
    assert cap.max_tokens == 123
    assert cap.get_model_settings() is payload
