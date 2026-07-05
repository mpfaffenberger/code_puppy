"""Textual ModalScreen for /queue — the TUI counterpart of the queue menu.

The classic ``/queue`` opens a prompt_toolkit ``arrow_select_async`` /
``PromptSession`` loop (``queue_menu.py``) that assumes ``suspended_run_ui``
handed it the raw terminal. In the Textual UI there is no run-UI to suspend,
so that loop no-ops / fights the Textual screen. This screen offers the same
view / add / edit / delete over the SAME data layer (the ``PauseController``'s
steer-queue: ``peek_pending_steer_queued`` / ``request_steer`` /
``replace_pending_steer_queued``) so the two UIs stay behaviourally identical.

UX:
  * left  -> queued prompts (↑/↓ to select, ⇧↑/⇧↓ to reorder)
  * right -> live full text of the highlighted prompt
  * a add · e edit · d delete · Esc close

Every mutation routes through the controller, so the ``(N queued)`` status
suffix updates live via its steer-queue listeners — exactly like the classic
menu.
"""

from __future__ import annotations

from typing import List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, OptionList, Static
from textual.widgets.option_list import Option

_PREVIEW_CELLS = 56  # menu-row preview length for long prompts


def _preview(text: str) -> str:
    """Collapse whitespace and clip long prompts for the list row."""
    flat = " ".join(text.split())
    if len(flat) <= _PREVIEW_CELLS:
        return flat
    return flat[: _PREVIEW_CELLS - 1] + "\u2026"


class QueueScreen(ModalScreen[None]):
    """View / add / edit / delete queued prompts. Dismisses with None."""

    CSS = """
    QueueScreen { align: center middle; }
    #dialog {
        width: 92%;
        height: 88%;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; }
    #summary { color: $text-muted; margin-bottom: 1; }
    #body { height: 1fr; }
    #left { width: 55%; }
    #items { height: 1fr; border: round $primary; }
    #details {
        width: 1fr;
        border: round $primary;
        margin-left: 1;
        padding: 0 1;
    }
    #footer { height: 3; margin-top: 1; align-horizontal: right; }
    #hint { width: 1fr; color: $text-muted; padding-top: 1; }
    #footer Button { height: 3; margin-left: 1; min-width: 9; }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("a", "add", "Add"),
        Binding("e", "edit", "Edit"),
        Binding("d", "delete", "Delete"),
        Binding("shift+up", "move_up", "Move up", show=False, priority=True),
        Binding("shift+down", "move_down", "Move down", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._items: List[str] = []

    # ------------------------------------------------------------------ layout
    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Prompt queue", id="title")
            yield Label("", id="summary")
            with Horizontal(id="body"):
                with Vertical(id="left"):
                    yield OptionList(id="items")
                with VerticalScroll(id="details"):
                    yield Static("", id="details-text")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2191/\u2193 select \u00b7 SHIFT+\u2191/\u2193 reorder"
                    " \u00b7 a add \u00b7 e edit \u00b7 d delete \u00b7 Esc close",
                    id="hint",
                )
                yield Button("Add", id="add", variant="primary")

    def on_mount(self) -> None:
        self._refresh(select=0)
        self.query_one("#items", OptionList).focus()

    # ----------------------------------------------------------------- reload
    def _controller(self):
        from code_puppy.messaging.pause_controller import get_pause_controller

        return get_pause_controller()

    def _refresh(self, select: Optional[int] = None) -> None:
        """Rebuild the list from the live queue, preserving the cursor."""
        items = self.query_one("#items", OptionList)
        previous = items.highlighted
        self._items = list(self._controller().peek_pending_steer_queued())

        items.clear_options()
        for i, text in enumerate(self._items):
            items.add_option(Option(self._row_label(i, text)))

        self.query_one("#summary", Label).update(
            f"{len(self._items)} item(s) \u00b7 newest last"
            if self._items
            else "Queue is empty \u2014 press 'a' to add a prompt"
        )

        if self._items:
            target = select if select is not None else previous
            if target is None:
                target = 0
            target = max(0, min(target, len(self._items) - 1))
            items.highlighted = target
            self._update_details(target)
        else:
            self._update_details(None)

    def _row_label(self, index: int, text: str) -> Text:
        label = Text()
        label.append(f"{index + 1:>2}. ", style="dim")
        label.append(_preview(text) or "(empty)")
        return label

    # ---------------------------------------------------------------- details
    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        self._update_details(event.option_index)

    def _update_details(self, index: Optional[int]) -> None:
        self.query_one("#details-text", Static).update(self._build_details(index))

    def _build_details(self, index: Optional[int]) -> Text:
        t = Text()
        t.append("PROMPT DETAILS\n\n", style="bold cyan")
        if index is None or index >= len(self._items):
            t.append("No prompt selected.", style="yellow")
            return t
        t.append("Position: ", style="bold")
        t.append(f"{index + 1} of {len(self._items)}\n\n")
        t.append("Text:\n", style="bold")
        t.append(self._items[index] or "(empty)", style="dim")
        return t

    # ----------------------------------------------------------------- actions
    def _highlighted_index(self) -> Optional[int]:
        idx = self.query_one("#items", OptionList).highlighted
        if idx is None or idx >= len(self._items):
            return None
        return idx

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_add()

    def action_add(self) -> None:
        self._prompt_text("Add a prompt to the queue", "", self._apply_add)

    def action_edit(self) -> None:
        idx = self._highlighted_index()
        if idx is None:
            return
        self._prompt_text(
            f"Edit queued prompt #{idx + 1}",
            self._items[idx],
            lambda text: self._apply_edit(idx, text),
        )

    def action_delete(self) -> None:
        idx = self._highlighted_index()
        if idx is None:
            return
        items = list(self._items)
        del items[idx]
        self._controller().replace_pending_steer_queued(items)
        self._refresh(select=idx)

    def action_move_up(self) -> None:
        """Swap the highlighted prompt with the one above it."""
        idx = self._highlighted_index()
        if idx is None or idx == 0:
            return
        items = list(self._items)
        items[idx - 1], items[idx] = items[idx], items[idx - 1]
        self._controller().replace_pending_steer_queued(items)
        self._refresh(select=idx - 1)

    def action_move_down(self) -> None:
        """Swap the highlighted prompt with the one below it."""
        idx = self._highlighted_index()
        if idx is None or idx >= len(self._items) - 1:
            return
        items = list(self._items)
        items[idx], items[idx + 1] = items[idx + 1], items[idx]
        self._controller().replace_pending_steer_queued(items)
        self._refresh(select=idx + 1)

    def action_close(self) -> None:
        self.dismiss(None)

    # --------------------------------------------------------------- edit form
    def _prompt_text(self, title: str, default: str, on_done) -> None:
        """Push a single-field FormScreen (textarea) and route its result."""
        from code_puppy.tui.screens.form import FormField, FormScreen

        field = FormField(
            key="text",
            label="Prompt",
            kind="textarea",
            default=default,
            required=True,
        )

        def _received(values) -> None:
            if not values:
                return
            text = (values.get("text") or "").strip()
            if text:
                on_done(text)

        self.app.push_screen(FormScreen(title, [field], submit_label="Save"), _received)

    def _apply_add(self, text: str) -> None:
        # request_steer(mode="queue") is the canonical append: it appends AND
        # fires the steer-queue listeners so the (N queued) suffix updates.
        self._controller().request_steer(text, mode="queue")
        self._refresh(select=len(self._items))  # cursor lands on the new tail

    def _apply_edit(self, index: int, text: str) -> None:
        items = list(self._items)
        if index >= len(items):
            self._refresh()
            return
        items[index] = text
        self._controller().replace_pending_steer_queued(items)
        self._refresh(select=index)


def open_queue(app) -> None:
    """register_screen opener: push the queue management screen (TUI only)."""
    app.push_screen(QueueScreen())


__all__ = ["QueueScreen", "open_queue"]
