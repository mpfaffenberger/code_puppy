"""Caching layer for shell command safety assessments.

This module provides an LRU cache for recently assessed commands to avoid redundant API calls.

The approach is simple and secure: let the LLM assess ALL commands and cache
those assessments. This eliminates the security risks of pre-defined whitelists
while providing the performance benefits of caching.
"""

from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional, Tuple

# Maximum number of cached assessments (LRU eviction after this)
MAX_CACHE_SIZE = 200


@dataclass
class CachedAssessment:
    """A cached safety assessment result."""

    risk: str
    reasoning: str


class CommandSafetyCache:
    """LRU cache for shell command safety assessments.

    This cache stores previous LLM assessments to avoid redundant API calls.
    It uses an OrderedDict for O(1) LRU eviction.
    """

    def __init__(self, max_size: int = MAX_CACHE_SIZE):
        self._cache: OrderedDict[Tuple[str, Optional[str]], CachedAssessment] = (
            OrderedDict()
        )
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def _make_key(self, command: str, cwd: Optional[str]) -> Tuple[str, Optional[str]]:
        """Create a cache key from command and cwd."""
        # Normalize command (strip whitespace)
        return (command.strip(), cwd)

    def get(
        self, command: str, cwd: Optional[str] = None
    ) -> Optional[CachedAssessment]:
        """Get a cached assessment if it exists.

        Args:
            command: The shell command
            cwd: Optional working directory

        Returns:
            CachedAssessment if found, None otherwise
        """
        key = self._make_key(command, cwd)
        if key in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None

    def put(
        self, command: str, cwd: Optional[str], assessment: CachedAssessment
    ) -> None:
        """Store an assessment in the cache.

        Args:
            command: The shell command
            cwd: Optional working directory
            assessment: The assessment result to cache
        """
        key = self._make_key(command, cwd)

        # If already exists, update and move to end
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = assessment
            return

        # Evict oldest if at capacity
        while len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)

        self._cache[key] = assessment

    def clear(self) -> None:
        """Clear all cached assessments."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def stats(self) -> dict:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1f}%",
        }


# Global cache instance (singleton for the session)
_cache = CommandSafetyCache()


def get_cache_stats() -> dict:
    """Get statistics about the cache performance."""
    return _cache.stats


def get_cached_assessment(
    command: str, cwd: Optional[str] = None
) -> Optional[CachedAssessment]:
    """Get a cached command safety assessment.

    Cache-only approach: use the LLM cache for speed, but let the LLM
    determine safety for all commands. No pre-defined whitelists.

    Args:
        command: The shell command to check
        cwd: Optional working directory

    Returns:
        CachedAssessment if found in cache, None if needs LLM assessment
    """
    return _cache.get(command, cwd)


def cache_assessment(
    command: str, cwd: Optional[str], risk: str, reasoning: str
) -> None:
    """Cache an LLM assessment result.

    Cache all LLM assessments since the same command should get
    the same assessment, providing both security and performance.

    Args:
        command: The shell command
        cwd: Optional working directory
        risk: The assessed risk level
        reasoning: The assessment reasoning
    """
    assessment = CachedAssessment(
        risk=risk,
        reasoning=reasoning,
    )
    _cache.put(command, cwd, assessment)
