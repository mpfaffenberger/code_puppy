"""Textual ModalScreen for /plugins — the TUI counterpart of PluginsMenu.

Lists loaded plugins grouped by tier (builtin/user/project) with their
enabled/disabled status, and lets the user toggle a plugin with ``e`` or
Enter. Reuses the same config layer (``set_plugin_disabled`` /
``get_disabled_plugins`` / ``get_loaded_plugins``) so behaviour matches the
classic prompt_toolkit menu. Wired via the register_screen hook (TUI only).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, OptionList, Static
from textual.widgets.option_list import Option


@dataclass
class _PluginRow:
    name: str
    tier: str
    disabled: bool


class PluginsScreen(ModalScreen[None]):
    """Browse + enable/disable plugins. Dismisses with None."""

    CSS = """
    PluginsScreen { align: center middle; }
    #dialog {
        width: 88%;
        height: 85%;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; margin-bottom: 1; }
    #body { height: 1fr; }
    #left { width: 50%; }
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
        Binding("escape", "cancel", "Close"),
        Binding("e", "toggle", "Toggle"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[_PluginRow] = []
        self._changed = False

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Plugins", id="title")
            with Horizontal(id="body"):
                with Vertical(id="left"):
                    yield OptionList(id="items")
                with VerticalScroll(id="details"):
                    yield Static("", id="details-text")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2191/\u2193 move \u00b7 e / Enter toggle \u00b7 Esc close",
                    id="hint",
                )
                yield Button("Close", id="dismiss", variant="primary")

    def on_mount(self) -> None:
        self._refresh()
        self.query_one("#items", OptionList).focus()

    # ------------------------------------------------------------------ data
    def _load_rows(self) -> List[_PluginRow]:
        from code_puppy.plugins import get_loaded_plugins
        from code_puppy.plugins.config import get_disabled_plugins

        loaded = get_loaded_plugins()
        disabled = get_disabled_plugins()
        rows: List[_PluginRow] = []
        for tier in ("builtin", "user", "project"):
            for name in sorted(loaded.get(tier, [])):
                rows.append(_PluginRow(name, tier, name in disabled))
        return rows

    def _refresh(self, *, select: Optional[str] = None) -> None:
        items = self.query_one("#items", OptionList)
        prev = items.highlighted or 0
        self._rows = self._load_rows()
        items.clear_options()
        if not self._rows:
            self.query_one("#details-text", Static).update(self._build_details(None))
            return
        target = 0
        for idx, row in enumerate(self._rows):
            items.add_option(Option(self._row_label(row), id=row.name))
            if select is not None and row.name == select:
                target = idx
        if select is None:
            target = min(prev, len(self._rows) - 1)
        items.highlighted = target
        self._update_details(self._rows[target].name)

    def _row_label(self, row: _PluginRow) -> Text:
        # Mirror the classic menu's +/x markers. Tier lives in the detail
        # panel; only surface it inline for the rarer user/project plugins so
        # an all-builtin list stays clean (no repeated [buil] noise).
        label = Text()
        if row.disabled:
            label.append("x ", style="bold red")
            label.append(row.name, style="dim strike")
            label.append("  (disabled)", style="bold red")
        else:
            label.append("+ ", style="bold green")
            label.append(row.name, style="green")
        if row.tier != "builtin":
            label.append(f"  ({row.tier})", style="dim")
        return label

    # ------------------------------------------------------------------ details
    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if event.option is not None:
            self._update_details(event.option.id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._toggle(event.option.id)

    def _highlighted_name(self) -> Optional[str]:
        items = self.query_one("#items", OptionList)
        if items.option_count and items.highlighted is not None:
            return items.get_option_at_index(items.highlighted).id
        return None

    def _update_details(self, name: Optional[str]) -> None:
        row = next((r for r in self._rows if r.name == name), None)
        self.query_one("#details-text", Static).update(self._build_details(row))

    def _build_details(self, row: Optional[_PluginRow]) -> Text:
        t = Text()
        t.append("PLUGIN DETAILS\n\n", style="bold cyan")
        if row is None:
            t.append("No plugins loaded.", style="yellow")
            return t
        t.append("Name: ", style="bold")
        t.append(f"{row.name}\n\n", style="cyan")
        t.append("Tier: ", style="bold")
        t.append(f"{row.tier}\n\n")
        t.append("Status: ", style="bold")
        if row.disabled:
            t.append("DISABLED\n\n", style="bold red")
        else:
            t.append("ENABLED\n\n", style="bold green")
        t.append("Press e (or Enter) to toggle.\n", style="dim")
        t.append("Changes take effect after a restart.", style="dim")
        return t

    # ------------------------------------------------------------------ actions
    def action_toggle(self) -> None:
        self._toggle(self._highlighted_name())

    def _toggle(self, name: Optional[str]) -> None:
        if not name:
            return
        from code_puppy.messaging import emit_success, emit_warning
        from code_puppy.plugins.config import set_plugin_disabled

        row = next((r for r in self._rows if r.name == name), None)
        if row is None:
            return
        new_disabled = not row.disabled
        if set_plugin_disabled(name, disabled=new_disabled):
            self._changed = True
            state = "disabled" if new_disabled else "re-enabled"
            emit_success(f"Plugin '{name}' {state}.")
            emit_warning("Restart Code Puppy for this change to take effect.")
        self._refresh(select=name)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)


def open_plugins(app) -> None:
    """register_screen opener: push the plugins management screen."""
    app.push_screen(PluginsScreen())


__all__ = ["PluginsScreen", "open_plugins"]
