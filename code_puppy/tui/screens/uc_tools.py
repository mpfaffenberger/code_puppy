"""Two-panel /uc Universal Constructor tool browser (list + Tool Details).

Mirrors the classic ``/uc`` panels: a tool list on the left + a live "Tool
Details" preview on the right (name, status, version, author, signature,
description). Enter views source; ``e`` toggles enabled; ``d`` deletes (with
confirmation). Shows a friendly empty-state when there are no tools (instead of
the old one-line ``emit_info``).

Toggle/delete/source loading reuse the classic ``uc_menu`` helpers (DRY).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, OptionList, Static
from textual.widgets.option_list import Option

from code_puppy.command_line.uc_menu import (
    _delete_tool,
    _get_tool_entries,
    _load_source_code,
    _toggle_tool_enabled,
)
from code_puppy.plugins.universal_constructor.models import UCToolInfo


class UCToolsScreen(ModalScreen[None]):
    """Two-panel UC tool browser. Dismisses with None."""

    CSS = """
    UCToolsScreen { align: center middle; }
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
        Binding("escape", "cancel", "Exit"),
        Binding("e", "toggle", "Toggle enabled"),
        Binding("d", "delete", "Delete"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._tools: List[UCToolInfo] = _get_tool_entries()
        self._by_name: Dict[str, UCToolInfo] = {t.full_name: t for t in self._tools}

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Universal Constructor Tools", id="title")
            with Horizontal(id="body"):
                with Vertical(id="left"):
                    yield OptionList(id="items")
                with VerticalScroll(id="details"):
                    yield Static("", id="details-text")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2191/\u2193 move \u00b7 Enter source \u00b7 e toggle \u00b7 "
                    "d delete \u00b7 Esc exit",
                    id="hint",
                )
                yield Button("Dismiss", id="dismiss", variant="primary")

    def on_mount(self) -> None:
        self._populate()
        self.query_one("#items", OptionList).focus()

    # ------------------------------------------------------------------ list
    def _populate(self, *, select: Optional[str] = None) -> None:
        items = self.query_one("#items", OptionList)
        prev = items.highlighted or 0
        items.clear_options()
        if not self._tools:
            self.query_one("#details-text", Static).update(self._build_details(None))
            return
        target = 0
        for idx, tool in enumerate(self._tools):
            suffix = "" if tool.meta.enabled else "  [disabled]"
            style = "" if tool.meta.enabled else "dim"
            label = Text(f"{tool.full_name}{suffix}", style=style)
            items.add_option(Option(label, id=tool.full_name))
            if select is not None and tool.full_name == select:
                target = idx
        if select is None:
            target = min(prev, len(self._tools) - 1)
        items.highlighted = target
        self._update_details(self._tools[target].full_name)

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if event.option is not None:
            self._update_details(event.option.id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._view_source(event.option.id)

    def _highlighted(self) -> Optional[UCToolInfo]:
        items = self.query_one("#items", OptionList)
        if items.option_count and items.highlighted is not None:
            return self._by_name.get(items.get_option_at_index(items.highlighted).id)
        return None

    # ------------------------------------------------------------------ details
    def _update_details(self, name: Optional[str]) -> None:
        tool = self._by_name.get(name) if name else None
        self.query_one("#details-text", Static).update(self._build_details(tool))

    def _build_details(self, tool: Optional[UCToolInfo]) -> Text:
        t = Text()
        t.append("TOOL DETAILS\n\n", style="bold cyan")
        if tool is None:
            if not self._tools:
                t.append("No UC tools found.\n", style="yellow")
                t.append("Ask the LLM to create one!", style="dim")
            else:
                t.append("No tool selected.", style="yellow")
            return t
        t.append("Name: ", style="bold")
        t.append(f"{tool.meta.name}\n\n", style="cyan")
        if tool.meta.namespace:
            t.append("Full Name: ", style="bold")
            t.append(f"{tool.full_name}\n\n")
        t.append("Status: ", style="bold")
        if tool.meta.enabled:
            t.append("ENABLED\n\n", style="bold green")
        else:
            t.append("DISABLED\n\n", style="bold red")
        t.append("Version: ", style="bold")
        t.append(f"{tool.meta.version}\n\n")
        if tool.meta.author:
            t.append("Author: ", style="bold")
            t.append(f"{tool.meta.author}\n\n")
        t.append("Signature: ", style="bold")
        t.append(f"{tool.signature}\n\n", style="yellow")
        t.append("Description:\n", style="bold")
        t.append(f"  {tool.meta.description}\n", style="dim")
        return t

    # ------------------------------------------------------------------ actions
    def _view_source(self, name: Optional[str]) -> None:
        tool = self._by_name.get(name) if name else None
        if tool is None:
            return
        from .source_view import SourceViewScreen

        lines, error = _load_source_code(tool)
        self.app.push_screen(
            SourceViewScreen(tool.full_name, "\n".join(lines or []), error)
        )

    def action_toggle(self) -> None:
        tool = self._highlighted()
        if tool is None:
            return
        _toggle_tool_enabled(tool)
        self._refresh(select=tool.full_name)

    def action_delete(self) -> None:
        tool = self._highlighted()
        if tool is None:
            return
        from code_puppy.messaging import ConfirmationRequest

        from .interactive import ConfirmModal

        request = ConfirmationRequest(
            prompt_id="__uc_delete__",
            title=f"Delete '{tool.full_name}'?",
            description="This permanently deletes the tool's source file.",
            options=["Delete", "Cancel"],
            allow_feedback=False,
        )

        def _confirmed(result) -> None:
            confirmed, _feedback = result
            if confirmed:
                _delete_tool(tool)
                self._refresh()

        self.app.push_screen(ConfirmModal(request), _confirmed)

    def _refresh(self, *, select: Optional[str] = None) -> None:
        self._tools = _get_tool_entries()
        self._by_name = {t.full_name: t for t in self._tools}
        self._populate(select=select)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)
