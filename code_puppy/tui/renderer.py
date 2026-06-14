"""TextualRenderer: a RendererProtocol implementation that feeds the new
Textual UI from the existing MessageBus.

Phase 0 scope
-------------
This is intentionally MINIMAL. It consumes the bus in a background thread
(mirroring ``RichConsoleRenderer._consume_loop_sync``) and turns a small set
of message types into Rich renderables that get mounted into the app.

Phase 1 will expand ``message_to_renderable`` to cover every ``AnyMessage``
subtype by refactoring ``rich_renderer.py``'s ``_render_x`` methods to RETURN
renderables (shared formatting, two thin sinks). Until then, unknown message
types fall back to a dim ``repr`` so nothing is ever lost or crashes.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from rich.text import Text

from code_puppy.messaging import (
    AnyMessage,
    MessageLevel,
    TextMessage,
    get_message_bus,
)

if TYPE_CHECKING:
    from .app import CooperApp


_LEVEL_STYLE = {
    MessageLevel.ERROR: "bold red",
    MessageLevel.WARNING: "yellow",
    MessageLevel.SUCCESS: "green",
    MessageLevel.INFO: "white",
    MessageLevel.DEBUG: "dim",
}
_LEVEL_PREFIX = {
    MessageLevel.ERROR: "x ",
    MessageLevel.WARNING: "! ",
    MessageLevel.SUCCESS: "+ ",
    MessageLevel.INFO: "i ",
    MessageLevel.DEBUG: "* ",
}


def message_to_renderable(msg: AnyMessage):
    """Convert a structured message into a Rich renderable.

    Phase 0 handles TextMessage explicitly; everything else gets a safe,
    readable fallback. Expand this in Phase 1, do NOT duplicate formatting.
    """
    if isinstance(msg, TextMessage):
        style = _LEVEL_STYLE.get(msg.level, "white")
        prefix = _LEVEL_PREFIX.get(msg.level, "")
        return Text(f"{prefix}{msg.text}", style=style)

    return Text(f"[{type(msg).__name__}] {msg!r}", style="dim")


class TextualRenderer:
    """Consume the MessageBus and push renderables into a Textual app.

    Faithfully mirrors ``RichConsoleRenderer``'s thread + polling lifecycle so
    the integration shape matches production from day one.
    """

    def __init__(self, app: "CooperApp") -> None:
        self._app = app
        self._bus = get_message_bus()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._bus.mark_renderer_active()
        self._thread = threading.Thread(target=self._consume_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._bus.mark_renderer_inactive()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _consume_loop(self) -> None:
        # Drain anything buffered before the UI came up (startup messages).
        for msg in self._bus.get_buffered_messages():
            self._dispatch(msg)
        self._bus.clear_buffer()

        while self._running:
            msg = self._bus.get_message_nowait()
            if msg is not None:
                self._dispatch(msg)
            else:
                time.sleep(0.01)

    def _dispatch(self, msg: AnyMessage) -> None:
        """Marshal a raw bus message onto the Textual UI thread safely.

        Formatting happens on the UI thread (in ``handle_bus_message``) where
        the target widget width is known, so captured output wraps correctly.
        """
        try:
            self._app.call_from_thread(self._app.handle_bus_message, msg)
        except Exception:
            # App may be shutting down; never crash the consumer thread.
            pass
