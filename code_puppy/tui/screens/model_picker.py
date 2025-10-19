"""
Model Picker modal for TUI.
Lists available models and lets the user select one.
"""

from __future__ import annotations

from typing import List, Optional

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label, ListItem, ListView, Static

from code_puppy.command_line.model_picker_completion import (
    get_active_model,
    load_model_names,
)


class ModelPicker(ModalScreen):
    """Modal to present available models for selection."""

    DEFAULT_CSS = """
    ModelPicker {
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

    #model-list {
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
    #select-button { background: $success; }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.model_names: List[str] = []
        self.list_view: Optional[ListView] = None

    def on_mount(self) -> None:
        self.model_names = load_model_names()
        current_model = get_active_model()

        # Populate the ListView
        if self.list_view is None:
            try:
                self.list_view = self.query_one("#model-list", ListView)
            except Exception:
                self.list_view = None

        if self.list_view is not None:
            try:
                self.list_view.clear()
            except Exception:
                self.list_view.children.clear()  # type: ignore
            selected_index = 0
            for i, name in enumerate(self.model_names):
                if name == current_model:
                    label = f"{name} [green]\u2190 current[/green]"
                    selected_index = i
                else:
                    label = name
                self.list_view.append(ListItem(Static(label)))

            if self.model_names:
                self.list_view.index = selected_index
                self.list_view.focus()

    def compose(self) -> ComposeResult:
        with Container(id="modal-container"):
            yield Label("Select a model (Esc to cancel)", id="list-label")
            self.list_view = ListView(id="model-list")
            yield self.list_view
            with Horizontal(classes="button-row"):
                yield Button("Cancel", id="cancel-button")
                yield Button("Select", id="select-button", variant="primary")

    @on(Button.Pressed, "#cancel-button")
    def cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#select-button")
    def select_model(self) -> None:
        if not self.list_view or not self.model_names:
            self.dismiss(None)
            return
        idx = self.list_view.index if self.list_view.index is not None else 0
        if 0 <= idx < len(self.model_names):
            self.dismiss(self.model_names[idx])
        else:
            self.dismiss(None)

    def on_list_view_selected(self, event: ListView.Selected) -> None:  # type: ignore
        self.select_model()
