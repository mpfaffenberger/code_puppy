"""Exercise eager timing through real CodeMode and the nested tool manager."""

import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import (
    AgentStreamEvent,
    ModelMessage,
    PartEndEvent,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from code_puppy.agents._code_mode import build_speculative_code_mode
from code_puppy.capabilities.eager_timing import EagerExecutionCompletedEvent


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["eager", "speculative", "miss"])
@pytest.mark.parametrize("partial", [False, True])
async def test_real_eager_overlap_excludes_speculative_launches(
    monkeypatch, mode, partial
):
    monkeypatch.setattr(
        "code_puppy.agents._code_mode.get_speculative_code_mode_enabled", lambda: True
    )
    clock = [10.0]
    monkeypatch.setattr(
        "code_puppy.capabilities.eager_timing.perf_counter", lambda: clock[0]
    )
    started = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()
    captured: list[AgentStreamEvent] = []
    requests = 0
    calls = 0

    async def slow_tool(value: str) -> str:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        finished.set()
        return value

    slow_tool.__name__ = "slow_tool" if mode == "eager" else "read_file"
    tool_name = slow_tool.__name__

    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal requests
        requests += 1
        if requests > 1:
            yield "done"
            return
        prefix = f'value = await {tool_name}(value="demo")\nmarker = 1\n'
        if mode == "miss":
            prefix = 'argument = "demo"\nvalue = await read_file(value=argument)\nmarker = 1\n'
        encoded = json.dumps({"code": prefix})
        yield {0: DeltaToolCall(name="run_code", json_args=encoded[:-2])}
        yield {0: DeltaToolCall(json_args="\\n")}
        await asyncio.wait_for(started.wait(), 2)
        clock[0] = 12.0
        if not partial:
            release.set()
            await asyncio.wait_for(finished.wait(), 2)
            clock[0] = 15.0
        yield {0: DeltaToolCall(json_args='value"}')}

    async def capture(
        ctx: RunContext[None], events: AsyncIterator[AgentStreamEvent]
    ) -> None:
        async for event in events:
            captured.append(event)
            if (
                partial
                and isinstance(event, PartEndEvent)
                and isinstance(event.part, ToolCallPart)
            ):
                clock[0] = 15.0
                release.set()

    agent = Agent(
        FunctionModel(stream_function=stream),
        tools=[slow_tool],
        capabilities=build_speculative_code_mode([tool_name]),
    )
    result = await agent.run("demo", event_stream_handler=capture)
    assert result.output == "done"
    assert calls == 1
    timing = [e for e in captured if isinstance(e, EagerExecutionCompletedEvent)]
    if mode == "speculative":
        assert timing == []
    else:
        assert len(timing) == 1
        assert timing[0].saved_ms == 2000.0
