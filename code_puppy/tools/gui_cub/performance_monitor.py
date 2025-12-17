"""Lightweight performance monitoring for GUI automation operations.

Provides telemetry for:
- Element tree traversal timing
- Fuzzy matching performance
- Cache hit/miss rates
- Overall operation profiling
"""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from rich.text import Text

from code_puppy.messaging import emit_info


@dataclass
class OperationMetrics:
    """Metrics for a single operation type."""

    operation: str
    count: int = 0
    total_time: float = 0.0
    min_time: float = float("inf")
    max_time: float = 0.0
    timings: list[float] = field(default_factory=list)

    @property
    def avg_time(self) -> float:
        """Average execution time in seconds."""
        return self.total_time / self.count if self.count > 0 else 0.0

    @property
    def avg_time_ms(self) -> float:
        """Average execution time in milliseconds."""
        return self.avg_time * 1000

    def record(self, elapsed: float) -> None:
        """Record a single timing measurement."""
        self.count += 1
        self.total_time += elapsed
        self.min_time = min(self.min_time, elapsed)
        self.max_time = max(self.max_time, elapsed)
        self.timings.append(elapsed)

        # Keep only last 100 timings to avoid memory bloat
        if len(self.timings) > 100:
            self.timings.pop(0)


class PerformanceMonitor:
    """Global performance monitor for GUI automation operations."""

    def __init__(self):
        self.metrics: dict[str, OperationMetrics] = defaultdict(
            lambda: OperationMetrics(operation="unknown")
        )
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.early_stops: int = 0
        self.full_searches: int = 0

    @contextmanager
    def measure(self, operation: str):
        """Context manager for measuring operation timing.

        Usage:
            with monitor.measure("element_tree_build"):
                elements = build_tree()
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            if operation not in self.metrics:
                self.metrics[operation] = OperationMetrics(operation=operation)
            self.metrics[operation].record(elapsed)

    def record_cache_hit(self) -> None:
        """Record a cache hit event."""
        self.cache_hits += 1

    def record_cache_miss(self) -> None:
        """Record a cache miss event."""
        self.cache_misses += 1

    def record_early_stop(self) -> None:
        """Record an early-stop search (confident match found)."""
        self.early_stops += 1

    def record_full_search(self) -> None:
        """Record a full exhaustive search."""
        self.full_searches += 1

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate (0.0 - 1.0)."""
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0

    @property
    def early_stop_rate(self) -> float:
        """Calculate early-stop rate (0.0 - 1.0)."""
        total = self.early_stops + self.full_searches
        return self.early_stops / total if total > 0 else 0.0

    def get_summary(self) -> dict[str, Any]:
        """Get performance summary as dictionary.

        Returns:
            Dictionary with timing stats and cache metrics
        """
        return {
            "operations": {
                op: {
                    "count": metrics.count,
                    "avg_ms": round(metrics.avg_time_ms, 2),
                    "min_ms": round(metrics.min_time * 1000, 2),
                    "max_ms": round(metrics.max_time * 1000, 2),
                }
                for op, metrics in self.metrics.items()
            },
            "cache": {
                "hits": self.cache_hits,
                "misses": self.cache_misses,
                "hit_rate": round(self.cache_hit_rate * 100, 1),
            },
            "search": {
                "early_stops": self.early_stops,
                "full_searches": self.full_searches,
                "early_stop_rate": round(self.early_stop_rate * 100, 1),
            },
        }

    def report(self, show_details: bool = True) -> None:
        """Print performance report to console.

        Args:
            show_details: Show detailed per-operation stats
        """
        emit_info(Text.from_markup("[bold cyan]\n=== Performance Report ===[/bold cyan]"))

        if show_details and self.metrics:
            emit_info(Text.from_markup("\n[bold]Operation Timings:[/bold]"))
            for op, metrics in sorted(self.metrics.items()):
                emit_info(
                    f"  {op:30s} "
                    f"n={metrics.count:3d}  "
                    f"avg={metrics.avg_time_ms:6.1f}ms  "
                    f"min={metrics.min_time * 1000:6.1f}ms  "
                    f"max={metrics.max_time * 1000:6.1f}ms"
                )

        # Cache stats
        total_cache_ops = self.cache_hits + self.cache_misses
        if total_cache_ops > 0:
            emit_info(Text.from_markup("\n[bold]Cache Performance:[/bold]"))
            emit_info(f"  Hits:      {self.cache_hits}")
            emit_info(f"  Misses:    {self.cache_misses}")
            emit_info(f"  Hit Rate:  {self.cache_hit_rate * 100:.1f}%")

        # Search optimization stats
        total_searches = self.early_stops + self.full_searches
        if total_searches > 0:
            emit_info(Text.from_markup("\n[bold]Search Optimization:[/bold]"))
            emit_info(f"  Early Stops:   {self.early_stops}")
            emit_info(f"  Full Searches: {self.full_searches}")
            emit_info(f"  Early Stop Rate: {self.early_stop_rate * 100:.1f}%")

        emit_info(Text.from_markup("[bold cyan]=========================\n[/bold cyan]"))

    def reset(self) -> None:
        """Reset all metrics."""
        self.metrics.clear()
        self.cache_hits = 0
        self.cache_misses = 0
        self.early_stops = 0
        self.full_searches = 0


# Global singleton instance
_global_monitor: PerformanceMonitor | None = None


def get_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance.

    Returns:
        Global PerformanceMonitor singleton
    """
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor


def reset_monitor() -> None:
    """Reset the global performance monitor."""
    global _global_monitor
    if _global_monitor:
        _global_monitor.reset()
