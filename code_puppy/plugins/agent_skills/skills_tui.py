"""Textual ModalScreen for /skills — the TUI counterpart of the skills menu.

Browses installed skills with a live detail panel and lets the user:
  * ``e`` / Enter -> toggle a skill enabled/disabled
  * ``v``         -> view the skill's SKILL.md
  * ``g``         -> toggle skills integration globally
  * ``r``         -> refresh the discovery cache

Reuses the same data layer (``discover_skills`` / ``parse_skill_metadata`` /
``get_disabled_skills`` / ``set_skill_disabled`` / ``get_skills_enabled`` /
``set_skills_enabled``) so behaviour matches the classic prompt_toolkit menu.
The remote-catalog installer (``/skills install``) is a separate flow and is
not part of this screen. Wired via the register_screen hook (TUI only).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, OptionList, Static
from textual.widgets.option_list import Option


@dataclass
class _SkillRow:
    name: str
    path: Path
    description: str
    version: Optional[str]
    author: Optional[str]
    tags: List[str]
    disabled: bool
    has_skill_md: bool


class SkillsScreen(ModalScreen[None]):
    """Browse + enable/disable/view skills. Dismisses with None."""

    CSS = """
    SkillsScreen { align: center middle; }
    #dialog {
        width: 92%;
        height: 88%;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; }
    #subtitle { color: $text-muted; margin-bottom: 1; }
    #body { height: 1fr; }
    #left { width: 48%; }
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
        Binding("e", "toggle", "Toggle skill"),
        Binding("v", "view", "View SKILL.md"),
        Binding("g", "toggle_global", "Toggle integration"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[_SkillRow] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Agent Skills", id="title")
            yield Label("", id="subtitle")
            with Horizontal(id="body"):
                with Vertical(id="left"):
                    yield OptionList(id="items")
                with VerticalScroll(id="details"):
                    yield Static("", id="details-text")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2191/\u2193 move \u00b7 e toggle \u00b7 v view \u00b7 "
                    "g integration \u00b7 r refresh \u00b7 Esc close",
                    id="hint",
                )
                yield Button("Close", id="dismiss", variant="primary")

    def on_mount(self) -> None:
        self._refresh()
        self.query_one("#items", OptionList).focus()

    # ------------------------------------------------------------------ data
    def _load_rows(self) -> List[_SkillRow]:
        from code_puppy.plugins.agent_skills.config import get_disabled_skills
        from code_puppy.plugins.agent_skills.discovery import discover_skills
        from code_puppy.plugins.agent_skills.metadata import parse_skill_metadata

        disabled = get_disabled_skills()
        rows: List[_SkillRow] = []
        for skill in discover_skills():
            meta = parse_skill_metadata(skill.path) if skill.has_skill_md else None
            name = meta.name if meta else skill.name
            rows.append(
                _SkillRow(
                    name=name,
                    path=skill.path,
                    description=(
                        meta.description if meta else "(no SKILL.md metadata found)"
                    ),
                    version=meta.version if meta else None,
                    author=meta.author if meta else None,
                    tags=list(meta.tags) if meta else [],
                    disabled=name in disabled,
                    has_skill_md=skill.has_skill_md,
                )
            )
        return rows

    def _refresh(self, *, select: Optional[str] = None) -> None:
        from code_puppy.plugins.agent_skills.config import get_skills_enabled

        items = self.query_one("#items", OptionList)
        prev = items.highlighted or 0
        self._rows = self._load_rows()

        enabled = get_skills_enabled()
        state = "[green]enabled[/]" if enabled else "[red]disabled[/]"
        self.query_one("#subtitle", Label).update(
            Text.from_markup(
                f"integration: {state}  \u00b7  {len(self._rows)} skill(s)  "
                "(press g to toggle integration)"
            )
        )

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

    def _row_label(self, row: _SkillRow) -> Text:
        label = Text()
        if row.disabled:
            label.append("\u25cb ", style="bold red")
            label.append(row.name, style="dim strike")
            label.append("  (disabled)", style="red")
        else:
            label.append("\u25cf ", style="bold green")
            label.append(row.name, style="green")
        if row.version:
            label.append(f"  v{row.version}", style="dim")
        return label

    # ------------------------------------------------------------------ details
    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        if event.option is not None:
            self._update_details(event.option.id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._toggle(event.option.id)

    def _highlighted(self) -> Optional[_SkillRow]:
        items = self.query_one("#items", OptionList)
        if items.option_count and items.highlighted is not None:
            name = items.get_option_at_index(items.highlighted).id
            return next((r for r in self._rows if r.name == name), None)
        return None

    def _update_details(self, name: Optional[str]) -> None:
        row = next((r for r in self._rows if r.name == name), None)
        self.query_one("#details-text", Static).update(self._build_details(row))

    def _build_details(self, row: Optional[_SkillRow]) -> Text:
        t = Text()
        t.append("SKILL DETAILS\n\n", style="bold cyan")
        if row is None:
            t.append("No skills found.\n", style="yellow")
            t.append(
                "Create skills in ~/.code_puppy/skills/ or ./skills/, "
                "or run /skills install.",
                style="dim",
            )
            return t
        t.append("Name: ", style="bold")
        t.append(f"{row.name}\n\n", style="cyan")
        t.append("Status: ", style="bold")
        if row.disabled:
            t.append("DISABLED\n\n", style="bold red")
        else:
            t.append("ENABLED\n\n", style="bold green")
        if row.version:
            t.append("Version: ", style="bold")
            t.append(f"{row.version}\n\n")
        if row.author:
            t.append("Author: ", style="bold")
            t.append(f"{row.author}\n\n")
        if row.tags:
            t.append("Tags: ", style="bold")
            t.append(f"{', '.join(row.tags)}\n\n", style="yellow")
        t.append("Description:\n", style="bold")
        t.append(f"  {row.description}\n", style="dim")
        return t

    # ------------------------------------------------------------------ actions
    def action_toggle(self) -> None:
        row = self._highlighted()
        if row is not None:
            self._toggle(row.name)

    def _toggle(self, name: Optional[str]) -> None:
        row = next((r for r in self._rows if r.name == name), None)
        if row is None:
            return
        from code_puppy.messaging import emit_success
        from code_puppy.plugins.agent_skills.config import set_skill_disabled

        new_disabled = not row.disabled
        set_skill_disabled(name, new_disabled)
        state = "disabled" if new_disabled else "enabled"
        emit_success(f"Skill {state}: {name}")
        self._refresh(select=name)

    def action_view(self) -> None:
        row = self._highlighted()
        if row is None:
            return
        from code_puppy.tui.screens.source_view import SourceViewScreen

        skill_md = row.path / "SKILL.md"
        try:
            content = skill_md.read_text(encoding="utf-8")
            error = None
        except Exception as exc:
            content = ""
            error = str(exc)
        self.app.push_screen(
            SourceViewScreen(
                f"{row.name} \u2014 SKILL.md", content, error, lexer="markdown"
            )
        )

    def action_toggle_global(self) -> None:
        from code_puppy.messaging import emit_success, emit_warning
        from code_puppy.plugins.agent_skills.config import (
            get_skills_enabled,
            set_skills_enabled,
        )

        new_state = not get_skills_enabled()
        set_skills_enabled(new_state)
        if new_state:
            emit_success("Skills integration enabled globally")
        else:
            emit_warning("Skills integration disabled globally")
        self._refresh()

    def action_refresh(self) -> None:
        from code_puppy.messaging import emit_success
        from code_puppy.plugins.agent_skills.discovery import refresh_skill_cache

        refreshed = refresh_skill_cache()
        valid = [s for s in refreshed if s.has_skill_md]
        emit_success(
            f"Refreshed skills cache: {len(refreshed)} discovered "
            f"({len(valid)} with SKILL.md)"
        )
        self._refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)


def open_skills(app) -> None:
    """register_screen opener: push the skills browser screen."""
    app.push_screen(SkillsScreen())


__all__ = ["SkillsScreen", "open_skills"]
