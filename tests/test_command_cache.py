"""Tests for shell command safety caching layer."""

from code_puppy.plugins.shell_safety.command_cache import (
    CachedAssessment,
    CommandSafetyCache,
    cache_assessment,
    get_cached_assessment,
)


class TestCacheFunctions:
    """Tests for the cache functionality."""

    def test_cache_miss_returns_none(self):
        """Should return None when cache miss."""
        from code_puppy.plugins.shell_safety.command_cache import get_cached_assessment

        result = get_cached_assessment("unknown command", None)
        assert result is None

    def test_cache_with_cwd(self):
        """Should differentiate by cwd."""
        cache = CommandSafetyCache(max_size=10)
        assessment1 = CachedAssessment(risk="low", reasoning="cwd1")
        assessment2 = CachedAssessment(risk="medium", reasoning="cwd2")

        cache.put("npm test", "/project1", assessment1)
        cache.put("npm test", "/project2", assessment2)

        result1 = cache.get("npm test", "/project1")
        result2 = cache.get("npm test", "/project2")

        assert result1.reasoning == "cwd1"
        assert result2.reasoning == "cwd2"

    def test_lru_eviction(self):
        """Should evict oldest entries when at capacity."""
        cache = CommandSafetyCache(max_size=3)

        cache.put("cmd1", None, CachedAssessment(risk="low", reasoning="1"))
        cache.put("cmd2", None, CachedAssessment(risk="low", reasoning="2"))
        cache.put("cmd3", None, CachedAssessment(risk="low", reasoning="3"))
        # Cache is now full

        # Add one more - should evict cmd1
        cache.put("cmd4", None, CachedAssessment(risk="low", reasoning="4"))

        assert cache.get("cmd1", None) is None  # Evicted
        assert cache.get("cmd2", None) is not None
        assert cache.get("cmd3", None) is not None
        assert cache.get("cmd4", None) is not None

    def test_lru_access_updates_order(self):
        """Accessing an entry should move it to most-recently-used."""
        cache = CommandSafetyCache(max_size=3)

        cache.put("cmd1", None, CachedAssessment(risk="low", reasoning="1"))
        cache.put("cmd2", None, CachedAssessment(risk="low", reasoning="2"))
        cache.put("cmd3", None, CachedAssessment(risk="low", reasoning="3"))

        # Access cmd1 - makes it most recently used
        cache.get("cmd1", None)

        # Add new entry - should evict cmd2 (oldest unused)
        cache.put("cmd4", None, CachedAssessment(risk="low", reasoning="4"))

        assert cache.get("cmd1", None) is not None  # Still there
        assert cache.get("cmd2", None) is None  # Evicted
        assert cache.get("cmd3", None) is not None
        assert cache.get("cmd4", None) is not None

    def test_cache_stats(self):
        """Should track hits and misses."""
        cache = CommandSafetyCache(max_size=10)
        cache.put("cmd1", None, CachedAssessment(risk="low", reasoning="1"))

        cache.get("cmd1", None)  # Hit
        cache.get("cmd1", None)  # Hit
        cache.get("cmd2", None)  # Miss

        stats = cache.stats
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert "66.7%" in stats["hit_rate"]

    def test_cache_clear(self):
        """Should clear all entries and reset stats."""
        cache = CommandSafetyCache(max_size=10)
        cache.put("cmd1", None, CachedAssessment(risk="low", reasoning="1"))
        cache.get("cmd1", None)

        cache.clear()

        assert cache.get("cmd1", None) is None
        assert cache.stats["hits"] == 0
        assert cache.stats["misses"] == 1  # The get after clear


class TestCacheIntegration:
    """Integration tests for the caching layer."""

    def setup_method(self):
        """Clear the global cache before each test."""
        # Access the cache directly to clear it
        from code_puppy.plugins.shell_safety.command_cache import _cache

        _cache.clear()

    def test_get_cached_assessment_returns_none_when_empty(self):
        """get_cached_assessment should return None when cache is empty."""
        result = get_cached_assessment("ls -la", None)
        assert result is None

    def test_get_cached_assessment_cache_hit(self):
        """Should return cached result when available."""
        # Pre-populate cache
        cache_assessment("npm install", None, "medium", "installs packages")

        result = get_cached_assessment("npm install", None)
        assert result is not None
        assert result.risk == "medium"

    def test_get_cached_assessment_miss(self):
        """Should return None when not in cache."""
        result = get_cached_assessment("some-unknown-command", None)
        assert result is None

    def test_cache_assessment_stores_in_global_cache(self):
        """cache_assessment should store in the global cache."""
        cache_assessment("docker build .", "/app", "medium", "builds container")

        result = get_cached_assessment("docker build .", "/app")
        assert result is not None
        assert result.risk == "medium"
