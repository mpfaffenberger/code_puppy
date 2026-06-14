"""Phase 2d: interactive request modals.

When the agent calls ``bus.request_input/confirmation/selection`` it emits a
request message and awaits a Future. The classic UI answers via console
prompts; the Textual UI answers via these ModalScreens.

CRITICAL INVARIANT: each modal MUST resolve with a response on every exit
path (including Escape), otherwise the agent's awaited Future never completes
and the turn hangs forever. Escape therefore maps to a safe default
(empty/default value, "No"/cancel, or selection-cancel).
"""

from __future__ import annotations

from typing import Optional, Tuple

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from code_puppy.messaging import (
    ConfirmationRequest,
    SelectionRequest,
    UserInputRequest,
)

_DIALOG_CSS = """
$mScreen {
    align: center middle;
}
#dialog {
    width: 72;
    max-height: 24;
    border: round $accent;
    background: $panel;
    padding: 1 2;
}
#title { text-style: bold; color: $accent; margin-bottom: 1; }
#desc { margin-bottom: 1; }
#buttons { height: auto; margin-top: 1; align-horizontal: right; }
Button { margin-left: 1; }
"""


class TextInputModal(ModalScreen[Optional[str]]):
    """Prompt for a line of text. Returns the value (or None if cancelled)."""

    CSS = _DIALOG_CSS.replace("$mScreen", "TextInputModal")
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, request: UserInputRequest) -> None:
        super().__init__()
        self._request = request

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._request.prompt_text, id="title")
            placeholder = (
                f"default: {self._request.default_value}"
                if self._request.default_value
                else ""
            )
            yield Input(
                placeholder=placeholder,
                password=self._request.input_type == "password",
                id="value",
            )

    def on_mount(self) -> None:
        self.query_one("#value", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        # Empty -> the bus falls back to the request's default value.
        self.dismiss(None)


class ConfirmModal(ModalScreen[Tuple[bool, Optional[str]]]):
    """Confirm with one button per option. Returns (confirmed, feedback).

    Per the classic contract, the FIRST option means confirmed=True.
    """

    CSS = _DIALOG_CSS.replace("$mScreen", "ConfirmModal")
    BINDINGS = [Binding("escape", "decline", "No")]

    def __init__(self, request: ConfirmationRequest) -> None:
        super().__init__()
        self._request = request

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._request.title, id="title")
            yield Static(self._request.description, id="desc")
            if self._request.allow_feedback:
                yield Input(placeholder="optional feedback...", id="feedback")
            with Horizontal(id="buttons"):
                for i, opt in enumerate(self._request.options):
                    variant = "primary" if i == 0 else "default"
                    yield Button(opt, id=f"opt-{i}", variant=variant)

    def on_mount(self) -> None:
        first = self.query("Button").first()
        if first:
            first.focus()

    def _feedback(self) -> Optional[str]:
        if not self._request.allow_feedback:
            return None
        try:
            val = self.query_one("#feedback", Input).value.strip()
        except Exception:
            return None
        return val or None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        index = int(str(event.button.id).split("-")[1])
        self.dismiss((index == 0, self._feedback()))

    def action_decline(self) -> None:
        self.dismiss((False, None))


class SelectionModal(ModalScreen[Tuple[int, str]]):
    """Pick one option from a list. Returns (index, value); (-1, '') cancels."""

    CSS = (
        _DIALOG_CSS.replace("$mScreen", "SelectionModal")
        + """
    #options { height: 1fr; border: round $primary; margin-top: 1; }
    """
    )
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, request: SelectionRequest) -> None:
        super().__init__()
        self._request = request

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._request.prompt_text, id="title")
            options = [
                Option(opt, id=str(i)) for i, opt in enumerate(self._request.options)
            ]
            yield OptionList(*options, id="options")

    def on_mount(self) -> None:
        self.query_one("#options", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        index = int(event.option.id)
        self.dismiss((index, self._request.options[index]))

    def action_cancel(self) -> None:
        # Mirrors the classic cancel: index -1, empty value.
        self.dismiss((-1, ""))
