"""Server-side session caching for fast session loading.

This module provides an LRU cache for deserialized session data,
dramatically reducing load times for frequently accessed sessions.
"""

import asyncio
import logging
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Configuration
MAX_CACHED_SESSIONS = 50  # Maximum number of sessions to cache
CACHE_TTL_SECONDS = 3600  # 1 hour TTL
MAX_WORKERS = 4

# Thread pool for async file I/O
_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)


class SessionCacheEntry:
    """A cached session entry with metadata."""

    __slots__ = [
        "messages",
        "json_messages",
        "metadata",
        "loaded_at",
        "last_accessed",
        "file_mtime",
    ]

    def __init__(
        self,
        messages: List[Any],
        json_messages: List[Dict[str, Any]],
        metadata: Dict[str, Any],
        file_mtime: float,
    ):
        self.messages = messages
        self.json_messages = json_messages  # Pre-serialized for fast API response
        self.metadata = metadata
        self.loaded_at = time.time()
        self.last_accessed = time.time()
        self.file_mtime = file_mtime

    @property
    def age_seconds(self) -> float:
        return time.time() - self.loaded_at

    @property
    def is_expired(self) -> bool:
        return self.age_seconds > CACHE_TTL_SECONDS

    def touch(self):
        """Update last accessed time."""
        self.last_accessed = time.time()


class SessionCache:
    """LRU cache for session data with async support.

    Features:
    - LRU eviction when cache is full
    - TTL-based expiration
    - File modification tracking for cache invalidation
    - Pre-serialized JSON for fast API responses
    - Thread-safe async operations
    """

    def __init__(self, max_size: int = MAX_CACHED_SESSIONS):
        self._cache: OrderedDict[str, SessionCacheEntry] = OrderedDict()
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0, "expirations": 0}

    async def get(
        self, session_id: str, session_file_path: Path
    ) -> Optional[Tuple[List[Dict[str, Any]], Dict[str, Any]]]:
        """Get cached session messages (pre-serialized JSON).

        Returns:
            Tuple of (json_messages, metadata) if cached and valid, None otherwise
        """
        async with self._lock:
            entry = self._cache.get(session_id)

            if entry is None:
                self._stats["misses"] += 1
                return None

            # Check TTL
            if entry.is_expired:
                self._stats["expirations"] += 1
                del self._cache[session_id]
                logger.debug("[Cache] Session %s expired", session_id)
                return None

            # Check if file was modified
            try:
                current_mtime = session_file_path.stat().st_mtime
                if current_mtime > entry.file_mtime:
                    self._stats["expirations"] += 1
                    del self._cache[session_id]
                    logger.debug(
                        f"[Cache] Session {session_id} file modified, invalidating cache"
                    )
                    return None
            except FileNotFoundError:
                del self._cache[session_id]
                return None

            # Cache hit!
            self._stats["hits"] += 1
            entry.touch()

            # Move to end (most recently used)
            self._cache.move_to_end(session_id)

            logger.debug(
                f"[Cache] HIT for session {session_id} (age: {entry.age_seconds:.1f}s)"
            )
            return entry.json_messages, entry.metadata

    async def put(
        self,
        session_id: str,
        session_file_path: Path,
        messages: List[Any],
        json_messages: List[Dict[str, Any]],
        metadata: Dict[str, Any],
    ):
        """Cache session data.

        Args:
            session_id: Unique session identifier
            session_file_path: Path to the session JSON file (for mtime tracking)
            messages: Raw message objects
            json_messages: Pre-serialized JSON messages
            metadata: Session metadata
        """
        async with self._lock:
            # Evict if at capacity
            while len(self._cache) >= self._max_size:
                # Remove oldest (first) item
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                self._stats["evictions"] += 1
                logger.debug("[Cache] Evicted session %s", oldest_key)

            # Get file mtime
            try:
                file_mtime = session_file_path.stat().st_mtime
            except FileNotFoundError:
                file_mtime = time.time()

            # Create entry
            entry = SessionCacheEntry(
                messages=messages,
                json_messages=json_messages,
                metadata=metadata,
                file_mtime=file_mtime,
            )

            self._cache[session_id] = entry
            logger.debug(
                f"[Cache] Cached session {session_id} ({len(messages)} messages)"
            )

    async def invalidate(self, session_id: str):
        """Remove a session from cache."""
        async with self._lock:
            if session_id in self._cache:
                del self._cache[session_id]
                logger.debug("[Cache] Invalidated session %s", session_id)

    async def clear(self):
        """Clear all cached sessions."""
        async with self._lock:
            self._cache.clear()
            logger.info("[Cache] All sessions cleared")

    @property
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        hit_rate = 0.0
        total = self._stats["hits"] + self._stats["misses"]
        if total > 0:
            hit_rate = self._stats["hits"] / total * 100

        return {
            **self._stats,
            "size": len(self._cache),
            "max_size": self._max_size,
            "hit_rate_percent": round(hit_rate, 1),
        }


# Global cache instance
_session_cache: Optional[SessionCache] = None


def get_session_cache() -> SessionCache:
    """Get the global session cache instance."""
    global _session_cache
    if _session_cache is None:
        _session_cache = SessionCache()
    return _session_cache


def _load_session_sync(session_file_path: Path) -> List[Any]:
    """Synchronous session loading (for executor)."""
    from code_puppy.session_storage import load_session

    return load_session(session_file_path.stem, session_file_path.parent)


def _serialize_message(msg: Any) -> Dict[str, Any]:
    """Serialize a pydantic-ai message to JSON-safe dict.

    Handles both wrapped and unwrapped message formats:
    - Wrapped (WS sessions): {'msg': <ModelRequest|ModelResponse>, 'agent': ..., 'model': ..., 'ts': ...}
    - Unwrapped: <ModelRequest|ModelResponse> or <ModelMessage>

    Preserves all message parts including ThinkingPart, ToolCallPart, TextPart, etc.
    """

    def _serialize_obj(obj: Any) -> Any:
        """Recursively serialize an object to JSON-safe types."""
        # Pydantic v2 models with model_dump
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json")

        # Handle dicts recursively
        if isinstance(obj, dict):
            return {k: _serialize_obj(v) for k, v in obj.items()}

        # Handle lists/tuples recursively
        if isinstance(obj, (list, tuple)):
            return [_serialize_obj(item) for item in obj]

        # JSON-safe primitives
        if isinstance(obj, (str, int, float, bool, type(None))):
            return obj

        # pydantic-ai message objects (ModelRequest, ModelResponse, Part subclasses)
        # They have __dict__ but are not Pydantic models
        if hasattr(obj, "__dict__"):
            result = {}
            for k, v in obj.__dict__.items():
                result[k] = _serialize_obj(v)
            return result

        # Fallback: convert to string
        return str(obj)

    # Handle wrapped message format (used in WS sessions)
    # {'msg': <ModelRequest|ModelResponse>, 'agent': ..., 'model': ..., 'ts': ...}
    if isinstance(msg, dict) and "msg" in msg:
        actual_msg = msg["msg"]
        return {
            "msg": _serialize_obj(actual_msg),
            "agent": msg.get("agent"),
            "model": msg.get("model"),
            "ts": msg.get("ts"),
        }

    # Handle unwrapped messages
    return _serialize_obj(msg)


def _serialize_messages_sync(messages: List[Any]) -> List[Dict[str, Any]]:
    """Synchronous batch serialization (for executor).

    Serializes all messages to JSON-safe dicts. Runs in thread pool
    to avoid blocking the event loop for large sessions.
    """
    return [_serialize_message(msg) for msg in messages]


async def load_session_cached(
    session_id: str, session_file_path: Path, timeout: float = 10.0
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Load session messages with caching.

    This is the main entry point for loading session data.
    It checks the cache first, and only loads from disk on cache miss.

    Args:
        session_id: Unique session identifier
        session_file_path: Path to the session JSON file
        timeout: Timeout for file operations

    Returns:
        Tuple of (json_messages, metadata)

    Raises:
        FileNotFoundError: If session JSON file does not exist
        asyncio.TimeoutError: If load times out
    """
    cache = get_session_cache()

    # Try cache first
    cached = await cache.get(session_id, session_file_path)
    if cached is not None:
        return cached

    # Cache miss - load from disk
    if not session_file_path.exists():
        raise FileNotFoundError(f"Session file not found: {session_file_path}")

    loop = asyncio.get_running_loop()

    # Load session file in thread pool
    start_time = time.time()
    messages = await asyncio.wait_for(
        loop.run_in_executor(_executor, _load_session_sync, session_file_path),
        timeout=timeout,
    )
    load_time = time.time() - start_time

    # Serialize to JSON in thread pool to avoid blocking event loop
    json_messages = await loop.run_in_executor(
        _executor, _serialize_messages_sync, messages
    )

    # Build metadata
    metadata = {
        "message_count": len(messages),
        "load_time_ms": round(load_time * 1000, 1),
    }

    # Cache for next time
    await cache.put(session_id, session_file_path, messages, json_messages, metadata)

    logger.info(
        f"[Cache] Loaded session {session_id} from disk in {load_time * 1000:.1f}ms"
    )

    return json_messages, metadata


async def invalidate_session_cache(session_id: str):
    """Invalidate a specific session in the cache.

    Call this when a session is modified or deleted.
    """
    cache = get_session_cache()
    await cache.invalidate(session_id)


async def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics for monitoring."""
    cache = get_session_cache()
    return cache.stats


async def shutdown_executor() -> None:
    """Shutdown the thread pool executor gracefully.

    This function ensures all pending tasks are completed before shutdown
    and prevents resource leaks. Should be called during application shutdown.

    Thread-safe and idempotent - safe to call multiple times.
    """
    global _executor

    if _executor is None:
        logger.debug("[Executor] Already shut down or never initialized")
        return

    try:
        logger.info("[Executor] Shutting down thread pool executor...")

        # Shutdown gracefully - wait for current tasks to complete
        # but don't cancel futures (they might be critical)
        _executor.shutdown(wait=True, cancel_futures=False)

        logger.info("[Executor] Thread pool executor shutdown complete")

        # Clear the reference
        _executor = None

    except Exception as e:
        logger.error("[Executor] Error during shutdown: %s", e, exc_info=True)
        # Still clear the reference even if shutdown had issues
        _executor = None
        raise
