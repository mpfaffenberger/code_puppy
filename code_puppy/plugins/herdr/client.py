"""Fire-and-forget client for the herdr pane socket.

herdr (https://herdr.dev) is a terminal workspace manager for coding
agents. When code-puppy runs inside a herdr pane, herdr injects three
environment variables:

* ``HERDR_ENV=1``          -- marks the pane as herdr-managed
* ``HERDR_SOCKET_PATH``    -- path to herdr's local control socket
* ``HERDR_PANE_ID``        -- the pane this process owns (e.g. ``w1:p1``)

This module speaks herdr's newline-delimited JSON socket protocol just
far enough to call ``pane.report_agent`` / ``pane.report_agent_session``.
It reads herdr's ack (and retries a few times if it doesn't come) so an
authoritative state edge is never silently lost, but it never raises into
the caller: reporting agent state must never be able to disturb the agent
itself. Delivery happens on a single daemon worker thread so the (sync)
permission hot-path and the async run loop both enqueue in O(1) and move
on.

Windows named-pipe transport is intentionally out of scope; herdr's
Windows build is beta and ``AF_UNIX`` is the contract everywhere else.
When the socket is unavailable the client is simply inactive.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import socket
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: source tag herdr attributes these reports to. The ``herdr:`` prefix is
#: the convention herdr uses for its own official integrations.
SOURCE = "herdr:codepuppy"
#: agent label; must match herdr's ``agent_label(Agent::CodePuppy)``.
AGENT = "codepuppy"

_CONNECT_TIMEOUT_S = 0.5
_QUEUE_MAX = 256

# Delivery is retried until herdr acks, because a silently-dropped report
# strands the pane on a stale state (a lost ``working`` shows idle mid-turn; a
# lost ``idle`` shows working after a Ctrl+C). Retrying the *same* envelope is
# safe: herdr dedupes on ``seq`` (rejects seq <= last_seq), so a report that
# already applied is harmlessly ignored on the retry.
_SEND_ATTEMPTS = 3
_SEND_BACKOFF_S = 0.05
_ACK_BYTES = 4096


class HerdrClient:
    """Enqueues agent-state reports and drains them on a worker thread."""

    def __init__(
        self,
        socket_path: Optional[str] = None,
        pane_id: Optional[str] = None,
    ) -> None:
        self._socket_path = socket_path or os.environ.get("HERDR_SOCKET_PATH")
        self._pane_id = pane_id or os.environ.get("HERDR_PANE_ID")
        self._active = bool(
            os.environ.get("HERDR_ENV") == "1"
            and self._socket_path
            and self._pane_id
            and hasattr(socket, "AF_UNIX")
        )
        self._queue: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue(
            maxsize=_QUEUE_MAX
        )
        self._seq_lock = threading.Lock()
        # Monotonic, process-unique sequence. herdr uses seq to discard
        # out-of-order reports, so it must only ever increase.
        self._seq = int(time.time() * 1000) * 1000
        self._worker: Optional[threading.Thread] = None
        if self._active:
            self._start_worker()

    @property
    def active(self) -> bool:
        return self._active

    def _start_worker(self) -> None:
        self._worker = threading.Thread(
            target=self._run,
            name="herdr-reporter",
            daemon=True,
        )
        self._worker.start()

    def _next_seq(self) -> int:
        with self._seq_lock:
            self._seq += 1
            return self._seq

    def _enqueue(self, method: str, params: Dict[str, Any]) -> None:
        if not self._active:
            return
        envelope = {
            "id": f"{SOURCE}:{self._next_seq()}",
            "method": method,
            "params": {
                "pane_id": self._pane_id,
                "source": SOURCE,
                "agent": AGENT,
                "seq": self._next_seq(),
                **params,
            },
        }
        try:
            self._queue.put_nowait(envelope)
        except queue.Full:
            # State is edge-triggered and deduped upstream; dropping a
            # report under extreme backpressure is harmless (herdr keeps
            # the last state it saw).
            logger.debug("herdr report queue full; dropping report")

    def report_state(self, state: str, agent_session_id: Optional[str] = None) -> None:
        """Report a semantic state: ``working`` / ``blocked`` / ``idle``."""
        params: Dict[str, Any] = {"state": state}
        if agent_session_id:
            params["agent_session_id"] = agent_session_id
        self._enqueue("pane.report_agent", params)

    def report_session(self, agent_session_id: str) -> None:
        """Report native session identity so herdr can restore context."""
        if not agent_session_id:
            return
        self._enqueue(
            "pane.report_agent_session",
            {"agent_session_id": agent_session_id},
        )

    def close(self) -> None:
        """Signal the worker to drain and stop. Best-effort, non-blocking."""
        if not self._active:
            return
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

    def _run(self) -> None:
        while True:
            envelope = self._queue.get()
            if envelope is None:
                return
            self._send(envelope)

    def _send(self, envelope: Dict[str, Any]) -> None:
        payload = (json.dumps(envelope) + "\n").encode("utf-8")
        last_exc: Optional[Exception] = None
        for attempt in range(_SEND_ATTEMPTS):
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                    sock.settimeout(_CONNECT_TIMEOUT_S)
                    sock.connect(self._socket_path)  # type: ignore[arg-type]
                    sock.sendall(payload)
                    # Read the ack so a report is only considered delivered
                    # once herdr has actually taken it. No ack (closed or
                    # timed-out) means it may not have applied -> retry.
                    if sock.recv(_ACK_BYTES):
                        return
            except (OSError, ValueError) as exc:
                last_exc = exc
            if attempt + 1 < _SEND_ATTEMPTS:
                time.sleep(_SEND_BACKOFF_S)
        # herdr may have exited or the pane was closed. Nothing left to do but
        # note it on the diagnostic channel -- never raise into the agent.
        logger.debug(
            "herdr report undelivered after %d attempts: %s",
            _SEND_ATTEMPTS,
            last_exc,
        )


__all__ = ["HerdrClient", "SOURCE", "AGENT"]
