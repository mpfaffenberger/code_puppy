"""Map code-puppy lifecycle events onto herdr's three semantic states.

herdr models every agent as ``working`` / ``blocked`` / ``idle``. This
reporter is the single writer of that state for the pane, so it keeps the
edge-triggering and arbitration rules in one place:

* **working**  -- a top-level run or a tool call is in flight.
* **blocked**  -- code-puppy is waiting on the human (permission prompt,
  ``ask_user_question``). This is best-effort: not every interactive
  prompt routes through a callback (shell-command approval does not), so
  herdr's screen manifest remains the authority that can override a stale
  ``working`` when a prompt is visible. We deliberately do **not** claim
  herdr full-lifecycle authority for exactly this reason.
* **idle**     -- the turn handed control back to the human.

Sub-agents fire the same ``agent_run_start`` / ``agent_run_end`` hooks as
the root agent, so a naive "end == idle" mapping would flip the pane idle
while the root run is still going. We refcount active runs (the same
pattern the puppy_spinner plugin uses) and only trust the interactive
turn boundary for idle.
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
        self._last_state: Optional[str] = None
        self._session_id: Optional[str] = None

    @property
    def active(self) -> bool:
        return self._client.active

    # -- state emission -------------------------------------------------

    def _emit(self, state: str) -> None:
        """Send *state* only when it changes (edge-triggered)."""
        with self._lock:
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
        self._emit(IDLE)

    def on_user_prompt(self, session_id: Optional[str] = None) -> None:
        self._remember_session(session_id)
        self._emit(WORKING)

    def on_run_start(self, session_id: Optional[str] = None) -> None:
        self._remember_session(session_id)
        with self._lock:
            self._run_depth += 1
        self._emit(WORKING)

    def on_run_end(self, session_id: Optional[str] = None) -> None:
        self._remember_session(session_id)
        with self._lock:
            self._run_depth = max(0, self._run_depth - 1)
            depth = self._run_depth
        # Only the outermost run finishing means the model stopped. The
        # interactive turn boundary is the true idle signal, but headless
        # (`-p`) runs never fire it, so falling idle at depth 0 keeps
        # non-interactive panes honest too.
        if depth == 0:
            self._emit(IDLE)

    def on_run_cancel(self) -> None:
        with self._lock:
            self._run_depth = 0
        self._emit(IDLE)

    def on_turn_end(self) -> None:
        with self._lock:
            self._run_depth = 0
        self._emit(IDLE)

    def on_tool_call(self, tool_name: str) -> None:
        # ask_user_question parks the agent on the human -> blocked.
        # Everything else is active work.
        if tool_name == "ask_user_question":
            self._emit(BLOCKED)
        else:
            self._emit(WORKING)

    def on_tool_done(self) -> None:
        # A tool completing means we are moving again (this is also what
        # clears a blocked ask_user_question / a resolved file prompt).
        self._emit(WORKING)

    def on_permission_prompt(self) -> None:
        self._emit(BLOCKED)

    def on_shutdown(self) -> None:
        self._emit(IDLE)
        self._client.close()


__all__ = ["HerdrReporter", "WORKING", "BLOCKED", "IDLE"]
