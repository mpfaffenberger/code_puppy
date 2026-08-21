"""Contract tests for the ``StreamRendering`` capability.

The streaming render pipeline used to reach pydantic-ai as a per-run
``event_stream_handler=`` kwarg; it now rides the ``wrap_run_event_stream``
capability seam, resolved per run against a context-local
``StreamObservation``. These tests pin the contract:

* no observation (or a disabled one) resolves inert, so the run stays
  non-streamed — the streaming gate's old "no handler" behaviour;
* an enabled observation streams the run, drives the handler with the run's
  events, records ``streamed_text``, and captures the observability group;
* state accumulates across sequential runs under one observation (the
  steer/hook follow-up loop shares one detector);
* the observation propagates into ``asyncio.create_task`` (the sub-agent
  invocation pattern);
* both construction sites attach the capability, and the main build no
  longer hands the raw handler to the ``wrap_pydantic_agent`` hook.
"""

import asyncio
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import patch

from pydantic_ai import Agent, PartDeltaEvent, PartStartEvent, RunContext
from pydantic_ai.capabilities import ProcessEventStream
from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ThinkingPart,
    ThinkingPartDelta,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from code_puppy.agents._stream_rendering import (
    StreamObservation,
    StreamRendering,
    current_stream_observation,
    stream_observation,
)


async def _consume(_ctx, events):
    async for _event in events:
        pass


def _stream_only_model(text: str = "woof woof") -> FunctionModel:
    """A model that can ONLY stream — a non-streamed request would raise."""

    async def stream_fn(_messages, _info: AgentInfo):
        yield text

    return FunctionModel(stream_function=stream_fn)


def _chunked_stream_model(*chunks: str) -> FunctionModel:
    """A stream-only model that emits each chunk as its own delta."""

    async def stream_fn(_messages, _info: AgentInfo):
        for chunk in chunks:
            yield chunk

    return FunctionModel(stream_function=stream_fn)


def _request_only_model(text: str = "plain") -> FunctionModel:
    """A model that can ONLY answer non-streamed requests."""

    def fn(_messages, _info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(content=text)])

    return FunctionModel(fn)


# ---------------------------------------------------------------------------
# StreamObservation context plumbing
# ---------------------------------------------------------------------------


def test_stream_observation_installs_and_restores():
    assert current_stream_observation() is None
    with stream_observation(_consume) as outer:
        assert current_stream_observation() is outer
        with stream_observation(_consume) as inner:
            assert current_stream_observation() is inner
        assert current_stream_observation() is outer
    assert current_stream_observation() is None


def test_stream_observation_restores_on_error():
    try:
        with stream_observation(_consume):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert current_stream_observation() is None


def test_observation_outlives_its_context_block():
    with stream_observation(_consume) as observation:
        pass
    # streamed_text stays readable after the registration is reverted — the
    # runtime reads it for the fallback-render decision after the run loop.
    assert observation.streamed_text is False


# ---------------------------------------------------------------------------
# for_run resolution
# ---------------------------------------------------------------------------


async def test_for_run_resolves_inert_without_observation():
    resolved = await StreamRendering().for_run(None)
    assert not resolved.has_wrap_run_event_stream


async def test_for_run_resolves_inert_when_disabled():
    with stream_observation(_consume, enabled=False):
        resolved = await StreamRendering().for_run(None)
    assert not resolved.has_wrap_run_event_stream


async def test_for_run_delivers_the_observation_detector():
    with stream_observation(_consume) as observation:
        resolved = await StreamRendering().for_run(None)
    assert isinstance(resolved, ProcessEventStream)
    assert resolved.handler is observation.detector
    assert resolved.has_wrap_run_event_stream


def test_stream_rendering_is_not_spec_constructible():
    assert StreamRendering.get_serialization_name() is None


def test_stream_rendering_alone_does_not_force_streaming():
    # The static capability must not trip pydantic-ai's "streaming needed"
    # check — only the per-run resolution may.
    assert not StreamRendering().has_wrap_run_event_stream


# ---------------------------------------------------------------------------
# Run behaviour through a real pydantic-ai agent
# ---------------------------------------------------------------------------


async def test_run_stays_non_streamed_without_observation():
    # A request-only model would raise UserError if the capability forced
    # streaming mode; a clean run proves the inert path.
    agent = Agent(
        model=_request_only_model(),
        output_type=str,
        capabilities=[StreamRendering()],
    )
    result = await agent.run("hi")
    assert result.output == "plain"


async def test_run_stays_non_streamed_when_observation_disabled():
    agent = Agent(
        model=_request_only_model(),
        output_type=str,
        capabilities=[StreamRendering()],
    )
    with stream_observation(_consume, enabled=False) as observation:
        result = await agent.run("hi")
    assert result.output == "plain"
    assert observation.streamed_text is False


async def test_enabled_observation_streams_and_drives_handler():
    seen: list = []
    contexts: list = []

    async def handler(ctx, events):
        contexts.append(ctx)
        async for event in events:
            seen.append(event)

    # A stream-only model proves the run actually streamed: a non-streamed
    # request against it would raise.
    agent = Agent(
        model=_stream_only_model("woof woof"),
        output_type=str,
        capabilities=[StreamRendering()],
    )
    with stream_observation(handler) as observation:
        result = await agent.run("hi")

    assert result.output == "woof woof"
    assert seen, "handler should observe the run's stream events"
    assert all(isinstance(ctx, RunContext) for ctx in contexts)
    assert observation.streamed_text is True


async def test_group_id_is_captured_into_observability_context(monkeypatch):
    captured: list = []
    monkeypatch.setattr(
        "code_puppy.observability.capture_agent_context", captured.append
    )
    agent = Agent(
        model=_stream_only_model(),
        output_type=str,
        capabilities=[StreamRendering()],
    )
    with stream_observation(_consume, group_id="grp-42"):
        await agent.run("hi")
    assert captured
    assert set(captured) == {"grp-42"}


async def test_no_group_id_skips_observability_capture(monkeypatch):
    captured: list = []
    monkeypatch.setattr(
        "code_puppy.observability.capture_agent_context", captured.append
    )
    agent = Agent(
        model=_stream_only_model(),
        output_type=str,
        capabilities=[StreamRendering()],
    )
    with stream_observation(_consume):
        await agent.run("hi")
    assert captured == []


async def test_streamed_text_accumulates_across_sequential_runs():
    agent = Agent(
        model=_stream_only_model(),
        output_type=str,
        capabilities=[StreamRendering()],
    )
    with stream_observation(_consume) as observation:
        await agent.run("one")
        assert observation.streamed_text is True
        await agent.run("two")
        assert observation.streamed_text is True


async def test_observation_propagates_into_created_task():
    # subagent_invocation launches the run via asyncio.create_task; the task's
    # context snapshot must carry the observation even though the with-block
    # exits before the await completes.
    agent = Agent(
        model=_stream_only_model(),
        output_type=str,
        capabilities=[StreamRendering()],
    )
    with stream_observation(_consume) as observation:
        task = asyncio.create_task(agent.run("hi"))
    result = await task
    assert result.output == "woof woof"
    assert observation.streamed_text is True


async def test_handler_sees_deltas_in_stream_order():
    # ProcessEventStream must not reorder the observed view — the renderer
    # depends on deltas arriving exactly as the model produced them.
    seen: list = []

    async def handler(_ctx, events):
        async for event in events:
            if isinstance(event, PartDeltaEvent):
                seen.append(event.delta.content_delta)
            elif isinstance(event, PartStartEvent):
                seen.append(event.part.content)

    agent = Agent(
        model=_chunked_stream_model("al", "pha ", "bra", "vo"),
        output_type=str,
        capabilities=[StreamRendering()],
    )
    with stream_observation(handler):
        result = await agent.run("hi")

    assert result.output == "alpha bravo"
    assert "".join(seen) == "alpha bravo"


async def test_early_returning_handler_does_not_stall_the_run():
    # An observer that bails after one event must not block the node stream
    # (pydantic-ai keeps forwarding; the old direct-consumption path drained
    # leftovers the same way).
    received: list = []

    async def one_and_done(_ctx, events):
        async for event in events:
            received.append(event)
            return

    agent = Agent(
        model=_chunked_stream_model("never", " gonna", " give"),
        output_type=str,
        capabilities=[StreamRendering()],
    )
    with stream_observation(one_and_done):
        result = await agent.run("hi")

    assert result.output == "never gonna give"
    assert len(received) == 1


async def test_raising_handler_propagates_to_the_run():
    # Parity with the per-run kwarg: a handler crash must surface, not be
    # swallowed into a silent render-less run.
    class HandlerBoom(Exception):
        pass

    async def explode(_ctx, events):
        async for _event in events:
            raise HandlerBoom("boom")

    agent = Agent(
        model=_stream_only_model(),
        output_type=str,
        capabilities=[StreamRendering()],
    )
    with stream_observation(explode):
        try:
            await agent.run("hi")
        except* HandlerBoom:
            propagated = True
        else:
            propagated = False
    assert propagated


async def test_nested_subagent_observation_shadows_and_restores():
    # The sub-agent topology: an outer (main-run) observation, an inner one
    # installed for the delegate, the delegate run launched via create_task,
    # and the outer observation restored — with each handler seeing only its
    # own run's events.
    outer_seen: list = []
    inner_seen: list = []

    async def outer_handler(_ctx, events):
        async for event in events:
            outer_seen.append(event)

    async def inner_handler(_ctx, events):
        async for event in events:
            inner_seen.append(event)

    outer_agent = Agent(
        model=_stream_only_model("outer text"),
        output_type=str,
        capabilities=[StreamRendering()],
    )
    inner_agent = Agent(
        model=_stream_only_model("inner text"),
        output_type=str,
        capabilities=[StreamRendering()],
    )

    with stream_observation(outer_handler) as outer_observation:
        with stream_observation(inner_handler) as inner_observation:
            task = asyncio.create_task(inner_agent.run("delegate"))
        assert current_stream_observation() is outer_observation
        inner_result = await task
        outer_result = await outer_agent.run("main")

    assert inner_result.output == "inner text"
    assert outer_result.output == "outer text"
    assert inner_observation.streamed_text is True
    assert outer_observation.streamed_text is True
    assert inner_seen and outer_seen
    assert not (set(map(id, inner_seen)) & set(map(id, outer_seen)))


async def test_detector_ignores_non_text_events():
    observation = StreamObservation(handler=_consume)

    async def thinking_only():
        yield PartStartEvent(index=0, part=ThinkingPart(content="pondering"))
        yield PartDeltaEvent(index=0, delta=ThinkingPartDelta(content_delta="..."))

    await observation.detector(None, thinking_only())
    assert observation.streamed_text is False


# ---------------------------------------------------------------------------
# Construction sites
# ---------------------------------------------------------------------------


class _AgentConfig:
    """Duck-typed BaseAgent stand-in (pattern shared with builder tests)."""

    def __init__(self):
        self._message_history = []
        self._compacted_message_hashes = set()
        self._puppy_rules = None
        self.name = "code-puppy"

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


def _load_test_model(*_args, **_kwargs):
    return TestModel(custom_output_text="woof"), "test-model"


def _builder_patches(_builder):
    return (
        patch.object(_builder, "load_model_with_fallback", _load_test_model),
        patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
        patch.object(_builder, "load_mcp_servers", lambda **_kwargs: []),
        patch.object(_builder, "make_model_settings", lambda *_args, **_kwargs: None),
        patch(
            "code_puppy.tools.register_tools_for_agent", lambda *_args, **_kwargs: None
        ),
    )


async def test_main_agent_build_attaches_stream_rendering():
    from code_puppy.agents import _builder

    config = _AgentConfig()
    seen: list = []

    async def handler(_ctx, events):
        async for event in events:
            seen.append(event)

    with ExitStack() as stack:
        for patcher in _builder_patches(_builder):
            stack.enter_context(patcher)
        built = _builder.build_pydantic_agent(config)

        # Without an observation the built agent must not stream...
        await built.run("start")
        assert seen == []

        # ...and with one, the capability delivers the handler.
        with stream_observation(handler) as observation:
            await built.run("again")

    assert seen
    assert observation.streamed_text is True


async def test_main_build_wrap_hook_no_longer_receives_the_handler():
    from code_puppy.agents import _builder

    captured: dict = {}

    def capture_wrap(_agent, pydantic_agent, **kwargs):
        captured.update(kwargs)
        return pydantic_agent

    with ExitStack() as stack:
        for patcher in _builder_patches(_builder):
            stack.enter_context(patcher)
        stack.enter_context(
            patch.object(_builder, "on_wrap_pydantic_agent", capture_wrap)
        )
        _builder.build_pydantic_agent(_AgentConfig())

    assert captured["kind"] == "main"
    assert captured["event_stream_handler"] is None


def _leaves(capability):
    children = getattr(capability, "capabilities", None)
    if children is None:
        yield capability
        return
    for child in children:
        yield from _leaves(child)


async def test_subagent_build_attaches_stream_rendering():
    from code_puppy.tools import subagent_invocation as si

    cfg = _AgentConfig()
    cfg.name = "web-retriever"
    captured: dict = {}

    def capture_wrap(_agent_config, pydantic_agent, **_kwargs):
        captured["agent"] = pydantic_agent
        return pydantic_agent

    with (
        patch("code_puppy.agents.agent_manager.load_agent", return_value=cfg),
        patch(
            "code_puppy.agents._builder.load_model_with_fallback",
            _load_test_model,
        ),
        patch("code_puppy.model_factory.make_model_settings", lambda *a, **k: None),
        patch("code_puppy.config.get_value", return_value="true"),  # no MCP
        patch.object(si, "on_wrap_pydantic_agent", capture_wrap),
    ):
        out = await si._invoke_agent_impl(
            context=SimpleNamespace(),
            agent_name="web-retriever",
            prompt="fetch me a stick",
        )

    assert out.error is None
    leaves = list(_leaves(captured["agent"]._root_capability))
    assert any(isinstance(leaf, StreamRendering) for leaf in leaves)
