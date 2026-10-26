"""Deterministic accounting for eager tool overlap and discarded snippets."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import PartEndEvent, PartStartEvent, ToolCallPart
from pydantic_ai.tools import ToolDefinition

from code_puppy.capabilities.eager_timing import (
    EagerExecutionCompletedEvent,
    EagerTiming,
)


@pytest.fixture
def timing(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(
        "code_puppy.capabilities.eager_timing.perf_counter", lambda: clock[0]
    )
    return EagerTiming(), SimpleNamespace(run_step=1, emit=AsyncMock()), clock


async def start(capability, ctx, name="run_code"):
    await capability.on_event(
        ctx,
        event=PartStartEvent(
            index=0,
            part=ToolCallPart(tool_name=name, tool_call_id="parent"),
        ),
    )


async def end(capability, ctx):
    await capability.on_event(
        ctx,
        event=PartEndEvent(
            index=0,
            part=ToolCallPart(tool_name="run_code", tool_call_id="parent"),
        ),
    )


async def invoke(
    capability, ctx, handler, *, call_id="parent__1", name="slow_tool", args=None
):
    return await capability.wrap_tool_execute(
        ctx,
        call=ToolCallPart(tool_name=name, tool_call_id=call_id),
        tool_def=ToolDefinition(name=name),
        args={} if args is None else args,
        handler=handler,
    )


async def successful(_args):
    return "success"


async def commit(capability, ctx):
    return await invoke(capability, ctx, successful, call_id="parent", name="run_code")


async def test_partial_overlap_stops_at_argument_end(timing):
    cap, ctx, clock = timing
    await start(cap, ctx)

    async def tool(_args):
        clock[0] = 12.0
        await end(cap, ctx)
        clock[0] = 15.0
        return "result"

    assert await invoke(cap, ctx, tool) == "result"
    ctx.emit.assert_not_called()
    assert await commit(cap, ctx) == "success"
    event = ctx.emit.call_args.args[0]
    assert isinstance(event, EagerExecutionCompletedEvent)
    assert event.saved_ms == 2000.0
    assert event.tool_call_id == "parent"
    assert cap._windows == {}


async def test_prefixed_wire_name_still_credits_resolved_run_code(timing):
    """Claude Code OAuth streams cp_run_code; dispatch resolves it to run_code."""
    cap, ctx, clock = timing
    await start(cap, ctx, name="cp_run_code")

    async def tool(_args):
        clock[0] = 12.0
        return "done"

    await invoke(cap, ctx, tool)
    await end(cap, ctx)
    await commit(cap, ctx)
    assert ctx.emit.call_args.args[0].saved_ms == 2000.0


async def test_native_tool_window_is_released_without_credit(timing):
    cap, ctx, clock = timing
    await start(cap, ctx, name="create_file")
    await invoke(cap, ctx, successful, call_id="parent", name="create_file")
    ctx.emit.assert_not_called()
    assert cap._windows == {}


async def test_fully_hidden_call_excludes_idle_generation_time(timing):
    cap, ctx, clock = timing
    await start(cap, ctx)

    async def tool(_args):
        clock[0] = 11.0
        return "done"

    await invoke(cap, ctx, tool)
    clock[0] = 20.0
    await end(cap, ctx)
    await commit(cap, ctx)
    assert ctx.emit.call_args.args[0].saved_ms == 1000.0


@pytest.mark.parametrize("call_id", ["parent__spec_1", "native-id", "unrelated__1"])
async def test_speculative_and_native_calls_do_not_count(timing, call_id):
    cap, ctx, clock = timing
    await start(cap, ctx)

    async def tool(_args):
        clock[0] = 12.0
        return "unchanged"

    assert await invoke(cap, ctx, tool, call_id=call_id) == "unchanged"
    await end(cap, ctx)
    await commit(cap, ctx)
    ctx.emit.assert_not_called()


async def test_cold_call_after_generation_does_not_count(timing):
    cap, ctx, clock = timing
    await start(cap, ctx)
    await end(cap, ctx)

    async def tool(_args):
        clock[0] = 20.0
        return "done"

    await invoke(cap, ctx, tool)
    await commit(cap, ctx)
    ctx.emit.assert_not_called()


@pytest.mark.parametrize("error", [ModelRetry("bad prefix"), asyncio.CancelledError()])
async def test_failed_or_cancelled_snippet_discards_credit(timing, error):
    cap, ctx, clock = timing
    await start(cap, ctx)

    async def tool(_args):
        clock[0] = 12.0
        return "done"

    await invoke(cap, ctx, tool)
    await end(cap, ctx)

    async def fail(_args):
        raise error

    with pytest.raises(type(error)):
        await invoke(cap, ctx, fail, call_id="parent", name="run_code")
    ctx.emit.assert_not_called()
    assert cap._windows == {}


async def test_restart_discards_credit(timing):
    cap, ctx, clock = timing
    await start(cap, ctx)

    async def tool(_args):
        clock[0] = 12.0
        return "done"

    await invoke(cap, ctx, tool)
    await end(cap, ctx)
    await invoke(
        cap, ctx, successful, call_id="parent", name="run_code", args={"restart": True}
    )
    ctx.emit.assert_not_called()


async def test_for_run_does_not_share_windows(timing):
    cap, ctx, _ = timing
    first = await cap.for_run(ctx)
    second = await cap.for_run(ctx)
    await start(first, ctx)
    assert first._windows
    assert not second._windows
    assert not cap._windows


async def test_reused_provider_id_on_another_step_does_not_match(timing):
    cap, ctx, clock = timing
    await start(cap, ctx)
    ctx.run_step = 2

    async def tool(_args):
        clock[0] = 12.0
        return "done"

    await invoke(cap, ctx, tool)
    await commit(cap, ctx)
    ctx.emit.assert_not_called()


async def test_telemetry_failure_preserves_tool_result(timing):
    cap, ctx, clock = timing
    await start(cap, ctx)

    async def tool(_args):
        clock[0] = 12.0
        return "done"

    await invoke(cap, ctx, tool)
    await end(cap, ctx)
    ctx.emit.side_effect = RuntimeError("telemetry unavailable")
    assert await commit(cap, ctx) == "success"
    assert cap._windows == {}
