"""Bounded liveness heartbeat for the boot-trace recorder.

A single long import can emit no trace event for tens of seconds. ``Heartbeat``
calls ``tick`` about once per interval, but only while the recorder has been
silent, so busy phases add nothing. Standard library only; every fault is
swallowed so the heartbeat can never affect startup.

Called by: boot_trace :: _Recorder.begin()
"""

import threading
import time
from typing import Callable


class Heartbeat:
    def __init__(
        self,
        tick: Callable[[], None],
        *,
        interval_s: float = 1.0,
        max_s: float = 300.0,
    ) -> None:
        self._tick = tick
        self._interval_s = interval_s
        self._max_s = max_s
        self._stop = threading.Event()
        # Held around every tick so stop() can wait out one already in flight.
        self._lock = threading.Lock()
        self._began = self._last_activity = time.monotonic()

    def start(self) -> None:
        try:
            self._began = self._last_activity = time.monotonic()
            threading.Thread(
                target=self._run, name="boot-trace-heartbeat", daemon=True
            ).start()
        except Exception:
            self._stop.set()

    def note_activity(self) -> None:
        self._last_activity = time.monotonic()

    def stop(self) -> None:
        """Idempotent; once it returns, no tick runs again."""
        try:
            self._stop.set()
            if self._lock.acquire(timeout=1.0):
                self._lock.release()
        except Exception:
            pass

    def _run(self) -> None:
        try:
            while not self._stop.wait(self._interval_s):
                now = time.monotonic()
                if now - self._began >= self._max_s:
                    return
                if now - self._last_activity < self._interval_s / 2:
                    continue
                with self._lock:
                    if self._stop.is_set():
                        return
                    try:
                        self._tick()
                    except Exception:
                        pass
        except Exception:
            pass
