"""Contract tests for the ``RunTelemetry`` capability (``after_run`` seam).

Covers the three layers of the conversion:

* the pure extraction helpers (byte-parity with the old eager code in
  ``_runtime.run_with_mcp``, including the ``int(value) or None`` zero-token
  quirk and the alias fallback chains);
* the capability seam itself (capture on ``after_run``, identity-gated
  read-and-clear ``consume``, behaviour under ``CombinedCapability``);
* the wiring (builder installs + stashes the instance; ``run_with_mcp``
  consumes the capture when ours, falls back for guests; sub-agent scope pin).
"""

from __future__ import annotations

import inspect
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.capabilities import AbstractCapability, CombinedCapability
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from code_puppy.agents import _builder, _runtime
from code_puppy.agents._run_telemetry import (
    RunTelemetry,
    empty_usage_metadata,
    extract_response_text,
    extract_usage_metadata,
)
from code_puppy.callbacks import _callbacks, clear_callbacks, register_callback


def _model_func(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart("hello world")])


# ---------------------------------------------------------------------------
# Extraction helpers: byte-parity with the retired eager code
# ---------------------------------------------------------------------------


class _Result:
    """Configurable stand-in for an ``AgentRunResult``."""

    def __init__(self, **attrs: Any) -> None:
        for key, value in attrs.items():
            setattr(self, key, value)


class _Usage:
    def __init__(self, **attrs: Any) -> None:
        for key, value in attrs.items():
            setattr(self, key, value)


def test_extract_response_text_contract():
    assert extract_response_text(None) == ""
    assert extract_response_text(_Result(data="from-data")) == "from-data"
    assert extract_response_text(_Result(data="")) == ""
    assert extract_response_text(_Result(output="from-output")) == "from-output"
    assert extract_response_text(_Result(output=None)) == ""
    # ``data`` wins over ``output`` (same branch order as the eager helper).
    assert extract_response_text(_Result(data="d", output="o")) == "d"
    assert extract_response_text("plain") == "plain"


def test_extract_usage_metadata_reads_primary_names():
    result = _Result(
        usage=_Usage(
            input_tokens=11,
            output_tokens=22,
            total_tokens=33,
            cache_read_tokens=44,
            cache_write_tokens=55,
            thinking_tokens=66,
        )
    )
    assert extract_usage_metadata(result) == {
        "usage_input_tokens": 11,
        "usage_output_tokens": 22,
        "usage_total_tokens": 33,
        "usage_cached_read_tokens": 44,
        "usage_cached_write_tokens": 55,
        "usage_thought_tokens": 66,
    }


def test_extract_usage_metadata_alias_fallbacks():
    result = _Result(
        usage=_Usage(
            request_tokens=7,
            completion_tokens=8,
            cached_read_tokens=9,
            cached_write_tokens=10,
            reasoning_tokens=12,
        )
    )
    metadata = extract_usage_metadata(result)
    assert metadata["usage_input_tokens"] == 7
    assert metadata["usage_output_tokens"] == 8
    assert metadata["usage_total_tokens"] is None
    assert metadata["usage_cached_read_tokens"] == 9
    assert metadata["usage_cached_write_tokens"] == 10
    assert metadata["usage_thought_tokens"] == 12


def test_extract_usage_metadata_zero_short_circuits_alias_chain():
    """Pin the eager quirk: ``int(value) or None`` maps 0 -> None AND stops
    the alias chain — a present-but-zero primary name shadows later aliases."""
    result = _Result(usage=_Usage(input_tokens=0, request_tokens=5))
    assert extract_usage_metadata(result)["usage_input_tokens"] is None


def test_extract_usage_metadata_missing_usage_is_all_none():
    assert extract_usage_metadata(_Result(data="x")) == empty_usage_metadata()
    assert extract_usage_metadata(None) == empty_usage_metadata()


def test_empty_usage_metadata_returns_fresh_dict_each_call():
    first = empty_usage_metadata()
    second = empty_usage_metadata()
    assert first == second
    assert first is not second


# ---------------------------------------------------------------------------
# The capability seam: capture + identity-gated consume
# ---------------------------------------------------------------------------


async def test_after_run_captures_the_identical_result_object():
    telemetry = RunTelemetry()
    agent = Agent(FunctionModel(_model_func), capabilities=[telemetry])

    result = await agent.run("go")

    consumed = telemetry.consume(result)
    assert consumed is not None
    text, usage = consumed
    assert text == "hello world"
    assert (
        usage["usage_input_tokens"]
        == extract_usage_metadata(result)["usage_input_tokens"]
    )
    assert usage == extract_usage_metadata(result)


async def test_capability_and_eager_fallback_produce_identical_payloads():
    telemetry = RunTelemetry()
    agent = Agent(FunctionModel(_model_func), capabilities=[telemetry])

    result = await agent.run("go")

    text, usage = telemetry.consume(result)
    assert text == extract_response_text(result)
    assert usage == extract_usage_metadata(result)


async def test_after_run_fires_under_combined_capability():
    telemetry = RunTelemetry()
    combined = CombinedCapability([AbstractCapability(), telemetry])
    agent = Agent(FunctionModel(_model_func), capabilities=[combined])

    result = await agent.run("go")

    assert telemetry.consume(result) is not None


async def test_consume_is_read_and_clear():
    telemetry = RunTelemetry()
    result = _Result(output="once")
    await telemetry.after_run(None, result=result)

    assert telemetry.consume(result) == ("once", empty_usage_metadata())
    assert telemetry.consume(result) is None


async def test_consume_requires_identity_match_and_clears_on_mismatch():
    telemetry = RunTelemetry()
    captured = _Result(output="captured")
    other = _Result(output="captured")  # equal-looking, different object
    await telemetry.after_run(None, result=captured)

    assert telemetry.consume(other) is None
    # The stale capture must be gone: even the right object now misses.
    assert telemetry.consume(captured) is None


async def test_consume_none_result_never_matches():
    telemetry = RunTelemetry()
    await telemetry.after_run(None, result=_Result(output="x"))
    assert telemetry.consume(None) is None


async def test_multi_run_last_capture_wins():
    telemetry = RunTelemetry()
    agent = Agent(FunctionModel(_model_func), capabilities=[telemetry])

    first = await agent.run("one")
    second = await agent.run("two")

    # Only the latest run's result matches — exactly the object
    # ``run_with_mcp`` ends up returning after steer/hook follow-ups.
    assert telemetry.consume(first) is None
    # consume cleared the slot above; recapture to prove second matched.
    await telemetry.after_run(None, result=second)
    assert telemetry.consume(second) is not None


async def test_after_run_returns_result_unchanged():
    telemetry = RunTelemetry()
    result = _Result(output="pass-through")
    assert await telemetry.after_run(None, result=result) is result


def test_spec_constructible_with_inherited_defaults():
    instance = RunTelemetry.from_spec()
    assert isinstance(instance, RunTelemetry)
    assert instance.consume(_Result(output="x")) is None


# ---------------------------------------------------------------------------
# Builder wiring
# ---------------------------------------------------------------------------


class _AgentConfig:
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


def _load_test_model(*_args, **_kwargs):
    return TestModel(custom_output_text="done"), "test-model"


def _builder_patches():
    return (
        patch.object(_builder, "load_model_with_fallback", _load_test_model),
        patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
        patch.object(_builder, "load_mcp_servers", lambda **_kwargs: []),
        patch.object(_builder, "make_model_settings", lambda *_args, **_kwargs: None),
        patch(
            "code_puppy.tools.register_tools_for_agent", lambda *_args, **_kwargs: None
        ),
    )


async def test_builder_stashes_and_installs_the_capability():
    config = _AgentConfig()
    with ExitStack() as stack:
        for patcher in _builder_patches():
            stack.enter_context(patcher)
        agent = _builder.build_pydantic_agent(config)
        result = await agent.run("start")

    telemetry = config._run_telemetry
    assert isinstance(telemetry, RunTelemetry)
    # The stashed instance IS the one riding the built agent: it captured the
    # exact result object the run returned.
    consumed = telemetry.consume(result)
    assert consumed is not None
    assert consumed[0] == "done"


def test_subagent_invocation_stays_out_of_scope():
    """Scope pin (mirrors #842): the sub-agent path keeps its own usage
    capture (``include_usage_metrics``); RunTelemetry is main-path only."""
    source = Path(inspect.getfile(_builder)).parent.parent
    subagent_source = (source / "tools" / "subagent_invocation.py").read_text(
        encoding="utf-8"
    )
    builder_source = (source / "agents" / "_builder.py").read_text(encoding="utf-8")
    assert "RunTelemetry" not in subagent_source
    assert "RunTelemetry" in builder_source  # positive control


# ---------------------------------------------------------------------------
# run_with_mcp custody: explicit-when-ours, fallback-for-guests
# ---------------------------------------------------------------------------


class _DummyResult:
    def __init__(self, data: str) -> None:
        self.data = data

    def all_messages(self) -> list[Any]:
        return []


class _ScriptedPydanticAgent:
    """Stand-in that can optionally deliver results through ``after_run``."""

    def __init__(self, *outcomes: Any, telemetry: RunTelemetry | None = None) -> None:
        self._outcomes = list(outcomes)
        self._telemetry = telemetry

    async def run(self, prompt: Any, **kwargs: Any) -> Any:
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if self._telemetry is not None:
            # Simulate pydantic-ai dispatching the after_run seam.
            await self._telemetry.after_run(None, result=outcome)
        return outcome


class _DummyAgent:
    name = "dummy-agent"

    def __init__(self, pydantic_agent: Any) -> None:
        self._code_generation_agent = pydantic_agent
        self._message_history = ["already-started"]
        self._mcp_servers: list[Any] = []

    def get_model_name(self) -> str:
        return "dummy-model"

    def get_full_system_prompt(self) -> str:
        return "unused because message history is non-empty"


@pytest.fixture(autouse=True)
def isolated_runtime_callbacks(monkeypatch: pytest.MonkeyPatch):
    snapshot = {phase: list(callbacks) for phase, callbacks in _callbacks.items()}
    clear_callbacks()
    monkeypatch.setattr(_runtime, "sigint_fallback_cancels", lambda: True)
    monkeypatch.setattr(_runtime, "get_enable_streaming", lambda: False)
    monkeypatch.setattr(_runtime, "should_render_fallback", lambda *_, **__: False)

    yield

    clear_callbacks()
    for phase, callbacks in snapshot.items():
        _callbacks[phase].extend(callbacks)


@pytest.fixture
def run_end_events() -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []

    def spy(
        agent_name: str,
        model_name: str,
        session_id: Any = None,
        success: bool = True,
        error: Any = None,
        response_text: Any = None,
        metadata: Any = None,
    ) -> None:
        seen.append(
            {
                "agent_name": agent_name,
                "model_name": model_name,
                "session_id": session_id,
                "success": success,
                "error": error,
                "response_text": response_text,
                "metadata": metadata,
            }
        )

    register_callback("agent_run_end", spy)
    return seen


async def test_run_with_mcp_uses_capability_capture_when_ours(
    monkeypatch: pytest.MonkeyPatch, run_end_events: list[dict[str, Any]]
) -> None:
    telemetry = RunTelemetry()
    pydantic_agent = _ScriptedPydanticAgent(_DummyResult("ok"), telemetry=telemetry)
    agent = _DummyAgent(pydantic_agent)
    agent._run_telemetry = telemetry

    # Sentinel the module-level fallback: if the tail ignored the capability,
    # the sentinel would leak into the reported response text.
    monkeypatch.setattr(_runtime, "extract_response_text", lambda _r: "FALLBACK")

    result = await _runtime.run_with_mcp(agent, "hello")

    assert result.data == "ok"
    assert len(run_end_events) == 1
    assert run_end_events[0]["response_text"] == "ok"
    assert run_end_events[0]["success"] is True
    # Capture was consumed at the tail — nothing left for a later turn.
    assert telemetry.consume(result) is None


async def test_run_with_mcp_falls_back_when_capability_bypassed(
    monkeypatch: pytest.MonkeyPatch, run_end_events: list[dict[str, Any]]
) -> None:
    telemetry = RunTelemetry()
    # Guest wrapper simulation: run() never dispatches after_run.
    pydantic_agent = _ScriptedPydanticAgent(_DummyResult("ok"), telemetry=None)
    agent = _DummyAgent(pydantic_agent)
    agent._run_telemetry = telemetry

    monkeypatch.setattr(_runtime, "extract_response_text", lambda _r: "FALLBACK")

    await _runtime.run_with_mcp(agent, "hello")

    assert len(run_end_events) == 1
    assert run_end_events[0]["response_text"] == "FALLBACK"


async def test_run_with_mcp_ignores_stale_capture_from_an_earlier_turn(
    run_end_events: list[dict[str, Any]],
) -> None:
    telemetry = RunTelemetry()
    # A previous turn captured, then its task failed before consuming.
    await telemetry.after_run(None, result=_DummyResult("stale"))

    pydantic_agent = _ScriptedPydanticAgent(_DummyResult("fresh"), telemetry=None)
    agent = _DummyAgent(pydantic_agent)
    agent._run_telemetry = telemetry

    await _runtime.run_with_mcp(agent, "hello")

    assert len(run_end_events) == 1
    # Identity gate rejected the stale capture; eager extraction reported the
    # real result — never the earlier turn's text.
    assert run_end_events[0]["response_text"] == "fresh"


async def test_run_with_mcp_without_capability_attribute_uses_fallback(
    run_end_events: list[dict[str, Any]],
) -> None:
    pydantic_agent = _ScriptedPydanticAgent(_DummyResult("plain"))
    agent = _DummyAgent(pydantic_agent)  # no _run_telemetry attribute at all

    await _runtime.run_with_mcp(agent, "hello")

    assert len(run_end_events) == 1
    assert run_end_events[0]["response_text"] == "plain"
    assert run_end_events[0]["metadata"]["usage_input_tokens"] is None
