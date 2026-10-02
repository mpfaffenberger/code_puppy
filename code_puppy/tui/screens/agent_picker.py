"""Two-panel agent picker modal (list + live details preview).

Mirrors the classic /agent panel: a filterable list on the left and an
AGENT DETAILS preview on the right that updates as you navigate (Name,
Display Name, Pinned Model, MCP Servers, Description, Status).

Dismisses with the chosen agent name, or None if cancelled.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from code_puppy.list_filtering import query_matches_text

# (name, display_name, description)
AgentEntry = Tuple[str, str, str]


class AgentPickerScreen(ModalScreen[Optional[str]]):
    """Filterable agent list with a live details preview."""

    CSS = """
    AgentPickerScreen { align: center middle; }
    #dialog {
        width: 90%;
        height: 85%;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; margin-bottom: 1; }
    #body { height: 1fr; }
    #left { width: 42%; }
    #filter { margin-bottom: 1; }
    #items { height: 1fr; border: round $primary; }
    #preview {
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

    def __init__(self, entries: List[AgentEntry], current: str) -> None:
        super().__init__()
        self._entries = entries
        self._current = current
        self._by_id: Dict[str, AgentEntry] = {e[0]: e for e in entries}

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(f"Select an agent (current: {self._current})", id="title")
            with Horizontal(id="body"):
                with Vertical(id="left"):
                    yield Input(placeholder="type to filter...", id="filter")
                    yield OptionList(id="items")
                with VerticalScroll(id="preview"):
                    yield Static("", id="details")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2191/\u2193 move \u00b7 Enter select \u00b7 Esc cancel",
                    id="hint",
                )
                yield Button("Pin", id="pin")
                yield Button("Clone", id="clone")
                yield Button("Delete", id="delete", variant="error")
                yield Button("Dismiss", id="dismiss", variant="primary")

    def on_mount(self) -> None:
        self._populate("")
        self.query_one("#filter", Input).focus()

    # ------------------------------------------------------------------ list
    def _populate(self, query: str) -> None:
        items = self.query_one("#items", OptionList)
        items.clear_options()
        for name, display, _desc in self._entries:
            if not query_matches_text(query, f"{name} {display}"):
                continue
            active = name == self._current
            marker = "> " if active else "  "
            label = Text(f"{marker}{display}")
            if active:
                label.append("  (active)", style="bold green")
            items.add_option(Option(label, id=name))
        if items.option_count:
            items.highlighted = 0
            self._update_preview(items.get_option_at_index(0).id)
        else:
            self.query_one("#details", Static).update(
                Text("No agents match.", style="dim")
            )

    def on_input_changed(self, event: Input.Changed) -> None:
        self._populate(event.value)

    def on_key(self, event: events.Key) -> None:
        # Filter Input keeps focus; forward navigation keys to the OptionList.
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
            self._update_preview(event.option.id)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        items = self.query_one("#items", OptionList)
        if items.option_count and items.highlighted is not None:
            self.dismiss(items.get_option_at_index(items.highlighted).id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "pin":
            self.action_pin()
        elif bid == "clone":
            self.action_clone()
        elif bid == "delete":
            self.action_delete()
        else:
            self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)

    # ------------------------------------------------------------------ actions
    def _highlighted_id(self) -> Optional[str]:
        items = self.query_one("#items", OptionList)
        if items.option_count and items.highlighted is not None:
            return items.get_option_at_index(items.highlighted).id
        return None

    def _refresh_entries(self, select: Optional[str] = None) -> None:
        """Rebuild the agent list (after a clone/delete) and re-select a row."""
        from code_puppy.agents import get_agent_descriptions
        from code_puppy.agents.agent_manager import (
            get_available_agents,
            get_current_agent_name,
        )

        agents = get_available_agents()
        descriptions = get_agent_descriptions()
        self._current = get_current_agent_name()
        self._entries = [
            (n, d, descriptions.get(n, "No description available"))
            for n, d in sorted(agents.items(), key=lambda kv: kv[1].lower())
        ]
        self._by_id = {e[0]: e for e in self._entries}
        self._populate(self.query_one("#filter", Input).value)
        if select and select in self._by_id:
            items = self.query_one("#items", OptionList)
            for i in range(items.option_count):
                if items.get_option_at_index(i).id == select:
                    items.highlighted = i
                    break

    def action_pin(self) -> None:
        """Pin a model to the highlighted agent (overrides the global model)."""
        name = self._highlighted_id()
        if not name:
            return
        from code_puppy.command_line.model_picker_completion import load_model_names

        from .base import FilterableListScreen, ListChoice

        current_pin = self._pinned_model(name)
        choices = [ListChoice(id="(unpin)", label="(unpin) - use the global model")]
        choices += [
            ListChoice(id=m, label=m, active=(m == current_pin))
            for m in sorted(load_model_names())
        ]

        def _picked(model_id) -> None:
            if not model_id:
                return
            from code_puppy.command_line.agent_menu import (
                _apply_pinned_model,
                apply_pending_pin_reload,
                consume_pending_pin_reloads,
            )

            _apply_pinned_model(name, model_id)
            for an, pm in consume_pending_pin_reloads():
                apply_pending_pin_reload(an, pm)
            self._update_preview(name)

        self.app.push_screen(
            FilterableListScreen(f"Pin a model for {name}", choices), _picked
        )

    def action_clone(self) -> None:
        """Clone the highlighted agent into an independent, editable copy."""
        name = self._highlighted_id()
        if not name:
            return
        from code_puppy.agents import clone_agent
        from code_puppy.messaging import emit_error, emit_success

        try:
            cloned = clone_agent(name)
        except Exception as exc:
            emit_error(f"Clone failed: {exc}")
            return
        emit_success(f"Cloned '{name}' -> '{cloned or name}'")
        self._refresh_entries(select=cloned or name)

    def action_delete(self) -> None:
        """Delete the highlighted clone (guarded: clones only, not active)."""
        name = self._highlighted_id()
        if not name:
            return
        from code_puppy.agents import is_clone_agent_name
        from code_puppy.messaging import emit_warning

        if not is_clone_agent_name(name):
            emit_warning("Only cloned agents can be deleted.")
            return
        if name == self._current:
            emit_warning("Cannot delete the active agent. Switch first.")
            return

        from uuid import uuid4

        from code_puppy.messaging import ConfirmationRequest

        from .interactive import ConfirmModal

        request = ConfirmationRequest(
            prompt_id=str(uuid4()),
            title="Delete clone?",
            description=f"Permanently delete the cloned agent '{name}'?",
            options=["Delete", "Cancel"],
        )

        def _confirmed(result) -> None:
            confirmed = result[0] if result else False
            if not confirmed:
                return
            from code_puppy.agents import delete_clone_agent
            from code_puppy.messaging import emit_error, emit_success

            try:
                ok = delete_clone_agent(name)
            except Exception as exc:
                emit_error(f"Delete failed: {exc}")
                return
            if ok:
                emit_success(f"Deleted clone '{name}'")
                self._refresh_entries()

        self.app.push_screen(ConfirmModal(request), _confirmed)

    # ------------------------------------------------------------------ preview
    def _update_preview(self, name: Optional[str]) -> None:
        details = self.query_one("#details", Static)
        entry = self._by_id.get(name) if name else None
        if entry is None:
            details.update(Text("No agent selected.", style="dim"))
            return
        details.update(self._build_details(entry))

    def _build_details(self, entry: AgentEntry) -> Text:
        name, display, description = entry
        is_current = name == self._current
        pinned = self._pinned_model(name)
        bound = self._bound_servers(name)

        t = Text()
        t.append("AGENT DETAILS\n\n", style="dim cyan")
        t.append("Name: ", style="bold")
        t.append(f"{name}\n\n")
        t.append("Display Name: ", style="bold")
        t.append(f"{display}\n\n", style="cyan")
        t.append("Pinned Model: ", style="bold")
        if pinned:
            t.append(f"{pinned}\n\n", style="yellow")
        else:
            t.append("default\n\n", style="dim")
        t.append("MCP Servers: ", style="bold")
        if bound:
            auto = sum(1 for opts in bound.values() if opts.get("auto_start"))
            summary = f"{len(bound)} bound" + (f" ({auto} auto-start)" if auto else "")
            t.append(f"{summary}\n\n", style="green")
        else:
            t.append("none bound (strict opt-in)\n\n", style="dim")
        t.append("Description:\n", style="bold")
        t.append(f"{description}\n\n", style="dim")
        t.append("Status: ", style="bold")
        if is_current:
            t.append("\u2713 Currently Active", style="bold green")
        else:
            t.append("Not active", style="dim")
        return t

    @staticmethod
    def _pinned_model(name: str) -> Optional[str]:
        try:
            from code_puppy.config import get_agent_pinned_model

            return get_agent_pinned_model(name)
        except Exception:
            return None

    @staticmethod
    def _bound_servers(name: str) -> dict:
        try:
            from code_puppy.mcp_.agent_bindings import get_bound_servers

            return get_bound_servers(name) or {}
        except Exception:
            return {}
