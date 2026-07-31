"""Session-wide spend accumulator for the cost_tracker plugin.

Fed by the ``agent_run_end`` callback with the *real billed* usage counts
that ``_runtime`` extracts from ``result.usage()`` (not the char-based
estimates used elsewhere for context-window math). Sub-agent runs fire
their own ``agent_run_end`` with their own usage, so summing every event
matches what the APIs actually bill - no double counting, because a
parent's usage never includes a sub-agent's own API calls.

State is process-lifetime ("since startup"): ``/clear`` wipes conversation
history but the money was still spent, so the meter keeps running.
``/cost reset`` zeroes it explicitly.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .pricing import ModelPricing, estimate_cost_usd, resolve_pricing


@dataclass
class ModelSpend:
    """Accumulated usage + estimated cost for one model-config name."""

    model_name: str
    runs: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: Optional[float] = None  # None => pricing unknown
    pricing: Optional[ModelPricing] = field(default=None, repr=False)


@dataclass(frozen=True)
class CostSnapshot:
    """Immutable view of the tracker for rendering."""

    total_cost_usd: float
    known_cost: bool  # True when at least one run had known pricing
    last_run_cost_usd: Optional[float]
    last_run_model: Optional[str]
    started_at: float
    per_model: Tuple[ModelSpend, ...]

    @property
    def unknown_models(self) -> List[ModelSpend]:
        return [m for m in self.per_model if m.cost_usd is None]


def _usage_int(metadata: Dict[str, Any], key: str) -> int:
    try:
        value = metadata.get(key)
        return max(int(value), 0) if value is not None else 0
    except (TypeError, ValueError):
        return 0


class SessionCostTracker:
    """Thread-safe accumulator; one instance per process (module singleton)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._per_model: Dict[str, ModelSpend] = {}
        self._pricing_cache: Dict[str, Tuple[Optional[ModelPricing], bool]] = {}
        self._last_run_cost: Optional[float] = None
        self._last_run_model: Optional[str] = None
        self._started_at = time.time()

    # -- recording ---------------------------------------------------------
    def record_run(self, model_name: str, metadata: Optional[Dict[str, Any]]) -> None:
        """Fold one finished agent run's billed usage into the totals.

        Never raises: cost tracking must not be able to break a run.
        """
        try:
            self._record_run(model_name, metadata)
        except Exception:  # pragma: no cover - defensive
            pass

    def _record_run(self, model_name: str, metadata: Optional[Dict[str, Any]]) -> None:
        if not model_name or not isinstance(metadata, dict):
            return
        input_tokens = _usage_int(metadata, "usage_input_tokens")
        output_tokens = _usage_int(metadata, "usage_output_tokens")
        cache_read = _usage_int(metadata, "usage_cached_read_tokens")
        cache_write = _usage_int(metadata, "usage_cached_write_tokens")
        if not any((input_tokens, output_tokens, cache_read, cache_write)):
            return  # cancelled/failed before any billing happened

        pricing, anthropic_style = self._get_pricing(model_name)
        run_cost: Optional[float] = None
        if pricing is not None:
            run_cost = estimate_cost_usd(
                pricing,
                input_tokens,
                output_tokens,
                cache_read,
                cache_write,
                anthropic_style=anthropic_style,
            )

        with self._lock:
            spend = self._per_model.setdefault(
                model_name, ModelSpend(model_name=model_name, pricing=pricing)
            )
            spend.runs += 1
            spend.input_tokens += input_tokens
            spend.output_tokens += output_tokens
            spend.cache_read_tokens += cache_read
            spend.cache_write_tokens += cache_write
            if run_cost is not None:
                spend.cost_usd = (spend.cost_usd or 0.0) + run_cost
                spend.pricing = pricing
            self._last_run_cost = run_cost
            self._last_run_model = model_name

    def _get_pricing(self, model_name: str) -> Tuple[Optional[ModelPricing], bool]:
        with self._lock:
            cached = self._pricing_cache.get(model_name)
        if cached is not None:
            return cached
        resolved = resolve_pricing(model_name)
        with self._lock:
            self._pricing_cache[model_name] = resolved
        return resolved

    # -- reading -----------------------------------------------------------
    def snapshot(self) -> CostSnapshot:
        with self._lock:
            per_model = tuple(
                ModelSpend(
                    model_name=m.model_name,
                    runs=m.runs,
                    input_tokens=m.input_tokens,
                    output_tokens=m.output_tokens,
                    cache_read_tokens=m.cache_read_tokens,
                    cache_write_tokens=m.cache_write_tokens,
                    cost_usd=m.cost_usd,
                    pricing=m.pricing,
                )
                for m in sorted(self._per_model.values(), key=lambda m: m.model_name)
            )
            total = sum(m.cost_usd or 0.0 for m in per_model)
            known = any(m.cost_usd is not None for m in per_model)
            return CostSnapshot(
                total_cost_usd=total,
                known_cost=known,
                last_run_cost_usd=self._last_run_cost,
                last_run_model=self._last_run_model,
                started_at=self._started_at,
                per_model=per_model,
            )

    def reset(self) -> None:
        with self._lock:
            self._per_model.clear()
            self._last_run_cost = None
            self._last_run_model = None
            self._started_at = time.time()
            # Pricing cache survives reset on purpose - prices don't change
            # mid-process, only the meter is being zeroed.


_TRACKER = SessionCostTracker()


def get_tracker() -> SessionCostTracker:
    return _TRACKER


def format_usd(value: Optional[float]) -> str:
    """Render a dollar amount with sane precision for tiny values."""
    if value is None:
        return "unknown"
    if value == 0:
        return "$0.00"
    if value < 0.01:
        return f"${value:.4f}"
    if value < 1:
        return f"${value:.3f}"
    return f"${value:,.2f}"


def format_tokens(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{value / 1_000:.0f}k"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)
