"""Contract tests for the CancellationTraceCapture capability.

Covers the promotion of the cancellation trace-context capture (the eager
``_observed_event_stream_handler`` closure in ``_runtime._do_run``) onto
pydantic-ai's ``wrap_run_event_stream`` seam:

- for_run resolution: no/disabled observation stays seam-less (no forced
  streaming); enabled observation resolves to the active capture.
- Capture cadence parity: one capture per event-stream-handler invocation,
  in the identical OTel span context the handler observes.
- Streaming-gate parity: gate off means zero captures even when a handler
  streams.
- ContextVar custody: None installs shadow, task-local installs die with
  the task.
- Wiring: builder registers the capability on the main path only;
  ``_do_run`` installs the per-turn observation; emit/clear custody stays
  eager.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from code_puppy.agents import _runtime
from code_puppy.agents._cancellation_trace import (
    CancellationTraceCapture,
    CancellationTraceObservation,
    _ActiveCancellationTraceCapture,
    current_cancellation_trace_observation,
    install_cancellation_trace_observation,
)
from code_puppy.callbacks import _callbacks, clear_callbacks, register_callback

AGENTS_DIR = Path(_runtime.__file__).parent
RUNTIME_SOURCE = (AGENTS_DIR / "_runtime.py").read_text()
BUILDER_SOURCE = (AGENTS_DIR / "_builder.py").read_text()
SUBAGENT_SOURCE = (AGENTS_DIR.parent / "tools" / "subagent_invocation.py").read_text()
CALLBACKS_SOURCE = (AGENTS_DIR.parent / "callbacks.py").read_text()


@pytest.fixture(autouse=True)
def isolated_observation():
    """Shadow any observation leaking in from the surrounding context."""
    install_cancellation_trace_observation(None)
    yield
    install_cancellation_trace_observation(None)


def make_stream_model() -> FunctionModel:
    """A model that ONLY supports streaming: proves a run streamed."""

    async def stream_func(messages: Any, info: AgentInfo):
        yield "hello "
        yield "world"

    return FunctionModel(stream_function=stream_func)


def make_request_model() -> FunctionModel:
    """A model that ONLY supports plain requests: proves a run did NOT
    stream (a streamed request raises UserError)."""

    def func(messages: Any, info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart("plain")])

    return FunctionModel(function=func)


async def consume(_ctx: Any, events: Any) -> None:
    async for _ in events:
        pass


# --- for_run resolution ------------------------------------------------------


async def test_for_run_without_observation_returns_self() -> None:
    capability = CancellationTraceCapture()
    resolved = await capability.for_run(None)
    assert resolved is capability
    # No seam override on the static class: the run must not be forced
    # into streaming mode.
    assert not resolved.has_wrap_run_event_stream


async def test_for_run_with_disabled_observation_returns_self() -> None:
    capability = CancellationTraceCapture()
    install_cancellation_trace_observation(
        CancellationTraceObservation(group_id="gid", enabled=False)
    )
    resolved = await capability.for_run(None)
    assert resolved is capability
    assert not resolved.has_wrap_run_event_stream


async def test_for_run_with_enabled_observation_resolves_active() -> None:
    capability = CancellationTraceCapture()
    observation = CancellationTraceObservation(group_id="gid", enabled=True)
    install_cancellation_trace_observation(observation)
    resolved = await capability.for_run(None)
    assert isinstance(resolved, _ActiveCancellationTraceCapture)
    assert resolved.observation is observation
    assert resolved.has_wrap_run_event_stream


# --- ContextVar custody ------------------------------------------------------


async def test_none_install_shadows_inherited_observation() -> None:
    """An explicit None install must hide an outer observation from nested
    tasks (the #840 stealing lesson): 'no capture here' must not fall
    through to an outer turn's group id."""
    outer = CancellationTraceObservation(group_id="outer", enabled=True)
    install_cancellation_trace_observation(outer)

    async def nested() -> Any:
        install_cancellation_trace_observation(None)
        return current_cancellation_trace_observation()

    assert await asyncio.create_task(nested()) is None
    # The outer context keeps its own observation.
    assert current_cancellation_trace_observation() is outer


async def test_observation_install_dies_with_its_task() -> None:
    """_do_run installs without reset; that is safe exactly because the
    turn's task context is discarded when the task completes."""

    async def turn() -> None:
        install_cancellation_trace_observation(
            CancellationTraceObservation(group_id="task-local", enabled=True)
        )

    await asyncio.create_task(turn())
    assert current_cancellation_trace_observation() is None


async def test_nested_task_uses_its_own_observation() -> None:
    """Nested run_with_mcp turns install their own observation in their own
    task; captures there must use the nested group id, and the outer turn
    keeps its own."""
    captured: list[str] = []
    outer_obs = CancellationTraceObservation(
        group_id="outer", enabled=True, capture=captured.append
    )
    install_cancellation_trace_observation(outer_obs)

    agent = Agent(make_stream_model(), capabilities=[CancellationTraceCapture()])

    async def nested_turn() -> None:
        install_cancellation_trace_observation(
            CancellationTraceObservation(
                group_id="inner", enabled=True, capture=captured.append
            )
        )
        await agent.run("nested", event_stream_handler=consume)

    await asyncio.create_task(nested_turn())
    await agent.run("outer", event_stream_handler=consume)

    assert set(captured[: captured.index("outer")]) == {"inner"}
    assert "inner" in captured and "outer" in captured


# --- run behavior ------------------------------------------------------------


async def test_inert_path_does_not_force_streaming() -> None:
    """Streaming-gate parity: with no observation the resolved capability
    has no wrap_run_event_stream, so a plain run stays non-streamed (the
    request-only model raises if pydantic-ai tries to stream)."""
    agent = Agent(make_request_model(), capabilities=[CancellationTraceCapture()])
    result = await agent.run("hi")
    assert result.output == "plain"


async def test_disabled_observation_never_captures_even_when_streaming() -> None:
    """Gate parity: streaming may happen (explicit handler) while the gate
    is off -- e.g. a caller-supplied handler outside run_with_mcp -- and
    the capture must stay silent, exactly like the eager wrapper that only
    existed when get_enable_streaming() was true."""
    captured: list[str] = []
    install_cancellation_trace_observation(
        CancellationTraceObservation(
            group_id="gid", enabled=False, capture=captured.append
        )
    )
    agent = Agent(make_stream_model(), capabilities=[CancellationTraceCapture()])
    result = await agent.run("hi", event_stream_handler=consume)
    assert result.output == "hello world"
    assert captured == []


async def test_capture_cadence_matches_handler_invocations() -> None:
    """The eager wrapper captured once per event_stream_handler invocation;
    the capability must capture once per wrapped node stream -- the same
    cadence, pinned by counting both in one run."""
    captured: list[str] = []
    handler_calls: list[str] = []

    async def counting_handler(_ctx: Any, events: Any) -> None:
        handler_calls.append("call")
        async for _ in events:
            pass

    install_cancellation_trace_observation(
        CancellationTraceObservation(
            group_id="gid", enabled=True, capture=captured.append
        )
    )
    agent = Agent(make_stream_model(), capabilities=[CancellationTraceCapture()])
    await agent.run("hi", event_stream_handler=counting_handler)

    assert len(captured) == len(handler_calls) > 0
    assert set(captured) == {"gid"}


async def test_capture_works_without_explicit_handler() -> None:
    """Seam property: an enabled observation auto-enables streaming even
    without an event_stream_handler. In production enabled is exactly the
    gate that also supplies the handler, so this only widens coverage for
    direct run() callers that install an enabled observation."""
    captured: list[str] = []
    install_cancellation_trace_observation(
        CancellationTraceObservation(
            group_id="gid", enabled=True, capture=captured.append
        )
    )
    agent = Agent(make_stream_model(), capabilities=[CancellationTraceCapture()])
    result = await agent.run("hi")
    assert result.output == "hello world"
    assert captured and set(captured) == {"gid"}


async def test_capture_sees_identical_span_context_as_handler() -> None:
    """The money test: under real OTel instrumentation, the capture runs in
    the same span context in which the event stream handler is invoked --
    so logfire.get_context() observes the identical value the eager
    wrapper captured."""
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.trace import TracerProvider
    from pydantic_ai.agent import InstrumentationSettings

    handler_spans: list[int] = []
    capture_spans: list[int] = []

    def span_capture(_gid: str) -> None:
        capture_spans.append(otel_trace.get_current_span().get_span_context().span_id)

    async def span_handler(_ctx: Any, events: Any) -> None:
        handler_spans.append(otel_trace.get_current_span().get_span_context().span_id)
        async for _ in events:
            pass

    install_cancellation_trace_observation(
        CancellationTraceObservation(group_id="gid", enabled=True, capture=span_capture)
    )
    agent = Agent(make_stream_model(), capabilities=[CancellationTraceCapture()])
    agent.instrument = InstrumentationSettings(tracer_provider=TracerProvider())
    await agent.run("hi", event_stream_handler=span_handler)

    assert handler_spans == capture_spans
    # Real recording spans, not the default invalid span.
    assert all(span_id != 0 for span_id in handler_spans)


async def test_events_pass_through_unchanged() -> None:
    """The active capture is a pure observer: the handler must see the
    exact same event sequence with and without it."""

    def collector(bucket: list[str]):
        async def handler(_ctx: Any, events: Any) -> None:
            async for event in events:
                bucket.append(repr(event))

        return handler

    baseline: list[str] = []
    agent_plain = Agent(make_stream_model())
    await agent_plain.run("hi", event_stream_handler=collector(baseline))

    observed: list[str] = []
    install_cancellation_trace_observation(
        CancellationTraceObservation(
            group_id="gid", enabled=True, capture=lambda _: None
        )
    )
    agent_cap = Agent(make_stream_model(), capabilities=[CancellationTraceCapture()])
    result = await agent_cap.run("hi", event_stream_handler=collector(observed))

    assert observed == baseline
    assert result.output == "hello world"


async def test_sequential_runs_keep_capturing() -> None:
    """Steer/hook follow-up parity: every run of the turn re-resolves the
    same observation, so captures keep firing run after run."""
    captured: list[str] = []
    install_cancellation_trace_observation(
        CancellationTraceObservation(
            group_id="gid", enabled=True, capture=captured.append
        )
    )
    agent = Agent(make_stream_model(), capabilities=[CancellationTraceCapture()])
    await agent.run("one", event_stream_handler=consume)
    first_run_captures = len(captured)
    await agent.run("two", event_stream_handler=consume)

    assert first_run_captures > 0
    assert len(captured) > first_run_captures


async def test_default_capture_late_binds_to_observability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """capture=None resolves through code_puppy.observability at call time,
    so test/plugin patches on the module keep intercepting."""
    seen: list[str] = []
    monkeypatch.setattr("code_puppy.observability.capture_agent_context", seen.append)
    install_cancellation_trace_observation(
        CancellationTraceObservation(group_id="gid", enabled=True)
    )
    agent = Agent(make_stream_model(), capabilities=[CancellationTraceCapture()])
    await agent.run("hi", event_stream_handler=consume)
    assert seen and set(seen) == {"gid"}


# --- wiring ------------------------------------------------------------------


class _FakeAgentConfig:
    """Minimal BaseAgent-shaped config for the real build path (mirrors
    tests/test_agent_span_naming.py)."""

    name = "cancellation-trace-test"
    display_name = "Cancellation Trace Test"

    def __init__(self) -> None:
        self._message_history: list[Any] = []
        self._compacted_message_hashes: set[Any] = set()
        self._puppy_rules = None

    def get_model_name(self) -> str:
        return "test-model"

    def get_full_system_prompt(self) -> str:
        return "You are a test agent."

    def get_available_tools(self) -> list[str]:
        return []

    def get_message_history(self) -> list[Any]:
        return self._message_history

    def set_message_history(self, history: list[Any]) -> None:
        self._message_history = history

    def __getattr__(self, item: str) -> Any:
        if item.startswith("__"):
            raise AttributeError(item)
        return lambda *a, **k: 0


def test_builder_wires_cancellation_trace_capture() -> None:
    from unittest.mock import patch

    from code_puppy.agents import _builder

    cfg = _FakeAgentConfig()
    with (
        patch.object(
            _builder,
            "load_model_with_fallback",
            lambda *a, **k: (TestModel(custom_output_text="woof"), "test-model"),
        ),
        patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
        patch.object(_builder, "load_mcp_servers", lambda **k: []),
        patch.object(_builder, "make_model_settings", lambda *a, **k: None),
        patch("code_puppy.tools.register_tools_for_agent", lambda *a, **k: None),
    ):
        built = _builder.build_pydantic_agent(cfg)

    leaves: list[Any] = []
    built.root_capability.apply(leaves.append)
    captures = [c for c in leaves if isinstance(c, CancellationTraceCapture)]
    assert len(captures) == 1


def test_subagent_site_excluded() -> None:
    """The eager capture never covered the sub-agent invoker's temp agents;
    the capability must not either."""
    assert "CancellationTraceCapture" not in SUBAGENT_SOURCE
    assert "install_cancellation_trace_observation" not in SUBAGENT_SOURCE


def test_eager_wrapper_retired_and_custody_stays_eager() -> None:
    """Source pins: the closure-based capture is gone, the runtime installs
    the observation instead, and the emit/clear custody outside the run
    boundary is untouched."""
    assert "async def _observed_event_stream_handler" not in RUNTIME_SOURCE
    assert "install_cancellation_trace_observation(" in RUNTIME_SOURCE
    # Turn-end custody and cancellation emission stay eager: no seam fires
    # on a cancelled run's exit path.
    assert "clear_agent_context(group_id)" in RUNTIME_SOURCE
    assert "emit_cancellation(group_id)" in CALLBACKS_SOURCE


def test_builder_registers_capability_in_main_list_only() -> None:
    assert "CancellationTraceCapture()" in BUILDER_SOURCE


# --- production-shaped runtime tests ----------------------------------------


class DummyResult:
    def __init__(self, data: str) -> None:
        self.data = data

    def all_messages(self) -> list[Any]:
        return []


class ScriptedPydanticAgent:
    def __init__(self, *outcomes: Any) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def run(self, prompt: Any, **kwargs: Any) -> Any:
        self.calls.append({"prompt": prompt, **kwargs})
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class DummyAgent:
    name = "dummy-agent"

    def __init__(self, pydantic_agent: Any) -> None:
        self._code_generation_agent = pydantic_agent
        self._message_history: list[Any] = []
        self._mcp_servers: list[Any] = []

    def get_model_name(self) -> str:
        return "dummy-model"

    def get_full_system_prompt(self) -> str:
        return "unused"


@pytest.fixture
def runtime_harness(monkeypatch: pytest.MonkeyPatch):
    """Isolate callbacks and interactive plumbing, as the runtime suites do."""
    snapshot = {phase: list(cbs) for phase, cbs in _callbacks.items()}
    clear_callbacks()
    monkeypatch.setattr(_runtime, "sigint_fallback_cancels", lambda: True)
    monkeypatch.setattr(_runtime, "should_render_fallback", lambda *_, **__: False)
    yield monkeypatch
    clear_callbacks()
    for phase, cbs in snapshot.items():
        _callbacks[phase].extend(cbs)


async def test_runtime_installs_observation_with_gate_state(
    runtime_harness: pytest.MonkeyPatch,
) -> None:
    """_do_run must install one observation per turn whose enabled flag is
    the streaming gate and whose group_id is the turn's group id (the
    session_id agent_run_start hooks receive)."""
    installed: list[CancellationTraceObservation | None] = []
    session_ids: list[str] = []

    runtime_harness.setattr(
        _runtime, "install_cancellation_trace_observation", installed.append
    )

    def on_start(agent_name: str, model_name: str, session_id: str = None) -> None:
        session_ids.append(session_id)

    register_callback("agent_run_start", on_start)

    for gate in (False, True):
        runtime_harness.setattr(_runtime, "get_enable_streaming", lambda g=gate: g)
        agent = DummyAgent(ScriptedPydanticAgent(DummyResult("ok")))
        await _runtime.run_with_mcp(agent, "hello")

    assert [obs.enabled for obs in installed] == [False, True]
    assert [obs.group_id for obs in installed] == session_ids
    # Default capture path (late-bound observability), fresh id per turn.
    assert all(obs.capture is None for obs in installed)
    assert len({obs.group_id for obs in installed}) == 2


async def test_run_with_mcp_end_to_end_capture(
    runtime_harness: pytest.MonkeyPatch,
) -> None:
    """Full production shape: a real pydantic-ai Agent carrying the
    capability, driven through run_with_mcp with the gate on, captures the
    turn's group id through the default observability path."""
    captured: list[str] = []
    session_ids: list[str] = []

    runtime_harness.setattr(_runtime, "get_enable_streaming", lambda: True)
    runtime_harness.setattr(_runtime, "event_stream_handler", consume)
    runtime_harness.setattr(
        "code_puppy.observability.capture_agent_context", captured.append
    )

    def on_start(agent_name: str, model_name: str, session_id: str = None) -> None:
        session_ids.append(session_id)

    register_callback("agent_run_start", on_start)

    pydantic_agent = Agent(
        make_stream_model(), capabilities=[CancellationTraceCapture()]
    )
    agent = DummyAgent(pydantic_agent)
    result = await _runtime.run_with_mcp(agent, "hello")

    assert result.output == "hello world"
    assert captured and set(captured) == set(session_ids)


async def test_run_with_mcp_gate_off_no_capture(
    runtime_harness: pytest.MonkeyPatch,
) -> None:
    """Gate off through the real runtime: the run stays non-streamed (the
    request-only model proves it) and nothing is captured."""
    captured: list[str] = []

    runtime_harness.setattr(_runtime, "get_enable_streaming", lambda: False)
    runtime_harness.setattr(
        "code_puppy.observability.capture_agent_context", captured.append
    )

    pydantic_agent = Agent(
        make_request_model(), capabilities=[CancellationTraceCapture()]
    )
    agent = DummyAgent(pydantic_agent)
    result = await _runtime.run_with_mcp(agent, "hello")

    assert result.output == "plain"
    assert captured == []
