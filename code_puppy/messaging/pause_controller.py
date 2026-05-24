"""PauseController - thread-safe primitive for pausing a running agent.

The PauseController lets an external thread (e.g. a raw stdin key listener,
a slash command, the UI) signal that the agent should pause at the next
safe boundary (between streaming events or between turns). It also lets
the user queue up "steering" messages that should be injected as a user
turn once the agent reaches the next turn boundary.

This is the Phase 1 foundation primitive. No runtime wiring, spinner
suppression, or keybindings live here — those will land in later phases.

    ┌─────────────────────────────────────────────────────────────┐
    │                     PauseController                          │
    │                                                              │
    │   pause()  ─────────────►  _paused = True                    │
    │                            event.clear()                     │
    │                                                              │
    │   resume() ─────────────►  _paused = False                   │
    │                            event.set()                       │
    │                                                              │
    │   request_steer(text) ──►  _steer_queue.append(text)         │
    │                                                              │
    │   await wait_if_paused() ── awaits event when paused         │
    └─────────────────────────────────────────────────────────────┘

Bulletproofing: pause() / resume() must NEVER raise if the event loop is
closed or unavailable — they fall back to direct `.set()/.clear()` on the
Event and silently swallow `RuntimeError`. This is essential because the
raw stdin key listener runs in a daemon thread with no asyncio loop.
"""

import asyncio
import threading
from typing import Callable, List, Literal, Optional

SteerMode = Literal["now", "queue"]
ResumeListener = Callable[[], None]


class PauseController:
    """Thread-safe pause/resume + steering-message queue for the agent.

    Safe to call from any thread, including daemon threads with no event
    loop. The asyncio.Event is lazily created on the first call to
    `wait_if_paused`, at which point we also capture the running loop
    reference so future `pause()`/`resume()` calls can schedule
    event.set()/event.clear() in a thread-safe way.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._paused: bool = False
        # Two queues, one per delivery mode (see ``request_steer`` docs).
        self._steer_queue_now: List[str] = []
        self._steer_queue_queued: List[str] = []
        self._resume_event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # Resume listeners (tiny pub-sub for things that want to wake up
        # when paused -> not-paused, e.g. the renderer flushing its buffer).
        self._resume_listeners: List[ResumeListener] = []
        self._resume_listeners_lock = threading.Lock()

    # =========================================================================
    # Pause / Resume
    # =========================================================================

    def pause(self) -> None:
        """Mark the controller as paused and clear the resume event.

        Safe to call from any thread. Never raises.
        """
        with self._lock:
            self._paused = True
            event = self._resume_event
            loop = self._loop

        if event is None:
            return

        self._call_on_loop(loop, event.clear)

    def resume(self) -> None:
        """Mark the controller as not paused and signal the resume event.

        Safe to call from any thread. Never raises. If this call causes a
        paused -> not-paused transition, registered resume listeners are
        invoked (each in a try/except so a broken listener doesn't break
        the others). A no-op resume() call (we were already not paused)
        does NOT fire listeners.
        """
        with self._lock:
            was_paused = self._paused
            self._paused = False
            event = self._resume_event
            loop = self._loop

        if event is not None:
            self._call_on_loop(loop, event.set)

        if was_paused:
            self._fire_resume_listeners()

    def is_paused(self) -> bool:
        """Return True if currently paused."""
        with self._lock:
            return self._paused

    # =========================================================================
    # Resume listeners (pub-sub)
    # =========================================================================

    def add_resume_listener(self, callback: ResumeListener) -> None:
        """Register a callback fired on every paused -> not-paused transition.

        Listeners are invoked synchronously in whichever thread calls
        ``resume()`` — keep them cheap and non-blocking. Duplicate
        registrations of the same callable are ignored.
        """
        with self._resume_listeners_lock:
            if callback not in self._resume_listeners:
                self._resume_listeners.append(callback)

    def remove_resume_listener(self, callback: ResumeListener) -> None:
        """Unregister a previously-added resume listener. No-op if absent."""
        with self._resume_listeners_lock:
            try:
                self._resume_listeners.remove(callback)
            except ValueError:
                pass

    def _fire_resume_listeners(self) -> None:
        """Call every registered resume listener; swallow individual errors."""
        with self._resume_listeners_lock:
            # Snapshot under lock so callbacks can re-register without
            # deadlocking and we don't trip ``list changed during iter``.
            listeners = list(self._resume_listeners)
        for listener in listeners:
            try:
                listener()
            except Exception:
                # A broken listener must not break the others.
                pass

    # =========================================================================
    # Steering queue
    # =========================================================================

    def request_steer(self, text: str, mode: SteerMode = "now") -> None:
        """Queue a steering message for delivery to the agent.

        The ``mode`` controls *when* the model sees it:
          - ``"now"`` (default): drained by the steer ``history_processor``
            and injected at the next model call — including between tool
            calls *within* the current ``agent.run()``. Interrupts the
            agent's current train of thought ASAP.
          - ``"queue"``: held until the current ``agent.run()`` completes,
            then drained by ``_runtime._do_run``'s loop and submitted as
            a fresh user turn. Won't interrupt in-progress work.

        Empty / whitespace-only strings are silently ignored regardless
        of mode.
        """
        if text is None:
            return
        stripped = text.strip()
        if not stripped:
            return
        with self._lock:
            if mode == "queue":
                self._steer_queue_queued.append(text)
            else:
                self._steer_queue_now.append(text)

    def drain_pending_steer_now(self) -> List[str]:
        """Atomically pop + return every queued ``now``-mode steer.

        Owned by the steer ``history_processor`` — do NOT call from the
        runtime loop or you'll double-inject.
        """
        with self._lock:
            drained = self._steer_queue_now
            self._steer_queue_now = []
        return drained

    def drain_pending_steer_queued(self) -> List[str]:
        """Atomically pop + return every queued ``queue``-mode steer.

        Owned by ``_runtime._do_run``'s between-turns loop — do NOT call
        from the history processor.
        """
        with self._lock:
            drained = self._steer_queue_queued
            self._steer_queue_queued = []
        return drained

    def has_pending_steer_now(self) -> bool:
        """True iff at least one ``now``-mode steer is queued."""
        with self._lock:
            return bool(self._steer_queue_now)

    def has_pending_steer_queued(self) -> bool:
        """True iff at least one ``queue``-mode steer is queued."""
        with self._lock:
            return bool(self._steer_queue_queued)

    def drain_pending_steer(self) -> List[str]:
        """Drain BOTH queues (queued-mode first, then now-mode).

        Used by the cancel-path + start-of-run hygiene helpers in
        ``_run_signals.py`` — neither cares which queue an orphan steer
        came from; they just want everything gone.
        """
        with self._lock:
            drained = self._steer_queue_queued + self._steer_queue_now
            self._steer_queue_queued = []
            self._steer_queue_now = []
        return drained

    def has_pending_steer(self) -> bool:
        """True iff EITHER queue is non-empty."""
        with self._lock:
            return bool(self._steer_queue_now or self._steer_queue_queued)

    # =========================================================================
    # Async wait
    # =========================================================================

    async def wait_if_paused(self, timeout: Optional[float] = None) -> bool:
        """Block until the controller is resumed (or until timeout).

        - Returns True immediately when not paused.
        - Returns True when resumed normally.
        - Returns False (and force-resumes) on timeout.

        Lazily creates the asyncio.Event on the current event loop and
        captures the loop reference so pause()/resume() can schedule
        event.set()/event.clear() in a thread-safe manner.
        """
        if not self.is_paused():
            return True

        event = self._ensure_event()

        try:
            if timeout is None:
                await event.wait()
            else:
                await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            # Force-resume so we don't leave the controller stuck.
            self.resume()
            return False

        return True

    # =========================================================================
    # Internals
    # =========================================================================

    def _ensure_event(self) -> asyncio.Event:
        """Lazily create the asyncio.Event bound to the current loop."""
        with self._lock:
            if self._resume_event is None:
                self._resume_event = asyncio.Event()
                # If we're paused, the event must be unset.
                if self._paused:
                    self._resume_event.clear()
                else:
                    self._resume_event.set()
                try:
                    self._loop = asyncio.get_running_loop()
                except RuntimeError:
                    self._loop = None
            return self._resume_event

    @staticmethod
    def _call_on_loop(
        loop: Optional[asyncio.AbstractEventLoop],
        fn,
    ) -> None:
        """Best-effort thread-safe call into the captured event loop.

        Falls back to direct invocation if the loop is closed or missing.
        Silently swallows RuntimeError so caller threads never crash.
        """
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(fn)
                return
            except RuntimeError:
                # Loop was closed between the check and the call.
                pass
        try:
            fn()
        except RuntimeError:
            # asyncio.Event.set/clear shouldn't raise, but be paranoid.
            pass


# =============================================================================
# Module-level singleton
# =============================================================================

_pause_controller: Optional[PauseController] = None
_pause_controller_lock = threading.Lock()


def get_pause_controller() -> PauseController:
    """Get or lazily create the global PauseController singleton."""
    global _pause_controller
    with _pause_controller_lock:
        if _pause_controller is None:
            _pause_controller = PauseController()
        return _pause_controller


def reset_pause_controller() -> None:
    """Reset the global PauseController (for testing)."""
    global _pause_controller
    with _pause_controller_lock:
        _pause_controller = None


__all__ = [
    "PauseController",
    "SteerMode",
    "get_pause_controller",
    "reset_pause_controller",
]
