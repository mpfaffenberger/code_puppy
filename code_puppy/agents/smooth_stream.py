"""Code Puppy adapters over termflow's steady-rate streaming engine.

The pacing machinery (buffer + adaptive background drain) lives in
``termflow.stream``; this module just wires it to Code Puppy's Rich
console styling, pause controller, and config toggles.

* :class:`ThinkingStreamSmoother` -- drains plain THINKING text (dim)
  through a Rich console.
* :class:`SmoothTermflowWriter` -- file-like proxy that drains
  pre-rendered ANSI markdown (from termflow) with a typewriter feel.
"""

from __future__ import annotations

from typing import Optional, TextIO

from rich.console import Console
from rich.markup import escape
from termflow.stream import SmoothWriter, StreamSmoother, split_by_visible

# Backwards-compatible alias: this helper graduated into termflow.
_split_by_visible = split_by_visible


def _pause_controller_is_paused() -> bool:
    """Best-effort check of the global pause controller.

    Injected into termflow's drainers so streamed output never types
    over the steering prompt.
    """
    try:
        from code_puppy.messaging.pause_controller import get_pause_controller

        return get_pause_controller().is_paused()
    except Exception:
        return False


class ThinkingStreamSmoother(StreamSmoother):
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
            self._emit_styled,
            tick_interval=tick_interval,
            catch_up_seconds=catch_up_seconds,
            min_chars_per_tick=min_chars_per_tick,
            is_paused=_pause_controller_is_paused,
        )
        self._console = console
        self._style = style

    def _emit_styled(self, chunk: str) -> None:
        self._console.print(f"[{self._style}]{escape(chunk)}[/{self._style}]", end="")


class SmoothTermflowWriter(SmoothWriter):
    """ANSI-atomic typewriter wired to Code Puppy's pause controller."""

    def __init__(
        self,
        target: TextIO,
        *,
        tick_interval: float = 0.012,
        catch_up_seconds: float = 0.5,
        min_chars_per_tick: int = 1,
    ) -> None:
        super().__init__(
            target,
            tick_interval=tick_interval,
            catch_up_seconds=catch_up_seconds,
            min_chars_per_tick=min_chars_per_tick,
            is_paused=_pause_controller_is_paused,
        )


def _is_interactive_target(target: TextIO) -> bool:
    """Only a human watching a terminal benefits from typewriter pacing.

    Pipes, files, CI logs and headless ``-p`` captures just pay the drain
    tail (~1s per text part with the default catch-up window) for nothing.
    """
    try:
        return bool(target.isatty())
    except Exception:
        return False


def make_thinking_smoother(console: Console) -> Optional[ThinkingStreamSmoother]:
    """Build a thinking smoother honoring the user's config toggle.

    Returns ``None`` when smoothing is disabled or the console isn't a
    terminal, so callers fall back to printing deltas directly.
    """
    if not _is_interactive_target(console.file):
        return None
    try:
        from code_puppy.config import get_smooth_thinking_stream

        if not get_smooth_thinking_stream():
            return None
    except Exception:
        pass
    return ThinkingStreamSmoother(console)


def make_smooth_termflow_writer(target: TextIO) -> Optional[SmoothTermflowWriter]:
    """Build a smooth termflow writer honoring the user's config toggle.

    Returns ``None`` when response smoothing is disabled or ``target``
    isn't a terminal, so callers fall back to writing straight to ``target``.
    """
    if not _is_interactive_target(target):
        return None
    try:
        from code_puppy.config import get_smooth_response_stream

        if not get_smooth_response_stream():
            return None
    except Exception:
        pass
    return SmoothTermflowWriter(target)
