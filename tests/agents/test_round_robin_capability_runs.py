"""End-to-end and wiring tests for the ``RoundRobinRequests`` capability.

Real ``Agent`` runs (streamed + non-streamed) proving capability custody,
rotation cadence, guest fallbacks, the documented continuation/teardown
divergences (pinned in both custodies), instrumentation gate behaviour, and
the builder / sub-agent construction-site wiring. The direct seam contract
lives in ``test_round_robin_capability.py``.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.wrapper import WrapperModel

from code_puppy.agents._round_robin import RoundRobinRequests
from code_puppy.round_robin_model import RoundRobinModel
from tests.agents.round_robin_capability_harness import (
    ScriptedLeaf,
    complete_response,
    make_leaf,
    spy_eager_requests,
    suspended_response,
)


async def test_agent_runs_distribute_across_leaves_capability_owned():
    hits: dict[str, int] = {}
    rr = RoundRobinModel(make_leaf("a", hits), make_leaf("b", hits))
    eager_calls = spy_eager_requests(rr)
    agent = Agent(model=rr, output_type=str, capabilities=[RoundRobinRequests(rr)])

    first = await agent.run("one")
    second = await agent.run("two")

    assert first.output == "reply from a"
    assert second.output == "reply from b"
    assert hits == {"a": 1, "b": 1}
    assert eager_calls == []  # ownership: the Model methods never ran


async def test_streamed_agent_run_routes_through_capability():
    hits: dict[str, int] = {}
    rr = RoundRobinModel(make_leaf("a", hits), make_leaf("b", hits))
    eager_calls = spy_eager_requests(rr)
    agent = Agent(model=rr, output_type=str, capabilities=[RoundRobinRequests(rr)])

    async def benign_handler(ctx, events):
        async for _ in events:
            pass

    result = await agent.run("one", event_stream_handler=benign_handler)

    assert result.output == "reply from a"
    assert hits == {"a": 1}
    assert eager_calls == []


async def test_rotate_every_cadence_preserved():
    hits: dict[str, int] = {}
    rr = RoundRobinModel(make_leaf("a", hits), make_leaf("b", hits), rotate_every=2)
    agent = Agent(model=rr, output_type=str, capabilities=[RoundRobinRequests(rr)])

    outputs = [(await agent.run(str(i))).output for i in range(4)]

    assert outputs == [
        "reply from a",
        "reply from a",
        "reply from b",
        "reply from b",
    ]


async def test_explicit_run_model_stays_authoritative():
    """``run(model=...)`` replaces the round-robin model wholesale — the
    capability passes through and the rotation is untouched, exactly as the
    eager path behaved when the model kwarg was overridden."""
    hits: dict[str, int] = {}
    rr = RoundRobinModel(make_leaf("a", hits), make_leaf("b", hits))
    explicit = make_leaf("explicit", hits)
    agent = Agent(model=rr, output_type=str, capabilities=[RoundRobinRequests(rr)])

    result = await agent.run("one", model=explicit)

    assert result.output == "reply from explicit"
    assert hits == {"explicit": 1}
    assert rr.next_model().model_name == "a"  # rotation never advanced


async def test_wrapped_model_falls_back_to_eager_rotation():
    """When something re-wraps the round-robin model (instrumentation), the
    identity gate fails and the eager ``RoundRobinModel.request`` path still
    rotates — every request advances the rotation exactly once."""
    hits: dict[str, int] = {}
    rr = RoundRobinModel(make_leaf("a", hits), make_leaf("b", hits))
    eager_calls = spy_eager_requests(rr)
    agent = Agent(
        model=WrapperModel(rr),
        output_type=str,
        capabilities=[RoundRobinRequests(rr)],
    )

    first = await agent.run("one")
    second = await agent.run("two")

    assert first.output == "reply from a"
    assert second.output == "reply from b"
    assert hits == {"a": 1, "b": 1}
    assert eager_calls == ["request", "request"]


async def test_rotation_state_shared_between_eager_and_capability_paths():
    hits: dict[str, int] = {}
    rr = RoundRobinModel(make_leaf("a", hits), make_leaf("b", hits))
    # One eager guest request advances the shared rotation...
    await rr.request(
        [ModelRequest(parts=[UserPromptPart(content="direct")])],
        None,
        ModelRequestParameters(),
    )
    assert hits == {"a": 1}

    # ...so the next capability-owned run picks up at leaf "b".
    agent = Agent(model=rr, output_type=str, capabilities=[RoundRobinRequests(rr)])
    result = await agent.run("one")
    assert result.output == "reply from b"


async def test_continuation_segments_stay_pinned_to_opening_leaf():
    """Documented divergence: a suspended → complete continuation chain is
    served entirely by the leaf that opened it; rotation advances once per
    wrapped request, not once per segment."""
    leaf_a = ScriptedLeaf(
        "a", [lambda: suspended_response("a"), lambda: complete_response("a")]
    )
    leaf_b = ScriptedLeaf("b", [lambda: complete_response("b")])
    rr = RoundRobinModel(leaf_a, leaf_b)
    agent = Agent(model=rr, output_type=str, capabilities=[RoundRobinRequests(rr)])

    result = await agent.run("one")

    assert result.output == "partial from afinal from a"  # one leaf, whole chain
    assert (leaf_a.calls, leaf_b.calls) == (2, 0)
    # Rotation advanced exactly once for the whole chain.
    assert rr.next_model() is leaf_b


async def test_eager_guest_path_still_rotates_across_continuation_segments():
    """Guest custody pin: the intact Model class keeps the old per-segment
    rotation (each segment enters RoundRobinModel.request), stitching the
    merged response from two different leaves — the behaviour the owned path
    deliberately diverges from."""
    leaf_a = ScriptedLeaf(
        "a", [lambda: suspended_response("a"), lambda: complete_response("a")]
    )
    leaf_b = ScriptedLeaf("b", [lambda: complete_response("b")])
    rr = RoundRobinModel(leaf_a, leaf_b)
    agent = Agent(model=rr, output_type=str)  # no capability: eager custody

    result = await agent.run("one")

    assert result.output == "partial from afinal from b"
    assert (leaf_a.calls, leaf_b.calls) == (1, 1)


async def test_streamed_teardown_skips_span_record_on_owned_path():
    """Documented divergence: the owned streamed fix-up records only after
    the stream fully drains, so a consumer failure mid-stream records
    nothing."""
    hits: dict[str, int] = {}
    rr = RoundRobinModel(make_leaf("a", hits), make_leaf("b", hits))
    agent = Agent(model=rr, output_type=str, capabilities=[RoundRobinRequests(rr)])
    recorded: list = []

    async def failing_handler(ctx, events):
        async for _ in events:
            raise RuntimeError("consumer exploded")

    with patch.object(
        RoundRobinModel,
        "record_span_attributes",
        lambda self, model: recorded.append(model),
    ):
        with pytest.raises(Exception):
            await agent.run("one", event_stream_handler=failing_handler)

    assert recorded == []


async def test_streamed_teardown_still_records_span_on_eager_guest_path():
    """Contrast pin for the divergence above: eager custody records the leaf
    at stream-open, so the same mid-consume failure still records it."""
    hits: dict[str, int] = {}
    rr = RoundRobinModel(make_leaf("a", hits), make_leaf("b", hits))
    agent = Agent(model=rr, output_type=str)  # no capability: eager custody
    recorded: list = []

    async def failing_handler(ctx, events):
        async for _ in events:
            raise RuntimeError("consumer exploded")

    with patch.object(
        RoundRobinModel,
        "record_span_attributes",
        lambda self, model: recorded.append(model),
    ):
        with pytest.raises(Exception):
            await agent.run("one", event_stream_handler=failing_handler)

    assert len(recorded) == 1
    assert recorded[0].model_name == "a"


async def test_prepare_request_application_count_matches_eager_path():
    """Non-idempotence probe: at the moment the leaf serves the request, the
    parameters must have passed ``customize_request_parameters`` the same
    number of times on both delivery paths (explicit prepare + the leaf's
    internal re-prepare)."""
    eager_leaf = ScriptedLeaf("eager", [lambda: complete_response("eager")])
    eager_rr = RoundRobinModel(eager_leaf)
    await eager_rr.request(
        [ModelRequest(parts=[UserPromptPart(content="direct")])],
        None,
        ModelRequestParameters(),
    )

    owned_leaf = ScriptedLeaf("owned", [lambda: complete_response("owned")])
    owned_rr = RoundRobinModel(owned_leaf)
    agent = Agent(
        model=owned_rr,
        output_type=str,
        capabilities=[RoundRobinRequests(owned_rr)],
    )
    await agent.run("one")

    assert len(eager_leaf.received) == len(owned_leaf.received) == 1
    eager_settings, eager_customizations = eager_leaf.received[0]
    owned_settings, owned_customizations = owned_leaf.received[0]
    assert eager_customizations == owned_customizations == 2
    assert eager_settings == owned_settings


async def test_instrumented_agent_still_takes_the_owned_path():
    """Pins the corrected instrumentation claim: 2.31.0 instrumentation is
    capability-based (no model wrapping), so instrumented requests still
    carry the bare round-robin model and the identity gate HOLDS."""
    from opentelemetry.sdk.trace import TracerProvider
    from pydantic_ai.models.instrumented import InstrumentationSettings

    hits: dict[str, int] = {}
    rr = RoundRobinModel(make_leaf("a", hits), make_leaf("b", hits))
    eager_calls = spy_eager_requests(rr)
    agent = Agent(model=rr, output_type=str, capabilities=[RoundRobinRequests(rr)])
    agent.instrument = InstrumentationSettings(tracer_provider=TracerProvider())

    result = await agent.run("one")

    assert result.output == "reply from a"
    assert hits == {"a": 1}
    assert eager_calls == []  # gate held: instrumentation did not re-wrap


async def test_coexists_with_plugin_message_transform():
    """Shares wrap_model_request with PluginMessageTransform: the transform's
    plugin callbacks still see (and mutate) messages while routing holds."""
    from code_puppy import callbacks
    from code_puppy.agents._model_message_transform import (
        build_model_message_transform,
    )

    hits: dict[str, int] = {}
    rr = RoundRobinModel(make_leaf("a", hits), make_leaf("b", hits))
    seen: list[int] = []

    def observe(_agent_name, messages):
        seen.append(len(messages))

    callbacks.register_callback("transform_model_messages", observe)
    try:
        agent = Agent(
            model=rr,
            output_type=str,
            capabilities=[
                RoundRobinRequests(rr),
                build_model_message_transform("test-agent"),
            ],
        )
        result = await agent.run("one")
    finally:
        callbacks.clear_callbacks("transform_model_messages")

    assert result.output == "reply from a"
    assert seen == [1]
    assert hits == {"a": 1}


def _find_round_robin_capabilities(built_agent) -> list[RoundRobinRequests]:
    found: list[RoundRobinRequests] = []

    def visitor(capability):
        if isinstance(capability, RoundRobinRequests):
            found.append(capability)

    built_agent.root_capability.apply(visitor)
    return found


def _build_with_model(model):
    from contextlib import contextmanager

    from code_puppy.agents import _builder

    class _FakeAgentConfig:
        name = "round-robin-puppy"
        display_name = "Round Robin Puppy"

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
            if item.startswith("__"):
                raise AttributeError(item)
            return lambda *a, **k: 0

    with (
        patch.object(
            _builder,
            "load_model_with_fallback",
            lambda *a, **k: (model, "test-model"),
        ),
        patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
        patch.object(_builder, "load_mcp_servers", lambda **k: []),
        patch.object(_builder, "make_model_settings", lambda *a, **k: None),
        patch("code_puppy.tools.register_tools_for_agent", lambda *a, **k: None),
    ):
        return _builder.build_pydantic_agent(_FakeAgentConfig())


def test_builder_attaches_capability_for_round_robin_model():
    rr = RoundRobinModel(make_leaf("a", {}), make_leaf("b", {}))
    built = _build_with_model(rr)
    found = _find_round_robin_capabilities(built)
    assert len(found) == 1
    assert found[0].model is rr


def test_builder_skips_capability_for_plain_model():
    built = _build_with_model(make_leaf("plain", {}))
    assert _find_round_robin_capabilities(built) == []


def test_subagent_construction_site_wires_round_robin():
    """Source pin: the sub-agent Agent(...) construction splices the same
    conditional builder, so a round-robin-pinned sub-agent is capability-owned
    too."""
    import inspect

    from code_puppy.tools import subagent_invocation

    source = inspect.getsource(subagent_invocation)
    assert "build_round_robin_requests" in source
    assert "*build_round_robin_requests(model)" in source


class _SubagentConfig:
    """Minimal agent-config shape for driving the real sub-agent invocation."""

    name = "test-agent"

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


async def test_subagent_invocation_routes_through_capability():
    """End-to-end sub-agent custody: a round-robin-resolved sub-agent's
    (streamed) request is served by the capability — the eager Model methods
    never run."""
    from code_puppy.tools import subagent_invocation

    hits: dict[str, int] = {}
    rr = RoundRobinModel(make_leaf("a", hits), make_leaf("b", hits))
    eager_calls = spy_eager_requests(rr)

    with (
        patch(
            "code_puppy.agents.agent_manager.load_agent",
            return_value=_SubagentConfig(),
        ),
        patch(
            "code_puppy.agents._builder.load_model_with_fallback",
            lambda *a, **k: (rr, "test-model"),
        ),
        patch(
            "code_puppy.model_factory.make_model_settings",
            lambda *_args, **_kwargs: None,
        ),
        patch("code_puppy.config.get_value", return_value="true"),
    ):
        result = await subagent_invocation._invoke_agent_impl(
            context=SimpleNamespace(), agent_name="test-agent", prompt="start"
        )

    assert result.error is None
    assert hits == {"a": 1}
    assert eager_calls == []
