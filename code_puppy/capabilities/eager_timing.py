"""Measure eager CodeMode tool latency hidden behind argument streaming."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from time import perf_counter

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.capabilities.abstract import (
    ValidatedToolArgs,
    WrapToolExecuteHandler,
)
from pydantic_ai.messages import (
    AgentStreamEvent,
    CapabilityEvent,
    PartEndEvent,
    PartStartEvent,
    ToolCallPart,
)
from pydantic_ai.tools import AgentDepsT, ToolDefinition

logger = logging.getLogger(__name__)


@dataclass(kw_only=True)
class EagerExecutionCompletedEvent(CapabilityEvent, namespace="code_puppy"):
    """A completed snippet reused tool latency hidden by eager execution."""

    saved_ms: float
    """Summed tool-call overlap with generation, not wall-clock speedup."""


@dataclass(kw_only=True)
class _StreamWindow:
    ended: float | None = None
    saved_ms: float = 0.0


@dataclass
class EagerTiming(AbstractCapability[AgentDepsT]):
    """Observe public execution hooks without changing tool behavior."""

    _windows: dict[tuple[int, str], _StreamWindow] = field(
        default_factory=dict, init=False, repr=False
    )

    async def for_run(self, ctx: RunContext[AgentDepsT]) -> EagerTiming[AgentDepsT]:
        return EagerTiming()

    async def on_event(
        self, ctx: RunContext[AgentDepsT], *, event: AgentStreamEvent
    ) -> None:
        # Wire names can be prefixed mid-stream (Claude Code OAuth sends
        # cp_run_code), so track every tool call and decide at execution.
        if isinstance(event, PartStartEvent) and isinstance(event.part, ToolCallPart):
            self._windows[(ctx.run_step, event.part.tool_call_id)] = _StreamWindow()
        elif isinstance(event, PartEndEvent) and isinstance(event.part, ToolCallPart):
            window = self._windows.get((ctx.run_step, event.part.tool_call_id))
            if window is not None and window.ended is None:
                window.ended = perf_counter()

    async def wrap_tool_execute(
        self,
        ctx: RunContext[AgentDepsT],
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: ValidatedToolArgs,
        handler: WrapToolExecuteHandler,
    ) -> object:
        parent_id, separator, sequence = call.tool_call_id.rpartition("__")
        if not separator or not sequence.isdecimal():
            key = (ctx.run_step, call.tool_call_id)
            window = self._windows.get(key)
            if window is not None and window.ended is None:
                window.ended = perf_counter()
            try:
                result = await handler(args)
                if (
                    tool_def.name == "run_code"
                    and window is not None
                    and not args.get("restart")
                    and window.saved_ms > 0
                ):
                    try:
                        await ctx.emit(
                            EagerExecutionCompletedEvent(
                                tool_call_id=call.tool_call_id,
                                saved_ms=window.saved_ms,
                            )
                        )
                    except Exception:
                        logger.debug("could not emit eager timing", exc_info=True)
                return result
            finally:
                self._windows.pop(key, None)

        # Harness nested calls use parent__N; speculative launches use
        # parent__spec_N and must not also be charged to eager execution.
        window = self._windows.get((ctx.run_step, parent_id))
        if window is None or window.ended is not None:
            return await handler(args)

        started = perf_counter()
        try:
            return await handler(args)
        finally:
            finished = perf_counter()
            cutoff = finished if window.ended is None else min(finished, window.ended)
            window.saved_ms += max(0.0, cutoff - started) * 1000
