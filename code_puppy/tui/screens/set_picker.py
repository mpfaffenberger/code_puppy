"""Two-panel /set config picker (settings list + live Setting Details).

Mirrors the classic ``/set`` panels: a category-grouped, filterable settings
list on the left (curated catalog + a Dynamic catch-all) and a live "Setting
Details" preview on the right (Key, Name, Category, Type, Current Value,
Description, Valid Values). Enter edits the highlighted setting via the
appropriate modal (choice/bool -> list picker, int/float/string -> text input);
``r`` resets it to its default.

Edits are routed through the same validated ``apply_setting`` path the classic
menu + ``/set key value`` use (DRY), deferring the agent reload to dismiss so a
multi-edit session doesn't thrash reloads.
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

from code_puppy.command_line.set_menu import (
    _Entry,
    _build_entries,
    _coerce_typed_input,
    _entry_matches,
)
from code_puppy.command_line.set_menu_render import (
    _type_display,
    truncate,
    value_for_display,
    wrap,
)
from code_puppy.command_line.set_menu_values import (
    display_value,
    is_default_value,
)


class SetPickerScreen(ModalScreen[bool]):
    """Two-panel settings picker. Returns True if anything changed."""

    CSS = """
    SetPickerScreen { align: center middle; }
    #dialog {
        width: 92%;
        height: 88%;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; margin-bottom: 1; }
    #body { height: 1fr; }
    #left { width: 48%; }
    #filter { margin-bottom: 1; }
    #items { height: 1fr; border: round $primary; }
    #details {
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
        Binding("escape", "cancel", "Save & Exit"),
        Binding("r", "reset", "Reset"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._entries: List[_Entry] = _build_entries()
        self._by_key: Dict[str, _Entry] = {e.setting.key: e for e in self._entries}
        self._changed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Puppy Config Settings", id="title")
            with Horizontal(id="body"):
                with Vertical(id="left"):
                    yield Input(placeholder="type to filter...", id="filter")
                    yield OptionList(id="items")
                with VerticalScroll(id="details"):
                    yield Static("", id="details-text")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2191/\u2193 move \u00b7 Enter edit \u00b7 r reset \u00b7 "
                    "Esc save & exit",
                    id="hint",
                )
                yield Button("Dismiss", id="dismiss", variant="primary")

    def on_mount(self) -> None:
        self._populate("")
        self.query_one("#filter", Input).focus()

    # ------------------------------------------------------------------ list
    def _row_label(self, entry: _Entry) -> Text:
        val = truncate(value_for_display(entry.setting))
        t = Text(f"  {entry.setting.display_name}")
        t.append("  = ", style="dim")
        if is_default_value(entry.setting):
            t.append("(Default) ", style="dim italic")
        t.append(val, style="dim")
        return t

    def _populate(self, query: str, *, select: Optional[str] = None) -> None:
        items = self.query_one("#items", OptionList)
        items.clear_options()
        q = query.strip().lower()
        last_cat: Optional[str] = None
        idx = 0
        first_sel: Optional[int] = None
        target: Optional[int] = None
        for entry in self._entries:
            if q and not _entry_matches(entry, q):
                continue
            if entry.category.name != last_cat:
                items.add_option(
                    Option(Text(entry.category.name, style="bold blue"), disabled=True)
                )
                last_cat = entry.category.name
                idx += 1
            items.add_option(Option(self._row_label(entry), id=entry.setting.key))
            if first_sel is None:
                first_sel = idx
            if select is not None and entry.setting.key == select:
                target = idx
            idx += 1
        chosen = target if target is not None else first_sel
        if chosen is not None:
            items.highlighted = chosen
            self._update_details(items.get_option_at_index(chosen).id)
        else:
            self.query_one("#details-text", Static).update(
                Text("No settings match.", style="dim")
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
        if event.option is not None and event.option.id is not None:
            self._update_details(event.option.id)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._edit(self._highlighted())

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._edit(event.option.id)

    def _highlighted(self) -> Optional[str]:
        items = self.query_one("#items", OptionList)
        if items.option_count and items.highlighted is not None:
            return items.get_option_at_index(items.highlighted).id
        return None

    # ------------------------------------------------------------------ details
    def _update_details(self, key: Optional[str]) -> None:
        self.query_one("#details-text", Static).update(self._build_details(key))

    def _build_details(self, key: Optional[str]) -> Text:
        t = Text()
        t.append("Setting Details\n\n", style="bold cyan")
        entry = self._by_key.get(key) if key else None
        if entry is None:
            t.append("No setting selected.", style="yellow")
            return t
        setting = entry.setting
        valid_values_str = ", ".join(setting.valid_values)
        for label, value, style in (
            ("Key: ", setting.key, "cyan"),
            ("Name: ", setting.display_name, "green"),
            ("Category: ", entry.category.name, "blue"),
        ):
            t.append(label, style="bold")
            t.append(f"{value}\n\n", style=style)
        t.append("Type: ", style="bold")
        t.append(f"{_type_display(setting, valid_values_str)}\n\n", style="yellow")
        t.append("Current Value: ", style="bold")
        current = display_value(setting)
        if current:
            if is_default_value(setting):
                t.append("(Default) ", style="dim italic")
            t.append(f"{current}", style="green")
        else:
            t.append("(not set)", style="dim")
        if setting.requires_restart:
            t.append("  (restart required)", style="yellow")
        t.append("\n\n")
        t.append("Description:\n", style="bold")
        for wrapped in wrap(setting.description):
            t.append(f"  {wrapped}\n", style="dim")
        if setting.type_hint == "choice" and setting.valid_values:
            t.append("\nValid Values:\n", style="bold")
            for val in setting.valid_values:
                if val == current:
                    t.append(f"   {val}  (current)\n", style="green")
                else:
                    t.append(f"    {val}\n", style="dim")
        t.append("\nTip: Press Enter to edit this setting.", style="dim")
        return t

    # ------------------------------------------------------------------ edit
    def _edit(self, key: Optional[str]) -> None:
        entry = self._by_key.get(key) if key else None
        if entry is None:
            return
        setting = entry.setting
        if setting.type_hint == "choice" and setting.valid_values:
            self._edit_choice(setting)
        elif setting.type_hint == "bool":
            self._edit_bool(setting)
        else:
            self._edit_text(setting)

    def _edit_choice(self, setting) -> None:
        from .base import FilterableListScreen, ListChoice

        current = display_value(setting)
        choices = [
            ListChoice(id=v, label=v, active=(v == current))
            for v in setting.valid_values
        ]

        def _picked(value) -> None:
            if value is not None:
                self._apply(setting, value)

        self.app.push_screen(
            FilterableListScreen(f"Value for {setting.key}", choices), _picked
        )

    def _edit_bool(self, setting) -> None:
        from .base import FilterableListScreen, ListChoice

        current = (display_value(setting) or "").lower() == "true"
        choices = [
            ListChoice(id="true", label="true", active=current),
            ListChoice(id="false", label="false", active=not current),
        ]

        def _picked(value) -> None:
            if value is not None:
                self._apply(setting, value)

        self.app.push_screen(
            FilterableListScreen(f"Value for {setting.key}", choices), _picked
        )

    def _edit_text(self, setting) -> None:
        from code_puppy.messaging import UserInputRequest

        from .interactive import TextInputModal

        current = "" if setting.sensitive else (display_value(setting) or "")
        request = UserInputRequest(
            prompt_id="__set__",
            prompt_text=f"New value for '{setting.key}' ({setting.type_hint}):",
            default_value=current,
            input_type="password" if setting.sensitive else "text",
        )

        def _on_value(value) -> None:
            if value is None:
                return
            coerced = _coerce_typed_input(setting.type_hint, value.strip())
            if coerced is None:
                from code_puppy.messaging import emit_error

                emit_error(f"Invalid {setting.type_hint} value: {value}")
                return
            self._apply(setting, coerced)

        self.app.push_screen(TextInputModal(request, prefill=True), _on_value)

    def _apply(self, setting, value) -> None:
        from code_puppy.command_line.config_apply import apply_setting
        from code_puppy.command_line.set_menu_values import mask_value
        from code_puppy.messaging import emit_error, emit_success, emit_warning

        result = apply_setting(setting.key, value, reload_agent=False)
        if not result.ok:
            emit_error(result.error or "Failed to apply setting.")
            return
        self._changed = True
        shown = mask_value(value) if setting.sensitive else value
        emit_success(f"Set {setting.key} = {shown}")
        if result.warning:
            emit_warning(result.warning)
        self._populate(self.query_one("#filter", Input).value, select=setting.key)

    # ------------------------------------------------------------------ actions
    def action_reset(self) -> None:
        key = self._highlighted()
        if not key:
            return
        from code_puppy.command_line.config_apply import invalidate_post_write_caches
        from code_puppy.config import reset_value
        from code_puppy.messaging import emit_success

        reset_value(key)
        invalidate_post_write_caches(key)
        self._changed = True
        emit_success(f"Reset {key} to default")
        self._populate(self.query_one("#filter", Input).value, select=key)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(self._changed)
