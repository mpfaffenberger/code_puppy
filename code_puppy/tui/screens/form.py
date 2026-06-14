"""Phase 3 kit: a reusable multi-field form ModalScreen.

Where ``FilterableListScreen`` handles "pick one of a list", ``FormScreen``
handles "fill in several fields" — the shape most remaining menus need
(custom MCP server, add-model, judges add/edit, etc.).

Supply a title + a list of ``FormField``s; the screen dismisses with a dict
of ``{field.key: value}`` on submit, or ``None`` on cancel. Required-field
validation is built in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Switch


@dataclass
class FormField:
    """One field in a FormScreen.

    kind:
      * ``"text"``     -> Input
      * ``"password"`` -> Input(password=True)
      * ``"select"``   -> Select over ``options``
      * ``"bool"``     -> Switch
    """

    key: str
    label: str
    kind: str = "text"
    default: Any = ""
    options: List[str] = field(default_factory=list)
    required: bool = False
    placeholder: str = ""


class FormScreen(ModalScreen[Optional[Dict[str, Any]]]):
    """A multi-field form. Dismisses with a values dict, or None if cancelled."""

    CSS = """
    FormScreen { align: center middle; }
    #dialog {
        width: 78;
        max-height: 28;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; margin-bottom: 1; }
    #fields { height: auto; max-height: 18; }
    .field-label { color: $text-muted; margin-top: 1; }
    .bool-row { height: auto; }
    .bool-row Label { width: 1fr; }
    #error { color: $error; margin-top: 1; }
    #buttons { height: auto; margin-top: 1; align-horizontal: right; }
    Button { margin-left: 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self, title: str, fields: List[FormField], *, submit_label: str = "Save"
    ) -> None:
        super().__init__()
        self._title = title
        self._fields = fields
        self._submit_label = submit_label

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._title, id="title")
            with VerticalScroll(id="fields"):
                for f in self._fields:
                    yield from self._compose_field(f)
            yield Label("", id="error")
            with Horizontal(id="buttons"):
                yield Button(self._submit_label, id="submit", variant="primary")
                yield Button("Cancel", id="cancel")

    def _compose_field(self, f: FormField) -> ComposeResult:
        wid = f"field-{f.key}"
        if f.kind == "bool":
            with Horizontal(classes="bool-row"):
                yield Label(f.label, classes="field-label")
                yield Switch(value=bool(f.default), id=wid)
        elif f.kind == "select":
            yield Label(f.label, classes="field-label")
            options = [(opt, opt) for opt in f.options]
            value = f.default if f.default in f.options else Select.BLANK
            yield Select(options, value=value, id=wid, allow_blank=True)
        else:
            yield Label(f.label, classes="field-label")
            yield Input(
                value=str(f.default or ""),
                placeholder=f.placeholder,
                password=(f.kind == "password"),
                id=wid,
            )

    def on_mount(self) -> None:
        # Focus the first editable field for fast entry.
        if self._fields:
            try:
                self.query_one(f"#field-{self._fields[0].key}").focus()
            except Exception:
                pass

    def _collect(self) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        for f in self._fields:
            widget = self.query_one(f"#field-{f.key}")
            if f.kind == "bool":
                values[f.key] = bool(widget.value)
            elif f.kind == "select":
                values[f.key] = "" if widget.value is Select.BLANK else widget.value
            else:
                values[f.key] = widget.value.strip()
        return values

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        values = self._collect()
        missing = [
            f.label for f in self._fields if f.required and not values.get(f.key)
        ]
        if missing:
            self.query_one("#error", Label).update("Required: " + ", ".join(missing))
            return
        self.dismiss(values)

    def action_cancel(self) -> None:
        self.dismiss(None)
