"""Smooth, rate-limited rendering for streaming THINKING blocks.

Models emit thinking-token deltas in bursts: a big lump, a pause, another
lump.  Printing each delta the instant it lands makes the THINKING block
stutter and jerk across the screen.

This module buffers incoming deltas and drains them to the console at a
steady cadence via a background task, so the thinking text scrolls smoothly
no matter how lumpy the upstream delivery is.

The drain rate is *adaptive*: each tick we emit a slice proportional to how
much is buffered, aiming to fully drain the current backlog over a short
catch-up window.  That keeps latency low when the model races ahead while
still feeling buttery when it trickles.
"""

from __future__ import annotations

import asyncio
import math
from typing import Optional

from rich.console import Console
from rich.markup import escape


class ThinkingStreamSmoother:
    """Buffer thinking deltas and print them at a consistent rate.

    Usage::

        smoother = ThinkingStreamSmoother(console)
        smoother.start()
        smoother.feed("some thinking text")
        ...
        await smoother.close()  # drains the remainder, then stops
    """

    def __init__(
        self,
        console: Console,
        *,
        style: str = "dim",
        tick_interval: float = 0.02,
        catch_up_seconds: float = 0.4,
        min_chars_per_tick: int = 2,
    ) -> None:
        """Create a smoother.

        Args:
            console: Rich console to print to.
            style: Rich style wrapped around each emitted chunk.
            tick_interval: Seconds between drain ticks (drain "framerate").
            catch_up_seconds: Target window to fully drain the current buffer.
                Smaller = snappier/less buffered; larger = smoother/laggier.
            min_chars_per_tick: Floor on characters emitted per tick so the
                stream always keeps creeping forward.
        """
        self._console = console
        self._style = style
        self._tick = tick_interval
        # Number of ticks over which we aim to drain the current backlog.
        self._catch_up_ticks = max(1, round(catch_up_seconds / tick_interval))
        self._min_chars = max(1, min_chars_per_tick)

        self._pending = ""
        self._closed = False
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """Spin up the background drain task (idempotent)."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    def feed(self, text: str) -> None:
        """Append streamed thinking text to the buffer."""
        if text:
            self._pending += text

    async def close(self) -> None:
        """Mark the stream finished and wait for the buffer to fully drain."""
        self._closed = True
        if self._task is not None:
            try:
                await self._task
            finally:
                self._task = None

    # ── internals ──────────────────────────────────────────────────────

    async def _run(self) -> None:
        """Drain the buffer at a steady, adaptive cadence."""
        try:
            while True:
                if not self._pending:
                    if self._closed:
                        return
                    await asyncio.sleep(self._tick)
                    continue

                # Emit a slice proportional to backlog so we drain it over
                # ~catch_up_ticks, with a floor to keep things moving.
                n = max(
                    self._min_chars,
                    math.ceil(len(self._pending) / self._catch_up_ticks),
                )
                chunk, self._pending = self._pending[:n], self._pending[n:]
                self._emit(chunk)
                await asyncio.sleep(self._tick)
        except asyncio.CancelledError:
            # Don't lose buffered thinking on cancellation -- flush it.
            if self._pending:
                self._emit(self._pending)
                self._pending = ""
            raise

    def _emit(self, chunk: str) -> None:
        escaped = escape(chunk)
        self._console.print(f"[{self._style}]{escaped}[/{self._style}]", end="")


def make_thinking_smoother(console: Console) -> Optional[ThinkingStreamSmoother]:
    """Build a smoother honoring the user's config toggle.

    Returns ``None`` when smoothing is disabled, so callers can fall back to
    printing deltas directly.
    """
    try:
        from code_puppy.config import get_smooth_thinking_stream

        if not get_smooth_thinking_stream():
            return None
    except Exception:
        # Config unavailable for some reason -- default to smoothing on.
        pass

    return ThinkingStreamSmoother(console)
