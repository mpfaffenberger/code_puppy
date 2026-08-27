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
  ``CompactionFailed``) dispatch at their stream position.

Listeners must never break the run: every handler is fail-open.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from pydantic_ai.capabilities import AbstractCapability, on_event
from pydantic_ai.tools import RunContext

from code_puppy.capabilities.compaction import (
    BeforeCompactionEvent,
    CompactionCompletedEvent,
    CompactionFailedEvent,
    ContextUsageMeasuredEvent,
    HistoryProcessingCompletedEvent,
    HistoryProcessingStartedEvent,
)

logger = logging.getLogger(__name__)


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
