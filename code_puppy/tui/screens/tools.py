"""A responsive modal listing the agent's available tools.

Renders ``tools_content`` (markdown) in a Textual ``Markdown`` widget, which
reflows on terminal resize -- unlike captured Rich output mounted as a fixed
-width Static (which clips when the window shrinks). Esc, q, or the Dismiss
button closes it.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.widgets import Markdown as MarkdownWidget


class ToolsScreen(ModalScreen[None]):
    """Scrollable, resize-responsive tool catalogue. Dismisses with None."""

    CSS = """
    ToolsScreen { align: center middle; }
    #dialog {
        width: 90%;
        height: 90%;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; margin-bottom: 1; }
    #body { height: 1fr; }
    /* Section headings (# in tools_content) default to centered -- left-align
       them so they read like section labels, not banners. */
    #body MarkdownH1, #body MarkdownH2 { content-align: left middle; }
    #footer { height: auto; margin-top: 1; align-horizontal: right; }
    #hint { width: 1fr; color: $text-muted; padding-top: 1; }
    #dismiss { margin-left: 1; }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
    ]

    def compose(self) -> ComposeResult:
        from code_puppy.tools.tools_content import tools_content

        with Vertical(id="dialog"):
            yield Label("Available Tools", id="title")
            with VerticalScroll(id="body"):
                yield MarkdownWidget(tools_content)
            with Horizontal(id="footer"):
                yield Label("Esc / q also dismiss", id="hint")
                yield Button("Dismiss", id="dismiss", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#body", VerticalScroll).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_close()

    def action_close(self) -> None:
        self.dismiss(None)
