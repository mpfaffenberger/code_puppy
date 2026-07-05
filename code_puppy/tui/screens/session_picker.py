"""Two-panel autosave session picker (list + live preview).

Mirrors the classic /autosave_load panel: a filterable session list on the
left and a PREVIEW on the right (Session, Saved, Messages/Tokens, and the
last user message) that updates as you navigate.

Dismisses with the chosen session name, or None if cancelled.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from code_puppy.list_filtering import query_matches_text

# (session_name, metadata dict)
SessionEntry = Tuple[str, dict]


class SessionPickerScreen(ModalScreen[Optional[str]]):
    """Filterable autosave session list with a live preview."""

    CSS = """
    SessionPickerScreen { align: center middle; }
    #dialog {
        width: 90%;
        height: 85%;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; margin-bottom: 1; }
    #body { height: 1fr; }
    #left { width: 45%; }
    #filter { margin-bottom: 1; }
    #items { height: 1fr; border: round $primary; }
    #preview {
        width: 1fr;
        border: round $primary;
        margin-left: 1;
        padding: 0 1;
    }
    #footer { height: auto; margin-top: 1; align-horizontal: right; }
    #hint { width: 1fr; color: $text-muted; padding-top: 1; }
    #dismiss { margin-left: 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, entries: List[SessionEntry], base_dir: Path) -> None:
        super().__init__()
        self._entries = entries
        self._base_dir = base_dir
        self._by_id: Dict[str, dict] = {name: meta for name, meta in entries}
        self._last_msg_cache: Dict[str, str] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Load autosave session", id="title")
            with Horizontal(id="body"):
                with Vertical(id="left"):
                    yield Input(placeholder="type to filter...", id="filter")
                    yield OptionList(id="items")
                with VerticalScroll(id="preview"):
                    yield Static("", id="details")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2191/\u2193 move \u00b7 Enter load \u00b7 Esc cancel", id="hint"
                )
                yield Button("Dismiss", id="dismiss", variant="primary")

    def on_mount(self) -> None:
        self._populate("")
        self.query_one("#filter", Input).focus()

    # ------------------------------------------------------------------ list
    def _populate(self, query: str) -> None:
        items = self.query_one("#items", OptionList)
        items.clear_options()
        for name, _meta in self._entries:
            if not query_matches_text(query, name):
                continue
            items.add_option(Option(Text(name), id=name))
        if items.option_count:
            items.highlighted = 0
            self._update_preview(items.get_option_at_index(0).id)
        else:
            self.query_one("#details", Static).update(
                Text("No sessions match.", style="dim")
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        self._populate(event.value)

    def on_key(self, event: events.Key) -> None:
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

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if event.option is not None:
            self._update_preview(event.option.id)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        items = self.query_one("#items", OptionList)
        if items.option_count and items.highlighted is not None:
            self.dismiss(items.get_option_at_index(items.highlighted).id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)

    # ------------------------------------------------------------------ preview
    def _update_preview(self, name: Optional[str]) -> None:
        details = self.query_one("#details", Static)
        if not name or name not in self._by_id:
            details.update(Text("No session selected.", style="dim"))
            return
        details.update(self._build_preview(name, self._by_id[name]))

    def _build_preview(self, name: str, meta: dict) -> Text:
        timestamp = meta.get("timestamp", "unknown")
        try:
            time_str = datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            time_str = str(timestamp)
        msg_count = meta.get("message_count", "?")
        tokens = meta.get("total_tokens", 0)
        try:
            tokens_str = f"{int(tokens):,}"
        except Exception:
            tokens_str = str(tokens)

        t = Text()
        t.append("PREVIEW\n\n", style="dim cyan")
        t.append("Session: ", style="bold")
        t.append(f"{name}\n")
        t.append(f"Saved: {time_str}\n", style="dim")
        t.append(f"Messages: {msg_count} \u00b7 Tokens: {tokens_str}\n\n", style="dim")
        t.append("Last Message:\n", style="bold")
        t.append(self._last_message(name), style="dim")
        return t

    def _last_message(self, name: str) -> str:
        if name in self._last_msg_cache:
            return self._last_msg_cache[name]
        try:
            from code_puppy.command_line.autosave_menu import (
                _extract_last_user_message,
            )
            from code_puppy.session_storage import load_session

            history = load_session(name, self._base_dir)
            msg = _extract_last_user_message(history)
        except Exception as exc:
            msg = f"(could not load preview: {exc})"
        # Keep the preview reasonable; the scroll handles the rest.
        if len(msg) > 4000:
            msg = msg[:4000] + "\n..."
        self._last_msg_cache[name] = msg
        return msg
