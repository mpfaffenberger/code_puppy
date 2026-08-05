r"""Fire-and-forget client for the herdr pane socket.

herdr (https://herdr.dev) is a terminal workspace manager for coding
agents. When code-puppy runs inside a herdr pane, herdr injects three
environment variables:

* ``HERDR_ENV=1``          -- marks the pane as herdr-managed
* ``HERDR_SOCKET_PATH``    -- path to herdr's local control socket
* ``HERDR_PANE_ID``        -- the pane this process owns (e.g. ``w1:p1``)

This module speaks herdr's newline-delimited JSON socket protocol far
enough to call ``pane.report_agent`` / ``pane.report_agent_session`` /
``pane.report_metadata`` / ``pane.release_agent``. It reads herdr's ack
(and retries a few times if it doesn't come) so an authoritative state
edge is never silently lost, but it never raises into the caller:
reporting agent state must never be able to disturb the agent itself.

Delivery runs on a single daemon worker thread fed by **coalescing
mailbox slots** rather than an unbounded queue:

* **Critical lane** -- state transitions, session references, and the
  final release. The worker drains these first.
* **Decorative lane** -- message-only state refreshes and pane metadata.
  These may be replaced by newer decorative work, and they are discarded
  entirely once a release is scheduled.

Each slot keeps only its newest value, so memory is bounded and the pane
always converges on the latest authoritative facts. Request ``id`` and
``seq`` are assigned immediately before the first wire attempt, so wire
order stays monotonic even when critical work overtakes decorative work;
retries reuse the same serialized envelope (herdr dedupes on ``seq``).

Transport is ``AF_UNIX`` everywhere it exists. On Windows (where CPython
still has no ``socket.AF_UNIX``), herdr's build -- via Rust's
``interprocess`` crate -- maps the file-style ``HERDR_SOCKET_PATH`` onto a
named pipe whose name *is* the full path (``\\.\pipe\C:\...\herdr.sock``),
so plain stdlib file I/O on that pipe path gives the same bidirectional
byte stream. When neither transport is available the client is simply
inactive.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

#: source tag herdr attributes these reports to. The ``herdr:`` prefix is
#: the convention herdr uses for its own official integrations.
SOURCE = "herdr:codepuppy"
#: agent label; must match herdr's ``agent_label(Agent::CodePuppy)``.
AGENT = "codepuppy"

_CONNECT_TIMEOUT_S = 0.5

# Delivery is retried until herdr acks, because a silently-dropped critical
# report strands the pane on a stale state (a lost ``working`` shows idle
# mid-turn; a lost ``idle`` shows working after a Ctrl+C). Retrying the *same*
# envelope is safe: herdr dedupes on ``seq`` (rejects seq <= last_seq), so a
# report that already applied is harmlessly ignored on the retry.
_SEND_ATTEMPTS = 3
_SEND_BACKOFF_S = 0.05
_ACK_BYTES = 4096

#: Pane metadata TTL (24h). herdr clears stale token/model values after this
#: window, which bounds how long an abrupt process death can leave stale
#: numbers on the sidebar.
_METADATA_TTL_MS = 86_400_000

# herdr request methods.
_M_STATE = "pane.report_agent"
_M_SESSION = "pane.report_agent_session"
_M_METADATA = "pane.report_metadata"
_M_RELEASE = "pane.release_agent"


class HerdrClient:
    """Coalescing, two-lane reporter drained on a single worker thread."""

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
            and (hasattr(socket, "AF_UNIX") or os.name == "nt")
        )

        # One condition guards every mailbox slot and the lifecycle flags.
        self._cond = threading.Condition()
        # Critical lane (latest-wins). ``None`` == empty.
        self._state: Optional[Dict[str, Any]] = None
        self._session: Optional[Dict[str, Any]] = None
        # Decorative lane (latest-wins, discarded on release).
        self._message: Optional[Dict[str, Any]] = None
        self._metadata: Optional[Dict[str, Any]] = None
        # Terminal release slot.
        self._release: Optional[Dict[str, Any]] = None

        self._closing = False
        self._release_scheduled = False
        self._released = threading.Event()

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

    # -- public API ----------------------------------------------------

    def report_state(
        self,
        state: str,
        agent_session_id: Optional[str] = None,
        *,
        message: Optional[str] = None,
        critical: bool = True,
    ) -> None:
        """Report a semantic state (``working`` / ``blocked`` / ``idle``).

        A genuine state *edge* is ``critical`` (default) and jumps the queue.
        A message-only refresh (same state, new activity text) should pass
        ``critical=False`` so it rides the decorative lane and can never
        delay an authoritative edge, session reference, or release.
        """
        params: Dict[str, Any] = {"state": state}
        if agent_session_id:
            params["agent_session_id"] = agent_session_id
        if message:
            params["message"] = message
        self._put("_state" if critical else "_message", params)

    def report_session(
        self,
        agent_session_id: Optional[str] = None,
        session_path: Optional[str] = None,
    ) -> None:
        """Report a stable session reference (critical lane)."""
        params: Dict[str, Any] = {}
        if agent_session_id:
            params["agent_session_id"] = agent_session_id
        if session_path:
            params["agent_session_path"] = session_path
        if not params:
            return
        self._put("_session", params)

    def report_metadata(self, tokens: Dict[str, Any]) -> None:
        """Report pane metadata (model / context / tokens) on the decorative lane."""
        if not tokens:
            return
        params: Dict[str, Any] = {
            "applies_to_source": SOURCE,
            "ttl_ms": _METADATA_TTL_MS,
            "tokens": dict(tokens),
        }
        self._put("_metadata", params)

    def _put(self, slot: str, params: Dict[str, Any]) -> None:
        if not self._active:
            return
        with self._cond:
            # Once a release is scheduled the pane is shutting down; refuse
            # new work so the release stays the final wire event.
            if self._closing:
                return
            setattr(self, slot, params)
            self._cond.notify()

    def release_and_close(self, timeout_s: float = 1.0) -> None:
        """Schedule one ``pane.release_agent`` and wait up to ``timeout_s``.

        Idempotent: repeated calls schedule a single release. Stops
        decorative input, discards pending decorative work, lets any pending
        critical work flush, then releases. The wait is bounded on the
        caller side, so an unavailable herdr can never exceed ``timeout_s``.
        """
        if not self._active:
            return
        self._schedule_release()
        self._released.wait(timeout=timeout_s)

    def close(self) -> None:
        """Best-effort, non-blocking shutdown: schedule the release and return."""
        if not self._active:
            return
        self._schedule_release()

    def _schedule_release(self) -> None:
        with self._cond:
            if self._release_scheduled:
                return
            self._release_scheduled = True
            self._closing = True
            # Decorative work is not worth delaying shutdown for.
            self._message = None
            self._metadata = None
            self._release = {}  # release_agent needs only the base params
            self._cond.notify()

    # -- worker --------------------------------------------------------

    def _take_next_locked(self) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Pop the next job by priority. Caller holds ``self._cond``.

        Order: critical state -> critical session -> (decorative message ->
        decorative metadata, only while not closing) -> terminal release.
        Critical work therefore always overtakes decorative work, and the
        release is only taken once the critical lane is drained.
        """
        if self._state is not None:
            params, self._state = self._state, None
            return _M_STATE, params
        if self._session is not None:
            params, self._session = self._session, None
            return _M_SESSION, params
        if not self._closing:
            if self._message is not None:
                params, self._message = self._message, None
                return _M_STATE, params
            if self._metadata is not None:
                params, self._metadata = self._metadata, None
                return _M_METADATA, params
        if self._closing and self._release is not None:
            params, self._release = self._release, None
            return _M_RELEASE, params
        return None

    def _run(self) -> None:
        while True:
            with self._cond:
                job = self._take_next_locked()
                while job is None:
                    if self._closing:
                        # Nothing left and shutting down -> unblock waiters.
                        self._released.set()
                        return
                    self._cond.wait()
                    job = self._take_next_locked()
                method, params = job
            self._send(method, params)
            if method == _M_RELEASE:
                self._released.set()
                return

    def _send(self, method: str, params: Dict[str, Any]) -> None:
        # Assign id + seq at wire time so critical work that overtook
        # decorative work still gets a higher (later) sequence number.
        seq = self._next_seq()
        envelope = {
            "id": f"{SOURCE}:{seq}",
            "method": method,
            "params": {
                "pane_id": self._pane_id,
                "source": SOURCE,
                "agent": AGENT,
                "seq": seq,
                **params,
            },
        }
        payload = (json.dumps(envelope) + "\n").encode("utf-8")
        last_exc: Optional[Exception] = None
        for attempt in range(_SEND_ATTEMPTS):
            try:
                if self._deliver(payload):
                    return
            except (OSError, ValueError) as exc:
                last_exc = exc
            if attempt + 1 < _SEND_ATTEMPTS:
                time.sleep(_SEND_BACKOFF_S)
        # herdr may have exited or the pane was closed. Nothing left to do but
        # note it on the diagnostic channel -- never raise into the agent.
        logger.debug(
            "herdr %s undelivered after %d attempts: %s",
            method,
            _SEND_ATTEMPTS,
            last_exc,
        )

    def _deliver(self, payload: bytes) -> bool:
        """One wire attempt. ``True`` means herdr acked the report.

        Any nonempty response is an ack: herdr already treats the report as
        taken (even a busy ``shown:false`` reply). No bytes (closed /
        timed-out) means it may not have applied -> caller retries the
        identical envelope.
        """
        if os.name == "nt":
            return self._deliver_pipe(payload)
        return self._deliver_unix(payload)

    def _deliver_unix(self, payload: bytes) -> bool:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(_CONNECT_TIMEOUT_S)
            sock.connect(self._socket_path)  # type: ignore[arg-type]
            sock.sendall(payload)
            return bool(sock.recv(_ACK_BYTES))

    def _deliver_pipe(self, payload: bytes) -> bool:
        # herdr's Windows build (Rust ``interprocess`` crate) exposes the
        # named pipe ``\\.\pipe\<full HERDR_SOCKET_PATH>``; the .sock file
        # itself is just a pid marker. CreateFile fails fast when herdr is
        # gone (OSError -> retry lane). The ack read has no timeout, but
        # replies are immediate in practice, the worker is a daemon thread,
        # and ``release_and_close`` is caller-bounded, so a wedged herdr
        # cannot hang the agent or its shutdown.
        pipe_name = "\\\\.\\pipe\\" + str(self._socket_path)
        with open(pipe_name, "r+b", buffering=0) as pipe:
            pipe.write(payload)
            return bool(pipe.readline(_ACK_BYTES))


__all__ = ["HerdrClient", "SOURCE", "AGENT"]
