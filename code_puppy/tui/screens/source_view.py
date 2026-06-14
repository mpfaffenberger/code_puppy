"""A scrollable, syntax-highlighted source viewer modal.

Used by the /uc tool browser to show a tool's source. Esc or q closes it.
"""

from __future__ import annotations

from typing import Optional

from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, RichLog


class SourceViewScreen(ModalScreen[None]):
    """Read-only source viewer. Dismisses with None."""

    CSS = """
    SourceViewScreen { align: center middle; }
    #dialog {
        width: 90%;
        height: 90%;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; margin-bottom: 1; }
    #code { height: 1fr; border: round $primary; }
    #hint { color: $text-muted; margin-top: 1; }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
    ]

    def __init__(self, title: str, content: str, error: Optional[str] = None) -> None:
        super().__init__()
        self._title = title
        self._content = content
        self._error = error

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._title, id="title")
            yield RichLog(id="code", wrap=False, markup=False, highlight=False)
            yield Label("Esc / q = close   arrows / PgUp / PgDn = scroll", id="hint")

    def on_mount(self) -> None:
        code = self.query_one("#code", RichLog)
        if self._error:
            code.write(Text(f"Could not load source: {self._error}", style="red"))
        else:
            code.write(
                Syntax(
                    self._content,
                    "python",
                    line_numbers=True,
                    word_wrap=False,
                )
            )
        code.focus()

    def action_close(self) -> None:
        self.dismiss(None)
