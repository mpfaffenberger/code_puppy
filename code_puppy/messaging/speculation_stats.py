"""Session speculation counters for the pinned status row, without transcript output."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from pydantic_ai.messages import AgentStreamEvent
from pydantic_ai_harness.code_mode import (
    SpeculativeCallClaimedEvent,
    SpeculativeCallEvictedEvent,
    SpeculativeCallLaunchedEvent,
    SpeculativeCallMissedEvent,
    SpeculativeCallSettledEvent,
    SpeculativeCodeUpdateEvent,
)

from code_puppy.capabilities.eager_timing import EagerExecutionCompletedEvent
from code_puppy.i18n import t

logger = logging.getLogger(__name__)
_SPECULATION_EVENTS = (
    EagerExecutionCompletedEvent,
    SpeculativeCallClaimedEvent,
    SpeculativeCallEvictedEvent,
    SpeculativeCallLaunchedEvent,
    SpeculativeCallMissedEvent,
    SpeculativeCallSettledEvent,
    SpeculativeCodeUpdateEvent,
)


@dataclass(kw_only=True)
class SpeculationStats:
    """Accumulate outcomes across snippets and turns in this terminal session."""

    hits: int = 0
    misses: int = 0
    wasted: int = 0
    saved_ms: float = 0.0
    eager_saved_ms: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def handle_event(self, event: AgentStreamEvent) -> bool:
        """Consume telemetry without retaining generated code or rendering a box."""
        if not isinstance(event, _SPECULATION_EVENTS):
            return False
        with self._lock:
            if isinstance(event, EagerExecutionCompletedEvent):
                self.eager_saved_ms += max(0.0, event.saved_ms)
            elif isinstance(event, SpeculativeCallClaimedEvent):
                self.hits += 1
                # Partial claims lack claim timestamps. Count only fully hidden
                # calls, a lower bound on summed latency, not wall-clock savings.
                if event.ready_at_claim:
                    self.saved_ms += max(0.0, event.elapsed_ms)
            elif isinstance(event, SpeculativeCallMissedEvent):
                self.misses += 1
            elif isinstance(event, SpeculativeCallEvictedEvent):
                self.wasted += 1
        return True

    def render(self) -> str:
        """Round hidden-latency totals down to preserve their lower bounds."""
        with self._lock:
            return t(
                "speculation.status",
                hits=self.hits,
                misses=self.misses,
                wasted=self.wasted,
                speculative_seconds=f"{self.saved_ms // 100 / 10:.1f}",
                eager_seconds=f"{self.eager_saved_ms // 100 / 10:.1f}",
            )


_stats = SpeculationStats()


def get_speculation_stats() -> SpeculationStats:
    return _stats


def get_speculation_status() -> str | None:
    """Return chrome only for the currently selected Speculative Puppy agent."""
    try:
        from code_puppy.agents.agent_manager import get_current_agent_name

        if get_current_agent_name() == "speculative-puppy":
            return _stats.render()
    except Exception:
        logger.debug("could not read speculation status", exc_info=True)
    return None


def refresh_speculation_status() -> None:
    """Synchronize pinned chrome at prompt boundaries, including agent switches."""
    try:
        from code_puppy.messaging.bottom_bar import get_bottom_bar

        get_bottom_bar().set_speculation_status(get_speculation_status())
    except Exception:
        logger.debug("could not refresh speculation status", exc_info=True)
