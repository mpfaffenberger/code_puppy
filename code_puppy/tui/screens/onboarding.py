"""A lightweight Textual onboarding slide deck.

Replaces the prompt_toolkit slide carousel for the TUI (which would corrupt the
screen if launched from inside Textual). Returns one of:
  * ``"model"``   -> caller should open the model picker
  * ``"done"``    -> finished
  * ``"skipped"`` -> user bailed
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Markdown

_SLIDES = [
    (
        "Welcome to Code Puppy",
        "I'm **cooper** - your loyal coding pup.\n\n"
        "Type a task and I'll plan, edit files, run commands, and report back. "
        "Everything streams live as I work.",
    ),
    (
        "Driving a turn",
        "- **Enter** sends your task\n"
        "- watch tool activity + the response stream in\n"
        "- **Esc** cancels a running turn\n"
        "- **Ctrl+T** injects a steering message mid-run",
    ),
    (
        "Commands & completion",
        "- **/help** lists all commands\n"
        "- **/model** picks a model, **/agent** switches agents\n"
        "- type **@** to complete file paths, **!cmd** to run a shell command\n"
        "- **Ctrl+P** opens the command palette",
    ),
    (
        "Let's get you a model",
        "Pick a model to start chatting - you can change it anytime with "
        "**/model**. Or finish and explore on your own.",
    ),
]


class OnboardingScreen(ModalScreen[str]):
    """Slide deck. Dismisses with 'model', 'done', or 'skipped'."""

    CSS = """
    OnboardingScreen { align: center middle; }
    #dialog {
        width: 72;
        height: 22;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; margin-bottom: 1; }
    #body { height: 1fr; }
    #dots { color: $text-muted; }
    #buttons { height: auto; margin-top: 1; align-horizontal: right; }
    Button { margin-left: 1; }
    """

    BINDINGS = [
        Binding("escape", "skip", "Skip"),
        Binding("left", "back", "Back", show=False),
        Binding("right", "next", "Next", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._index = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(_SLIDES[0][0], id="title")
            yield Markdown(_SLIDES[0][1], id="body")
            yield Label("", id="dots")
            with Horizontal(id="buttons"):
                yield Button("Skip", id="skip")
                yield Button("Back", id="back")
                yield Button("Next", id="next", variant="primary")
                yield Button("Pick a model", id="model")

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        title, body = _SLIDES[self._index]
        self.query_one("#title", Label).update(title)
        self.query_one("#body", Markdown).update(body)
        dots = " ".join("*" if i == self._index else "." for i in range(len(_SLIDES)))
        self.query_one("#dots", Label).update(
            f"{dots}    slide {self._index + 1} of {len(_SLIDES)}"
        )
        last = self._index == len(_SLIDES) - 1
        self.query_one("#next", Button).label = "Finish" if last else "Next"
        self.query_one("#back", Button).disabled = self._index == 0
        self.query_one("#model", Button).display = last

    def action_back(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._refresh()

    def action_next(self) -> None:
        if self._index < len(_SLIDES) - 1:
            self._index += 1
            self._refresh()
        else:
            self.dismiss("done")

    def action_skip(self) -> None:
        self.dismiss("skipped")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "skip":
            self.dismiss("skipped")
        elif button_id == "back":
            self.action_back()
        elif button_id == "next":
            self.action_next()
        elif button_id == "model":
            self.dismiss("model")
