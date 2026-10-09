"""Cancellation trace-context capture as a pydantic-ai capability.

``emit_cancellation`` (``code_puppy/observability.py``) links the
"Agent run cancelled" Logfire warning to the run's live trace by attaching
the context captured during the run's most recent streamed model request.
Previously ``_runtime._do_run`` smuggled that capture into an
``_observed_event_stream_handler`` closure wrapped around the run's
``event_stream_handler``. This module promotes the capture to a
first-class capability on pydantic-ai's ``wrap_run_event_stream`` seam.

Parity notes:

- The capture fires once per streamed node event stream, when the
  consumer first pulls the wrapped stream -- in the same task, and
  therefore the same OTel context, in which the run's
  ``event_stream_handler`` is invoked -- so ``logfire.get_context()``
  observes the identical value the eager wrapper captured. The eager
  wrapper captured at handler *invocation*; a handler that defers (or
  skips) iterating its events defers (or skips) the capture here. The
  production handler (``StreamingTextDetector`` wrapping the render
  handler) consumes immediately, so the two moments coincide in
  practice.
- The streaming gate is preserved. ``CancellationTraceCapture`` itself
  does NOT override ``wrap_run_event_stream``; only the per-run resolved
  ``_ActiveCancellationTraceCapture`` does. When no observation is
  installed (direct ``pydantic_agent.run()`` calls outside
  ``run_with_mcp``) or the observation is disabled (streaming gate off),
  ``for_run`` returns ``self``, pydantic-ai does not force the run into
  streaming mode, and no capture happens -- byte-identical to the eager
  wrapper only existing when ``get_enable_streaming()`` was true.
- ``clear_agent_context`` (turn-end custody in the task-body ``finally``)
  and ``emit_cancellation`` (the await-site ``except*`` handlers via
  ``on_agent_run_cancel``) stay eager: both run outside the run boundary,
  where no capability seam fires -- a cancelled run never reaches
  ``after_run``, and the ``CancelledError`` delivered inside the run
  carries no usable snapshot at the ``wrap_run`` seam.

The observation is installed with a plain ``ContextVar.set`` and never
reset: ``_do_run`` executes inside the turn's agent task, whose context
dies with the task, and nested ``run_with_mcp`` turns run in their own
task where their own install shadows the snapshot inherited at
``create_task`` time.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, AsyncIterable, Callable, Optional

from pydantic_ai.capabilities import AbstractCapability

__all__ = [
    "CancellationTraceCapture",
    "CancellationTraceObservation",
    "current_cancellation_trace_observation",
    "install_cancellation_trace_observation",
]


@dataclass(frozen=True)
class CancellationTraceObservation:
    """One turn's capture parameters, installed by ``_runtime._do_run``.

    ``capture`` is an injectable seam for tests; ``None`` resolves to
    ``code_puppy.observability.capture_agent_context`` at call time so
    monkeypatching the observability module keeps intercepting.
    """

    group_id: str
    enabled: bool
    capture: Optional[Callable[[str], None]] = None


_observation_var: ContextVar[Optional[CancellationTraceObservation]] = ContextVar(
    "cancellation_trace_observation", default=None
)


def install_cancellation_trace_observation(
    observation: Optional[CancellationTraceObservation],
) -> None:
    """Advertise ``observation`` to ``CancellationTraceCapture.for_run``.

    ``None`` shadows any inherited observation (nested-context hygiene --
    an explicit "no capture here" must not fall through to an outer
    turn's group id).
    """
    _observation_var.set(observation)


def current_cancellation_trace_observation() -> Optional[CancellationTraceObservation]:
    """Return the observation visible in the current context, if any."""
    return _observation_var.get()


def _resolve_capture(
    observation: CancellationTraceObservation,
) -> Callable[[str], None]:
    if observation.capture is not None:
        return observation.capture
    # Late binding: resolved through the module attribute at call time so
    # test patches on ``code_puppy.observability`` apply.
    from code_puppy import observability

    return observability.capture_agent_context


@dataclass
class _ActiveCancellationTraceCapture(AbstractCapability[Any]):
    """Per-run resolved form: pass events through, capture trace context.

    Overriding ``wrap_run_event_stream`` here (and only here) keeps the
    force-streaming side effect of the seam confined to runs whose
    observation is enabled -- exactly the runs that already stream.
    """

    observation: CancellationTraceObservation

    async def wrap_run_event_stream(
        self,
        ctx: Any,
        *,
        stream: AsyncIterable[Any],
    ) -> AsyncIterable[Any]:
        _resolve_capture(self.observation)(self.observation.group_id)
        try:
            async for event in stream:
                yield event
        finally:
            # Mirror AbstractCapability.wrap_run_event_stream's base
            # implementation: propagate closure to the wrapped stream.
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                await aclose()


@dataclass
class CancellationTraceCapture(AbstractCapability[Any]):
    """Static entry registered in the builder's ``capabilities=[...]``.

    Stateless; resolves the turn's observation once per run.
    """

    async def for_run(self, ctx: Any) -> AbstractCapability[Any]:
        observation = current_cancellation_trace_observation()
        if observation is None or not observation.enabled:
            # No seam override on this class, so returning ``self`` keeps
            # the run genuinely non-streamed (no forced streaming mode).
            return self
        return _ActiveCancellationTraceCapture(observation=observation)
