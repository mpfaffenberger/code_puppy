"""Best-effort asynchronous writer for boot-trace events.

Producers only append to a bounded in-memory queue under a short lock; one
daemon writer thread owns every blocking operation (open, encode, os.write).
A stalled or broken sink can therefore lose trace events or delay exit by at most
the bounded drain wait in ``Sink.request_stop``, never hang boot.

Called by: boot_trace :: _create_recorder()
"""

import json
import os
import sys
import threading
import time
from collections import deque

MAX_QUEUE = 512
MAX_LINE = 2048
DRAIN_TIMEOUT_S = 0.25
STDERR_PREFIX = b"CODE_PUPPY_BOOT_TRACE "


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        try:
            written = os.write(fd, view)
        except BlockingIOError:
            # Someone else set O_NONBLOCK on the shared stderr description;
            # we never change it, so just wait for the reader.
            time.sleep(0.01)
            continue
        if written <= 0:
            raise OSError("boot trace sink accepted no bytes")
        view = view[written:]


def _open(target: str) -> tuple[int, bytes]:
    """Return ``(fd, line_prefix)``; raises on anything unusable."""
    if target == "stderr":
        stderr_fd = sys.stderr.fileno()
        if stderr_fd in (0, 1):
            raise ValueError("stderr must not alias stdin/stdout")
        return os.dup(stderr_fd), STDERR_PREFIX
    if not os.path.isabs(target):
        raise ValueError("file sink needs an absolute path")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    return os.open(target, flags, 0o600), b""


class Sink:
    """Sequence/span-id allocator plus lossy FIFO queue feeding one writer thread."""

    def __init__(self, target: str, *, boot_id: str, t0_ns: int) -> None:
        self._target = target
        self._boot_id = boot_id
        self._t0_ns = t0_ns
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._queue: deque[tuple[int, dict]] = deque()
        self._seq = 0
        self._span_counter = 0
        self._dropped = 0
        self._dropped_reported = 0
        self._stopped = False
        self._disabled = False
        self._thread: threading.Thread | None = None
        self._drain_waited = False
        try:
            thread = threading.Thread(
                target=self._run, name="boot-trace-writer", daemon=True
            )
            thread.start()
            self._thread = thread
        except Exception:
            self._disabled = True

    def next_span_id(self) -> str:
        with self._lock:
            self._span_counter += 1
            return format(self._span_counter, "x")

    def offer(self, event: dict) -> None:
        """Queue a semantic event (everything except ``seq``); never blocks."""
        if not isinstance(event, dict):
            self.record_drop()
            return
        with self._cond:
            if self._disabled or self._stopped:
                return
            self._seq += 1  # consumed even when the event is dropped below
            if len(self._queue) >= MAX_QUEUE:
                self._dropped += 1
                return
            self._queue.append((self._seq, event))
            self._cond.notify()

    def record_drop(self) -> None:
        """Count an event the producer rejected before it reached ``offer``."""
        with self._cond:
            if self._disabled or self._stopped:
                return
            self._seq += 1
            self._dropped += 1
            self._cond.notify()

    def request_stop(self, timeout: float = DRAIN_TIMEOUT_S) -> None:
        """Ask the writer to drain, then wait at most ``timeout`` in total.

        The wait keeps the root ``boot`` terminal (always the queue tail) from
        being lost when a short-lived run exits; a stalled sink still can't hold
        boot longer than ``timeout``, however many callers stop us.
        """
        with self._cond:
            self._stopped = True
            self._cond.notify_all()
            thread = self._thread
            if self._drain_waited or thread is None:
                return
            self._drain_waited = True
        if thread is not threading.current_thread():
            thread.join(timeout)

    def _append_drop_mark_locked(self) -> None:
        if self._dropped == self._dropped_reported or len(self._queue) >= MAX_QUEUE:
            return
        self._seq += 1
        self._span_counter += 1
        self._dropped_reported = self._dropped
        self._queue.append(
            (
                self._seq,
                {
                    "phase": "boot.dropped",
                    "span": format(self._span_counter, "x"),
                    "kind": "mark",
                    "tMonoMs": round((time.monotonic_ns() - self._t0_ns) / 1e6, 3),
                    "tWallMs": time.time_ns() // 1_000_000,
                    "attrs": {},
                    "dropped": self._dropped,
                },
            )
        )

    def _next_item(self) -> tuple[int, dict] | None:
        with self._cond:
            while True:
                if self._queue:
                    item = self._queue.popleft()
                    self._append_drop_mark_locked()  # the freed tail slot
                    return item
                if self._dropped != self._dropped_reported:
                    self._append_drop_mark_locked()
                    continue
                if self._stopped or self._disabled:
                    return None
                self._cond.wait()

    def _reject_in_writer(self) -> None:
        # The event already owns a seq; only the cumulative count grows.
        with self._cond:
            self._dropped += 1
            self._append_drop_mark_locked()

    def _disable(self) -> None:
        with self._cond:
            self._disabled = True
            self._queue.clear()
            self._cond.notify_all()

    def _encode(self, seq: int, event: dict, prefix: bytes) -> bytes | None:
        record = {"v": 1, "bootId": self._boot_id, "seq": seq}
        try:
            record.update(event)
            record["seq"] = seq
            body = json.dumps(
                record, ensure_ascii=True, allow_nan=False, separators=(",", ":")
            ).encode("ascii")
        except Exception:
            return None
        line = prefix + body + b"\n"
        return line if len(line) <= MAX_LINE else None

    def _run(self) -> None:
        try:
            fd, prefix = _open(self._target)
        except Exception:
            self._disable()
            return
        try:
            while True:
                item = self._next_item()
                if item is None:
                    return
                line = self._encode(item[0], item[1], prefix)
                if line is None:
                    self._reject_in_writer()
                else:
                    _write_all(fd, line)
        except Exception:
            self._disable()
        finally:
            os.close(fd)
