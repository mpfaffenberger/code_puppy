"""Standalone "agent is alive" heartbeat — decoupled from the spinner.

The sparkle spinner shows *contextual* status (thinking / running a tool) and
is deliberately paused while streamed text renders, which leaves gaps. This
heartbeat is a separate concern: it just signals that the process is alive for
the entire duration of an agent turn, including those gaps.

It pulses the **terminal title bar** (OSC 2), which never collides with the
scrollback or the spinner's Rich ``Live`` region — the title is a separate
channel from the visible content area. That decoupling is the whole point:
liveliness is independent of both the streaming process and the spinner.
"""

from __future__ import annotations

import sys
import threading

# A calm circular light filling and emptying — reads as a steady pulse.
_FRAMES = ["○", "◔", "◑", "◕", "●", "◕", "◑", "◔"]
_LABEL = "Mist · working"
_IDLE_TITLE = "Mist"
_INTERVAL = 0.4  # seconds per frame


class LivenessHeartbeat:
    """A background title-bar pulse, ref-counted across nested agent runs."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._depth = 0  # ref-count: keep pulsing while any run is active

    def _supported(self) -> bool:
        try:
            return bool(sys.stdout) and sys.stdout.isatty()
        except Exception:
            return False

    def _write_title(self, text: str) -> None:
        try:
            sys.stdout.write(f"\033]2;{text}\007")
            sys.stdout.flush()
        except Exception:
            pass

    def _run(self) -> None:
        i = 0
        while not self._stop.is_set():
            self._write_title(f"{_FRAMES[i % len(_FRAMES)]} {_LABEL}")
            i += 1
            self._stop.wait(_INTERVAL)
        self._write_title(_IDLE_TITLE)

    def start(self) -> None:
        """Begin (or ref-count into) the heartbeat. No-op without a TTY."""
        if not self._supported():
            return
        with self._lock:
            self._depth += 1
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, name="liveness-heartbeat", daemon=True
            )
            self._thread.start()

    def stop(self) -> None:
        """Ref-count out; actually stop only when the last run ends."""
        with self._lock:
            if self._depth > 0:
                self._depth -= 1
            if self._depth > 0:
                return
            self._stop.set()
            thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=0.5)

    @property
    def active(self) -> bool:
        with self._lock:
            return self._depth > 0


_heartbeat = LivenessHeartbeat()


def get_heartbeat() -> LivenessHeartbeat:
    """Return the process-wide liveliness heartbeat."""
    return _heartbeat


__all__ = ["LivenessHeartbeat", "get_heartbeat"]
