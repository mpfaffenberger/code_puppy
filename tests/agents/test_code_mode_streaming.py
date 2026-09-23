"""Exercise the released sandbox and speculation with a deterministic stream."""

import asyncio
import json
from collections.abc import AsyncIterator

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import AgentStreamEvent, ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai_harness.code_mode import (
    SpeculativeCallClaimedEvent,
    SpeculativeCallLaunchedEvent,
    SpeculativeCodeUpdateEvent,
)

from code_puppy.agents._code_mode import build_speculative_code_mode
from code_puppy.agents.agent_speculative_puppy import SpeculativePuppyAgent


@pytest.mark.asyncio
async def test_streamed_read_is_claimed_once_and_write_is_not_speculated(monkeypatch):
    monkeypatch.setattr(
        "code_puppy.agents._code_mode.get_speculative_code_mode_enabled", lambda: True
    )
    read_started = asyncio.Event()
    reads: list[str] = []
    writes: list[str] = []
    events: list[AgentStreamEvent] = []
    requests = 0

    async def read_file(file_path: str) -> str:
        reads.append(file_path)
        read_started.set()
        return "file contents"

    async def create_file(content: str) -> str:
        writes.append(content)
        return "saved"

    async def replace_in_file(content: str) -> str:
        writes.append(content)
        return "replaced"

    async def stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal requests
        requests += 1
        assert {tool.name for tool in info.function_tools} == {
            "run_code",
            "create_file",
            "replace_in_file",
        }
        if requests == 2:
            yield {
                0: DeltaToolCall(
                    name="create_file", json_args='{"content":"file contents"}'
                )
            }
            return
        if requests == 3:
            yield {
                0: DeltaToolCall(
                    name="replace_in_file", json_args='{"content":"updated"}'
                )
            }
            return
        if requests > 3:
            yield "done"
            return
        prefix = 'text = await read_file(file_path="example.py")\n'
        args = json.dumps({"code": prefix})
        yield {0: DeltaToolCall(name="run_code", json_args=args[:-2])}
        # A second delta lets the stream consumer process the closed statement.
        yield {0: DeltaToolCall(json_args="\\n")}
        await asyncio.wait_for(read_started.wait(), 2)
        assert not writes
        tail = "text"
        yield {0: DeltaToolCall(json_args=json.dumps(tail)[1:-1] + '"}')}

    async def capture(
        ctx: RunContext[None], stream_events: AsyncIterator[AgentStreamEvent]
    ) -> None:
        async for event in stream_events:
            events.append(event)

    agent = Agent(
        FunctionModel(stream_function=stream),
        tools=[read_file, create_file, replace_in_file],
        capabilities=build_speculative_code_mode(
            SpeculativePuppyAgent(), ["read_file", "create_file", "replace_in_file"]
        ),
    )
    result = await agent.run("read then save", event_stream_handler=capture)
    assert result.output == "done"
    assert reads == ["example.py"]
    assert writes == ["file contents", "updated"]
    launches = [
        event for event in events if isinstance(event, SpeculativeCallLaunchedEvent)
    ]
    claims = [
        event for event in events if isinstance(event, SpeculativeCallClaimedEvent)
    ]
    assert launches and claims
    assert {event.wrapped_tool_name for event in launches} == {"read_file"}
    assert {event.launch_id for event in launches} == {
        event.launch_id for event in claims
    }
    assert any(isinstance(event, SpeculativeCodeUpdateEvent) for event in events)
