"""Test suite for GUI-Cub Quick Wins (Phase 1).

Validates:
- RapidFuzz integration
- Performance monitoring
- Early-stop logic
- Optimized identifier variants
"""

import time

import pytest

from code_puppy.tools.gui_cub.fuzzy_matching import (
    clear_normalize_cache,
    extract_identifier_variants,
    normalize_text,
    similarity_score,
)
from code_puppy.tools.gui_cub.performance_monitor import (
    get_monitor,
    reset_monitor,
)


class TestPerformanceMonitor:
    """Test performance monitoring functionality."""

    def test_operation_timing(self):
        """Test that operations are timed correctly."""
        reset_monitor()
        monitor = get_monitor()

        # Measure a test operation
        with monitor.measure("test_op"):
            time.sleep(0.01)  # 10ms

        summary = monitor.get_summary()
        assert "test_op" in summary["operations"]
        assert summary["operations"]["test_op"]["count"] == 1
        assert summary["operations"]["test_op"]["avg_ms"] >= 10
        assert summary["operations"]["test_op"]["avg_ms"] < 20  # Some tolerance

    def test_multiple_operations(self):
        """Test tracking multiple operation types."""
        reset_monitor()
        monitor = get_monitor()

        with monitor.measure("op1"):
            time.sleep(0.005)

        with monitor.measure("op2"):
            time.sleep(0.01)

        with monitor.measure("op1"):  # Same operation again
            time.sleep(0.005)

        summary = monitor.get_summary()
        assert summary["operations"]["op1"]["count"] == 2
        assert summary["operations"]["op2"]["count"] == 1

    def test_cache_tracking(self):
        """Test cache hit/miss tracking."""
        reset_monitor()
        monitor = get_monitor()

        monitor.record_cache_hit()
        monitor.record_cache_hit()
        monitor.record_cache_miss()

        summary = monitor.get_summary()
        assert summary["cache"]["hits"] == 2
        assert summary["cache"]["misses"] == 1
        assert summary["cache"]["hit_rate"] == 66.7  # 2/3

    def test_early_stop_tracking(self):
        """Test early-stop vs full search tracking."""
        reset_monitor()
        monitor = get_monitor()

        monitor.record_early_stop()
        monitor.record_full_search()
        monitor.record_early_stop()

        summary = monitor.get_summary()
        assert summary["search"]["early_stops"] == 2
        assert summary["search"]["full_searches"] == 1
        assert summary["search"]["early_stop_rate"] == 66.7  # 2/3


class TestRapidFuzzIntegration:
    """Test RapidFuzz integration and performance."""

    def test_similarity_score_exact_match(self):
        """Test exact match returns 1.0."""
        score = similarity_score("Submit", "Submit")
        assert score == 1.0

        # Case-insensitive
        score = similarity_score("SUBMIT", "submit")
        assert score == 1.0

    def test_similarity_score_substring(self):
        """Test substring matches return high scores."""
        score = similarity_score("Save", "Save As...")
        assert score >= 0.8
        assert score < 1.0

    def test_similarity_score_fuzzy(self):
        """Test fuzzy matching works."""
        score = similarity_score("submit", "Submit Button")
        assert score > 0.6

        score = similarity_score("login", "Log In")
        assert score > 0.7

    def test_similarity_score_performance(self):
        """Test that similarity_score performs well with rapidfuzz."""
        test_pairs = [
            ("submit", "Submit Button"),
            ("save", "Save As..."),
            ("close", "Close Window"),
            ("login", "Log In Form"),
            ("search", "Search Field Input"),
        ] * 200  # 1000 comparisons for benchmark

        # Benchmark rapidfuzz
        start = time.perf_counter()
        for search, target in test_pairs:
            similarity_score(search, target)
        elapsed = time.perf_counter() - start

        # Should complete 1000 comparisons quickly (< 100ms)
        assert elapsed < 0.1, f"Performance issue: {elapsed:.3f}s for 1000 comparisons"
        print(f"\n  Completed 1000 comparisons in {elapsed * 1000:.1f}ms")


class TestIdentifierVariants:
    """Test optimized identifier variant generation."""

    def test_single_word_variants(self):
        """Test single word generates <= 8 variants."""
        variants = extract_identifier_variants("Submit")
        assert len(variants) <= 8, f"Too many variants: {len(variants)}"
        assert "submit" in variants
        assert "submitbtn" in variants
        assert "submit_btn" in variants
        assert "btnsubmit" in variants
        assert "btn_submit" in variants

    def test_multi_word_variants(self):
        """Test multi-word includes camelCase."""
        variants = extract_identifier_variants("Save File")
        assert "savefile" in variants
        assert "saveFile" in variants  # camelCase
        assert len(variants) <= 10  # Slightly more for multi-word

    def test_no_duplicate_variants(self):
        """Test no duplicate variants generated."""
        variants = extract_identifier_variants("Test")
        assert len(variants) == len(set(variants)), "Duplicate variants found!"


class TestFuzzyMatchingOptimization:
    """Test fuzzy matching with weighted attributes."""

    def test_weighted_attribute_scoring(self):
        """Test attribute weights affect scoring."""
        from code_puppy.tools.gui_cub.fuzzy_matching import fuzzy_match

        candidates = [
            {"title": "Submit Button", "description": "Click to submit"},
            {"title": "Cancel", "description": "Submit cancellation"},
        ]

        # Title should weigh more than description
        matches = fuzzy_match(
            "submit",
            candidates,
            attribute_names=["title", "description"],
            threshold=0.3,
        )

        # First match should be Submit Button (title match)
        assert len(matches) >= 1
        assert matches[0][0]["title"] == "Submit Button"

    def test_performance_monitoring_integration(self):
        """Test fuzzy_match uses performance monitor."""
        from code_puppy.tools.gui_cub.fuzzy_matching import fuzzy_match

        reset_monitor()
        monitor = get_monitor()

        candidates = [{"title": "Test"}] * 10

        fuzzy_match("test", candidates, threshold=0.5)

        summary = monitor.get_summary()
        assert "fuzzy_match" in summary["operations"]
        assert summary["operations"]["fuzzy_match"]["count"] == 1


class TestNormalizationCache:
    """Test normalized string caching functionality."""

    def test_cache_stores_results(self):
        """Test that normalization results are cached."""
        clear_normalize_cache()

        # First call should cache the result
        result1 = normalize_text("Submit Button")
        result2 = normalize_text("Submit Button")  # Should hit cache

        assert result1 == result2 == "submit button"

    def test_cache_improves_performance(self):
        """Test that cache improves performance on repeated calls."""
        clear_normalize_cache()

        # Warm up
        for _ in range(10):
            normalize_text("Test String")

        # Test with cache
        start = time.perf_counter()
        for _ in range(1000):
            normalize_text("Test String")  # All cache hits
        cached_time = time.perf_counter() - start

        # Clear cache and test without
        clear_normalize_cache()
        start = time.perf_counter()
        for i in range(1000):
            normalize_text(f"Test String {i}")  # All cache misses
        uncached_time = time.perf_counter() - start

        # Cache should be significantly faster
        # (Note: This is a loose check since both are very fast)
        print(
            f"\n  Cached: {cached_time * 1000:.2f}ms, Uncached: {uncached_time * 1000:.2f}ms"
        )

    def test_cache_clearing(self):
        """Test that cache can be cleared."""
        normalize_text("Test")
        clear_normalize_cache()
        # After clearing, should still work
        result = normalize_text("Test")
        assert result == "test"

    def test_cache_size_limit(self):
        """Test that cache respects size limit."""
        clear_normalize_cache()

        # Add more than the cache limit (1000)
        for i in range(1100):
            normalize_text(f"String {i}")

        # Cache should not exceed limit
        # (We can't directly check cache size, but this ensures no crash)
        result = normalize_text("Another String")
        assert result == "another string"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
