"""Custom Params editor for /model_settings (parity with the classic menu).

``CUSTOM_MODEL_SETTING`` ("custom") is a reserved, non-scalar setting: a
free-form JSON blob of ``key = value`` pairs merged into ``extra_body`` by
``make_model_settings``. It needs its own list/add/edit/delete UI rather than
the choice/boolean/numeric editors in ``model_settings.py`` -- split out here
to keep that file under the repo's line-count cap.

Mirrors ``ModelSettingsMenu._enter_custom_view`` / ``_save_custom_input`` /
``_delete_custom_pair`` in the classic menu (reuses the same config-layer
helpers so persistence format and parsing stay identical).
"""

from __future__ import annotations

from typing import Dict, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, OptionList
from textual.widgets.option_list import Option

from code_puppy.command_line.model_settings_menu import _format_custom_value
from code_puppy.config import (
    get_custom_model_settings,
    parse_config_scalar,
    set_custom_model_setting,
)

_ADD_NEW_ID = "__add_new__"


class CustomParamsModal(ModalScreen[bool]):
    """List/add/edit/delete a model's custom request params.

    Returns True if anything changed (so the caller can refresh its cache).
    """

    CSS = """
    CustomParamsModal { align: center middle; }
    #dialog {
        width: 70%;
        max-height: 80%;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; margin-bottom: 1; }
    #items { height: 1fr; border: round $primary; }
    #footer { height: auto; margin-top: 1; align-horizontal: right; }
    #hint { width: 1fr; color: $text-muted; padding-top: 1; }
    #footer Button { margin-left: 1; min-width: 9; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Back"),
        Binding("d", "delete", "Delete"),
    ]

    def __init__(self, model_name: str) -> None:
        super().__init__()
        self._model = model_name
        self._settings: Dict = get_custom_model_settings(model_name)
        self._changed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"Custom Params - {self._model}", id="title")
            yield OptionList(id="items")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2191/\u2193 move \u00b7 Enter add/edit \u00b7 d delete \u00b7 Esc back",
                    id="hint",
                )
                yield Button("Back", id="dismiss", variant="primary")

    def on_mount(self) -> None:
        self._populate()
        self.query_one("#items", OptionList).focus()

    # ------------------------------------------------------------------ list
    def _populate(self) -> None:
        items = self.query_one("#items", OptionList)
        prev = items.highlighted or 0
        items.clear_options()
        for key, value in self._settings.items():
            label = Text(f"{key} = {_format_custom_value(value)}")
            items.add_option(Option(label, id=key))
        items.add_option(Option(Text("+ Add new param", style="dim"), id=_ADD_NEW_ID))
        items.highlighted = min(prev, items.option_count - 1)

    def _highlighted_key(self) -> Optional[str]:
        items = self.query_one("#items", OptionList)
        if items.option_count and items.highlighted is not None:
            key = items.get_option_at_index(items.highlighted).id
            return None if key == _ADD_NEW_ID else key
        return None

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        key = None if event.option.id == _ADD_NEW_ID else event.option.id
        self._start_input(key)

    # ------------------------------------------------------------------ add/edit
    def _start_input(self, existing_key: Optional[str]) -> None:
        from code_puppy.messaging import UserInputRequest

        from .interactive import TextInputModal

        if existing_key is not None:
            seed = (
                f"{existing_key} = {_format_custom_value(self._settings[existing_key])}"
            )
        else:
            seed = ""
        request = UserInputRequest(
            prompt_id="__custom_param__",
            prompt_text="key = value (dotted keys nest, e.g. a.b.c = medium):",
            default_value=seed or None,
        )

        def _on_value(value) -> None:
            if value is None:
                return
            self._save_input(existing_key, value)

        self.app.push_screen(TextInputModal(request, prefill=True), _on_value)

    def _save_input(self, existing_key: Optional[str], text: str) -> None:
        from code_puppy.messaging import emit_error, emit_success

        key, sep, value = (part.strip() for part in text.partition("="))
        if not sep or not key or not value:
            emit_error("Expected format: key = value")
            return
        if existing_key and existing_key != key:
            # Renamed -- drop the stale key so it doesn't linger.
            set_custom_model_setting(self._model, existing_key, None)
        set_custom_model_setting(self._model, key, parse_config_scalar(value))
        self._reload()
        emit_success(f"Set custom param {key} = {value}")

    # ------------------------------------------------------------------ delete
    def action_delete(self) -> None:
        key = self._highlighted_key()
        if key is None:
            return
        from code_puppy.messaging import emit_success

        set_custom_model_setting(self._model, key, None)
        self._reload()
        emit_success(f"Deleted custom param {key}")

    def _reload(self) -> None:
        self._settings = get_custom_model_settings(self._model)
        self._changed = True
        self._populate()

    # ------------------------------------------------------------------ actions
    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(self._changed)
