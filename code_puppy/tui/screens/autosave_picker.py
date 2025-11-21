"""
Autosave Picker modal for TUI.
Lists recent autosave sessions and lets the user load one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView, Static

from code_puppy.session_storage import list_sessions


@dataclass(slots=True)
class AutosaveEntry:
    name: str
    timestamp: Optional[str]
    message_count: Optional[int]


def _load_metadata(base_dir: Path, name: str) -> Tuple[Optional[str], Optional[int]]:
    meta_path = base_dir / f"{name}_meta.json"
    try:
        with meta_path.open("r", encoding="utf-8") as meta_file:
            data = json.load(meta_file)
        return data.get("timestamp"), data.get("message_count")
    except Exception:
        return None, None


class AutosavePicker(ModalScreen):
    """Modal to present available autosave sessions for selection."""

    DEFAULT_CSS = """
    AutosavePicker {
        align: center middle;
    }

    #modal-container {
        width: 80%;
        max-width: 100;
        height: 24;
        min-height: 18;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
        layout: vertical;
    }

    #list-label {
        width: 100%;
        height: 1;
        color: $text;
        text-align: left;
    }

    #autosave-list {
        height: 1fr;
        overflow: auto;
        border: solid $primary-darken-2;
        background: $surface-darken-1;
        margin: 1 0;
    }

    .button-row {
        height: 3;
        align-horizontal: right;
        margin-top: 1;
    }

    #cancel-button { background: $primary-darken-1; }
    #load-button { background: $success; }
    """

    def __init__(self, autosave_dir: Path, **kwargs):
        super().__init__(**kwargs)
        self.autosave_dir = autosave_dir
        self.entries: List[AutosaveEntry] = []
        self.list_view: Optional[ListView] = None

    def on_mount(self) -> None:
        names = list_sessions(self.autosave_dir)
        raw_entries: List[Tuple[str, Optional[str], Optional[int]]] = []
        for name in names:
            ts, count = _load_metadata(self.autosave_dir, name)
            raw_entries.append((name, ts, count))

        def sort_key(entry):
            _, ts, _ = entry
            if ts:
                try:
                    return datetime.fromisoformat(ts)
                except ValueError:
                    return datetime.min
            return datetime.min

        raw_entries.sort(key=sort_key, reverse=True)
        self.entries = [AutosaveEntry(*e) for e in raw_entries]

        # Populate the ListView now that entries are ready
        if self.list_view is None:
            try:
                self.list_view = self.query_one("#autosave-list", ListView)
            except Exception:
                self.list_view = None

        if self.list_view is not None:
            # Clear existing items if any
            try:
                self.list_view.clear()
            except Exception:
                # Fallback: remove children manually
                self.list_view.children.clear()  # type: ignore

            for entry in self.entries[:50]:
                ts = entry.timestamp or "unknown time"
                count = (
                    f"{entry.message_count} msgs"
                    if entry.message_count is not None
                    else "unknown size"
                )
                label = f"{entry.name} — {count}, saved at {ts}"
                self.list_view.append(ListItem(Static(label)))

            # Focus and select first item for better UX
            if len(self.entries) > 0:
                self.list_view.index = 0
                self.list_view.focus()

    def compose(self) -> ComposeResult:
        with Container(id="modal-container"):
            yield Label("Select an autosave to load (Esc to cancel)", id="list-label")
            self.list_view = ListView(id="autosave-list")
            # populate items
            for entry in self.entries[:50]:  # cap to avoid long lists
                ts = entry.timestamp or "unknown time"
                count = (
                    f"{entry.message_count} msgs"
                    if entry.message_count is not None
                    else "unknown size"
                )
                label = f"{entry.name} — {count}, saved at {ts}"
                self.list_view.append(ListItem(Static(label)))
            yield self.list_view
            with Horizontal(classes="button-row"):
                yield Button("Cancel", id="cancel-button")
                yield Button("Load", id="load-button", variant="primary")

    @on(Button.Pressed, "#cancel-button")
    def cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#load-button")
    def load_selected(self) -> None:
        if not self.list_view or not self.entries:
            self.dismiss(None)
            return
        idx = self.list_view.index if self.list_view.index is not None else 0
        if 0 <= idx < len(self.entries):
            self.dismiss(self.entries[idx].name)
        else:
            self.dismiss(None)

    def on_list_view_selected(self, event: ListView.Selected) -> None:  # type: ignore
        # Double-enter may select; we just map to load button
        self.load_selected()
