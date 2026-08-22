"""Contract tests for the ``RoundRobinRequests`` capability.

Pins the promotion of ``RoundRobinModel``'s per-request rotation onto
pydantic-ai's ``wrap_model_request`` seam:

* seam contract — routing, copy isolation, guest pass-through, eager
  ``prepare_request`` merge parity, span-attr fix-up, error custody;
* end-to-end — real ``Agent`` runs (streamed + non-streamed) served by the
  capability with ``RoundRobinModel.request`` never invoked, rotate_every
  cadence, explicit-model override, wrapped-model eager fallback, shared
  rotation state, coexistence with ``PluginMessageTransform``;
* wiring — builder conditional splice (both polarities) and the sub-agent
  construction site source pin.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models import Model, ModelRequestContext, ModelRequestParameters
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.wrapper import WrapperModel

from code_puppy.agents._round_robin import (
    RoundRobinRequests,
    build_round_robin_requests,
)
from code_puppy.round_robin_model import RoundRobinModel

# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------


def _make_leaf(name: str, hits: dict[str, int]) -> FunctionModel:
    """A FunctionModel leaf that records how often it served a request."""

    def respond(messages: list, info: AgentInfo) -> ModelResponse:
        hits[name] = hits.get(name, 0) + 1
        return ModelResponse(parts=[TextPart(f"reply from {name}")])

    async def stream_respond(messages: list, info: AgentInfo):
        hits[name] = hits.get(name, 0) + 1
        yield f"reply from {name}"

    return FunctionModel(respond, stream_function=stream_respond, model_name=name)


class _ScriptedLeaf(Model):
    """A minimal leaf Model with a scripted response sequence.

    Mirrors real provider leaves: ``request`` calls ``self.prepare_request``
    internally before serving, and records what it received so parity
    assertions can compare the eager and capability-owned delivery paths.
    """

    def __init__(self, name: str, script):
        super().__init__()
        self._name = name
        self.script = list(script)
        self.calls = 0
        self.customize_calls = 0
        self.received: list[tuple] = []

    @property
    def model_name(self) -> str:
        return self._name

    @property
    def system(self) -> str:
        return "test"

    def customize_request_parameters(self, model_request_parameters):
        # Deliberately observable (non-idempotent counter): parity between
        # eager and owned paths must show the SAME application count at the
        # moment the request is served.
        self.customize_calls += 1
        return model_request_parameters

    async def request(self, messages, model_settings, model_request_parameters):
        model_settings, model_request_parameters = self.prepare_request(
            model_settings, model_request_parameters
        )
        self.calls += 1
        self.received.append((model_settings, self.customize_calls))
        return self.script.pop(0)()


def _suspended(name: str) -> ModelResponse:
    return ModelResponse(
        parts=[TextPart(f"partial from {name}")],
        state="suspended",
        provider_response_id="job-1",
    )


def _complete(name: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(f"final from {name}")])


def _request_context(model, prompt: str = "hi") -> ModelRequestContext:
    return ModelRequestContext(
        model=model,
        messages=[ModelRequest(parts=[UserPromptPart(content=prompt)])],
        model_settings=None,
        model_request_parameters=ModelRequestParameters(),
    )


async def _passthrough_handler(req_ctx: ModelRequestContext) -> ModelResponse:
    return ModelResponse(parts=[TextPart("handled")])


# ---------------------------------------------------------------------------
# seam contract
# ---------------------------------------------------------------------------


async def test_routes_requests_to_alternating_leaves():
    hits: dict[str, int] = {}
    leaf_a, leaf_b = _make_leaf("a", hits), _make_leaf("b", hits)
    rr = RoundRobinModel(leaf_a, leaf_b)
    capability = RoundRobinRequests(rr)

    routed: list = []

    async def handler(req_ctx: ModelRequestContext) -> ModelResponse:
        routed.append(req_ctx.model)
        return ModelResponse(parts=[TextPart("ok")])

    for _ in range(4):
        await capability.wrap_model_request(
            SimpleNamespace(),
            request_context=_request_context(rr),
            handler=handler,
        )

    assert routed == [leaf_a, leaf_b, leaf_a, leaf_b]


async def test_original_context_is_not_mutated():
    rr = RoundRobinModel(_make_leaf("a", {}), _make_leaf("b", {}))
    capability = RoundRobinRequests(rr)
    original = _request_context(rr)
    original_messages = original.messages

    received: list[ModelRequestContext] = []

    async def handler(req_ctx: ModelRequestContext) -> ModelResponse:
        received.append(req_ctx)
        return ModelResponse(parts=[TextPart("ok")])

    await capability.wrap_model_request(
        SimpleNamespace(), request_context=original, handler=handler
    )

    assert original.model is rr
    assert original.messages is original_messages
    assert received[0] is not original
    assert received[0].messages is original_messages  # shallow copy, #830 shape


async def test_guest_context_passes_through_untouched():
    """A context carrying any other model must pass through identically —
    that request's rotation (if any) belongs to the outer model's own
    ``request`` path."""
    rr = RoundRobinModel(_make_leaf("a", {}), _make_leaf("b", {}))
    capability = RoundRobinRequests(rr)
    other = _make_leaf("other", {})
    ctx = _request_context(other)

    received: list[ModelRequestContext] = []

    async def handler(req_ctx: ModelRequestContext) -> ModelResponse:
        received.append(req_ctx)
        return ModelResponse(parts=[TextPart("ok")])

    await capability.wrap_model_request(
        SimpleNamespace(), request_context=ctx, handler=handler
    )

    assert received[0] is ctx  # identical object — no copy, no swap
    # Rotation untouched: the next owned request still starts at leaf "a".
    assert rr.next_model().model_name == "a"


async def test_prepare_request_merge_mirrors_eager_path():
    """The routed context must carry exactly what ``RoundRobinModel.request``
    would have handed the leaf: ``leaf.prepare_request(settings, params)``."""
    hits: dict[str, int] = {}
    leaf = FunctionModel(
        lambda m, i: ModelResponse(parts=[TextPart("ok")]),
        model_name="leaf",
        settings={"temperature": 0.5},
    )
    rr = RoundRobinModel(leaf, _make_leaf("b", hits))
    capability = RoundRobinRequests(rr)

    ctx = _request_context(rr)
    ctx.model_settings = {"max_tokens": 10}
    expected_settings, expected_params = leaf.prepare_request(
        ctx.model_settings, ctx.model_request_parameters
    )

    received: list[ModelRequestContext] = []

    async def handler(req_ctx: ModelRequestContext) -> ModelResponse:
        received.append(req_ctx)
        return ModelResponse(parts=[TextPart("ok")])

    await capability.wrap_model_request(
        SimpleNamespace(), request_context=ctx, handler=handler
    )

    assert received[0].model_settings == expected_settings
    assert received[0].model_settings["temperature"] == 0.5
    assert received[0].model_settings["max_tokens"] == 10
    assert received[0].model_request_parameters == expected_params


async def test_span_attributes_recorded_for_routed_leaf_only():
    hits: dict[str, int] = {}
    leaf_a, leaf_b = _make_leaf("a", hits), _make_leaf("b", hits)
    rr = RoundRobinModel(leaf_a, leaf_b)
    capability = RoundRobinRequests(rr)
    recorded: list = []

    with patch.object(
        RoundRobinModel,
        "record_span_attributes",
        lambda self, model: recorded.append(model),
    ):
        await capability.wrap_model_request(
            SimpleNamespace(),
            request_context=_request_context(rr),
            handler=_passthrough_handler,
        )
        # Guest pass-through must not record anything.
        await capability.wrap_model_request(
            SimpleNamespace(),
            request_context=_request_context(_make_leaf("other", {})),
            handler=_passthrough_handler,
        )

    assert recorded == [leaf_a]


async def test_handler_error_propagates_after_rotation_without_span_record():
    """Eager parity: rotation advances before the request; a failed request
    neither rolls the rotation back nor records span attributes."""
    hits: dict[str, int] = {}
    rr = RoundRobinModel(_make_leaf("a", hits), _make_leaf("b", hits))
    capability = RoundRobinRequests(rr)
    recorded: list = []

    async def broken_handler(req_ctx: ModelRequestContext) -> ModelResponse:
        raise RuntimeError("provider exploded")

    with patch.object(
        RoundRobinModel,
        "record_span_attributes",
        lambda self, model: recorded.append(model),
    ):
        try:
            await capability.wrap_model_request(
                SimpleNamespace(),
                request_context=_request_context(rr),
                handler=broken_handler,
            )
        except RuntimeError:
            pass
        else:  # pragma: no cover - defensive
            raise AssertionError("handler error must propagate")

    assert recorded == []
    # Rotation already advanced past leaf "a" — next owned request gets "b".
    assert rr.next_model().model_name == "b"


def test_not_spec_constructible():
    # Live Model reference (provider HTTP clients) — #833 precedent.
    assert RoundRobinRequests.get_serialization_name() is None


def test_build_round_robin_requests_conditional_splice():
    rr = RoundRobinModel(_make_leaf("a", {}))
    caps = build_round_robin_requests(rr)
    assert len(caps) == 1 and caps[0].model is rr
    assert build_round_robin_requests(_make_leaf("plain", {})) == []


# ---------------------------------------------------------------------------
# end-to-end through a real Agent
# ---------------------------------------------------------------------------


def _spy_eager_requests(rr: RoundRobinModel) -> list[str]:
    """Instance-level spies counting eager RoundRobinModel request entries."""
    calls: list[str] = []
    original_request = rr.request
    original_stream = rr.request_stream

    async def spying_request(*args, **kwargs):
        calls.append("request")
        return await original_request(*args, **kwargs)

    def spying_stream(*args, **kwargs):
        calls.append("request_stream")
        return original_stream(*args, **kwargs)

    rr.request = spying_request  # type: ignore[method-assign]
    rr.request_stream = spying_stream  # type: ignore[method-assign]
    return calls


async def test_agent_runs_distribute_across_leaves_capability_owned():
    hits: dict[str, int] = {}
    rr = RoundRobinModel(_make_leaf("a", hits), _make_leaf("b", hits))
    eager_calls = _spy_eager_requests(rr)
    agent = Agent(model=rr, output_type=str, capabilities=[RoundRobinRequests(rr)])

    first = await agent.run("one")
    second = await agent.run("two")

    assert first.output == "reply from a"
    assert second.output == "reply from b"
    assert hits == {"a": 1, "b": 1}
    assert eager_calls == []  # ownership: the Model methods never ran


async def test_streamed_agent_run_routes_through_capability():
    hits: dict[str, int] = {}
    rr = RoundRobinModel(_make_leaf("a", hits), _make_leaf("b", hits))
    eager_calls = _spy_eager_requests(rr)
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
    rr = RoundRobinModel(_make_leaf("a", hits), _make_leaf("b", hits), rotate_every=2)
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
    rr = RoundRobinModel(_make_leaf("a", hits), _make_leaf("b", hits))
    explicit = _make_leaf("explicit", hits)
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
    rr = RoundRobinModel(_make_leaf("a", hits), _make_leaf("b", hits))
    eager_calls = _spy_eager_requests(rr)
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
    rr = RoundRobinModel(_make_leaf("a", hits), _make_leaf("b", hits))
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
    leaf_a = _ScriptedLeaf("a", [lambda: _suspended("a"), lambda: _complete("a")])
    leaf_b = _ScriptedLeaf("b", [lambda: _complete("b")])
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
    leaf_a = _ScriptedLeaf("a", [lambda: _suspended("a"), lambda: _complete("a")])
    leaf_b = _ScriptedLeaf("b", [lambda: _complete("b")])
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
    rr = RoundRobinModel(_make_leaf("a", hits), _make_leaf("b", hits))
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
    rr = RoundRobinModel(_make_leaf("a", hits), _make_leaf("b", hits))
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
    eager_leaf = _ScriptedLeaf("eager", [lambda: _complete("eager")])
    eager_rr = RoundRobinModel(eager_leaf)
    await eager_rr.request(
        [ModelRequest(parts=[UserPromptPart(content="direct")])],
        None,
        ModelRequestParameters(),
    )

    owned_leaf = _ScriptedLeaf("owned", [lambda: _complete("owned")])
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


async def test_coexists_with_plugin_message_transform():
    """Shares wrap_model_request with PluginMessageTransform: the transform's
    plugin callbacks still see (and mutate) messages while routing holds."""
    from code_puppy import callbacks
    from code_puppy.agents._model_message_transform import (
        build_model_message_transform,
    )

    hits: dict[str, int] = {}
    rr = RoundRobinModel(_make_leaf("a", hits), _make_leaf("b", hits))
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


# ---------------------------------------------------------------------------
# wiring
# ---------------------------------------------------------------------------


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
    rr = RoundRobinModel(_make_leaf("a", {}), _make_leaf("b", {}))
    built = _build_with_model(rr)
    found = _find_round_robin_capabilities(built)
    assert len(found) == 1
    assert found[0].model is rr


def test_builder_skips_capability_for_plain_model():
    built = _build_with_model(_make_leaf("plain", {}))
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
    rr = RoundRobinModel(_make_leaf("a", hits), _make_leaf("b", hits))
    eager_calls = _spy_eager_requests(rr)

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
