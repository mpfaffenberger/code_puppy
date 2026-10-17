"""Rich ``Console`` that keeps rendering from killing the run on a dead handle."""

from __future__ import annotations

from typing import IO, Optional

from rich.console import Console

from code_puppy.messaging.safe_stream import (
    SafeTextStream,
    ensure_safe_text_stream,
    is_dead_handle_error,
)


class SafeConsole(Console):
    """Console that goes silent after its output handle dies.

    ``_check_buffer`` is the one render entry point shared by every supported
    Rich version, including the legacy-Windows renderer that bypasses
    ``file.write``. ``file`` is wrapped lazily rather than once at construction
    because Rich resolves ``sys.stdout`` on each access when no file is given,
    and the transcript guard swaps ``sys.stdout`` at runtime.

    The latch is permanent for the console's lifetime and, once set, nothing
    is rendered or recorded. Pending segments are only discarded at the
    outermost buffer level so ``capture()`` and nested ``with console:`` blocks
    keep their content.
    """

    _dead = False
    _safe_view: Optional[tuple[IO[str], SafeTextStream]] = None

    @property
    def file(self) -> IO[str]:
        raw = Console.file.fget(self)  # type: ignore[attr-defined]
        cached = self._safe_view
        if cached is not None and cached[0] is raw:
            return cached[1]  # type: ignore[return-value]
        safe = ensure_safe_text_stream(raw)
        self._safe_view = (raw, safe)  # type: ignore[assignment]
        return safe  # type: ignore[return-value]

    @file.setter
    def file(self, new_file: IO[str]) -> None:
        Console.file.fset(self, new_file)  # type: ignore[attr-defined]

    def _check_buffer(self) -> None:
        with self._lock:
            if self._dead:
                self._discard_pending()
                return
            try:
                super()._check_buffer()
            except OSError as exc:
                if not is_dead_handle_error(exc):
                    raise
                self._mark_dead()

    def on_broken_pipe(self) -> None:
        self._mark_dead()

    def _mark_dead(self) -> None:
        self._dead = True
        self._discard_pending()

    def _discard_pending(self) -> None:
        if not self._buffer_index:
            del self._buffer[:]


__all__ = ["SafeConsole"]
