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

from rich.text import Text

from code_puppy.capabilities.eager_timing import EagerExecutionCompletedEvent
from code_puppy.i18n import ngettext, t
from code_puppy.messaging.theme_accent import agent_accent

logger = logging.getLogger(__name__)
# Palette slots only (bright_black etc.) so /theme recolors the row via OSC 4.
_MUTED = "bright_black"
_SEP = " \u00b7 "
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

    def render(self) -> Text:
        """One styled row: counts light up only when non-zero, one headline total."""
        with self._lock:
            hits, misses, wasted = self.hits, self.misses, self.wasted
            spec_ms, eager_ms = self.saved_ms, self.eager_saved_ms
        total = _seconds(spec_ms + eager_ms)
        row = Text()
        row.append(t("speculation.label"), style=f"bold {agent_accent()}")
        row.append("  ")
        row.append(
            ngettext("speculation.hits", hits), style=_count(hits, "bright_green")
        )
        row.append(_SEP, style=_MUTED)
        row.append(
            ngettext("speculation.misses", misses), style=_count(misses, "yellow")
        )
        row.append(_SEP, style=_MUTED)
        row.append(ngettext("speculation.wasted", wasted), style=_count(wasted, "red"))
        row.append("    ")
        row.append(
            t("speculation.saved", seconds=total),
            style="bold bright_green" if total != "0.0" else _MUTED,
        )
        row.append("   ")
        row.append(
            t(
                "speculation.breakdown",
                speculative_seconds=_seconds(spec_ms),
                eager_seconds=_seconds(eager_ms),
            ),
            style=_MUTED,
        )
        return row


def _seconds(ms: float) -> str:
    """Round down so the displayed total stays a lower bound."""
    return f"{ms // 100 / 10:.1f}"


def _count(value: int, color: str) -> str:
    return f"bold {color}" if value else _MUTED


_stats = SpeculationStats()


def get_speculation_stats() -> SpeculationStats:
    return _stats


def get_speculation_status() -> Text | None:
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
