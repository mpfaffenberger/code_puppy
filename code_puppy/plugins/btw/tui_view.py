"""Textual modal for `/btw` answers -- the TUI counterpart of inline_view.py.

Why this can't just reuse ``inline_view``: that module writes straight to
the real terminal and blocks the calling thread on a raw termios/msvcrt
keypress read to detect dismissal. Once Textual owns the screen it has its
own input driver reading the same fd, and ``_handle_custom_command`` runs
synchronously on the app's event loop -- so the classic path just hangs
(competing for keystrokes) with nothing visible on screen until the
120s dismiss timeout fires. Looks exactly like "nothing happens" on ENTER.

This module runs the query as an async Textual worker (no thread hop
needed, we're already on the app's own event loop) and renders progress /
answer in a normal ``ModalScreen``.
"""

from __future__ import annotations

import logging

from rich.markdown import Markdown as RichMarkdown
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static

logger = logging.getLogger(__name__)


def is_textual_active() -> bool:
    """True when a Textual App is driving the current terminal session."""
    try:
        import textual

        return textual.active_app.get(None) is not None
    except Exception:
        return False


def ask_in_modal(question: str, model_name: str) -> None:
    """Push the /btw modal onto the active Textual app, if any (no-op else)."""
    try:
        import textual

        app = textual.active_app.get(None)
    except Exception:
        app = None
    if app is None:
        return
    app.push_screen(BtwAnswerScreen(question, model_name))


class BtwAnswerScreen(ModalScreen[None]):
    """Ask a quick side question, show the answer. Dismisses with None.

    Same dismiss keys as the classic dismiss-wait (Enter/Space/Esc), minus
    the blocking raw-terminal read that doesn't play nice with Textual.
    """

    CSS = """
    BtwAnswerScreen { align: center middle; }
    #btw-dialog {
        width: 80%;
        max-width: 100;
        height: auto;
        max-height: 85%;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #btw-question { text-style: bold; color: $accent; margin-bottom: 1; }
    #btw-body { height: auto; max-height: 24; }
    #btw-hint { color: $text-muted; margin-top: 1; }
    """

    BINDINGS = [
        Binding("escape", "dismiss_now", "Close"),
        Binding("enter", "dismiss_now", "Close"),
        Binding("space", "dismiss_now", "Close"),
        Binding("q", "dismiss_now", "Close"),
    ]

    def __init__(self, question: str, model_name: str) -> None:
        super().__init__()
        self._question = question
        self._model_name = model_name

    def compose(self) -> ComposeResult:
        with Vertical(id="btw-dialog"):
            yield Label(f"/btw {self._question}", id="btw-question")
            yield Static(f"thinking ({self._model_name})...", id="btw-body")
            yield Label("Press Enter / Space / Esc to close", id="btw-hint")

    def on_mount(self) -> None:
        self._ask_worker()

    @work(exclusive=True)
    async def _ask_worker(self) -> None:
        from .side_query import _ask

        body = self.query_one("#btw-body", Static)
        try:
            answer = await _ask(self._model_name, self._question)
        except Exception as exc:
            logger.debug("btw: tui query failed", exc_info=True)
            body.update(f"[bold red]/btw failed ({type(exc).__name__}): {exc}[/]")
            return
        body.update(RichMarkdown(answer))

    def action_dismiss_now(self) -> None:
        self.dismiss(None)


__all__ = ["BtwAnswerScreen", "ask_in_modal", "is_textual_active"]
