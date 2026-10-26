"""Review regressions for dynamic overhead and production receipt wiring."""

import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models import Model, StreamedResponse
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RequestUsage

from code_puppy import token_usage
from code_puppy.agents import _compaction
from code_puppy.agents._model_message_transform import build_model_message_transform
from code_puppy.context_accounting import context_tokens, record_anchor
from code_puppy.round_robin_model import RoundRobinModel


def history():
    prefix = [ModelRequest(parts=[UserPromptPart("hello")])]
    response = ModelResponse(
        parts=[TextPart("reply")],
        model_name="model",
        usage=RequestUsage(input_tokens=160000, output_tokens=10),
    )
    record_anchor(prefix, response, context_overhead=50)
    return [*prefix, response]


def _owner(**extra):
    base = dict(
        _message_history=[],
        _compacted_message_hashes=set(),
        _get_model_context_length=lambda: 200000,
        _estimate_context_overhead=lambda: 0,
        name="test",
    )
    base.update(extra)
    return SimpleNamespace(**base)


@pytest.mark.parametrize("overhead", [51, 1000, 25])
def test_dynamic_overhead_adjusts_anchor_instead_of_discarding(overhead):
    assert context_tokens(history(), "model", overhead) == 160010 + overhead - 50


def test_shared_entry_point_imports_in_fresh_process():
    result = subprocess.run(
        [sys.executable, "-c", "import code_puppy.context_accounting"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


async def test_nonzero_processor_overhead_is_recorded_and_reused():
    overhead = Mock(return_value=123)
    owner = _owner(_estimate_context_overhead=overhead)
    model = FunctionModel(
        lambda messages, info: ModelResponse(
            parts=[TextPart("ok")],
            usage=RequestUsage(input_tokens=160000, output_tokens=10),
        ),
        model_name="model",
    )
    agent = Agent(
        model,
        capabilities=[
            _compaction.HistoryCompaction(owner),
            build_model_message_transform("test", owner),
        ],
    )
    messages = (await agent.run("hello")).all_messages()
    assert messages[-1].metadata["context_anchor"]["overhead"] == 123
    assert context_tokens(messages, "model", 124) == 160011
    assert overhead.call_count == 1

    overhead.return_value = 124
    result2 = await agent.run("next turn", message_history=messages)
    assert overhead.call_count == 2
    # The follow-up turn's own stamped overhead reflects the new value. Its
    # response isn't merged into ``owner._message_history`` until a *third*
    # request's before_model_request would run -- which never happens here
    # -- so check the run result's own message list instead.
    final_response = result2.all_messages()[-1]
    assert final_response.metadata["context_anchor"]["overhead"] == 124


async def test_round_robin_response_is_valid_for_current_model():
    from code_puppy.context_accounting import active_model_name

    model = FunctionModel(
        lambda messages, info: ModelResponse(
            parts=[TextPart("ok")],
            usage=RequestUsage(input_tokens=150000, output_tokens=10),
        ),
        model_name="model",
    )
    rotating = RoundRobinModel(model, TestModel(model_name="other"))
    owner = SimpleNamespace(cur_model=rotating, get_model_name=lambda: "config-alias")
    messages = (
        await Agent(
            rotating, capabilities=[build_model_message_transform("routing-test")]
        ).run("hello")
    ).all_messages()
    assert context_tokens(messages, active_model_name(owner), 0) == 150010


def test_model_switch_status_uses_shared_counter():
    from code_puppy.model_switching import _refresh_context_status

    owner = SimpleNamespace(
        cur_model=TestModel(model_name="model"),
        get_model_name=lambda: "alias",
        get_message_history=history,
        _estimate_context_overhead=lambda: 50,
        _get_model_context_length=lambda: 200000,
        estimate_tokens_for_message=lambda msg: 1,
    )
    with (
        patch(
            "code_puppy.messaging.spinner.format_context_info",
            side_effect=lambda total, *args: str(total),
        ),
        patch("code_puppy.messaging.spinner.update_spinner_context") as update,
    ):
        _refresh_context_status(owner)
    update.assert_called_once_with("160010")


def test_breakdown_preserves_bucket_sum_and_shared_total(monkeypatch):
    from code_puppy.agents import agent_manager

    owner = SimpleNamespace(
        cur_model=TestModel(model_name="model"),
        get_model_name=lambda: "alias",
        get_message_history=history,
        _estimate_context_overhead=lambda: 50,
        _get_model_context_length=lambda: 200000,
    )
    monkeypatch.setattr(agent_manager, "get_current_agent", lambda: owner)
    monkeypatch.setattr(
        token_usage,
        "compute_overhead_breakdown",
        lambda agent: token_usage.OverheadBreakdown(10, 20, 30, 40),
    )
    usage = token_usage.get_current_usage()
    assert usage.overhead_tokens == 100
    assert usage.total_tokens == 160010


def test_breakdown_exceeding_shared_total_does_not_override_display(monkeypatch):
    """Regression: the breakdown is an independent, approximate re-estimate
    (e.g. a live MCP tool-schema lookup vs. the agent's cached server list
    the shared total used), so it can come out *larger* than the shared
    total. The displayed aggregate must stay the authoritative shared total
    -- never ``max(total, breakdown.total)`` -- or the status bar and
    compaction's own trigger would disagree about how full the window is.
    """
    from code_puppy.agents import agent_manager

    owner = SimpleNamespace(
        cur_model=TestModel(model_name="model"),
        get_model_name=lambda: "alias",
        get_message_history=history,
        _estimate_context_overhead=lambda: 50,
        _get_model_context_length=lambda: 200000,
    )
    monkeypatch.setattr(agent_manager, "get_current_agent", lambda: owner)
    # Breakdown sum (10+20+30+500_000 == 500_060) vastly exceeds the shared
    # total (160010) -- simulating a live MCP lookup ballooning relative to
    # the cached server list the shared estimator saw.
    monkeypatch.setattr(
        token_usage,
        "compute_overhead_breakdown",
        lambda agent: token_usage.OverheadBreakdown(10, 20, 30, 500_000),
    )
    usage = token_usage.get_current_usage()
    assert usage.overhead_tokens == 500_060
    # The authoritative total is unchanged by the oversized breakdown.
    assert usage.total_tokens == 160010
    # used_tokens may go negative-clamped-to-0 here -- that's an intentional
    # signal that the breakdown and the shared total disagree, not a
    # separate bug to paper over by clamping the *authoritative* total.
    assert usage.used_tokens == 0


async def test_real_round_robin_agent_retains_anchor_between_steps():
    from pydantic_ai.messages import ToolCallPart

    calls = 0

    def respond(messages, info):
        nonlocal calls
        calls += 1
        parts = [ToolCallPart("ping", {}, "id")] if calls == 1 else [TextPart("done")]
        return ModelResponse(
            parts=parts, usage=RequestUsage(input_tokens=150000, output_tokens=10)
        )

    rotating = RoundRobinModel(
        FunctionModel(respond, model_name="a"), FunctionModel(respond, model_name="b")
    )
    owner = _owner(_estimate_context_overhead=lambda: 123)
    agent = Agent(
        rotating,
        capabilities=[
            _compaction.HistoryCompaction(owner),
            build_model_message_transform("test", owner),
        ],
    )

    @agent.tool_plain
    def ping() -> str:
        return "pong"

    await agent.run("hello")
    tool_call_response = next(
        m
        for m in owner._message_history
        if isinstance(m, ModelResponse)
        and any(isinstance(p, ToolCallPart) for p in m.parts)
    )
    assert tool_call_response.metadata["context_anchor"]
    # The final "done" response is from whichever candidate ran second and
    # isn't merged into ``owner._message_history`` within this same run (the
    # merge happens at the *next* request's before_model_request, same as
    # the tool-call step above) -- so validate against the candidate
    # identity set a compaction trigger would actually see mid-run.
    from code_puppy.context_accounting import model_names

    # Confirms the anchor is actually used (API usage dominates the total)
    # rather than a silent fallback to a tens-of-tokens chars/2.5 estimate.
    # Not pinned to an exact figure: passing overhead=0 here while the
    # stamped receipt recorded overhead=123 nets a small negative delta.
    assert context_tokens(owner._message_history, model_names(rotating), 0) > 100000


async def test_in_place_transform_does_not_get_identity_shortcut():
    from code_puppy import callbacks

    def rewrite(name, messages):
        messages[-1].parts[-1].content = "rewritten in place"

    callbacks.register_callback("transform_model_messages", rewrite)
    agent = Agent(
        FunctionModel(
            lambda messages, info: ModelResponse(
                parts=[TextPart("ok")],
                usage=RequestUsage(input_tokens=1000, output_tokens=10),
            ),
            model_name="model",
        ),
        capabilities=[build_model_message_transform("test")],
    )
    messages = (await agent.run("hello")).all_messages()
    assert not (messages[-1].metadata or {}).get("context_anchor")


class _TwoSegmentModel(Model):
    """First segment suspends, second completes -- the same provider-agnostic
    merge path real Anthropic ``pause_turn`` / OpenAI background-mode
    continuations go through (keyed only on ``response.state`` in
    ``pydantic_ai.models._continuation``). ``segments`` controls how many
    suspended hand-offs happen before the final complete response: one
    element is a single-segment control (no continuation at all).
    """

    def __init__(self, segments):
        self._segments = list(segments)
        self._n = 0

    @property
    def model_name(self):
        return "continuation-test"

    @property
    def system(self):
        return "test"

    async def request(self, messages, model_settings, model_request_parameters):
        state, input_tokens, text = self._segments[self._n]
        self._n += 1
        return ModelResponse(
            parts=[TextPart(text)],
            model_name=self.model_name,
            state=state,
            provider_response_id=f"seg-{self._n}",
            usage=RequestUsage(input_tokens=input_tokens, output_tokens=5),
        )


@dataclass
class _FakeStreamSegment(StreamedResponse):
    """Minimal controllable ``StreamedResponse`` for exercising the
    streaming continuation loop (``models/_continuation.py``'s composite
    also calls ``model.continuation_delay`` per intermediate segment, same
    as the non-streaming loop in ``_agent_graph.model_request``).
    """

    _model_name: str = ""
    _text: str = ""
    _input_tokens: int = 0
    _output_tokens: int = 0

    def __post_init__(self):
        self._usage = RequestUsage(
            input_tokens=self._input_tokens, output_tokens=self._output_tokens
        )

    async def _get_event_iterator(self):
        for event in self._parts_manager.handle_text_delta(
            vendor_part_id="content", content=self._text
        ):
            yield event

    async def close_stream(self):
        pass

    @property
    def model_name(self):
        return self._model_name

    @property
    def provider_name(self):
        return "test"

    @property
    def provider_url(self):
        return None

    @property
    def timestamp(self):
        return datetime.now(timezone.utc)


class _TwoSegmentStreamingModel(Model):
    """Streaming counterpart of ``_TwoSegmentModel``."""

    def __init__(self, segments):
        self._segments = list(segments)
        self._n = 0

    @property
    def model_name(self):
        return "continuation-stream-test"

    @property
    def system(self):
        return "test"

    async def request(self, messages, model_settings, model_request_parameters):
        raise NotImplementedError

    def request_stream(
        self, messages, model_settings, model_request_parameters, run_context=None
    ):
        state, input_tokens, text = self._segments[self._n]
        self._n += 1
        model_name = self.model_name

        class _Ctx:
            async def __aenter__(ctx_self):
                seg = _FakeStreamSegment(
                    model_request_parameters=model_request_parameters,
                    _model_name=model_name,
                    _text=text,
                    _input_tokens=input_tokens,
                    _output_tokens=5,
                )
                seg.state = state
                return seg

            async def __aexit__(ctx_self, *exc):
                return False

        return _Ctx()


async def _noop_event_stream_handler(_ctx, events):
    async for _event in events:
        pass


async def test_continuation_suppresses_receipt_non_streaming():
    """Round-2 review fix: a request-local model wrapper observes the
    suspended->continued chain via ``continuation_delay`` *before*
    pydantic-ai merges the segments, so the capability can decline to
    anchor a cumulative-usage response instead of stamping it as if it
    were one measured prompt. See ``_ContinuationObserver`` in
    ``_model_message_transform.py``.
    """
    owner = _owner()
    agent = Agent(
        _TwoSegmentModel(
            [("suspended", 10_000, "partial..."), ("complete", 11_000, "...done")]
        ),
        capabilities=[
            _compaction.HistoryCompaction(owner),
            build_model_message_transform("test", owner),
        ],
    )
    result = await agent.run("hello")
    final = result.all_messages()[-1]

    # Billing/usage itself is untouched -- still the real cumulative sum.
    assert final.usage.input_tokens == 21_000
    # But no receipt is stamped against it: this total isn't one prompt.
    assert (final.metadata or {}).get("context_anchor") is None


async def test_continuation_suppresses_receipt_streaming():
    """Streaming counterpart: the composite stream's continuation loop
    (``models/_continuation.py``) also calls ``continuation_delay`` per
    segment, so the same observer/suppression applies.
    """
    owner = _owner()
    agent = Agent(
        _TwoSegmentStreamingModel(
            [("suspended", 10_000, "partial..."), ("complete", 11_000, "...done")]
        ),
        capabilities=[
            _compaction.HistoryCompaction(owner),
            build_model_message_transform("test", owner),
        ],
    )
    result = await agent.run("hello", event_stream_handler=_noop_event_stream_handler)
    final = result.all_messages()[-1]

    assert final.usage.input_tokens == 21_000
    assert (final.metadata or {}).get("context_anchor") is None


async def test_single_segment_control_still_anchors():
    """Control: an ordinary, non-continued response through the *same*
    wrapped-model code path still gets anchored normally -- the observer
    only suppresses when a continuation is actually observed, it doesn't
    blanket-disable anchoring just because the machinery is present.
    """
    owner = _owner()
    agent = Agent(
        _TwoSegmentModel([("complete", 10_000, "done")]),
        capabilities=[
            _compaction.HistoryCompaction(owner),
            build_model_message_transform("test", owner),
        ],
    )
    result = await agent.run("hello")
    final = result.all_messages()[-1]

    assert final.usage.input_tokens == 10_000
    receipt = (final.metadata or {}).get("context_anchor")
    assert receipt is not None
    total = context_tokens(result.all_messages(), "continuation-test", 0)
    # 10_000 input + 5 output replay == 10_005, plus the "hello" prompt's
    # own few estimated tokens -- in the same ballpark the reviewer's own
    # single-segment control reported (10,010).
    assert 10_000 < total < 10_100
