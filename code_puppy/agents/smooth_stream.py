"""Steady-rate streaming helpers for buttery-smooth terminal output.

Models emit token deltas in bursts: a big lump, a pause, another lump.
Printing each delta the instant it lands makes output stutter and jerk.

This module provides a small ``SteadyDrainer`` base that buffers incoming
content and releases it to the terminal at an *adaptive, consistent* rate via
a background task.  Two flavours ride on top of it:

* :class:`ThinkingStreamSmoother` -- drains plain THINKING text (dim) through
  a Rich console.
* :class:`SmoothTermflowWriter` -- a file-like proxy that drains pre-rendered
  ANSI markdown (from termflow) character-by-character, keeping escape
  sequences atomic so colors never get split mid-code.  This gives the AGENT
  RESPONSE block a sexy typewriter feel. 😎

Adaptive pacing: each tick we release a slice proportional to the backlog,
aiming to fully drain it over a short catch-up window.  Latency stays low when
the model races ahead, while it still feels smooth when it trickles.
"""

from __future__ import annotations

import asyncio
import math
from typing import Optional, TextIO

from rich.console import Console
from rich.markup import escape

# Reuse termflow's battle-tested ANSI matcher so we never split an escape
# sequence (CSI colors, OSC hyperlinks, etc.) across drain ticks.
from termflow.ansi.utils import ANSI_ESCAPE_RE


class SteadyDrainer:
    """Drive a background task that drains a buffer at an adaptive rate.

    Subclasses implement the buffer mechanics via :meth:`_remaining_units`,
    :meth:`_drain_units`, and :meth:`_flush_all`.  A "unit" is whatever the
    subclass counts as one step of progress (e.g. a visible character).
    """

    def __init__(
        self,
        *,
        tick_interval: float = 0.02,
        catch_up_seconds: float = 0.4,
        min_units_per_tick: int = 1,
    ) -> None:
        self._tick = tick_interval
        # Ticks over which we aim to drain the current backlog.
        self._catch_up_ticks = max(1, round(catch_up_seconds / tick_interval))
        self._min_units = max(1, min_units_per_tick)
        self._closed = False
        self._task: Optional[asyncio.Task] = None
        self._pending = ""

    def start(self) -> None:
        """Spin up the background drain task (idempotent)."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        """Mark the stream finished and wait for the buffer to fully drain."""
        self._closed = True
        task, self._task = self._task, None
        if task is None:
            return
        try:
            await task
        except asyncio.CancelledError:
            # We were cancelled while waiting (user interrupt). Make sure
            # the drain task dies with us and nothing prints afterwards.
            task.cancel()
            self._discard_all()
            raise

    def abort(self) -> None:
        """Stop immediately and discard buffered content (user interrupt).

        Unlike :meth:`close`, nothing further is printed: the user asked us
        to stop, so dumping the backlog would just be noise.
        """
        self._closed = True
        self._discard_all()
        task, self._task = self._task, None
        if task is not None:
            task.cancel()

    async def _run(self) -> None:
        try:
            was_paused = self._is_paused()
            while True:
                if self._is_paused():
                    if not was_paused:
                        # Pause just began (user steering). Flush the tail in
                        # ONE atomic write — it lands before the steering
                        # prompt renders, and an empty buffer means close()
                        # returns immediately instead of stalling the agent
                        # pipeline inside the model's HTTP stream (held-open
                        # connections get killed upstream → RemoteProtocolError
                        # on the very next model call).
                        self._flush_all()
                    was_paused = True
                    if self._closed and self._remaining_units() <= 0:
                        return
                    # Anything fed DURING the pause stays silent until resume
                    # so we never type over the steering prompt.
                    await asyncio.sleep(self._tick)
                    continue
                was_paused = False
                remaining = self._remaining_units()
                if remaining <= 0:
                    if self._closed:
                        return
                    await asyncio.sleep(self._tick)
                    continue
                n = max(
                    self._min_units,
                    math.ceil(remaining / self._catch_up_ticks),
                )
                self._drain_units(n)
                await asyncio.sleep(self._tick)
        except asyncio.CancelledError:
            # Cancellation means interrupt/shutdown: stop typing NOW and
            # drop the backlog instead of dumping it into the terminal.
            self._discard_all()
            raise

    def _discard_all(self) -> None:
        """Throw away any buffered content without emitting it."""
        self._pending = ""

    @staticmethod
    def _is_paused() -> bool:
        """Best-effort check of the global pause controller."""
        try:
            from code_puppy.messaging.pause_controller import get_pause_controller

            return get_pause_controller().is_paused()
        except Exception:
            return False

    # ── subclass hooks ─────────────────────────────────────────────────
    def _remaining_units(self) -> int:  # pragma: no cover - abstract
        raise NotImplementedError

    def _drain_units(self, n: int) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def _flush_all(self) -> None:  # pragma: no cover - abstract
        raise NotImplementedError


class ThinkingStreamSmoother(SteadyDrainer):
    """Buffer THINKING deltas and print them at a consistent rate."""

    def __init__(
        self,
        console: Console,
        *,
        style: str = "dim",
        tick_interval: float = 0.02,
        catch_up_seconds: float = 0.4,
        min_chars_per_tick: int = 2,
    ) -> None:
        super().__init__(
            tick_interval=tick_interval,
            catch_up_seconds=catch_up_seconds,
            min_units_per_tick=min_chars_per_tick,
        )
        self._console = console
        self._style = style

    def feed(self, text: str) -> None:
        """Append streamed thinking text to the buffer."""
        if text:
            self._pending += text

    def _remaining_units(self) -> int:
        return len(self._pending)

    def _drain_units(self, n: int) -> None:
        chunk, self._pending = self._pending[:n], self._pending[n:]
        self._emit(chunk)

    def _flush_all(self) -> None:
        if self._pending:
            self._emit(self._pending)
            self._pending = ""

    def _emit(self, chunk: str) -> None:
        self._console.print(f"[{self._style}]{escape(chunk)}[/{self._style}]", end="")


class SmoothTermflowWriter(SteadyDrainer):
    """File-like proxy that types pre-rendered ANSI text out smoothly.

    termflow's ``Renderer`` writes ANSI-styled markdown to this object; the
    background drainer then releases it to ``target`` one visible character at
    a time.  ANSI escape sequences are emitted atomically (and greedily
    attached to the preceding character) so styling never breaks.
    """

    def __init__(
        self,
        target: TextIO,
        *,
        tick_interval: float = 0.012,
        catch_up_seconds: float = 0.5,
        min_chars_per_tick: int = 1,
    ) -> None:
        super().__init__(
            tick_interval=tick_interval,
            catch_up_seconds=catch_up_seconds,
            min_units_per_tick=min_chars_per_tick,
        )
        self._target = target

    # ── file-like interface used by termflow.Renderer ──────────────────
    def write(self, text: str) -> int:
        if text:
            self._pending += text
        return len(text)

    def flush(self) -> None:
        # Real flushing is owned by the drain task; termflow flushes eagerly
        # after every write, but we want to control the cadence ourselves.
        pass

    # ── drainer hooks ──────────────────────────────────────────────────
    def _remaining_units(self) -> int:
        # Count visible chars from the live buffer so escape sequences split
        # across write() boundaries can't desync a cached counter.
        return len(ANSI_ESCAPE_RE.sub("", self._pending))

    def _drain_units(self, n: int) -> None:
        emit, rest, _ = _split_by_visible(self._pending, n)
        if not emit:
            return
        self._pending = rest
        self._target.write(emit)
        self._target.flush()

    def _flush_all(self) -> None:
        if self._pending:
            self._target.write(self._pending)
            self._target.flush()
            self._pending = ""


def _split_by_visible(s: str, budget: int) -> tuple[str, str, int]:
    """Split ``s`` after ``budget`` visible chars, keeping ANSI codes atomic.

    Returns ``(emit, rest, consumed_visible)`` where ``emit`` contains exactly
    ``consumed_visible`` visible characters plus any ANSI escape sequences that
    surround them (trailing escapes are greedily attached so style-off codes
    flush together with their text).
    """
    i = 0
    consumed = 0
    n = len(s)
    while i < n and consumed < budget:
        m = ANSI_ESCAPE_RE.match(s, i)
        if m:
            i = m.end()
        else:
            i += 1
            consumed += 1
    # Greedily attach any trailing escape sequences.
    while True:
        m = ANSI_ESCAPE_RE.match(s, i)
        if not m:
            break
        i = m.end()
    return s[:i], s[i:], consumed


def make_thinking_smoother(console: Console) -> Optional[ThinkingStreamSmoother]:
    """Build a thinking smoother honoring the user's config toggle.

    Returns ``None`` when smoothing is disabled, so callers fall back to
    printing deltas directly.
    """
    try:
        from code_puppy.config import get_smooth_thinking_stream

        if not get_smooth_thinking_stream():
            return None
    except Exception:
        pass
    return ThinkingStreamSmoother(console)


def make_smooth_termflow_writer(target: TextIO) -> Optional[SmoothTermflowWriter]:
    """Build a smooth termflow writer honoring the user's config toggle.

    Returns ``None`` when response smoothing is disabled, so callers fall back
    to writing straight to ``target``.
    """
    try:
        from code_puppy.config import get_smooth_response_stream

        if not get_smooth_response_stream():
            return None
    except Exception:
        pass
    return SmoothTermflowWriter(target)
