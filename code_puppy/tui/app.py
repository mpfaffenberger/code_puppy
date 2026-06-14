"""CooperApp: the Textual application shell for Code Puppy's new TUI.

Phase 0 scope
-------------
This is the SCAFFOLD. It boots, wires the TextualRenderer to the real
MessageBus, and lays out the eventual chat surface: a scrollback log plus a
multiline prompt (decided: TextArea, Enter submits / Shift+Enter newlines).

What's intentionally NOT here yet (later phases):
* Phase 1 - full message-type rendering parity
* Phase 2 - real input loop, slash commands, completions, steer/cancel/pause
* Phase 3 - menus as ModalScreens

The prompt is present but inert in Phase 0 (it prints a 'coming soon' notice)
so the layout and key handling can be felt without pretending the agent loop
is wired.
"""

from __future__ import annotations

from rich.console import RenderableType
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, RichLog, TextArea

from code_puppy.messaging import (
    AnyMessage,
    MessageLevel,
    TextMessage,
    get_message_bus,
)

from .capture import RichCaptureFormatter
from .renderer import TextualRenderer, message_to_renderable


class PromptArea(TextArea):
    """Multiline prompt. Enter submits; Shift+Enter inserts a newline."""

    def _on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            self.app.submit_prompt(self.text)
            self.text = ""
        # Shift+Enter / ctrl+j fall through to default newline insertion.


class CooperApp(App):
    """Code Puppy's Textual UI (Phase 0 scaffold)."""

    CSS = """
    Screen { background: $surface; }
    #log {
        border: round $primary;
        padding: 0 1;
        background: $panel;
    }
    #prompt {
        height: 5;
        border: round $accent;
        margin-top: 1;
    }
    """

    BINDINGS = [("ctrl+q", "quit", "Quit")]
    TITLE = "Code Puppy"
    SUB_TITLE = "Textual UI (Phase 0 scaffold)"

    def __init__(self, initial_command: str | None = None) -> None:
        super().__init__()
        self._initial_command = initial_command
        self._renderer = TextualRenderer(self)
        # Phase 1 capture bridge: reuse the classic Rich formatting verbatim.
        self._formatter = RichCaptureFormatter()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            # Captured output is already fully styled by the classic renderer;
            # render it verbatim (no re-highlighting / markup re-parsing) so we
            # don't double-process span boundaries.
            yield RichLog(id="log", wrap=True, markup=False, highlight=False)
            yield PromptArea(id="prompt", soft_wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        bus = get_message_bus()
        bus.emit(
            TextMessage(
                level=MessageLevel.SUCCESS,
                text="Textual UI active (Phase 0 scaffold). Agent loop lands in Phase 2.",
            )
        )
        self._renderer.start()
        self.query_one("#prompt", PromptArea).focus()
        if self._initial_command:
            self.submit_prompt(self._initial_command)

    def write_renderable(self, renderable: RenderableType) -> None:
        """Mount a renderable into the scrollback."""
        self.query_one("#log", RichLog).write(renderable)

    def handle_bus_message(self, message: AnyMessage) -> None:
        """Render a bus message into the scrollback (runs on the UI thread).

        Uses the Phase 1 capture bridge for full parity with the classic UI.
        Falls back to a minimal renderable only if capture yields nothing for
        a plain TextMessage (defensive; shouldn't normally happen).
        """
        log = self.query_one("#log", RichLog)
        width = log.size.width or None
        renderable = self._formatter.format(message, width=width)
        if renderable is None:
            # Capture suppressed/skipped this message. Only surface a fallback
            # for plain text so nothing user-facing is silently lost.
            if isinstance(message, TextMessage):
                renderable = message_to_renderable(message)
            else:
                return
        log.write(renderable)

    def submit_prompt(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        # Phase 0: the agent loop isn't wired yet. Echo + notice via the bus so
        # the full bus -> renderer path is exercised even in the scaffold.
        bus = get_message_bus()
        bus.emit(TextMessage(level=MessageLevel.INFO, text=f"You typed: {text}"))
        bus.emit(
            TextMessage(
                level=MessageLevel.WARNING,
                text="Agent loop not wired yet (Phase 2). Ctrl+Q to quit.",
            )
        )

    def on_unmount(self) -> None:
        self._renderer.stop()


def build_app(initial_command: str | None = None) -> CooperApp:
    """Factory used by the launcher and by tests."""
    return CooperApp(initial_command=initial_command)
