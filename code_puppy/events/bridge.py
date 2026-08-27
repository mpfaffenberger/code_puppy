"""The Code Puppy capability-event bridge.

One capability, wired LAST in every ``capabilities=[...]`` block, that
subscribes to the typed event families emitted by the pure capabilities
in ``code_puppy.capabilities`` and translates them into Code Puppy's
application surfaces:

* legacy ``code_puppy.callbacks`` phases (plugin + hook-engine API),
* spinner/status updates,
* user-facing messaging.

This is deliberately the *only* module that knows both worlds. The
capabilities never import Code Puppy; Code Puppy consumes their events
here without reaching into capability internals. Upstreaming a
capability to pydantic-ai-harness only changes an import line here.

Dispatch semantics (pydantic-ai #7794):

* Inline events (``HistoryProcessingStarted/Completed``,
  ``BeforeCompaction``) reach these listeners synchronously, before the
  emitting operation proceeds — so legacy callback timing is preserved
  and ``BeforeCompaction`` can be cancelled by a hook decision.
* Stream events (``ContextUsageMeasured``, ``CompactionCompleted``,
  ``CompactionFailed``, and the ``code_mode.*`` speculation family from
  pydantic-ai-harness#699) dispatch at their stream position.

Listeners must never break the run: every handler is fail-open.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from pydantic_ai.capabilities import AbstractCapability, on_event
from pydantic_ai.tools import RunContext

from pydantic_ai_harness.code_mode import (
    SpeculativeCallClaimedEvent,
    SpeculativeCallEvictedEvent,
    SpeculativeCallLaunchedEvent,
    SpeculativeCallMissedEvent,
    SpeculativeCallSettledEvent,
)

from code_puppy.capabilities.compaction import (
    BeforeCompactionEvent,
    CompactionCompletedEvent,
    CompactionFailedEvent,
    ContextUsageMeasuredEvent,
    HistoryProcessingCompletedEvent,
    HistoryProcessingStartedEvent,
)

logger = logging.getLogger(__name__)


def _preview_arguments(arguments: dict, limit: int = 60) -> str:
    """Render launch arguments compactly for a one-line message."""
    rendered = ", ".join(f"{key}={value!r}" for key, value in arguments.items())
    return rendered if len(rendered) <= limit else rendered[: limit - 1] + "\u2026"


@dataclass
class CapabilityEventBridge(AbstractCapability[Any]):
    """Translates typed capability events into Code Puppy behavior."""

    agent: Optional[Any] = None
    """The owning Code Puppy agent, when available. Used only to enrich
    legacy callback payloads (live history snapshots); listeners degrade
    gracefully without it."""

    # ------------------------------------------------------------------
    # compaction.* family
    # ------------------------------------------------------------------

    @on_event(HistoryProcessingStartedEvent)
    async def _history_processing_started(
        self, ctx: RunContext[Any], event: HistoryProcessingStartedEvent
    ) -> None:
        try:
            from code_puppy.callbacks import on_message_history_processor_start

            on_message_history_processor_start(
                agent_name=event.agent_name,
                session_id=event.session_id,
                message_history=self._history_snapshot(),
                incoming_messages=[],
            )
        except Exception:  # pragma: no cover - observation must not break runs
            logger.exception("history-processing-start bridge listener failed")

    @on_event(HistoryProcessingCompletedEvent)
    async def _history_processing_completed(
        self, ctx: RunContext[Any], event: HistoryProcessingCompletedEvent
    ) -> None:
        try:
            from code_puppy.callbacks import on_message_history_processor_end

            on_message_history_processor_end(
                agent_name=event.agent_name,
                session_id=event.session_id,
                message_history=self._history_snapshot(),
                messages_added=event.messages_added,
                messages_filtered=event.messages_filtered,
            )
        except Exception:  # pragma: no cover
            logger.exception("history-processing-end bridge listener failed")

    @on_event(ContextUsageMeasuredEvent)
    async def _context_usage_measured(
        self, ctx: RunContext[Any], event: ContextUsageMeasuredEvent
    ) -> None:
        try:
            # Late-bound through the module so plugins that patch
            # ``_compaction.update_spinner_context`` (context-indicator)
            # keep intercepting status updates during the bridge era.
            from code_puppy.agents import _compaction
            from code_puppy.messaging.spinner import format_context_info

            _compaction.update_spinner_context(
                format_context_info(
                    event.total_tokens,
                    event.model_max_tokens,
                    event.proportion_used,
                )
            )
        except Exception:  # pragma: no cover
            logger.exception("context-usage bridge listener failed")

    @on_event(BeforeCompactionEvent)
    async def _before_compaction(
        self, ctx: RunContext[Any], event: BeforeCompactionEvent
    ) -> None:
        try:
            from code_puppy.callbacks import on_pre_compact

            # Advisory today (parity with the historical on_pre_compact
            # call); a future hook-engine decision can call event.cancel().
            await on_pre_compact(
                event.agent_name or "unknown",
                event.strategy,
                event.message_count,
                event.total_tokens,
            )
        except Exception:  # pragma: no cover
            logger.exception("pre-compact bridge listener failed")

    @on_event(CompactionCompletedEvent)
    async def _compaction_completed(
        self, ctx: RunContext[Any], event: CompactionCompletedEvent
    ) -> None:
        if not event.forced:
            return
        try:
            from code_puppy.messaging import emit_success

            detail = "" if event.dropped_count else " History was already minimal."
            emit_success(f"Mid-run compaction complete.{detail}")
        except Exception:  # pragma: no cover
            logger.exception("compaction-completed bridge listener failed")

    @on_event(CompactionFailedEvent)
    async def _compaction_failed(
        self, ctx: RunContext[Any], event: CompactionFailedEvent
    ) -> None:
        try:
            from code_puppy.messaging import emit_error

            emit_error(f"Compaction failed: [{event.error_type}] {event.error_message}")
        except Exception:  # pragma: no cover
            logger.exception("compaction-failed bridge listener failed")

    # ------------------------------------------------------------------
    # code_mode.* family (speculative execution, harness#699)
    # ------------------------------------------------------------------
    # `SpeculativeCodeUpdateEvent` is deliberately not rendered here: it
    # mirrors the model's delta cadence (one event per streamed chunk) and
    # exists for the live SpeculationPanel, which consumes it straight
    # from the run's event stream. The one-liners below are the fallback
    # surface for contexts where no panel cycle owns the terminal (headless
    # runs, events flushed after a retry); while a cycle is active the
    # panel renders the same transitions and these listeners stay silent.

    @staticmethod
    def _panel_owns_the_stream() -> bool:
        from code_puppy.messaging.speculation_panel import get_speculation_panel

        return get_speculation_panel().active

    @on_event(SpeculativeCallLaunchedEvent)
    async def _speculative_launched(
        self, ctx: RunContext[Any], event: SpeculativeCallLaunchedEvent
    ) -> None:
        try:
            if self._panel_owns_the_stream():
                return
            from code_puppy.messaging import emit_info

            lines = (
                f"L{event.line_start}"
                if event.line_start == event.line_end
                else f"L{event.line_start}-{event.line_end}"
            )
            emit_info(
                f"\u26a1 speculating {event.sandbox_function}"
                f"({_preview_arguments(event.arguments)}) \u00b7 {lines}, "
                "model still writing"
            )
        except Exception:  # pragma: no cover - observation must not break runs
            logger.exception("speculative-launch bridge listener failed")

    @on_event(SpeculativeCallSettledEvent)
    async def _speculative_settled(
        self, ctx: RunContext[Any], event: SpeculativeCallSettledEvent
    ) -> None:
        try:
            if self._panel_owns_the_stream():
                return
            from code_puppy.messaging import emit_info

            if event.outcome == "ready":
                emit_info(
                    f"\u26a1 {event.launch_id.rsplit('__', 1)[-1]} ready in "
                    f"{event.elapsed_ms:.0f}ms, before the snippet finished streaming"
                )
            else:
                emit_info(
                    f"\u26a1 speculative call failed after {event.elapsed_ms:.0f}ms; "
                    "the error surfaces when the snippet asks for it"
                )
        except Exception:  # pragma: no cover
            logger.exception("speculative-settle bridge listener failed")

    @on_event(SpeculativeCallClaimedEvent)
    async def _speculative_claimed(
        self, ctx: RunContext[Any], event: SpeculativeCallClaimedEvent
    ) -> None:
        try:
            if self._panel_owns_the_stream():
                return
            from code_puppy.messaging import emit_success

            waited = (
                "result was already waiting"
                if event.ready_at_claim
                else "claimed mid-flight"
            )
            emit_success(
                f"\U0001f3af speculation hit: {event.wrapped_tool_name} ran "
                f"{event.elapsed_ms:.0f}ms during generation ({waited})"
            )
        except Exception:  # pragma: no cover
            logger.exception("speculative-claim bridge listener failed")

    @on_event(SpeculativeCallMissedEvent)
    async def _speculative_missed(
        self, ctx: RunContext[Any], event: SpeculativeCallMissedEvent
    ) -> None:
        try:
            if self._panel_owns_the_stream():
                return
            from code_puppy.messaging import emit_info

            emit_info(
                f"\u2744\ufe0f speculation miss: {event.wrapped_tool_name} runs cold"
            )
        except Exception:  # pragma: no cover
            logger.exception("speculative-miss bridge listener failed")

    @on_event(SpeculativeCallEvictedEvent)
    async def _speculative_evicted(
        self, ctx: RunContext[Any], event: SpeculativeCallEvictedEvent
    ) -> None:
        try:
            if self._panel_owns_the_stream():
                return
            from code_puppy.messaging import emit_info

            emit_info(
                f"\U0001f5d1\ufe0f speculation wasted: {event.wrapped_tool_name} "
                f"({event.state}) was never claimed"
            )
        except Exception:  # pragma: no cover
            logger.exception("speculative-evict bridge listener failed")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _history_snapshot(self) -> list:
        if self.agent is None:
            return []
        try:
            return list(getattr(self.agent, "_message_history", []) or [])
        except Exception:  # pragma: no cover
            return []

    @classmethod
    def get_serialization_name(cls) -> Optional[str]:
        """Not spec-serializable: may hold a live agent reference."""
        return None
