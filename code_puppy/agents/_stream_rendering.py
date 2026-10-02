"""Streaming render delivery via the pydantic-ai capability seam.

Historically the streaming pipeline reached pydantic-ai as a per-run
``event_stream_handler=`` kwarg: ``_runtime._do_run`` (main agent) and
``subagent_invocation`` (invoke_agent tool) each picked a handler, wrapped it
in a ``StreamingTextDetector``, and passed it to every ``run()`` call. This
module promotes that delivery to a first-class capability,
:class:`StreamRendering`, using pydantic-ai's ``wrap_run_event_stream`` seam
(via the stock ``ProcessEventStream`` observer, which tees events to the
handler while passing them through unchanged).

The seam is static but the state is per-run, so the two meet through a
context-local :class:`StreamObservation`:

* The **caller** (``_do_run`` / ``_invoke_agent``) installs an observation
  with :func:`stream_observation` around its ``run()`` calls. The observation
  carries the handler to drive, the observability ``group_id`` to capture,
  and whether streaming is enabled for this run sequence.
* The **capability** resolves the observation once per run in ``for_run``.
  With no observation (or streaming disabled) it resolves to an inert
  capability that does *not* override ``wrap_run_event_stream`` — pydantic-ai
  then keeps the run non-streamed, exactly as passing no handler did.
* ``streamed_text`` accumulates across every run under one observation
  (initial run + steer/hook follow-ups share the detector, as the old shared
  ``StreamingTextDetector`` instance did), so the caller's fallback-render
  decision after the loop is unchanged.

The observation rides a ``ContextVar``: ``asyncio.create_task`` snapshots the
context, so a sub-agent run launched as a task sees the observation installed
by its invoker, and a nested invocation's own observation shadows the outer
one only within that task.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability, ProcessEventStream

from code_puppy.agents._non_streaming_render import StreamingTextDetector


@dataclass
class StreamObservation:
    """Run-scoped streaming state shared between a caller and the capability.

    ``handler`` is the event-stream consumer to drive (the main renderer, the
    sub-agent silencer, ...). ``group_id``, when set, is captured into the
    observability context before the handler runs — mirroring the old
    ``_observed_event_stream_handler`` wrapper. ``enabled=False`` records the
    streaming gate: the capability resolves inert and the run stays
    non-streamed.
    """

    handler: Callable[..., Any]
    group_id: Optional[str] = None
    enabled: bool = True
    _detector: StreamingTextDetector = field(init=False, repr=False)

    def __post_init__(self) -> None:
        async def _observed(ctx: Any, events: Any) -> Any:
            if self.group_id is not None:
                from code_puppy.observability import capture_agent_context

                capture_agent_context(self.group_id)
            return await self.handler(ctx, events)

        self._detector = StreamingTextDetector(_observed)

    @property
    def streamed_text(self) -> bool:
        """Whether any run under this observation streamed visible text."""
        return self._detector.streamed_text

    @property
    def detector(self) -> StreamingTextDetector:
        """The detector-wrapped handler the capability delivers per run.

        Doubles as the ``should_render_fallback`` detector argument — the
        detector is both the event-stream consumer and the streamed-text
        flag-holder, exactly as it was under the per-run kwarg.
        """
        return self._detector


_current_observation: ContextVar[Optional[StreamObservation]] = ContextVar(
    "code_puppy_stream_observation", default=None
)


def current_stream_observation() -> Optional[StreamObservation]:
    """Return the observation installed for the current context, if any."""
    return _current_observation.get()


@contextmanager
def stream_observation(
    handler: Callable[..., Any],
    *,
    group_id: Optional[str] = None,
    enabled: bool = True,
) -> Iterator[StreamObservation]:
    """Install a fresh :class:`StreamObservation` for the enclosed run(s).

    Yields the observation so the caller can read ``streamed_text`` after the
    runs complete (the object stays valid past the ``with`` block; only the
    context-local registration is reverted).
    """
    observation = StreamObservation(handler=handler, group_id=group_id, enabled=enabled)
    token = _current_observation.set(observation)
    try:
        yield observation
    finally:
        _current_observation.reset(token)


# Shared inert resolution for gated-off runs. A plain ``AbstractCapability``
# does not override ``wrap_run_event_stream``, so pydantic-ai keeps the run
# non-streamed — byte-for-byte the old "no event_stream_handler" behaviour.
# Stateless, so one instance is safe to share across concurrent runs.
_INERT = AbstractCapability()


@dataclass
class StreamRendering(AbstractCapability[Any]):
    """Deliver the run's event-stream handler through the capability seam.

    Stateless at rest: everything per-run lives on the
    :class:`StreamObservation` resolved in :meth:`for_run`. Attaching this
    capability to an agent therefore does NOT force streaming on its own —
    only runs whose caller installed an enabled observation stream (pydantic-ai
    checks ``has_wrap_run_event_stream`` on the *resolved* run capability).
    """

    async def for_run(self, ctx: RunContext[Any]) -> AbstractCapability[Any]:
        observation = current_stream_observation()
        if observation is None or not observation.enabled:
            return _INERT
        # ``ProcessEventStream`` (observer form) tees each node's events to
        # the handler while passing them through unchanged — the same view the
        # old per-run ``event_stream_handler`` kwarg consumed, with delivery
        # back-pressure preserved (a paused handler stalls the stream).
        return ProcessEventStream(observation.detector)

    @classmethod
    def get_serialization_name(cls) -> Optional[str]:
        # Resolution depends on ambient context-local state; a spec cannot
        # meaningfully reconstruct it.
        return None


__all__ = [
    "StreamObservation",
    "StreamRendering",
    "current_stream_observation",
    "stream_observation",
]
