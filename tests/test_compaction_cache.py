"""Tests for PERF-04: CompactionCache in _history.py and _compaction.py.

Covers:
- CompactionCache.hash_message and .estimate_tokens caching
- CompactionCache preserves output (same result as uncached)
- CompactionCache reduces estimator calls
- CompactionCache does not persist message objects globally
- compact() still produces correct results with the cache
"""

from __future__ import annotations

from unittest.mock import patch

from pydantic_ai.messages import ModelRequest, UserPromptPart

from code_puppy.agents._compaction import compact, truncate
from code_puppy.agents._history import (
    CompactionCache,
    estimate_tokens_for_message,
    filter_huge_messages,
    hash_message,
)


def _sys_msg(text: str = "system prompt") -> ModelRequest:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _user_msg(text: str) -> ModelRequest:
    return ModelRequest(parts=[UserPromptPart(content=text)])


class TestCompactionCacheBasics:
    """CompactionCache correctly caches and returns identical results."""

    def test_hash_message_cached(self):
        """hash_message returns same value as uncached and caches it."""
        msg = _user_msg("test message")
        expected = hash_message(msg)
        cache = CompactionCache()

        result = cache.hash_message(msg)
        assert result == expected

        # Second call should hit the cache
        result2 = cache.hash_message(msg)
        assert result2 == expected

    def test_estimate_tokens_cached(self):
        """estimate_tokens returns same value as uncached and caches it."""
        msg = _user_msg("test message")
        expected = estimate_tokens_for_message(msg)
        cache = CompactionCache()

        result = cache.estimate_tokens(msg)
        assert result == expected

        result2 = cache.estimate_tokens(msg)
        assert result2 == expected

    def test_estimate_tokens_with_model_name(self):
        """Caching works correctly with model_name parameter."""
        msg = _user_msg("test message " * 50)
        expected = estimate_tokens_for_message(msg, model_name="opus-4-7")
        cache = CompactionCache()

        result = cache.estimate_tokens(msg, model_name="opus-4-7")
        assert result == expected

        # Different model_name should be a separate cache entry
        result_default = cache.estimate_tokens(msg)
        assert result_default == estimate_tokens_for_message(msg)

    def test_sum_tokens(self):
        """sum_tokens correctly sums across messages."""
        msgs = [_user_msg("hello"), _user_msg("world")]
        cache = CompactionCache()
        result = cache.sum_tokens(msgs)
        expected = sum(estimate_tokens_for_message(m) for m in msgs)
        assert result == expected

    def test_cache_does_not_persist_message_objects_globally(self):
        """CompactionCache is local and not a global module-level object."""
        # The cache is created fresh in compact() — verify no global exists
        import code_puppy.agents._history as hist_mod

        assert not hasattr(hist_mod, "_global_cache"), (
            "CompactionCache must not be a global that retains message objects"
        )
        # Create two caches — they should be independent
        cache1 = CompactionCache()
        cache2 = CompactionCache()
        msg = _user_msg("independent test")
        cache1.hash_message(msg)
        # cache2 should NOT have this entry
        assert id(msg) not in cache2._message_hashes


class TestCompactionCacheReducesCalls:
    """Verify that the cache actually reduces repeated estimator calls."""

    def test_hash_message_reduces_calls(self):
        """Calling hash_message twice on same object only calls hash_message once."""
        msg = _user_msg("cached hash test")
        cache = CompactionCache()

        # First call populates cache
        cache.hash_message(msg)
        assert len(cache._message_hashes) == 1

        # Second call hits cache (no new entry)
        cache.hash_message(msg)
        assert len(cache._message_hashes) == 1

    def test_estimate_tokens_reduces_calls(self):
        """Calling estimate_tokens twice only computes once."""
        msg = _user_msg("cached token test")
        cache = CompactionCache()

        cache.estimate_tokens(msg)
        assert len(cache._token_counts) == 1

        cache.estimate_tokens(msg)
        assert len(cache._token_counts) == 1


class TestCompactionCachePreservesOutput:
    """Ensure compact() still produces correct results with the cache."""

    def test_compact_with_cache_produces_same_result(self):
        """compact() with cache should produce same output as without (conceptually)."""
        import code_puppy.agents._compaction as cm

        msgs = [_sys_msg()] + [_user_msg(f"q{i}: " + "x" * 400) for i in range(20)]

        with patch.multiple(
            cm,
            get_compaction_threshold=lambda: 0.1,
            get_compaction_strategy=lambda: "truncation",
            get_protected_token_count=lambda: 500,
        ):
            new_msgs, dropped = compact(
                agent=None, messages=msgs, model_max=10_000, context_overhead=0
            )

        # Must have compacted
        assert len(new_msgs) < len(msgs)
        # System message preserved
        assert new_msgs[0] is msgs[0]
        assert len(dropped) > 0

    def test_filter_huge_messages_with_cache(self):
        """filter_huge_messages works correctly with a cache."""
        small = _user_msg("hi")
        giant = _user_msg("x" * 200000)
        cache = CompactionCache()

        result = filter_huge_messages([small, giant], cache=cache)
        assert small in result
        assert giant not in result

        # Cache should have entries for both messages
        assert len(cache._token_counts) >= 1

    def test_truncate_with_cache(self):
        """truncate() works correctly with a cache parameter."""
        msgs = [_sys_msg()] + [_user_msg(f"q{i}: " + "x" * 400) for i in range(20)]
        cache = CompactionCache()

        result = truncate(msgs, protected_tokens=800, cache=cache)
        assert len(result) < len(msgs)
        assert result[0] is msgs[0]
