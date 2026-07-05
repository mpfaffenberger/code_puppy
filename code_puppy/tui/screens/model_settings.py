"""Two-panel /model_settings picker (model list + per-model setting editor).

Mirrors the classic ``/model_settings`` panels:

* ``ModelSettingsScreen`` — pick a model (left) with a live "Model Info"
  preview (right) showing whether it's active, its current settings, and the
  list of configurable settings. Enter opens that model's editor.
* ``ModelSettingDetailScreen`` — list a model's supported settings with their
  current values (left) + a detail/description preview (right). Enter edits the
  highlighted setting (choice/boolean -> list picker, numeric -> text input);
  ``r`` resets it to the model default.

All edits apply immediately through the real setters. The opener reloads the
active agent on dismiss when anything changed (matches classic).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from code_puppy.command_line.model_settings_menu import (
    SETTING_DEFINITIONS,
    _get_model_display_settings,
    _get_setting_choices,
    _get_setting_default,
    _load_all_model_names,
)
from code_puppy.config import (
    get_global_model_name,
    model_supports_setting,
    set_model_setting,
    set_openai_reasoning_effort,
    set_openai_reasoning_summary,
    set_openai_verbosity,
)
from code_puppy.list_filtering import query_matches_text


# --------------------------------------------------------------------------- helpers
def _supported_settings(model_name: str) -> List[str]:
    """Settings (in canonical order) that the given model supports."""
    return [k for k in SETTING_DEFINITIONS if model_supports_setting(model_name, k)]


def _format_value(setting: str, value, model_name: str) -> str:
    """Render a setting value the way the classic menu does."""
    sdef = SETTING_DEFINITIONS.get(setting)
    if sdef is None:
        return str(value) if value is not None else "(unknown)"
    if value is None:
        default = _get_setting_default(setting, model_name)
        return f"(default: {default})" if default is not None else "(model default)"
    if sdef.get("type") == "boolean":
        return "Enabled" if value else "Disabled"
    if sdef.get("type") == "choice":
        return str(value)
    return sdef.get("format", "{:.2f}").format(value)


# OpenAI reasoning controls are global, not per-model; route them specially
# (mirrors ModelSettingsMenu._save_edit / _reset_to_default).
_GLOBAL_SETTERS = {
    "reasoning_effort": set_openai_reasoning_effort,
    "summary": set_openai_reasoning_summary,
    "verbosity": set_openai_verbosity,
}
_GLOBAL_RESET_DEFAULTS = {
    "reasoning_effort": "medium",
    "summary": "auto",
    "verbosity": "medium",
}


def _save_setting(model_name: str, setting: str, value) -> None:
    setter = _GLOBAL_SETTERS.get(setting)
    if setter is not None:
        setter(value)
    else:
        set_model_setting(model_name, setting, value)


def _reset_setting(model_name: str, setting: str) -> None:
    if setting in _GLOBAL_RESET_DEFAULTS:
        _GLOBAL_SETTERS[setting](_GLOBAL_RESET_DEFAULTS[setting])
    else:
        set_model_setting(model_name, setting, None)


# --------------------------------------------------------------------------- detail
class ModelSettingDetailScreen(ModalScreen[bool]):
    """Edit a single model's supported settings. Returns True if anything changed."""

    CSS = """
    ModelSettingDetailScreen { align: center middle; }
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
    #items { height: 1fr; border: round $primary; }
    #detail {
        width: 1fr;
        border: round $primary;
        margin-left: 1;
        padding: 0 1;
    }
    #footer { height: auto; margin-top: 1; align-horizontal: right; }
    #hint { width: 1fr; color: $text-muted; padding-top: 1; }
    #footer Button { margin-left: 1; min-width: 9; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Back"),
        Binding("r", "reset", "Reset"),
    ]

    def __init__(self, model_name: str) -> None:
        super().__init__()
        self._model = model_name
        self._settings = _supported_settings(model_name)
        self._values: Dict = _get_model_display_settings(model_name)
        self._changed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"Settings - {self._model}", id="title")
            with Horizontal(id="body"):
                with Vertical(id="left"):
                    yield OptionList(id="items")
                with VerticalScroll(id="detail"):
                    yield Static("", id="detail-text")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2191/\u2193 move \u00b7 Enter edit \u00b7 r reset \u00b7 Esc back",
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
        if not self._settings:
            self.query_one("#detail-text", Static).update(
                Text("This model has no configurable settings.", style="dim")
            )
            return
        for setting in self._settings:
            sdef = SETTING_DEFINITIONS[setting]
            value = self._values.get(setting)
            label = Text(f"{sdef['name']}: ", style="bold")
            shown = _format_value(setting, value, self._model)
            label.append(shown, style="" if value is not None else "dim")
            items.add_option(Option(label, id=setting))
        items.highlighted = min(prev, items.option_count - 1)
        self._update_detail(self._settings[items.highlighted])

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if event.option is not None:
            self._update_detail(event.option.id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._edit(event.option.id)

    # ------------------------------------------------------------------ detail pane
    def _update_detail(self, setting: Optional[str]) -> None:
        self.query_one("#detail-text", Static).update(self._build_detail(setting))

    def _build_detail(self, setting: Optional[str]) -> Text:
        t = Text()
        if not setting:
            return t
        sdef = SETTING_DEFINITIONS[setting]
        value = self._values.get(setting)
        default = _get_setting_default(setting, self._model)
        t.append(f"{sdef['name']}\n\n", style="bold cyan")
        t.append(f"{sdef.get('description', '')}\n\n")
        t.append("Current: ", style="bold")
        t.append(f"{_format_value(setting, value, self._model)}\n")
        t.append("Default: ", style="bold")
        t.append(f"{default if default is not None else '(model default)'}\n")
        stype = sdef.get("type")
        if stype == "numeric":
            t.append("Range: ", style="bold")
            t.append(f"{sdef['min']} - {sdef['max']} (step {sdef['step']})\n")
        elif stype == "choice":
            t.append("Choices: ", style="bold")
            t.append(", ".join(_get_setting_choices(setting, self._model)) + "\n")
        elif stype == "boolean":
            t.append("Choices: ", style="bold")
            t.append("Enabled, Disabled\n")
        return t

    # ------------------------------------------------------------------ edit
    def _highlighted(self) -> Optional[str]:
        items = self.query_one("#items", OptionList)
        if items.option_count and items.highlighted is not None:
            return items.get_option_at_index(items.highlighted).id
        return None

    def _edit(self, setting: Optional[str]) -> None:
        if not setting:
            return
        stype = SETTING_DEFINITIONS[setting].get("type")
        if stype == "choice":
            self._edit_choice(setting)
        elif stype == "boolean":
            self._edit_boolean(setting)
        elif stype == "numeric":
            self._edit_numeric(setting)

    def _edit_choice(self, setting: str) -> None:
        from .base import FilterableListScreen, ListChoice

        sdef = SETTING_DEFINITIONS[setting]
        current = self._values.get(setting)
        choices = [
            ListChoice(id=c, label=c, active=(str(current) == c))
            for c in _get_setting_choices(setting, self._model)
        ]

        def _picked(value) -> None:
            if value is not None:
                self._apply(setting, value)

        self.app.push_screen(FilterableListScreen(sdef["name"], choices), _picked)

    def _edit_boolean(self, setting: str) -> None:
        from .base import FilterableListScreen, ListChoice

        sdef = SETTING_DEFINITIONS[setting]
        current = bool(self._values.get(setting))
        choices = [
            ListChoice(id="true", label="Enabled", active=current),
            ListChoice(id="false", label="Disabled", active=not current),
        ]

        def _picked(value) -> None:
            if value is not None:
                self._apply(setting, value == "true")

        self.app.push_screen(FilterableListScreen(sdef["name"], choices), _picked)

    def _edit_numeric(self, setting: str) -> None:
        from code_puppy.messaging import UserInputRequest

        from .interactive import TextInputModal

        sdef = SETTING_DEFINITIONS[setting]
        current = self._values.get(setting)
        default = _get_setting_default(setting, self._model)
        seed = current if current is not None else default
        request = UserInputRequest(
            prompt_id="__model_setting__",
            prompt_text=f"{sdef['name']} ({sdef['min']} - {sdef['max']}):",
            default_value=str(seed) if seed is not None else None,
        )

        def _on_value(value) -> None:
            if value is None or not str(value).strip():
                return
            from code_puppy.messaging import emit_error

            try:
                num = float(str(value).strip())
            except ValueError:
                emit_error(f"Invalid number: {value}")
                return
            num = max(sdef["min"], min(sdef["max"], num))
            if sdef.get("format") == "{:.0f}":
                num = int(num)
            self._apply(setting, num)

        self.app.push_screen(TextInputModal(request, prefill=True), _on_value)

    def _apply(self, setting: str, value) -> None:
        from code_puppy.messaging import emit_success

        _save_setting(self._model, setting, value)
        self._values = _get_model_display_settings(self._model)
        self._changed = True
        self._populate()
        emit_success(f"Set {SETTING_DEFINITIONS[setting]['name']} = {value}")

    # ------------------------------------------------------------------ actions
    def action_reset(self) -> None:
        setting = self._highlighted()
        if not setting:
            return
        from code_puppy.messaging import emit_success

        _reset_setting(self._model, setting)
        self._values = _get_model_display_settings(self._model)
        self._changed = True
        self._populate()
        emit_success(f"Reset {SETTING_DEFINITIONS[setting]['name']} to default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(self._changed)


# --------------------------------------------------------------------------- picker
class ModelSettingsScreen(ModalScreen[bool]):
    """Pick a model + live Model Info preview. Returns True if anything changed."""

    CSS = """
    ModelSettingsScreen { align: center middle; }
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
    #info {
        width: 1fr;
        border: round $primary;
        margin-left: 1;
        padding: 0 1;
    }
    #footer { height: auto; margin-top: 1; align-horizontal: right; }
    #hint { width: 1fr; color: $text-muted; padding-top: 1; }
    #footer Button { margin-left: 1; min-width: 9; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self) -> None:
        super().__init__()
        self._models: List[str] = _load_all_model_names()
        self._active = get_global_model_name()
        self._changed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Select a Model to Configure", id="title")
            with Horizontal(id="body"):
                with Vertical(id="left"):
                    yield Input(placeholder="type to filter...", id="filter")
                    yield OptionList(id="items")
                with VerticalScroll(id="info"):
                    yield Static("", id="info-text")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2191/\u2193 move \u00b7 Enter configure \u00b7 Esc close",
                    id="hint",
                )
                yield Button("Dismiss", id="dismiss", variant="primary")

    def on_mount(self) -> None:
        self._populate("", select=self._active)
        self.query_one("#filter", Input).focus()

    # ------------------------------------------------------------------ list
    def _populate(self, query: str, *, select: Optional[str] = None) -> None:
        items = self.query_one("#items", OptionList)
        items.clear_options()
        target = 0
        idx = 0
        for name in self._models:
            if not query_matches_text(query, name):
                continue
            label = Text(name)
            if name == self._active:
                label.append("  (active)", style="bold green")
            items.add_option(Option(label, id=name))
            if select is not None and name == select:
                target = idx
            idx += 1
        if items.option_count:
            items.highlighted = min(target, items.option_count - 1)
            opt = items.get_option_at_index(items.highlighted)
            self._update_info(opt.id)
        else:
            self.query_one("#info-text", Static).update(
                Text("No models match.", style="dim")
            )

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

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if event.option is not None:
            self._update_info(event.option.id)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._configure(self._highlighted())

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._configure(event.option.id)

    def _highlighted(self) -> Optional[str]:
        items = self.query_one("#items", OptionList)
        if items.option_count and items.highlighted is not None:
            return items.get_option_at_index(items.highlighted).id
        return None

    # ------------------------------------------------------------------ configure
    def _configure(self, model_name: Optional[str]) -> None:
        if not model_name:
            return

        def _done(changed) -> None:
            if changed:
                self._changed = True
            self._update_info(model_name)

        self.app.push_screen(ModelSettingDetailScreen(model_name), _done)

    # ------------------------------------------------------------------ info pane
    def _update_info(self, model_name: Optional[str]) -> None:
        self.query_one("#info-text", Static).update(self._build_info(model_name))

    def _build_info(self, model_name: Optional[str]) -> Text:
        t = Text()
        if not model_name:
            return t
        t.append("Model Info\n\n", style="bold cyan")
        t.append(f"{model_name}\n\n", style="bold")
        if model_name == self._active:
            t.append("\u2713 Currently active model\n\n", style="green")

        values = _get_model_display_settings(model_name)
        if values:
            t.append("Current settings:\n", style="bold")
            for key, value in values.items():
                name = SETTING_DEFINITIONS.get(key, {}).get("name", key)
                t.append(f"  \u2022 {name}: ")
                t.append(f"{_format_value(key, value, model_name)}\n", style="cyan")
            t.append("\n")
        else:
            t.append("Using all default settings\n\n", style="dim")

        supported = _supported_settings(model_name)
        t.append("Configurable Settings:\n", style="bold")
        if supported:
            for key in supported:
                t.append(f"  \u2022 {SETTING_DEFINITIONS[key]['name']}\n", style="dim")
        else:
            t.append("  (none for this model)\n", style="dim")
        return t

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(self._changed)
