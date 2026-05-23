"""Token usage calculation for the current agent's context window.

Kept separate from ``register_callbacks.py`` so this stays unit-testable in
isolation and so callbacks file remains thin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Thresholds (fractions of context window). Match the visual indicator buckets:
#   <30% green, 30–<60% yellow, ≥60% red.
# Boundaries are exclusive on the upper end: e.g. exactly 0.30 → yellow,
# exactly 0.60 → red. Keep ``_format_usage_report`` legend in sync.
GREEN_THRESHOLD = 0.30
YELLOW_THRESHOLD = 0.60

GREEN_CIRCLE = "🟢"
YELLOW_CIRCLE = "🟡"
RED_CIRCLE = "🔴"


@dataclass(frozen=True)
class ContextUsage:
    """Snapshot of how full the current agent's context window is."""

    used_tokens: int
    overhead_tokens: int
    capacity: int

    @property
    def total_tokens(self) -> int:
        return self.used_tokens + self.overhead_tokens

    @property
    def proportion(self) -> float:
        if self.capacity <= 0:
            return 0.0
        return self.total_tokens / self.capacity

    @property
    def percent(self) -> float:
        return self.proportion * 100.0

    @property
    def indicator(self) -> str:
        return pick_indicator(self.proportion)


def pick_indicator(proportion: float) -> str:
    """Pick the colored-circle emoji for a given usage proportion (0..1)."""
    if proportion < GREEN_THRESHOLD:
        return GREEN_CIRCLE
    if proportion < YELLOW_THRESHOLD:
        return YELLOW_CIRCLE
    return RED_CIRCLE


def get_current_usage() -> Optional[ContextUsage]:
    """Compute current context-window usage for the active agent.

    Returns ``None`` whenever any required piece of data is unavailable —
    missing agent, missing model config, or *any* exception while estimating
    history/used/overhead/capacity. We deliberately do **not** fall back to
    zero on partial failures: a misleading 🟢 indicator is worse than no
    indicator at all (the prompt simply hides the badge).
    """
    try:
        from code_puppy.agents.agent_manager import get_current_agent
    except Exception:
        return None

    try:
        agent = get_current_agent()
    except Exception:
        return None
    if agent is None:
        return None

    try:
        history = agent.get_message_history() or []
        used = sum(agent.estimate_tokens_for_message(m) for m in history)
        overhead = agent._estimate_context_overhead()
        capacity = agent._get_model_context_length()
    except Exception:
        return None

    if capacity <= 0:
        return None

    return ContextUsage(
        used_tokens=int(used),
        overhead_tokens=int(overhead),
        capacity=int(capacity),
    )
