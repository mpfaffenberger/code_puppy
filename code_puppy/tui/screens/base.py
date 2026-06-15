"""Phase 3 kit: reusable ModalScreen building blocks for menus.

The bulk of Phase 3 is porting ~50 prompt_toolkit menus to Textual modals.
To keep that DRY, most are just a filterable list: type to narrow, Enter/click
to choose. ``FilterableListScreen`` captures that once; concrete menus supply
a title + choices and handle the dismissed id.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList
from textual.widgets.option_list import Option

from code_puppy.list_filtering import query_matches_text


@dataclass
class ListChoice:
    """One row in a FilterableListScreen.

    ``style`` is an optional Rich style applied to the label (e.g.
    ``"on #0b3e0b"`` for a color swatch in a color picker).
    """

    id: str
    label: str
    search: str = ""
    active: bool = False
    style: str = ""

    def __post_init__(self) -> None:
        if not self.search:
            self.search = self.label


class FilterableListScreen(ModalScreen[Optional[str]]):
    """A filter box + list. Returns the chosen choice id, or None if cancelled."""

    CSS = """
    FilterableListScreen { align: center middle; }
    #dialog {
        width: 78;
        height: 26;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; margin-bottom: 1; }
    #filter { margin-bottom: 1; }
    #items { height: 1fr; border: round $primary; }
    #footer { height: auto; margin-top: 1; align-horizontal: right; }
    #hint { width: 1fr; color: $text-muted; padding-top: 1; }
    #dismiss { margin-left: 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        title: str,
        choices: List[ListChoice],
        *,
        placeholder: str = "type to filter...",
        active_marker: str = "> ",
    ) -> None:
        super().__init__()
        self._title = title
        self._choices = choices
        self._placeholder = placeholder
        self._active_marker = active_marker

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._title, id="title")
            yield Input(placeholder=self._placeholder, id="filter")
            yield OptionList(id="items")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2191/\u2193 = move   Enter = select   Esc = cancel", id="hint"
                )
                yield Button("Dismiss", id="dismiss", variant="primary")

    def on_mount(self) -> None:
        self._populate("")
        self.query_one("#filter", Input).focus()

    def on_key(self, event: events.Key) -> None:
        # The filter Input keeps focus so typing narrows the list; forward
        # list-navigation keys to the OptionList (which isn't focused).
        if event.key in ("up", "down", "pageup", "pagedown", "home", "end"):
            items = self.query_one("#items", OptionList)
            count = items.option_count
            if count:
                event.stop()
                event.prevent_default()
                cur = items.highlighted or 0
                if event.key == "down":
                    items.highlighted = min(count - 1, cur + 1)
                elif event.key == "up":
                    items.highlighted = max(0, cur - 1)
                elif event.key == "pagedown":
                    items.highlighted = min(count - 1, cur + 10)
                elif event.key == "pageup":
                    items.highlighted = max(0, cur - 10)
                elif event.key == "home":
                    items.highlighted = 0
                elif event.key == "end":
                    items.highlighted = count - 1

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_cancel()

    def _populate(self, query: str) -> None:
        items = self.query_one("#items", OptionList)
        items.clear_options()
        for choice in self._choices:
            if not query_matches_text(query, choice.search):
                continue
            marker = (
                self._active_marker if choice.active else " " * len(self._active_marker)
            )
            label = Text(f"{marker}{choice.label}", style=choice.style or "")
            if choice.active:
                label.append("  (active)", style="bold green")
            items.add_option(Option(label, id=choice.id))
        if items.option_count:
            items.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        self._populate(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        items = self.query_one("#items", OptionList)
        if items.option_count and items.highlighted is not None:
            opt = items.get_option_at_index(items.highlighted)
            self.dismiss(opt.id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)
