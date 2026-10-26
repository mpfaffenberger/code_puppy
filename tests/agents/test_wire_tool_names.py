"""Streamed Claude Code wire names resolve before stream watchers see them."""

from types import SimpleNamespace

import pytest
from pydantic_ai.messages import (
    PartDeltaEvent,
    PartEndEvent,
    PartStartEvent,
    TextPart,
    ToolCallPart,
    ToolCallPartDelta,
)

from code_puppy.agents._wire_tool_names import (
    StreamedToolNameNormalizer,
    _normalized,
)


@pytest.fixture
def ctx():
    return SimpleNamespace(tool_manager=SimpleNamespace(tools={"run_code": object()}))


def _tool_event(kind, name):
    return kind(index=0, part=ToolCallPart(tool_name=name, tool_call_id="toolu_1"))


@pytest.mark.parametrize("kind", [PartStartEvent, PartEndEvent])
def test_prefixed_run_code_resolves_without_mutating_original(ctx, kind):
    event = _tool_event(kind, "cp_run_code")

    out = _normalized(ctx, event)

    assert out.part.tool_name == "run_code"
    assert out.part.tool_call_id == "toolu_1"
    assert event.part.tool_name == "cp_run_code"


def test_registry_owned_prefixed_name_is_kept(ctx):
    ctx.tool_manager.tools["cp_run_code"] = object()
    event = _tool_event(PartStartEvent, "cp_run_code")
    assert _normalized(ctx, event) is event


@pytest.mark.parametrize(
    "event",
    [
        _tool_event(PartStartEvent, "run_code"),
        PartStartEvent(index=0, part=TextPart(content="hi")),
        PartDeltaEvent(index=0, delta=ToolCallPartDelta(args_delta="x")),
    ],
)
def test_untouched_events_pass_through_by_identity(ctx, event):
    assert _normalized(ctx, event) is event


async def test_wrapper_rewrites_only_prefixed_tool_parts(ctx):
    async def stream():
        yield _tool_event(PartStartEvent, "cp_run_code")
        yield PartDeltaEvent(index=0, delta=ToolCallPartDelta(args_delta="{"))
        yield _tool_event(PartEndEvent, "cp_run_code")

    names = []
    async for event in StreamedToolNameNormalizer().wrap_run_event_stream(
        ctx, stream=stream()
    ):
        part = getattr(event, "part", None)
        names.append(part.tool_name if part is not None else None)

    assert names == ["run_code", None, "run_code"]
