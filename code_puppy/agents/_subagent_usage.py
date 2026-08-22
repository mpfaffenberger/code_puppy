"""Per-request usage capture for sub-agent invocations, as a capability.

``invoke_agent_with_model`` reports token usage per model request
(``per_request_usage``) and the final request's context size
(``final_context_tokens``). Previously both were derived after the run by
walking ``result.new_messages()`` for ``ModelResponse`` objects. This module
moves the *observation* to pydantic-ai's ``after_model_request`` capability
seam: each response is recorded at the exact moment the run appends it to
state, and the recorded sequence is handed back to the invocation layer at
the run boundary.

Parity is guaranteed structurally rather than promised:

* ``after_model_request`` receives the IDENTICAL ``ModelResponse`` object
  that ``_finish_handling`` appends to run state (verified against
  pydantic-ai 2.31.0 source and empirically for both streamed and
  non-streamed requests), so the captured objects are the same objects an
  eager ``new_messages()`` walk would visit.
* ``consume()`` is read-and-clear and double-gated. The identity gate
  (``captured result is result``) rejects stale captures from failed
  earlier attempts (streaming-retry re-entry) and guest wrappers that
  bypass capabilities. The consistency gate rejects captures whose
  response sequence no longer matches the result's recorded
  ``ModelResponse`` objects -- mid-run compaction may summarize away a
  long run's own earlier responses, and the old ``new_messages()`` walk
  never saw those.
* Every rejection converges on the caller's eager fallback, which feeds
  the exact same extraction helpers (``extract_per_request_usage`` /
  ``extract_final_context_tokens``) -- so both paths are byte-identical.

Scope: the run-total ``usage_metrics`` (``result.usage``) and the
wall-clock ``duration_ms`` deliberately stay at the call site. The timing
spans streaming-retry attempts -- multiple ``agent.run()`` calls -- so it
cannot live inside a per-run capability with parity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ModelResponse


@dataclass
class PerRequestUsageCapture(AbstractCapability[Any]):
    """Capture each run's ``ModelResponse`` objects at the seam.

    One instance is constructed per sub-agent invocation. ``for_run``
    hands each ``agent.run()`` a fresh collector so responses never leak
    across streaming-retry attempts; the collector stows its capture in
    this instance's one-slot buffer at ``after_run``, which only fires for
    runs that produced a result.
    """

    # One-slot last-capture buffer: [(result, responses)]. A list (not an
    # Optional field) so per-run collectors can share it by reference.
    _capture: List[Tuple[Any, Tuple[ModelResponse, ...]]] = field(
        default_factory=list, init=False, repr=False
    )

    async def for_run(self, ctx: Any) -> AbstractCapability[Any]:
        return _PerRequestUsageRun(capture_slot=self._capture)

    def consume(self, result: Any) -> Optional[Sequence[ModelResponse]]:
        """Return the owned capture for ``result``, or ``None`` to fall back.

        Read-and-clear: stale captures are discarded on the way out so a
        later invocation can never inherit them. ``None`` means the caller
        must derive usage eagerly from ``result.new_messages()`` -- the
        pre-capability behavior.
        """
        if not self._capture:
            return None
        captured_result, responses = self._capture[0]
        self._capture.clear()
        if captured_result is not result:
            return None

        # Consistency gate: the capture is authoritative only while it
        # matches the responses the result actually recorded. Guarded so a
        # result whose ``new_messages()`` raises fails over to the eager
        # path, preserving the old call-site failure mode.
        try:
            recorded = [
                message
                for message in result.new_messages()
                if isinstance(message, ModelResponse)
            ]
        except Exception:
            return None
        if len(recorded) != len(responses):
            return None
        if any(seen is not kept for seen, kept in zip(responses, recorded)):
            return None
        return list(responses)


@dataclass
class _PerRequestUsageRun(AbstractCapability[Any]):
    """Run-scoped collector resolved by ``PerRequestUsageCapture.for_run``."""

    capture_slot: List[Tuple[Any, Tuple[ModelResponse, ...]]]
    _responses: List[ModelResponse] = field(
        default_factory=list, init=False, repr=False
    )

    async def after_model_request(
        self, ctx: Any, *, request_context: Any, response: ModelResponse
    ) -> ModelResponse:
        self._responses.append(response)
        return response

    async def after_run(self, ctx: Any, *, result: Any) -> Any:
        self.capture_slot[:] = [(result, tuple(self._responses))]
        return result


def build_per_request_usage_capture(
    include_usage_metrics: bool,
) -> Tuple[Optional[PerRequestUsageCapture], List[PerRequestUsageCapture]]:
    """Build the capture for one invocation, or nothing when metrics are off.

    Returns ``(capture, splice)`` so the call site can keep a handle for
    ``consume()`` while splicing the capability into ``capabilities=[...]``
    unconditionally (mirroring ``build_tool_output_limits``).
    """
    if not include_usage_metrics:
        return None, []
    capture = PerRequestUsageCapture()
    return capture, [capture]


__all__ = [
    "PerRequestUsageCapture",
    "build_per_request_usage_capture",
]
