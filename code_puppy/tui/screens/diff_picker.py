"""Two-panel diff-color picker modal (menu + live syntax-highlighted preview).

Mirrors the classic ``/diff`` panel: a small menu on the left (Configure
Addition / Deletion color) and a LIVE PREVIEW on the right that renders a real
syntax-highlighted sample diff with the currently configured colors. Left/Right
arrows cycle the preview language.

Enter (or click) on a menu row opens a swatch color picker; the preview updates
in place. ``Dismiss``/Esc closes the modal. Colors are applied immediately via
the real setters (consistent with the ``/colors`` picker).
"""

from __future__ import annotations

from typing import List, Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, OptionList, Static
from textual.widgets.option_list import Option

from code_puppy.command_line.diff_menu import (
    ADDITION_COLORS,
    DELETION_COLORS,
    LANGUAGE_SAMPLES,
    SUPPORTED_LANGUAGES,
)

ADDITIONS = "additions"
DELETIONS = "deletions"


class DiffPickerScreen(ModalScreen[None]):
    """Diff-color menu with a live syntax-highlighted preview (mirrors classic)."""

    CSS = """
    DiffPickerScreen { align: center middle; }
    #dialog {
        width: 90%;
        height: 85%;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; margin-bottom: 1; }
    #body { height: 1fr; }
    #left { width: 38%; }
    #items { height: auto; border: round $primary; }
    #lang-hint { color: $warning; margin-top: 1; }
    #nav-hint { color: $text-muted; margin-top: 1; }
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

    def __init__(self) -> None:
        super().__init__()
        self._lang_index = 0

    # ------------------------------------------------------------------ compose
    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Diff Color Configuration", id="title")
            with Horizontal(id="body"):
                with Vertical(id="left"):
                    yield OptionList(
                        Option("Configure Addition Color", id=ADDITIONS),
                        Option("Configure Deletion Color", id=DELETIONS),
                        id="items",
                    )
                    yield Label("", id="lang-hint")
                    yield Label(
                        "\u2190\u2192 change language \u00b7 Enter configure",
                        id="nav-hint",
                    )
                with VerticalScroll(id="preview"):
                    yield Static("", id="details")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2191/\u2193 move \u00b7 \u2190\u2192 language \u00b7 "
                    "Enter configure \u00b7 Esc close",
                    id="hint",
                )
                yield Button("Dismiss", id="dismiss", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#items", OptionList).focus()
        self._refresh()

    # ------------------------------------------------------------------ helpers
    @property
    def _language(self) -> str:
        return SUPPORTED_LANGUAGES[self._lang_index]

    def _cycle_language(self, delta: int) -> None:
        self._lang_index = (self._lang_index + delta) % len(SUPPORTED_LANGUAGES)
        self._refresh()

    def _refresh(self) -> None:
        self.query_one("#lang-hint", Label).update(
            f"Language: {self._language.upper()}  (\u2190\u2192 to change)"
        )
        self.query_one("#details", Static).update(self._build_preview())

    # ------------------------------------------------------------------ keys
    def on_key(self, event: events.Key) -> None:
        if event.key in ("left", "right"):
            event.stop()
            event.prevent_default()
            self._cycle_language(-1 if event.key == "left" else 1)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._open_color_picker(event.option.id)

    # ------------------------------------------------------------------ buttons
    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)

    # ------------------------------------------------------------------ color pick
    def _open_color_picker(self, which: Optional[str]) -> None:
        if which not in (ADDITIONS, DELETIONS):
            return
        from code_puppy.config import (
            get_diff_addition_color,
            get_diff_deletion_color,
        )

        from .base import FilterableListScreen, ListChoice

        if which == ADDITIONS:
            color_dict = ADDITION_COLORS
            current = get_diff_addition_color()
            title = "Diff addition color"
        else:
            color_dict = DELETION_COLORS
            current = get_diff_deletion_color()
            title = "Diff deletion color"

        choices: List[ListChoice] = [
            ListChoice(
                id=hex_value,
                label=name,
                search=f"{name} {hex_value}",
                style=f"on {hex_value}",
                active=(hex_value.lower() == current.lower()),
            )
            for name, hex_value in color_dict.items()
        ]

        def _picked(hex_value) -> None:
            if not hex_value:
                return
            from code_puppy.config import (
                set_diff_addition_color,
                set_diff_deletion_color,
            )
            from code_puppy.messaging import emit_success

            if which == ADDITIONS:
                set_diff_addition_color(hex_value)
                emit_success(f"Set diff addition color to {hex_value}")
            else:
                set_diff_deletion_color(hex_value)
                emit_success(f"Set diff deletion color to {hex_value}")
            self._refresh()

        self.app.push_screen(FilterableListScreen(title, choices), _picked)

    # ------------------------------------------------------------------ preview
    def _build_preview(self) -> Text:
        from code_puppy.config import (
            get_diff_addition_color,
            get_diff_deletion_color,
        )
        from code_puppy.tools.common import format_diff_with_colors

        filename, sample = LANGUAGE_SAMPLES.get(
            self._language, LANGUAGE_SAMPLES["python"]
        )

        t = Text()
        t.append("LIVE PREVIEW - Syntax Highlighted Diff\n\n", style="bold cyan")
        t.append("Addition Color: ", style="bold")
        t.append(f"{get_diff_addition_color()}\n")
        t.append("Deletion Color: ", style="bold")
        t.append(f"{get_diff_deletion_color()}\n\n")
        t.append("Language: ", style="bold yellow")
        t.append(f"{self._language.upper()}", style="bold yellow")
        t.append("  (\u2190 \u2192 to cycle)\n\n", style="dim")
        t.append(f"Example ({filename}):\n\n", style="bold")
        try:
            t.append(format_diff_with_colors(sample))
        except Exception as exc:  # pragma: no cover - defensive
            t.append(f"Preview error: {exc}", style="red")
        return t
