"""Textual ModalScreen for /plugins — the TUI counterpart of PluginsMenu.

Lists loaded plugins grouped by tier (builtin/user/project) with their
enabled/disabled status, and lets the user toggle a plugin with ``e`` or
Enter. Project plugins that are untrusted or changed require a trust
ceremony (TrustCeremonyScreen) before they can be activated.

Reuses the same config layer (``set_plugin_disabled`` /
``get_disabled_plugins`` / ``get_loaded_plugins`` /
``get_project_plugin_status``) so behaviour matches the classic
prompt_toolkit menu. Wired via the register_screen hook (TUI only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

# Status values that map to the classic _PluginEntry.status field.
_TRUST_REQUIRED = {"untrusted", "changed"}
_ACTIVATE_ONLY = {"disabled", "error"}


@dataclass
class _PluginRow:
    name: str
    tier: str
    disabled: bool
    # "loaded" | "untrusted" | "changed" | "disabled" | "error"
    status: str = "loaded"
    # files in the plugin dir (populated for project plugins before trust)
    file_listing: str = field(default="", compare=False)


class TrustCeremonyScreen(ModalScreen[bool]):
    """Modal requiring the user to type 'trust' to activate a project plugin.

    Returns True if trust was granted and the plugin activated, False otherwise.
    Mirrors classic's ``plugins_menu_layout.py`` trust popup, using native
    Textual widgets instead of prompt_toolkit (which fights the Textual screen).
    """

    CSS = """
    TrustCeremonyScreen { align: center middle; }
    #trust-dialog {
        width: 80%;
        max-width: 72;
        height: auto;
        border: double $warning;
        background: $panel;
        padding: 1 2;
    }
    #trust-title { text-style: bold; color: $warning; margin-bottom: 1; }
    #trust-body { height: auto; margin-bottom: 1; }
    #trust-files { color: $text-muted; margin-bottom: 1; height: auto; }
    #trust-input-row { height: 3; }
    #trust-input {
        width: 1fr;
        height: 3;
        border: round $warning;
    }
    #trust-footer { height: 3; margin-top: 1; align-horizontal: right; }
    #trust-footer Button { height: 3; margin-left: 1; min-width: 9; }
    #trust-error { color: $error; height: auto; }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, plugin_name: str, file_listing: str) -> None:
        super().__init__()
        self._plugin_name = plugin_name
        self._file_listing = file_listing
        self._error = ""

    def compose(self) -> ComposeResult:
        from code_puppy.plugins.plugin_list.project_trust_flow import ACCEPT_WORD

        with Vertical(id="trust-dialog"):
            yield Label("⚠  Trust Project Plugin", id="trust-title")
            yield Static(
                Text.from_markup(
                    f"[bold]Plugin:[/bold] [cyan]{self._plugin_name}[/cyan]\n\n"
                    "This project plugin will execute code from your repository.\n"
                    "Review the files below, then type "
                    f"[bold yellow]{ACCEPT_WORD}[/bold yellow] to confirm."
                ),
                id="trust-body",
            )
            yield Static(self._file_listing, id="trust-files")
            yield Static("", id="trust-error")
            with Horizontal(id="trust-input-row"):
                yield Input(
                    placeholder=f'Type "{ACCEPT_WORD}" to confirm',
                    id="trust-input",
                )
            with Horizontal(id="trust-footer"):
                yield Button("Cancel", id="cancel-btn", variant="default")
                yield Button("Confirm", id="confirm-btn", variant="warning")

    def on_mount(self) -> None:
        self.query_one("#trust-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._try_confirm(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self._try_confirm(self.query_one("#trust-input", Input).value)
        else:
            self.dismiss(False)

    def _try_confirm(self, text: str) -> None:
        from code_puppy.plugins.plugin_list.project_trust_flow import (
            ACCEPT_WORD,
            grant_trust_and_load,
        )

        if text.strip().lower() != ACCEPT_WORD:
            err = self.query_one("#trust-error", Static)
            err.update(
                f"That isn't '{ACCEPT_WORD}' — type it exactly, or press Esc to cancel."
            )
            self.query_one("#trust-input", Input).value = ""
            return

        ok, msg = grant_trust_and_load(self._plugin_name)
        if not ok:
            err = self.query_one("#trust-error", Static)
            err.update(f"Failed to trust plugin: {msg}")
            return
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


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
                    "↑/↓ move · e / Enter toggle · Esc close",
                    id="hint",
                )
                yield Button("Close", id="dismiss", variant="primary")

    def on_mount(self) -> None:
        self._refresh()
        self.query_one("#items", OptionList).focus()

    # ------------------------------------------------------------------ data
    def _load_rows(self) -> List[_PluginRow]:
        from code_puppy.plugins import (
            get_loaded_plugins,
            get_project_plugin_status,
        )
        from code_puppy.plugins.config import get_disabled_plugins

        loaded = get_loaded_plugins()
        disabled = get_disabled_plugins()
        rows: List[_PluginRow] = []

        # Loaded (and enabled/disabled) plugins across all tiers.
        for tier in ("builtin", "user", "project"):
            for name in sorted(loaded.get(tier, [])):
                is_disabled = name in disabled
                rows.append(
                    _PluginRow(
                        name=name,
                        tier=tier,
                        disabled=is_disabled,
                        status="disabled" if is_disabled else "loaded",
                    )
                )

        # Project plugins held back by the trust gate (not yet in loaded set).
        try:
            statuses = get_project_plugin_status()
        except Exception:
            statuses = {}
        shown = {r.name for r in rows if r.tier == "project"}
        for name in sorted(statuses):
            if statuses[name] != "loaded" and name not in shown:
                file_listing = _get_file_listing(name)
                rows.append(
                    _PluginRow(
                        name=name,
                        tier="project",
                        disabled=True,
                        status=statuses[name],
                        file_listing=file_listing,
                    )
                )
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
        label = Text()
        # Status prefix markers — mirror classic menu's +/x/? markers.
        if row.status == "untrusted":
            label.append("? ", style="bold yellow")
            label.append(row.name, style="yellow")
            label.append("  (untrusted)", style="bold yellow")
        elif row.status == "changed":
            label.append("! ", style="bold yellow")
            label.append(row.name, style="yellow")
            label.append("  (changed)", style="bold yellow")
        elif row.status == "error":
            label.append("x ", style="bold red")
            label.append(row.name, style="dim strike")
            label.append("  (error)", style="bold red")
        elif row.disabled:
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

        status_text = {
            "loaded": ("ENABLED", "bold green"),
            "disabled": ("DISABLED", "bold red"),
            "untrusted": ("UNTRUSTED (press e to trust)", "bold yellow"),
            "changed": ("CHANGED (re-trust required, press e)", "bold yellow"),
            "error": ("ERROR (see logs)", "bold red"),
        }
        label, style = status_text.get(row.status, (row.status.upper(), ""))
        t.append(f"{label}\n\n", style=style)

        if row.status in _TRUST_REQUIRED:
            t.append("Press e (or Enter) to open the trust ceremony.\n", style="dim")
            if row.file_listing:
                t.append("\nFiles:\n", style="bold")
                t.append(row.file_listing, style="dim")
        elif row.status in _ACTIVATE_ONLY:
            t.append("Press e (or Enter) to activate.\n", style="dim")
        else:
            t.append("Press e (or Enter) to toggle.\n", style="dim")
            t.append("Changes take effect after a restart.", style="dim")
        return t

    # ------------------------------------------------------------------ actions
    def action_toggle(self) -> None:
        self._toggle(self._highlighted_name())

    def _toggle(self, name: Optional[str]) -> None:
        if not name:
            return
        row = next((r for r in self._rows if r.name == name), None)
        if row is None:
            return

        if row.status in _TRUST_REQUIRED:
            # Ceremony required — open the trust modal as a child screen.
            file_listing = row.file_listing or _get_file_listing(row.name)
            self.app.push_screen(
                TrustCeremonyScreen(row.name, file_listing),
                self._on_trust_result,
            )
            return

        if row.status in _ACTIVATE_ONLY:
            # Already trusted; just (re)activate without ceremony.
            from code_puppy.messaging import emit_success, emit_warning
            from code_puppy.plugins.plugin_list.project_trust_flow import (
                activate_project_plugin,
            )

            _ok, message = activate_project_plugin(row.name)
            if _ok:
                emit_success(message)
            else:
                emit_warning(message)
            self._refresh(select=row.name)
            return

        # Standard toggle for loaded plugins.
        from code_puppy.messaging import emit_success, emit_warning
        from code_puppy.plugins.config import set_plugin_disabled

        new_disabled = not row.disabled
        if set_plugin_disabled(row.name, disabled=new_disabled):
            self._changed = True
            state = "disabled" if new_disabled else "re-enabled"
            emit_success(f"Plugin '{row.name}' {state}.")
            emit_warning("Restart Code Puppy for this change to take effect.")
        self._refresh(select=row.name)

    def _on_trust_result(self, trusted: bool) -> None:
        """Called when the TrustCeremonyScreen dismisses."""
        if trusted:
            from code_puppy.messaging import emit_success

            emit_success("Plugin trusted and loaded — no restart needed.")
        self._refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)


def _get_file_listing(plugin_name: str) -> str:
    """Return a bullet-list of files in the project plugin dir (best-effort)."""
    try:
        from code_puppy.plugins import get_project_plugins_directory
        from code_puppy.plugins.plugin_list.project_trust_flow import (
            plugin_file_listing,
        )

        project_dir = get_project_plugins_directory()
        if project_dir is None:
            return ""
        plugin_dir = project_dir / plugin_name
        if not plugin_dir.is_dir():
            return ""
        return plugin_file_listing(plugin_dir)
    except Exception:
        return ""


def open_plugins(app) -> None:
    """register_screen opener: push the plugins management screen."""
    app.push_screen(PluginsScreen())


__all__ = ["PluginsScreen", "TrustCeremonyScreen", "open_plugins"]
