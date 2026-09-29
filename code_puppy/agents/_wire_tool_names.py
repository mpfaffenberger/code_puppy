"""Resolve wire-prefixed tool names in the stream before capabilities watch it."""

from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import replace

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import (
    AgentStreamEvent,
    PartEndEvent,
    PartStartEvent,
    ToolCallPart,
)
from pydantic_ai.tools import AgentDepsT

from code_puppy._pydantic_tool_helpers import _normalize_claude_code_tool_name


class StreamedToolNameNormalizer(AbstractCapability[AgentDepsT]):
    """Claude Code OAuth streams ``cp_run_code``; the ToolManager patch only
    fixes dispatch. Stream watchers such as the CodeMode eager pump and
    speculation launcher match on ``run_code``, so rewrite the events they see.
    The accumulated response is left as delivered."""

    async def wrap_run_event_stream(
        self,
        ctx: RunContext[AgentDepsT],
        *,
        stream: AsyncIterable[AgentStreamEvent],
    ) -> AsyncIterable[AgentStreamEvent]:
        async for event in stream:
            yield _normalized(ctx, event)


def _normalized(ctx: RunContext[object], event: AgentStreamEvent) -> AgentStreamEvent:
    if not isinstance(event, (PartStartEvent, PartEndEvent)):
        return event
    part = event.part
    if not isinstance(part, ToolCallPart):
        return event
    resolved = _normalize_claude_code_tool_name(ctx.tool_manager, part.tool_name)
    if resolved == part.tool_name:
        return event
    return replace(event, part=replace(part, tool_name=resolved))
