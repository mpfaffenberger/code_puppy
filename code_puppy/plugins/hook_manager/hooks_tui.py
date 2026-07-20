"""Textual ModalScreen for /hooks — the TUI counterpart of the hooks menu.

Lists all configured Claude Code hooks (project + global) with their
enabled/disabled status, and lets the user toggle (``e``/Enter) or delete
(``d``) the highlighted hook. Reuses the same config layer
(``flatten_all_hooks`` / ``toggle_hook_enabled`` / ``delete_hook`` / the
save+load helpers) so behaviour matches the classic prompt_toolkit menu.
Wired via the register_screen hook (TUI only).
"""

from __future__ import annotations

from typing import List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, OptionList, Static
from textual.widgets.option_list import Option

from code_puppy.plugins.hook_manager.config import HookEntry


class HooksScreen(ModalScreen[None]):
    """Browse + enable/disable/delete Claude Code hooks. Dismisses with None."""

    CSS = """
    HooksScreen { align: center middle; }
    #dialog {
        width: 92%;
        height: 88%;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; margin-bottom: 1; }
    #body { height: 1fr; }
    #left { width: 52%; }
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
        Binding("d", "delete", "Delete"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._entries: List[HookEntry] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Claude Code Hooks", id="title")
            with Horizontal(id="body"):
                with Vertical(id="left"):
                    yield OptionList(id="items")
                with VerticalScroll(id="details"):
                    yield Static("", id="details-text")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2191/\u2193 move \u00b7 e toggle \u00b7 d delete \u00b7 Esc close",
                    id="hint",
                )
                yield Button("Close", id="dismiss", variant="primary")

    def on_mount(self) -> None:
        self._refresh()
        self.query_one("#items", OptionList).focus()

    # ------------------------------------------------------------------ data
    def _refresh(self, *, keep_index: Optional[int] = None) -> None:
        from code_puppy.plugins.hook_manager.config import flatten_all_hooks

        items = self.query_one("#items", OptionList)
        prev = keep_index if keep_index is not None else (items.highlighted or 0)
        self._entries = flatten_all_hooks()
        items.clear_options()
        if not self._entries:
            self.query_one("#details-text", Static).update(self._build_details(None))
            return
        for idx, entry in enumerate(self._entries):
            items.add_option(Option(self._row_label(entry), id=str(idx)))
        target = min(prev, len(self._entries) - 1)
        items.highlighted = target
        self._update_details(target)

    def _row_label(self, entry: HookEntry) -> Text:
        label = Text()
        label.append(f"[{entry.source[:4]}] ", style="dim")
        if entry.enabled:
            label.append("\u25cf ", style="bold green")
        else:
            label.append("\u25cb ", style="bold red")
        label.append(f"{entry.event_type} ", style="cyan")
        label.append(f"({entry.display_matcher}) ", style="dim")
        label.append(entry.display_command, style="" if entry.enabled else "dim strike")
        return label

    # ------------------------------------------------------------------ details
    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if event.option is not None:
            self._update_details(int(event.option.id))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._toggle(int(event.option.id))

    def _highlighted_index(self) -> Optional[int]:
        items = self.query_one("#items", OptionList)
        if items.option_count and items.highlighted is not None:
            return int(items.get_option_at_index(items.highlighted).id)
        return None

    def _update_details(self, index: int) -> None:
        entry = self._entries[index] if 0 <= index < len(self._entries) else None
        self.query_one("#details-text", Static).update(self._build_details(entry))

    def _build_details(self, entry: Optional[HookEntry]) -> Text:
        t = Text()
        t.append("HOOK DETAILS\n\n", style="bold cyan")
        if entry is None:
            t.append("No hooks configured.\n", style="yellow")
            t.append(
                "Add hooks to .claude/settings.json (project) or "
                "~/.code_puppy/hooks.json (global).",
                style="dim",
            )
            return t
        t.append("Event: ", style="bold")
        t.append(f"{entry.event_type}\n\n", style="cyan")
        t.append("Source: ", style="bold")
        t.append(f"{entry.source}\n\n")
        t.append("Status: ", style="bold")
        if entry.enabled:
            t.append("ENABLED\n\n", style="bold green")
        else:
            t.append("DISABLED\n\n", style="bold red")
        t.append("Matcher: ", style="bold")
        t.append(f"{entry.matcher}\n\n", style="yellow")
        t.append("Type: ", style="bold")
        t.append(f"{entry.hook_type}  (timeout {entry.timeout}ms)\n\n")
        t.append("Command:\n", style="bold")
        t.append(f"{entry.command}\n", style="dim")
        return t

    # ------------------------------------------------------------------ actions
    def _save_toggle(self, entry: HookEntry, new_enabled: bool) -> None:
        from code_puppy.plugins.hook_manager.config import (
            _load_global_hooks_config,
            _load_project_hooks_config,
            save_global_hooks_config,
            save_hooks_config,
            toggle_hook_enabled,
        )

        if entry.source == "global":
            cfg = toggle_hook_enabled(
                _load_global_hooks_config(),
                entry.event_type,
                entry._group_index,
                entry._hook_index,
                new_enabled,
            )
            save_global_hooks_config(cfg)
        else:
            cfg = toggle_hook_enabled(
                _load_project_hooks_config(),
                entry.event_type,
                entry._group_index,
                entry._hook_index,
                new_enabled,
            )
            save_hooks_config(cfg)

    def action_toggle(self) -> None:
        idx = self._highlighted_index()
        if idx is not None:
            self._toggle(idx)

    def _toggle(self, index: int) -> None:
        if not (0 <= index < len(self._entries)):
            return
        from code_puppy.messaging import emit_success

        entry = self._entries[index]
        new_enabled = not entry.enabled
        self._save_toggle(entry, new_enabled)
        state = "enabled" if new_enabled else "disabled"
        emit_success(f"Hook {state}: {entry.display_command}")
        self._refresh(keep_index=index)

    def action_delete(self) -> None:
        idx = self._highlighted_index()
        if idx is None or not (0 <= idx < len(self._entries)):
            return
        entry = self._entries[idx]

        from code_puppy.messaging import ConfirmationRequest

        from code_puppy.tui.screens.interactive import ConfirmModal

        request = ConfirmationRequest(
            prompt_id="__hook_delete__",
            title=f"Delete this {entry.source} hook?",
            description=f"[{entry.event_type}] {entry.display_command}",
            options=["Delete", "Cancel"],
            allow_feedback=False,
        )

        def _confirmed(result) -> None:
            confirmed, _feedback = result
            if confirmed:
                self._delete_entry(entry)

        self.app.push_screen(ConfirmModal(request), _confirmed)

    def _delete_entry(self, entry: HookEntry) -> None:
        from code_puppy.messaging import emit_warning
        from code_puppy.plugins.hook_manager.config import (
            _load_global_hooks_config,
            _load_project_hooks_config,
            delete_hook,
            save_global_hooks_config,
            save_hooks_config,
        )

        if entry.source == "global":
            cfg = delete_hook(
                _load_global_hooks_config(),
                entry.event_type,
                entry._group_index,
                entry._hook_index,
            )
            save_global_hooks_config(cfg)
        else:
            cfg = delete_hook(
                _load_project_hooks_config(),
                entry.event_type,
                entry._group_index,
                entry._hook_index,
            )
            save_hooks_config(cfg)
        emit_warning(f"Deleted hook: {entry.display_command}")
        self._refresh(keep_index=0)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)


def open_hooks(app) -> None:
    """register_screen opener: push the hooks management screen."""
    app.push_screen(HooksScreen())


__all__ = ["HooksScreen", "open_hooks"]
