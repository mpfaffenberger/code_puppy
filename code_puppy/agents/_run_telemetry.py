"""Run-end telemetry captured at the pydantic-ai run boundary.

Promotes the ``agent_run_end`` payload extraction — human-readable response
text plus usage token metadata — from eager post-``await`` bookkeeping in
``_runtime.run_with_mcp`` to a first-class capability on pydantic-ai's
``after_run`` seam (its first claim in this codebase).

Semantics, verified against pydantic-ai 2.31.0:

* ``after_run`` fires once per successful ``Agent.run()`` and receives the
  **identical** ``AgentRunResult`` object the caller gets back — including
  when the capability rides inside a ``CombinedCapability``. A turn may
  contain several runs (the initial call plus queued-steer / hook-retry
  follow-ups); each capture overwrites the last, so the surviving snapshot
  always describes the run whose result ``run_with_mcp`` ultimately returns.
* ``after_run`` is NOT called when a run ends without a result, so failed or
  cancelled turns never capture — matching the eager code, which only
  extracted after a successful ``await``.

Custody handshake (the explicit-when-ours, fallback-for-guests split):
``run_with_mcp`` calls :meth:`RunTelemetry.consume` with the result it is
about to report. ``consume`` hands back the captured telemetry only when the
captured result **is** that exact object; anything else (a guest wrapper
that bypassed capabilities, a ``None`` result from a swallowed
``UsageLimitExceeded``, a stale capture from an earlier turn whose task
failed before consuming) falls through to the eager extraction helpers
below — which are the same functions the capability itself uses, so both
paths produce byte-identical payloads.

The capability holds no live agent references and needs no constructor
arguments, so it keeps the inherited ``get_serialization_name`` default and
stays spec-constructible; a fresh instance simply hasn't captured anything
yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from pydantic_ai.capabilities import AbstractCapability

# One entry per usage figure forwarded to ``agent_run_end`` consumers (e.g.
# run-stats calibration, the kennel, token tracking plugins).
_USAGE_KEYS = (
    "usage_input_tokens",
    "usage_output_tokens",
    "usage_total_tokens",
    "usage_cached_read_tokens",
    "usage_cached_write_tokens",
    "usage_thought_tokens",
)


def empty_usage_metadata() -> dict[str, int | None]:
    """Fresh all-``None`` usage dict (each caller gets its own to mutate)."""
    return {key: None for key in _USAGE_KEYS}


def extract_response_text(result: Any) -> str:
    """Best-effort extraction of human-readable text from a pydantic-ai result."""
    if result is None:
        return ""
    if hasattr(result, "data"):
        return str(result.data) if result.data else ""
    if hasattr(result, "output"):
        return str(result.output) if result.output else ""
    return str(result)


def extract_usage_metadata(result: Any) -> dict[str, int | None]:
    """Best-effort usage-token extraction; all-``None`` dict on any failure."""
    try:
        # Property access (not a call): `result.usage()` is a deprecated
        # callable-property since pydantic-ai 1.107 and warns when called.
        usage = result.usage

        def _pick_usage_int(*names: str) -> int | None:
            for name in names:
                value = getattr(usage, name, None)
                if value is not None:
                    return int(value) or None
            return None

        return {
            "usage_input_tokens": _pick_usage_int(
                "input_tokens", "request_tokens", "prompt_tokens"
            ),
            # Real billed output tokens -- calibrates the run-stats TG
            # estimate (see run_stats.snapshot_cycle_into_aggregates).
            "usage_output_tokens": _pick_usage_int(
                "output_tokens", "response_tokens", "completion_tokens"
            ),
            "usage_total_tokens": _pick_usage_int("total_tokens"),
            "usage_cached_read_tokens": _pick_usage_int(
                "cache_read_tokens", "cached_read_tokens"
            ),
            "usage_cached_write_tokens": _pick_usage_int(
                "cache_write_tokens", "cached_write_tokens"
            ),
            "usage_thought_tokens": _pick_usage_int(
                "thinking_tokens", "thought_tokens", "reasoning_tokens"
            ),
        }
    except Exception:
        return empty_usage_metadata()


@dataclass
class RunTelemetry(AbstractCapability[Any]):
    """Capture ``agent_run_end`` telemetry at the run boundary.

    Instance state is a single last-capture slot: ``(result, text, usage)``.
    The result reference anchors the identity check in :meth:`consume`; it is
    released on every consume, so nothing outlives the turn that reads it.
    """

    _captured: Optional[Tuple[Any, str, dict[str, int | None]]] = field(
        default=None, init=False, repr=False, compare=False
    )

    async def after_run(self, ctx: Any, *, result: Any) -> Any:
        self._captured = (
            result,
            extract_response_text(result),
            extract_usage_metadata(result),
        )
        return result

    def consume(self, result: Any) -> Optional[Tuple[str, dict[str, int | None]]]:
        """Return ``(response_text, usage_metadata)`` captured for ``result``.

        Read-and-clear. ``None`` (caller must fall back to eager extraction)
        unless the last captured result is *identical* to ``result`` — the
        identity check is what makes stale captures from earlier turns, guest
        wrappers that bypass capabilities, and ``None`` results all converge
        on the fallback path instead of reporting the wrong run's telemetry.
        """
        captured, self._captured = self._captured, None
        if captured is not None and result is not None and captured[0] is result:
            return captured[1], captured[2]
        return None
