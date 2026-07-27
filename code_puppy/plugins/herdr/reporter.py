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
from typing import Optional, Tuple

from .client import HerdrClient
from . import sources

logger = logging.getLogger(__name__)

WORKING = "working"
BLOCKED = "blocked"
IDLE = "idle"

# Decorative activity strings (the ``message`` field on ``pane.report_agent``).
# State stays authoritative; these are best-effort colour commentary.
THINKING = "thinking"
AWAITING = "awaiting input"


class HerdrReporter:
    """Thread-safe, dedup-ing bridge from callbacks to :class:`HerdrClient`."""

    def __init__(self, client: HerdrClient) -> None:
        self._client = client
        self._lock = threading.Lock()
        self._run_depth = 0
        self._awaiting = False
        self._awaiting_notify = True
        self._last_reported_state: Optional[str] = None
        self._last_reported_message: Optional[str] = None
        # Latest working activity (``thinking`` / ``running <tool>``). Only
        # surfaces while WORKING; BLOCKED and IDLE derive their own message.
        self._activity: Optional[str] = None
        # Durable session reference (name, pickle_path) -- NOT the per-run
        # group_id UUID, which changes every turn and can't identify a
        # resumable session.
        self._session_ref: Optional[Tuple[str, str]] = None

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

    def _message_for_locked(self, state: str) -> Optional[str]:
        """Derive the decorative message for a state. Caller holds lock."""
        if state == BLOCKED:
            return AWAITING
        if state == WORKING:
            return self._activity or THINKING
        return None

    def _sync(self) -> None:
        """Report a changed (state, message) pair, optionally suppressing blocked.

        A genuine state edge rides the critical lane; a message-only change
        (same state, new activity) rides the decorative lane so it can never
        delay an authoritative edge. User-initiated menus retain
        ``notify=False`` for their whole lifetime: their internal ``blocked``
        state must not touch the edge trackers, so closing the menu does not
        re-send an unchanged state.
        """
        with self._lock:
            state = self._recompute_locked()
            if state == BLOCKED and not self._awaiting_notify:
                return
            message = self._message_for_locked(state)
            state_changed = state != self._last_reported_state
            message_changed = message != self._last_reported_message
            if not state_changed and not message_changed:
                return
            self._last_reported_state = state
            self._last_reported_message = message
            session_id = self._session_ref[0] if self._session_ref else None
            critical = state_changed
        self._client.report_state(state, session_id, message=message, critical=critical)

    def _refresh_session(self) -> None:
        """Resolve the durable session reference and report it on change.

        Ignores per-run group_ids entirely. Resolution happens OUTSIDE the
        lock (guardrail). The next prompt after ``/clear``, ``/session new``,
        ``/autosave_load``, ``/load_context``, a quick resume, or an agent
        switch refreshes herdr with no core session callback.
        """
        ref = sources.current_session_ref()
        if ref is None:
            return
        with self._lock:
            changed = ref != self._session_ref
            self._session_ref = ref
        if changed:
            self._client.report_session(ref[0], ref[1])

    # -- lifecycle handlers (all sync; safe from async or worker threads) --

    def on_startup(self) -> None:
        self._sync()  # depth 0, not awaiting -> idle

    def on_user_prompt(self, *_ignored) -> None:
        # Ignore the callback's per-run group_id; resolve the durable session.
        self._refresh_session()

    def on_run_start(self, *_ignored) -> None:
        with self._lock:
            self._run_depth += 1
            # The OUTER run starting is the canonical "thinking" edge. Nested
            # sub-agent runs keep whatever activity is already showing.
            if self._run_depth == 1:
                self._activity = THINKING
        self._sync()

    def on_run_end(self, *_ignored) -> None:
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
            self._activity = None
        self._sync()

    def on_tool_start(self, tool_name: str) -> None:
        """A tool call started -> decorative ``running <tool>`` activity."""
        # Resolve the message OUTSIDE the lock (guardrail: reporter locks
        # never cover source resolution).
        activity = sources.activity_message(tool_name)
        with self._lock:
            self._activity = activity
        self._sync()

    def on_tool_complete(self) -> None:
        """A tool call finished -> back to ``thinking`` while the run continues."""
        with self._lock:
            self._activity = THINKING
        self._sync()

    def on_turn_end(self) -> None:
        with self._lock:
            self._run_depth = 0
            self._awaiting = False
            self._activity = None
        self._sync()
        # A completed interactive turn is the canonical place to refresh pane
        # metadata: the token payload is computed once, OUTSIDE the reporter
        # lock, and enqueued on the decorative lane. Sending every turn also
        # refreshes the metadata TTL even when the formatted values are
        # unchanged. Tool callbacks and blocked edges do no token math.
        self._emit_metadata()

    def _emit_metadata(self) -> None:
        """Compute and enqueue pane metadata. Never holds the reporter lock."""
        payload = sources.current_tokens_payload()
        if payload:
            self._client.report_metadata(payload)

    def on_awaiting_user_input(self, awaiting: bool, *, notify: bool = True) -> None:
        """Track an interactive wait, notifying only when requested."""
        with self._lock:
            self._awaiting = bool(awaiting)
            self._awaiting_notify = bool(notify)
        self._sync()

    def on_shutdown(self) -> None:
        # Release pane authority directly -- no intermediate idle report.
        # release_and_close() is idempotent and bounded, so calling it from
        # both session_end and shutdown (and against an unavailable herdr)
        # can never delay process exit.
        self._client.release_and_close()


__all__ = ["HerdrReporter", "WORKING", "BLOCKED", "IDLE", "THINKING", "AWAITING"]
