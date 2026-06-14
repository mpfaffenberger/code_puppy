"""Phase 1 capture bridge: reuse the classic Rich formatting in Textual.

Instead of duplicating ~1,400 lines of presentation logic, we drive the real
``RichConsoleRenderer`` against a private in-memory console, capture its ANSI
output per message, and hand it back as a Textual-friendly ``rich.text.Text``
(via ``Text.from_ansi``). This gives the Textual UI instant, full parity with
the classic UI for every message type, present and future, with:

* **zero formatting duplication** (maximally DRY),
* **zero risk to the shipped classic UI** (we never touch the real terminal),
* **free reuse of all policy gates** (pause/suppress/output-level live in
  ``_do_render``).

Interactive and animated message types (spinners, user-input/confirmation/
selection requests) are intentionally NOT handled here -- they become real
Textual widgets in Phase 2.
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console
from rich.text import Text

from code_puppy.messaging import (
    AnyMessage,
    ConfirmationRequest,
    RichConsoleRenderer,
    SelectionRequest,
    SpinnerControl,
    UserInputRequest,
    get_message_bus,
)

# Message types the capture bridge skips (handled as live widgets in Phase 2).
_SKIP_TYPES = (
    SpinnerControl,
    UserInputRequest,
    ConfirmationRequest,
    SelectionRequest,
)

_DEFAULT_WIDTH = 100


class RichCaptureFormatter:
    """Format bus messages into Rich Text by capturing the classic renderer."""

    def __init__(self, width: int = _DEFAULT_WIDTH) -> None:
        self._console = Console(
            file=StringIO(),
            force_terminal=True,
            color_system="truecolor",
            width=width,
            record=True,
        )
        # Reuse the real renderer purely for its formatting. We never call
        # start()/stop(), so it spawns no thread and consumes no messages.
        self._renderer = RichConsoleRenderer(get_message_bus(), self._console)

    def should_skip(self, message: AnyMessage) -> bool:
        """True for interactive/animated types the bridge doesn't render."""
        return isinstance(message, _SKIP_TYPES)

    def format(self, message: AnyMessage, width: int | None = None) -> Text | None:
        """Return styled Text for a message, or None if nothing was rendered.

        None means the message was suppressed by a policy gate or produced no
        output (e.g. AgentResponseMessage, which the classic renderer skips
        because responses stream separately).
        """
        if self.should_skip(message):
            return None

        if width and width > 0:
            try:
                self._console.width = width
            except Exception:
                pass

        try:
            self._renderer._do_render(message)
            ansi = self._console.export_text(clear=True, styles=True)
        except Exception:
            # Never let a formatting hiccup crash the UI; drop any partial
            # buffer and bail out gracefully.
            try:
                self._console.export_text(clear=True)
            except Exception:
                pass
            return None

        if not ansi.strip():
            return None
        return Text.from_ansi(ansi.rstrip("\n"))
