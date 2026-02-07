"""Comprehensive test suite for GUI-Cub performance monitoring."""

import time

import pytest

from code_puppy.tools.gui_cub.performance_monitor import (
    OperationMetrics,
    PerformanceMonitor,
    get_monitor,
    reset_monitor,
)


class TestOperationMetrics:
    """Test OperationMetrics dataclass."""

    def test_initialization(self):
        """Test metrics initialization."""
        metrics = OperationMetrics(operation="test_op")

        assert metrics.operation == "test_op"
        assert metrics.count == 0
        assert metrics.total_time == 0.0
        assert metrics.min_time == float("inf")
        assert metrics.max_time == 0.0
        assert len(metrics.timings) == 0

    def test_record_single_timing(self):
        """Test recording single timing."""
        metrics = OperationMetrics(operation="test_op")
        metrics.record(0.123)

        assert metrics.count == 1
        assert metrics.total_time == 0.123
        assert metrics.min_time == 0.123
        assert metrics.max_time == 0.123
        assert len(metrics.timings) == 1

    def test_record_multiple_timings(self):
        """Test recording multiple timings."""
        metrics = OperationMetrics(operation="test_op")
        metrics.record(0.1)
        metrics.record(0.2)
        metrics.record(0.05)
        metrics.record(0.3)

        assert metrics.count == 4
        assert metrics.total_time == 0.65
        assert metrics.min_time == 0.05
        assert metrics.max_time == 0.3
        assert len(metrics.timings) == 4

    def test_avg_time_calculation(self):
        """Test average time calculation."""
        metrics = OperationMetrics(operation="test_op")
        metrics.record(0.1)
        metrics.record(0.2)
        metrics.record(0.3)

        # Use pytest.approx for floating point comparison
        assert metrics.avg_time == pytest.approx(0.2)  # (0.1 + 0.2 + 0.3) / 3

    def test_avg_time_ms_calculation(self):
        """Test average time in milliseconds."""
        metrics = OperationMetrics(operation="test_op")
        metrics.record(0.1)  # 100ms
        metrics.record(0.2)  # 200ms

        # Use pytest.approx for floating point comparison
        assert metrics.avg_time_ms == pytest.approx(150.0)  # Average of 100 and 200

    def test_avg_time_zero_count(self):
        """Test average time with zero recordings."""
        metrics = OperationMetrics(operation="test_op")
        assert metrics.avg_time == 0.0
        assert metrics.avg_time_ms == 0.0

    def test_timings_list_limit(self):
        """Test that timings list is limited to 100 entries."""
        metrics = OperationMetrics(operation="test_op")

        # Record 150 timings
        for i in range(150):
            metrics.record(0.001 * i)

        # Should only keep last 100
        assert len(metrics.timings) == 100
        assert metrics.count == 150  # Count should still be accurate

        # First timing should be removed
        assert 0.0 not in metrics.timings
        # Last timing should be present
        assert metrics.timings[-1] == 0.149


class TestPerformanceMonitor:
    """Test PerformanceMonitor class."""

    def test_initialization(self):
        """Test monitor initialization."""
        monitor = PerformanceMonitor()

        assert len(monitor.metrics) == 0
        assert monitor.cache_hits == 0
        assert monitor.cache_misses == 0
        assert monitor.early_stops == 0
        assert monitor.full_searches == 0

    def test_measure_context_manager(self):
        """Test measure context manager."""
        monitor = PerformanceMonitor()

        with monitor.measure("test_operation"):
            time.sleep(0.01)  # 10ms

        assert "test_operation" in monitor.metrics
        assert monitor.metrics["test_operation"].count == 1
        assert monitor.metrics["test_operation"].avg_time >= 0.01

    def test_measure_multiple_operations(self):
        """Test measuring multiple different operations."""
        monitor = PerformanceMonitor()

        with monitor.measure("op1"):
            time.sleep(0.005)

        with monitor.measure("op2"):
            time.sleep(0.01)

        with monitor.measure("op1"):
            time.sleep(0.005)

        assert monitor.metrics["op1"].count == 2
        assert monitor.metrics["op2"].count == 1

    def test_measure_handles_exceptions(self):
        """Test that measure still records timing on exception."""
        monitor = PerformanceMonitor()

        try:
            with monitor.measure("error_op"):
                time.sleep(0.005)
                raise ValueError("Test error")
        except ValueError:
            pass

        # Should still have recorded the timing
        assert "error_op" in monitor.metrics
        assert monitor.metrics["error_op"].count == 1

    def test_record_cache_hit(self):
        """Test cache hit recording."""
        monitor = PerformanceMonitor()
        monitor.record_cache_hit()
        monitor.record_cache_hit()
        monitor.record_cache_hit()

        assert monitor.cache_hits == 3
        assert monitor.cache_misses == 0

    def test_record_cache_miss(self):
        """Test cache miss recording."""
        monitor = PerformanceMonitor()
        monitor.record_cache_miss()
        monitor.record_cache_miss()

        assert monitor.cache_hits == 0
        assert monitor.cache_misses == 2

    def test_cache_hit_rate_calculation(self):
        """Test cache hit rate calculation."""
        monitor = PerformanceMonitor()
        monitor.record_cache_hit()
        monitor.record_cache_hit()
        monitor.record_cache_hit()
        monitor.record_cache_miss()

        # 3 hits out of 4 total = 0.75
        assert monitor.cache_hit_rate == 0.75

    def test_cache_hit_rate_zero_operations(self):
        """Test cache hit rate with zero operations."""
        monitor = PerformanceMonitor()
        assert monitor.cache_hit_rate == 0.0

    def test_record_early_stop(self):
        """Test early stop recording."""
        monitor = PerformanceMonitor()
        monitor.record_early_stop()
        monitor.record_early_stop()

        assert monitor.early_stops == 2
        assert monitor.full_searches == 0

    def test_record_full_search(self):
        """Test full search recording."""
        monitor = PerformanceMonitor()
        monitor.record_full_search()
        monitor.record_full_search()
        monitor.record_full_search()

        assert monitor.early_stops == 0
        assert monitor.full_searches == 3

    def test_early_stop_rate_calculation(self):
        """Test early stop rate calculation."""
        monitor = PerformanceMonitor()
        monitor.record_early_stop()
        monitor.record_early_stop()
        monitor.record_full_search()

        # 2 early stops out of 3 total = 0.666...
        assert abs(monitor.early_stop_rate - 0.6666666666666666) < 0.0001

    def test_early_stop_rate_zero_searches(self):
        """Test early stop rate with zero searches."""
        monitor = PerformanceMonitor()
        assert monitor.early_stop_rate == 0.0

    def test_get_summary(self):
        """Test summary generation."""
        monitor = PerformanceMonitor()

        with monitor.measure("test_op"):
            time.sleep(0.01)

        monitor.record_cache_hit()
        monitor.record_cache_miss()
        monitor.record_early_stop()

        summary = monitor.get_summary()

        assert "operations" in summary
        assert "cache" in summary
        assert "search" in summary

        assert "test_op" in summary["operations"]
        assert summary["operations"]["test_op"]["count"] == 1

        assert summary["cache"]["hits"] == 1
        assert summary["cache"]["misses"] == 1
        assert summary["cache"]["hit_rate"] == 50.0

        assert summary["search"]["early_stops"] == 1
        assert summary["search"]["full_searches"] == 0

    def test_reset(self):
        """Test monitor reset."""
        monitor = PerformanceMonitor()

        with monitor.measure("test_op"):
            time.sleep(0.005)

        monitor.record_cache_hit()
        monitor.record_early_stop()

        # Reset
        monitor.reset()

        assert len(monitor.metrics) == 0
        assert monitor.cache_hits == 0
        assert monitor.cache_misses == 0
        assert monitor.early_stops == 0
        assert monitor.full_searches == 0


class TestGlobalMonitor:
    """Test global monitor singleton."""

    def test_get_monitor_returns_same_instance(self):
        """Test that get_monitor returns same instance."""
        monitor1 = get_monitor()
        monitor2 = get_monitor()

        assert monitor1 is monitor2

    def test_reset_monitor(self):
        """Test global monitor reset."""
        monitor = get_monitor()

        with monitor.measure("test_op"):
            time.sleep(0.005)

        reset_monitor()

        # Should be empty after reset
        assert len(monitor.metrics) == 0

    def test_reset_monitor_creates_new_state(self):
        """Test that reset_monitor clears state."""
        monitor = get_monitor()

        monitor.record_cache_hit()
        monitor.record_early_stop()

        reset_monitor()

        assert monitor.cache_hits == 0
        assert monitor.early_stops == 0


class TestPerformanceMonitorIntegration:
    """Test performance monitor in realistic scenarios."""

    def test_typical_workflow(self):
        """Test typical GUI automation workflow."""
        reset_monitor()
        monitor = get_monitor()

        # Simulate element tree build
        with monitor.measure("build_element_tree"):
            time.sleep(0.02)

        # Simulate fuzzy matching
        with monitor.measure("fuzzy_match"):
            time.sleep(0.01)
            monitor.record_cache_miss()  # First search

        with monitor.measure("fuzzy_match"):
            time.sleep(0.005)
            monitor.record_cache_hit()  # Cached result

        # Simulate early stop
        monitor.record_early_stop()

        summary = monitor.get_summary()

        assert summary["operations"]["build_element_tree"]["count"] == 1
        assert summary["operations"]["fuzzy_match"]["count"] == 2
        assert summary["cache"]["hit_rate"] == 50.0
        assert summary["search"]["early_stop_rate"] == 100.0

    def test_performance_comparison(self):
        """Test comparing cached vs uncached performance."""
        reset_monitor()
        monitor = get_monitor()

        # Uncached operations (slower)
        for _ in range(3):
            with monitor.measure("uncached_op"):
                time.sleep(0.01)
                monitor.record_cache_miss()

        # Cached operations (faster)
        for _ in range(7):
            with monitor.measure("cached_op"):
                time.sleep(0.001)  # 10x faster with cache
                monitor.record_cache_hit()

        summary = monitor.get_summary()

        uncached_avg = summary["operations"]["uncached_op"]["avg_ms"]
        cached_avg = summary["operations"]["cached_op"]["avg_ms"]

        # Cached should be significantly faster
        assert cached_avg < uncached_avg
        assert summary["cache"]["hit_rate"] == 70.0  # 7/10


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
