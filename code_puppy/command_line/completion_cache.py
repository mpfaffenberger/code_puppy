"""Tiny thread-safe TTL caches for interactive completion lookups."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    """Cache one value briefly, coalescing concurrent cold loads."""

    def __init__(self, ttl: float = 4.0, clock: Callable[[], float] = time.monotonic):
        self.ttl = ttl
        self.clock = clock
        self._value: T | None = None
        self._deadline = 0.0
        self._lock = threading.Lock()

    def get(self, loader: Callable[[], T]) -> T:
        now = self.clock()
        if self._value is not None and now < self._deadline:
            return self._value
        with self._lock:
            now = self.clock()
            if self._value is None or now >= self._deadline:
                self._value = loader()
                self._deadline = now + self.ttl
            return self._value

    def clear(self) -> None:
        with self._lock:
            self._value = None
            self._deadline = 0.0
