"""Map code-puppy lifecycle events onto herdr's three semantic states.

herdr models every agent as ``working`` / ``blocked`` / ``idle``. This
reporter is the single writer of that state for the pane, and code-puppy
reports it *authoritatively* -- herdr never has to infer our state from the
screen.

State is a pure function of two facts we own directly:

* **run depth** -- how many agent runs are in flight (root + sub-agents).
  ``> 0`` means the model is doing work.
* **awaiting** -- whether code-puppy is parked on the human. This comes from
  the ``awaiting_user_input`` callback, which fires from the *one*
  process-wide choke-point every interactive wait passes through
  (shell-command approval, file-permission approval, ``ask_user_question``,
  and every menu/picker). Because that single source covers every prompt --
  including shell-command approval, which prompts from inside the tool -- the
  plugin sees every block directly. There is nothing left for herdr to guess.

Effective state::

    blocked   if awaiting              (parked on the human)
    working   elif run_depth > 0       (a run is in flight)
    idle      otherwise                (control is the human's)

Sub-agents fire the same ``agent_run_start`` / ``agent_run_end`` hooks as the
root agent, so we refcount active runs (the same pattern the puppy_spinner
plugin uses) rather than flipping idle when a sub-agent finishes.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from .client import HerdrClient

logger = logging.getLogger(__name__)

WORKING = "working"
BLOCKED = "blocked"
IDLE = "idle"


class HerdrReporter:
    """Thread-safe, dedup-ing bridge from callbacks to :class:`HerdrClient`."""

    def __init__(self, client: HerdrClient) -> None:
        self._client = client
        self._lock = threading.Lock()
        self._run_depth = 0
        self._awaiting = False
        self._last_state: Optional[str] = None
        self._session_id: Optional[str] = None

    @property
    def active(self) -> bool:
        return self._client.active

    # -- state derivation ----------------------------------------------

    def _recompute_locked(self) -> Optional[str]:
        """Return the effective state from the facts we hold. Caller holds lock."""
        if self._awaiting:
            return BLOCKED
        if self._run_depth > 0:
            return WORKING
        return IDLE

    def _sync(self) -> None:
        """Recompute the effective state and emit it if it changed (edge)."""
        with self._lock:
            state = self._recompute_locked()
            if state == self._last_state:
                return
            self._last_state = state
            session_id = self._session_id
        self._client.report_state(state, session_id)

    def _remember_session(self, session_id: Optional[str]) -> None:
        if not session_id:
            return
        with self._lock:
            new = session_id != self._session_id
            self._session_id = session_id
        if new:
            self._client.report_session(session_id)

    # -- lifecycle handlers (all sync; safe from async or worker threads) --

    def on_startup(self) -> None:
        self._sync()  # depth 0, not awaiting -> idle

    def on_user_prompt(self, session_id: Optional[str] = None) -> None:
        # Capture native session identity as early as possible; the run
        # starting (below) is what actually flips us to working.
        self._remember_session(session_id)

    def on_run_start(self, session_id: Optional[str] = None) -> None:
        self._remember_session(session_id)
        with self._lock:
            self._run_depth += 1
        self._sync()

    def on_run_end(self, session_id: Optional[str] = None) -> None:
        self._remember_session(session_id)
        with self._lock:
            self._run_depth = max(0, self._run_depth - 1)
        # At depth 0 the model has stopped. The interactive turn boundary is
        # the canonical idle signal, but headless (`-p`) runs never fire it,
        # so falling idle at depth 0 keeps non-interactive panes honest too.
        self._sync()

    def on_run_cancel(self) -> None:
        with self._lock:
            self._run_depth = 0
            self._awaiting = False
        self._sync()

    def on_turn_end(self) -> None:
        with self._lock:
            self._run_depth = 0
            self._awaiting = False
        self._sync()

    def on_awaiting_user_input(self, awaiting: bool) -> None:
        """The authoritative block signal: parked on the human iff ``awaiting``."""
        with self._lock:
            self._awaiting = bool(awaiting)
        self._sync()

    def on_shutdown(self) -> None:
        with self._lock:
            self._run_depth = 0
            self._awaiting = False
        self._sync()  # idle
        self._client.close()


__all__ = ["HerdrReporter", "WORKING", "BLOCKED", "IDLE"]
