"""Tests for fallback rendering when streaming emits no text (issue #295)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic_ai import PartDeltaEvent, PartStartEvent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
    ToolCallPart,
    UserPromptPart,
)

from code_puppy.agents._non_streaming_render import (
    StreamingTextDetector,
    _collect_final_text_from_messages,
    _collect_thinking_from_messages,
    render_result_without_streaming,
    should_render_fallback,
)

# --- StreamingTextDetector --------------------------------------------------


class _StubResult:
    def __init__(self, messages):
        self._messages = messages

    def all_messages(self):
        return self._messages


async def _drain_through_detector(events):
    """Pipe ``events`` through a detector wrapping a pass-through inner."""

    captured = []

    async def inner(ctx, wrapped_events):
        async for ev in wrapped_events:
            captured.append(ev)

    detector = StreamingTextDetector(inner)

    async def _async_iter():
        for ev in events:
            yield ev

    await detector(ctx=None, events=_async_iter())
    return detector, captured


@pytest.mark.asyncio
async def test_detector_flags_text_part_start():
    events = [PartStartEvent(index=0, part=TextPart(content="hello"))]
    detector, captured = await _drain_through_detector(events)
    assert detector.streamed_text is True
    assert len(captured) == 1  # events still forwarded


@pytest.mark.asyncio
async def test_detector_flags_text_part_delta():
    events = [
        PartStartEvent(index=0, part=TextPart(content="")),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="tok")),
    ]
    detector, captured = await _drain_through_detector(events)
    assert detector.streamed_text is True
    assert len(captured) == 2


@pytest.mark.asyncio
async def test_detector_ignores_thinking_and_tool_events():
    events = [
        PartStartEvent(index=0, part=ThinkingPart(content="mmm")),
        PartDeltaEvent(index=0, delta=ThinkingPartDelta(content_delta="more")),
        PartStartEvent(index=1, part=ToolCallPart(tool_name="x", args={})),
    ]
    detector, captured = await _drain_through_detector(events)
    assert detector.streamed_text is False
    assert len(captured) == 3


@pytest.mark.asyncio
async def test_detector_ignores_empty_text_part():
    events = [PartStartEvent(index=0, part=TextPart(content="   "))]
    detector, _ = await _drain_through_detector(events)
    assert detector.streamed_text is False


# --- should_render_fallback -------------------------------------------------


def test_should_render_fallback_skip_dbos_wins():
    detector = SimpleNamespace(streamed_text=False)
    assert should_render_fallback(detector, skip=True) is False


def test_should_render_fallback_no_detector_means_render():
    assert should_render_fallback(None, skip=False) is True


def test_should_render_fallback_streamed_text_means_skip():
    detector = SimpleNamespace(streamed_text=True)
    assert should_render_fallback(detector, skip=False) is False


def test_should_render_fallback_no_text_streamed_means_render():
    detector = SimpleNamespace(streamed_text=False)
    assert should_render_fallback(detector, skip=False) is True


# --- Message walkers --------------------------------------------------------


def _mk_result(*model_responses):
    """Build a ``_StubResult`` with a user prompt + the given responses."""
    messages = [ModelRequest(parts=[UserPromptPart(content="hi")])]
    messages.extend(model_responses)
    return _StubResult(messages)


def test_collect_final_text_from_last_response_only():
    result = _mk_result(
        ModelResponse(parts=[TextPart(content="draft")]),
        ModelResponse(parts=[TextPart(content="final "), TextPart(content="answer")]),
    )
    assert _collect_final_text_from_messages(result) == "final answer"


def test_collect_final_text_handles_no_model_response():
    result = _StubResult([ModelRequest(parts=[UserPromptPart(content="x")])])
    assert _collect_final_text_from_messages(result) == ""


def test_collect_thinking_from_intermediate_responses():
    result = _mk_result(
        ModelResponse(parts=[ThinkingPart(content="step 1")]),
        ModelResponse(parts=[ThinkingPart(content="step 2")]),
        ModelResponse(parts=[TextPart(content="done")]),
    )
    thinking = _collect_thinking_from_messages(result)
    assert "step 1" in thinking
    assert "step 2" in thinking
    # Final response's text must not leak into thinking.
    assert "done" not in thinking


def test_collect_thinking_empty_when_only_final_response():
    result = _mk_result(ModelResponse(parts=[TextPart(content="done")]))
    assert _collect_thinking_from_messages(result) == ""


def test_collectors_tolerate_broken_all_messages():
    class Boom:
        def all_messages(self):
            raise RuntimeError("nope")

    assert _collect_final_text_from_messages(Boom()) == ""
    assert _collect_thinking_from_messages(Boom()) == ""


# --- render_result_without_streaming ----------------------------------------


def test_render_renders_final_text_only_when_no_thinking():
    result = _mk_result(ModelResponse(parts=[TextPart(content="the answer")]))
    with patch(
        "code_puppy.agents._non_streaming_render.display_non_streamed_result"
    ) as disp:
        render_result_without_streaming(result)

    assert disp.call_count == 1
    assert disp.call_args.args[0] == "the answer"


def test_render_renders_thinking_and_final_text():
    result = _mk_result(
        ModelResponse(parts=[ThinkingPart(content="hmm")]),
        ModelResponse(parts=[TextPart(content="answer")]),
    )
    with patch(
        "code_puppy.agents._non_streaming_render.display_non_streamed_result"
    ) as disp:
        render_result_without_streaming(result)

    assert disp.call_count == 2
    first_call, second_call = disp.call_args_list
    assert first_call.args[0] == "hmm"
    assert first_call.kwargs.get("banner_text") == "THINKING"
    assert second_call.args[0] == "answer"


def test_render_swallows_display_errors():
    result = _mk_result(ModelResponse(parts=[TextPart(content="boom")]))
    with patch(
        "code_puppy.agents._non_streaming_render.display_non_streamed_result",
        side_effect=RuntimeError("console dead"),
    ):
        # Must not raise.
        render_result_without_streaming(result)


def test_render_skips_empty_final_text():
    result = _mk_result(ModelResponse(parts=[TextPart(content="   ")]))
    with patch(
        "code_puppy.agents._non_streaming_render.display_non_streamed_result"
    ) as disp:
        render_result_without_streaming(result)
    disp.assert_not_called()
