"""Textual ModalScreen for /prune — the TUI counterpart of PruneMenu.

The classic ``/prune`` opens a prompt_toolkit split-panel that corrupts the
Textual screen. This screen offers the same multi-select pruning over the
SAME data layer (``build_message_entries`` / ``ContextBudget`` /
``_perform_prune``) so the two UIs stay behaviourally identical.

UX:
  * left  -> multi-select list (Space toggles, ``a`` all / ``c`` clear)
  * right -> live detail of the highlighted message
  * Enter -> prune the checked messages; Esc -> cancel.

System-prompt messages are protected (never listed), matching the classic
menu's locked rows and ``_perform_prune``'s defensive filter.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, SelectionList, Static
from textual.widgets.selection_list import Selection

from code_puppy.plugins.prune.prune_model import ContextBudget, MessageEntry

_ROLE_MARKERS = {
    "user": ("you", "bold cyan"),
    "assistant": ("asst", "bold green"),
    "tool-return": ("tool", "yellow"),
    "system": ("sys", "magenta"),
}


def _budget_summary(budget: ContextBudget) -> str:
    if not budget.available:
        return "Select messages to prune \u00b7 system prompt is protected"
    pct = budget.percent_used
    pieces = []
    if budget.total_used is not None and budget.context_length:
        pct_s = f" ({pct:.0f}%)" if pct is not None else ""
        pieces.append(
            f"context: {budget.total_used:,}/{budget.context_length:,} tokens{pct_s}"
        )
    if budget.out_of_context_messages:
        pieces.append(f"{budget.out_of_context_messages} msg(s) already out of context")
    return "  \u00b7  ".join(pieces) or "Select messages to prune"


class PruneScreen(ModalScreen[None]):
    """Multi-select history pruner. Dismisses with None (applies in place)."""

    CSS = """
    PruneScreen { align: center middle; }
    #dialog {
        width: 92%;
        height: 88%;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; }
    #budget { color: $text-muted; margin-bottom: 1; }
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
        Binding("escape", "cancel", "Cancel"),
        Binding("a", "select_all", "Select all"),
        Binding("c", "clear_all", "Clear"),
        Binding("enter", "prune", "Prune"),
    ]

    def __init__(self, entries: List[MessageEntry], budget: ContextBudget) -> None:
        super().__init__()
        # Newest-first, skip pure tool-returns (they ride with their parent)
        # and locked system rows (never prunable).
        self._rows: List[MessageEntry] = [
            e
            for e in reversed(entries)
            if not e.is_pure_tool_return and not e.is_locked
        ]
        self._by_index: Dict[int, MessageEntry] = {
            e.history_index: e for e in self._rows
        }
        self._budget = budget

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Prune conversation history", id="title")
            yield Label(_budget_summary(self._budget), id="budget")
            with Horizontal(id="body"):
                with Vertical(id="left"):
                    yield SelectionList(id="items")
                with VerticalScroll(id="details"):
                    yield Static("", id="details-text")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2191/\u2193 move \u00b7 Space toggle \u00b7 a all \u00b7 "
                    "c clear \u00b7 Enter prune \u00b7 Esc cancel",
                    id="hint",
                )
                yield Button("Prune", id="prune", variant="error")

    def on_mount(self) -> None:
        items = self.query_one("#items", SelectionList)
        for entry in self._rows:
            items.add_option(Selection(self._row_label(entry), entry.history_index))
        if self._rows:
            items.highlighted = 0
            self._update_details(self._rows[0].history_index)
        items.focus()

    # ------------------------------------------------------------------ labels
    def _row_label(self, entry: MessageEntry) -> Text:
        marker, style = _ROLE_MARKERS.get(entry.role, ("?", "dim"))
        label = Text()
        label.append(f"{entry.history_index:>3} ", style="dim")
        label.append(f"{marker:<4} ", style=style)
        if entry.tool_calls:
            label.append(f"\u2692 {len(entry.tool_calls)} ", style="yellow")
        if entry.tokens is not None:
            ctx = "" if entry.in_context else " \u2702"
            label.append(f"[{entry.tokens}t{ctx}] ", style="dim")
        label.append(entry.preview or "(no text)")
        return label

    # ------------------------------------------------------------------ details
    def on_selection_list_selection_highlighted(
        self, event: SelectionList.SelectionHighlighted
    ) -> None:
        value = getattr(event.selection, "value", None)
        if value is not None:
            self._update_details(value)

    def _update_details(self, history_index: int) -> None:
        entry = self._by_index.get(history_index)
        self.query_one("#details-text", Static).update(self._build_details(entry))

    def _build_details(self, entry: Optional[MessageEntry]) -> Text:
        t = Text()
        t.append("MESSAGE DETAILS\n\n", style="bold cyan")
        if entry is None:
            t.append("No message selected.", style="yellow")
            return t
        marker, style = _ROLE_MARKERS.get(entry.role, ("?", "dim"))
        t.append("Role: ", style="bold")
        t.append(f"{entry.role}\n", style=style)
        t.append("History index: ", style="bold")
        t.append(f"{entry.history_index}\n")
        if entry.tokens is not None:
            t.append("Tokens: ", style="bold")
            here = "in context" if entry.in_context else "out of context"
            t.append(f"{entry.tokens} ({here})\n")
        t.append("\n")
        if entry.thinking_segments:
            t.append("Thinking:\n", style="bold magenta")
            for seg in entry.thinking_segments:
                t.append(f"  {seg}\n", style="dim")
            t.append("\n")
        if entry.tool_calls:
            t.append("Tool calls:\n", style="bold yellow")
            for tc in entry.tool_calls:
                t.append(f"  {tc.icon} {tc.name}", style="yellow")
                if tc.args_preview:
                    t.append(f" ({tc.args_preview})", style="dim")
                t.append("\n")
            t.append("\n")
        t.append("Text:\n", style="bold")
        t.append(entry.full_text or "(no text)", style="dim")
        return t

    # ------------------------------------------------------------------ actions
    def action_select_all(self) -> None:
        self.query_one("#items", SelectionList).select_all()

    def action_clear_all(self) -> None:
        self.query_one("#items", SelectionList).deselect_all()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_prune()

    def action_prune(self) -> None:
        from code_puppy.messaging import emit_info

        from code_puppy.plugins.prune.register_callbacks import _perform_prune

        selected = set(self.query_one("#items", SelectionList).selected)
        self.dismiss(None)
        if not selected:
            emit_info("/prune: nothing selected \u2013 history unchanged")
            return
        _perform_prune(selected)

    def action_cancel(self) -> None:
        from code_puppy.messaging import emit_info

        self.dismiss(None)
        emit_info("/prune: cancelled")


def open_prune(app) -> None:
    """register_screen opener: build entries from live history and push the
    multi-select prune screen. Mirrors the classic ``_launch_menu`` guards."""
    from code_puppy.agents.agent_manager import get_current_agent
    from code_puppy.messaging import emit_error, emit_info
    from code_puppy.plugins.prune.prune_model import (
        ContextBudget,
        annotate_context_window,
        build_message_entries,
    )

    try:
        agent = get_current_agent()
    except Exception as exc:
        emit_error(f"/prune: could not get current agent \u2013 {exc}")
        return

    raw_history = list(agent.get_message_history())
    entries = build_message_entries(raw_history)
    if not entries or all(e.is_locked or e.is_pure_tool_return for e in entries):
        emit_info("/prune: no prunable messages")
        return

    try:
        budget = annotate_context_window(entries, raw_history, agent)
    except Exception:
        budget = ContextBudget()

    app.push_screen(PruneScreen(entries, budget))


__all__ = ["PruneScreen", "open_prune"]
