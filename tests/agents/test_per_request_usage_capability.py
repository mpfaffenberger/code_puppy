"""Contract tests for the ``PerRequestUsageCapture`` capability.

The capability observes each ``ModelResponse`` on pydantic-ai's
``after_model_request`` seam and hands the invocation layer an owned,
consistency-checked capture at the run boundary. These tests pin:

* seam capture parity with an eager ``new_messages()`` walk (identity,
  order, streamed and non-streamed requests);
* the read-and-clear + identity + consistency gates on ``consume()``,
  including the mid-run history-rewrite case where the gates are the only
  thing standing between us and a phantom usage entry;
* per-run isolation across sequential runs on one agent (the
  streaming-retry re-entry shape);
* byte-identical extraction between the capability path and the eager
  fallback path;
* the conditional construction helper used by the call site.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import (
    AgentInfo,
    DeltaToolCall,
    FunctionModel,
)

from code_puppy.agents._subagent_usage import (
    PerRequestUsageCapture,
    build_per_request_usage_capture,
)
from code_puppy.tools.subagent_usage_metrics import (
    extract_final_context_tokens,
    extract_per_request_usage,
)


def _tool_then_text_model() -> FunctionModel:
    """One tool-call response, then a final text response.

    Termination is driven by the *visible* history (a tool-return part), so
    the model behaves correctly for plain runs. Tests that rewrite history
    mid-run use ``_counted_model`` instead.
    """

    def req_fn(messages, info: AgentInfo) -> ModelResponse:
        has_tool_return = any(
            getattr(part, "part_kind", "") == "tool-return"
            for message in messages
            for part in getattr(message, "parts", [])
        )
        if not has_tool_return:
            return ModelResponse(parts=[ToolCallPart(tool_name="greet", args="{}")])
        return ModelResponse(parts=[TextPart("done")])

    async def stream_fn(messages, info: AgentInfo):
        has_tool_return = any(
            getattr(part, "part_kind", "") == "tool-return"
            for message in messages
            for part in getattr(message, "parts", [])
        )
        if not has_tool_return:
            yield {1: DeltaToolCall(name="greet", json_args="{}")}
        else:
            yield "do"
            yield "ne"

    return FunctionModel(req_fn, stream_function=stream_fn)


def _counted_model(counter: dict) -> FunctionModel:
    """Tool call on the first request, text afterwards, regardless of history."""

    def req_fn(messages, info: AgentInfo) -> ModelResponse:
        counter["calls"] = counter.get("calls", 0) + 1
        if counter["calls"] == 1:
            return ModelResponse(parts=[ToolCallPart(tool_name="greet", args="{}")])
        return ModelResponse(parts=[TextPart("done")])

    return FunctionModel(req_fn)


def _agent_with(model: FunctionModel, *capabilities) -> Agent:
    agent = Agent(model, capabilities=list(capabilities))

    @agent.tool_plain
    def greet() -> str:
        return "hi"

    return agent


def _recorded_responses(result) -> list[ModelResponse]:
    return [m for m in result.new_messages() if isinstance(m, ModelResponse)]


class TestSeamCapture:
    def test_captures_every_response_object_in_order(self):
        capture = PerRequestUsageCapture()
        agent = _agent_with(_tool_then_text_model(), capture)

        result = asyncio.run(agent.run("go"))

        owned = capture.consume(result)
        assert owned is not None
        recorded = _recorded_responses(result)
        assert len(owned) == len(recorded) == 2
        assert all(a is b for a, b in zip(owned, recorded))

    def test_streamed_requests_are_captured_identically(self):
        capture = PerRequestUsageCapture()
        agent = _agent_with(_tool_then_text_model(), capture)

        async def handler(ctx, events):
            async for _ in events:
                pass

        result = asyncio.run(agent.run("go", event_stream_handler=handler))

        owned = capture.consume(result)
        assert owned is not None
        recorded = _recorded_responses(result)
        assert len(owned) == len(recorded) == 2
        assert all(a is b for a, b in zip(owned, recorded))

    def test_capture_survives_neighbouring_capabilities(self):
        # The production list runs ProcessHistory ahead of the capture; a
        # pass-through processor must not disturb ownership.
        capture = PerRequestUsageCapture()
        agent = _agent_with(
            _tool_then_text_model(), ProcessHistory(lambda messages: messages), capture
        )

        result = asyncio.run(agent.run("go"))

        assert capture.consume(result) is not None


class TestConsumeGates:
    def test_consume_is_read_and_clear(self):
        capture = PerRequestUsageCapture()
        agent = _agent_with(_tool_then_text_model(), capture)

        result = asyncio.run(agent.run("go"))

        assert capture.consume(result) is not None
        assert capture.consume(result) is None

    def test_identity_gate_rejects_foreign_results(self):
        capture = PerRequestUsageCapture()
        agent = _agent_with(_tool_then_text_model(), capture)

        asyncio.run(agent.run("go"))

        assert capture.consume(object()) is None
        # The stale capture was cleared on the way out.
        assert capture._capture == []

    def test_empty_slot_returns_none(self):
        assert PerRequestUsageCapture().consume(object()) is None

    def test_consistency_gate_rejects_mid_run_history_rewrite(self):
        # A ProcessHistory pass that drops this run's own tool-call response
        # (the shape mid-run compaction produces on a long sub-agent run):
        # the seam saw two responses but the result records one. The eager
        # walk on main never reported the dropped response, so the capture
        # must disown itself rather than report a phantom usage entry.
        def dropper(messages):
            return [
                m
                for m in messages
                if not (
                    isinstance(m, ModelResponse)
                    and any(isinstance(p, ToolCallPart) for p in m.parts)
                )
            ]

        capture = PerRequestUsageCapture()
        agent = _agent_with(
            _counted_model({}), ProcessHistory(dropper), capture
        )

        result = asyncio.run(agent.run("go"))

        assert len(capture._capture[0][1]) == 2
        assert len(_recorded_responses(result)) == 1
        assert capture.consume(result) is None

    def test_consistency_gate_tolerates_new_messages_raising(self):
        capture = PerRequestUsageCapture()
        agent = _agent_with(_tool_then_text_model(), capture)

        asyncio.run(agent.run("go"))

        class ExplodingResult:
            def new_messages(self):
                raise RuntimeError("boom")

        exploding = ExplodingResult()
        # Force the identity gate to pass so the consistency gate runs.
        capture._capture[0] = (exploding, capture._capture[0][1])
        assert capture.consume(exploding) is None


class TestPerRunIsolation:
    def test_sequential_runs_do_not_accumulate(self):
        # Streaming-retry re-entry shape: multiple run() calls on one agent.
        capture = PerRequestUsageCapture()
        agent = _agent_with(_tool_then_text_model(), capture)

        first = asyncio.run(agent.run("go"))
        second = asyncio.run(
            agent.run("again", message_history=first.all_messages())
        )

        owned = capture.consume(second)
        assert owned is not None
        assert len(owned) == len(_recorded_responses(second)) == 1
        # The first run's capture was overwritten, not merged.
        assert capture.consume(first) is None

    def test_stale_capture_from_earlier_run_is_disowned(self):
        capture = PerRequestUsageCapture()
        agent = _agent_with(_tool_then_text_model(), capture)

        first = asyncio.run(agent.run("go"))
        asyncio.run(agent.run("again", message_history=first.all_messages()))

        # Consuming with the FIRST result must not surface the SECOND
        # run's capture.
        assert capture.consume(first) is None


class TestExtractionParity:
    def test_owned_capture_yields_identical_entries_to_eager_walk(self):
        capture = PerRequestUsageCapture()
        agent = _agent_with(_tool_then_text_model(), capture)

        result = asyncio.run(agent.run("go"))

        eager_entries = extract_per_request_usage(result.new_messages())
        eager_context = extract_final_context_tokens(result.new_messages())

        owned = capture.consume(result)
        assert owned is not None
        assert extract_per_request_usage(owned) == eager_entries
        assert extract_final_context_tokens(owned) == eager_context
        # FunctionModel reports real usage; make sure the parity assertion
        # is not vacuous.
        assert eager_entries and eager_entries[0].input_tokens

    def test_fallback_path_is_the_old_behavior(self):
        # When consume() disowns, the call site walks new_messages() -- the
        # literal pre-capability code. Simulated here end to end.
        capture = PerRequestUsageCapture()
        agent = _agent_with(_tool_then_text_model(), capture)

        result = asyncio.run(agent.run("go"))
        capture._capture.clear()  # guest wrapper shape: seam never fired

        source = capture.consume(result)
        assert source is None
        source = result.new_messages()
        assert extract_per_request_usage(source) == extract_per_request_usage(
            result.new_messages()
        )


class TestConstructionHelper:
    def test_disabled_metrics_build_nothing(self):
        capture, splice = build_per_request_usage_capture(False)
        assert capture is None
        assert splice == []

    def test_enabled_metrics_share_one_instance(self):
        capture, splice = build_per_request_usage_capture(True)
        assert isinstance(capture, PerRequestUsageCapture)
        assert splice == [capture]
        assert splice[0] is capture

    def test_capture_is_spec_constructible(self):
        # No live references: the capability round-trips through the spec
        # machinery with inherited defaults (series precedent: #844).
        name = PerRequestUsageCapture.get_serialization_name()
        assert name == "PerRequestUsageCapture"
        rebuilt = PerRequestUsageCapture.from_spec()
        assert isinstance(rebuilt, PerRequestUsageCapture)


class TestCallSiteWiring:
    def test_invocation_layer_wires_capture_and_consume(self):
        # Source pin: the invocation layer builds the capture, splices it
        # into capabilities, and consumes at the success boundary with the
        # eager walk as fallback.
        import inspect

        from code_puppy.tools import subagent_invocation

        source = inspect.getsource(subagent_invocation)
        assert "build_per_request_usage_capture" in source
        assert "usage_capture.consume(result)" in source
        assert "*usage_capture_splice" in source
        # The fallback is still the eager helpers on new_messages().
        assert "extract_per_request_usage(usage_source)" in source
        assert "extract_final_context_tokens(usage_source)" in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
