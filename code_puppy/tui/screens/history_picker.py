"""/history modal: search + pick a previous prompt (classic Ctrl+R source).

Reads the same command-history file prompt_toolkit's reverse-search (Ctrl+R)
uses, newest-first, and lets you filter + pick one. Picking dismisses with the
full prompt string; the opener drops it into the input box for editing/sending.
"""

from __future__ import annotations

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


def load_prompt_history() -> List[str]:
    """Return previous prompts newest-first (deduped), from the Ctrl+R source."""
    try:
        from code_puppy.config import COMMAND_HISTORY_FILE
        from prompt_toolkit.history import FileHistory

        strings = list(FileHistory(COMMAND_HISTORY_FILE).load_history_strings())
    except Exception:
        return []

    seen = set()
    out: List[str] = []
    for s in strings:  # already newest-first
        s = s.rstrip("\n")
        if not s.strip() or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _one_line(text: str, limit: int = 200) -> str:
    """Collapse a (possibly multi-line) prompt to a single display line."""
    collapsed = " \u23ce ".join(part for part in text.splitlines() if part.strip())
    collapsed = collapsed or text.strip()
    if len(collapsed) > limit:
        collapsed = collapsed[: limit - 1] + "\u2026"
    return collapsed


class HistoryScreen(ModalScreen[Optional[str]]):
    """Filterable list of previous prompts. Returns the chosen prompt (or None)."""

    CSS = """
    HistoryScreen { align: center middle; }
    #dialog {
        width: 80%;
        height: auto;
        max-height: 85%;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; margin-bottom: 1; }
    #filter { margin-bottom: 1; }
    #items { height: auto; max-height: 18; border: round $primary; }
    #footer { height: 3; margin-top: 1; align-horizontal: right; }
    #hint { width: 1fr; color: $text-muted; padding-top: 1; }
    #dismiss { height: 3; margin-left: 1; min-width: 11; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, prompts: List[str]) -> None:
        super().__init__()
        self._prompts = prompts

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Prompt History (/history)", id="title")
            yield Input(placeholder="type to filter...", id="filter")
            yield OptionList(id="items")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2b06\ufe0f \u2b07\ufe0f navigate \u00b7 Enter select \u00b7 "
                    "Esc cancel",
                    id="hint",
                )
                yield Button("Dismiss", id="dismiss", variant="primary")

    def on_mount(self) -> None:
        self._populate("")
        self.query_one("#filter", Input).focus()

    def _populate(self, query: str) -> None:
        items = self.query_one("#items", OptionList)
        items.clear_options()
        for idx, prompt in enumerate(self._prompts):
            if not query_matches_text(query, prompt):
                continue
            items.add_option(Option(Text(_one_line(prompt)), id=str(idx)))
        if items.option_count:
            items.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        self._populate(event.value)

    def on_key(self, event: events.Key) -> None:
        # Filter keeps focus; forward navigation keys to the OptionList.
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

    def on_input_submitted(self, event: Input.Submitted) -> None:
        items = self.query_one("#items", OptionList)
        if items.option_count and items.highlighted is not None:
            self._choose(items.get_option_at_index(items.highlighted).id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._choose(event.option.id)

    def _choose(self, option_id: Optional[str]) -> None:
        if option_id is None:
            return
        try:
            self.dismiss(self._prompts[int(option_id)])
        except (ValueError, IndexError):
            self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)
