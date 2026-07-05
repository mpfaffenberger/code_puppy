"""Two-panel banner-color picker modal (list + live preview).

Mirrors the classic ``/colors`` panel: a filterable banner list on the left and
a LIVE PREVIEW on the right that renders every banner with its current color +
sample content, highlighting the selected row as you navigate.

Enter (or click) on a banner opens a swatch color picker; the preview updates
in place. ``Reset All`` restores defaults; ``Dismiss``/Esc closes the modal.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from code_puppy.command_line.colors_menu import (
    BANNER_COLORS,
    BANNER_DISPLAY_INFO,
    BANNER_SAMPLE_CONTENT,
)
from code_puppy.list_filtering import query_matches_text

# (banner_key, display_name, icon, current_color)
BannerRow = Tuple[str, str, str, str]


class ColorsPickerScreen(ModalScreen[None]):
    """Filterable banner list with a live color preview (mirrors classic)."""

    CSS = """
    ColorsPickerScreen { align: center middle; }
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
        self._keys: List[str] = list(BANNER_DISPLAY_INFO.keys())

    # ------------------------------------------------------------------ compose
    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Banner Color Configuration", id="title")
            with Horizontal(id="body"):
                with Vertical(id="left"):
                    yield Input(placeholder="type to filter...", id="filter")
                    yield OptionList(id="items")
                with VerticalScroll(id="preview"):
                    yield Static("", id="details")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2191/\u2193 move \u00b7 Enter recolor \u00b7 Esc close",
                    id="hint",
                )
                yield Button("Reset All", id="reset")
                yield Button("Dismiss", id="dismiss", variant="primary")

    def on_mount(self) -> None:
        self._populate("")
        self.query_one("#filter", Input).focus()

    # ------------------------------------------------------------------ data
    @staticmethod
    def _colors() -> dict:
        from code_puppy.config import get_all_banner_colors

        return get_all_banner_colors()

    def _rows(self) -> List[BannerRow]:
        colors = self._colors()
        rows: List[BannerRow] = []
        for key in self._keys:
            display, icon = BANNER_DISPLAY_INFO[key]
            rows.append((key, display, icon, colors.get(key, "blue")))
        return rows

    # ------------------------------------------------------------------ list
    def _populate(self, query: str, *, select: Optional[str] = None) -> None:
        items = self.query_one("#items", OptionList)
        items.clear_options()
        target_index = 0
        idx = 0
        for key, display, _icon, color in self._rows():
            if not query_matches_text(query, f"{key} {display}"):
                continue
            label = Text(f"{display} ")
            label.append(f"[{color}]", style="dim")
            items.add_option(Option(label, id=key))
            if select is not None and key == select:
                target_index = idx
            idx += 1
        if items.option_count:
            items.highlighted = min(target_index, items.option_count - 1)
            opt = items.get_option_at_index(items.highlighted)
            self._update_preview(opt.id)
        else:
            self.query_one("#details", Static).update(
                Text("No banners match.", style="dim")
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
        self._open_color_picker(self._highlighted_id())

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._open_color_picker(event.option.id)

    # ------------------------------------------------------------------ buttons
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "reset":
            self.action_reset_all()
        else:
            self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_reset_all(self) -> None:
        from code_puppy.config import DEFAULT_BANNER_COLORS, set_banner_color
        from code_puppy.messaging import emit_success

        for key, color in DEFAULT_BANNER_COLORS.items():
            set_banner_color(key, color)
        emit_success("Reset all banner colors to defaults.")
        self._populate(
            self.query_one("#filter", Input).value, select=self._highlighted_id()
        )

    # ------------------------------------------------------------------ color pick
    def _highlighted_id(self) -> Optional[str]:
        items = self.query_one("#items", OptionList)
        if items.option_count and items.highlighted is not None:
            return items.get_option_at_index(items.highlighted).id
        return None

    def _open_color_picker(self, banner: Optional[str]) -> None:
        if not banner:
            return
        from code_puppy.config import get_banner_color

        from .base import FilterableListScreen, ListChoice

        display, _icon = BANNER_DISPLAY_INFO[banner]
        current = get_banner_color(banner)
        choices = [
            ListChoice(
                id=name,  # friendly name is unique; rich value may repeat
                label=name,
                search=f"{name} {rich}",
                style=f"on {rich}",
                active=(rich == current),
            )
            for name, rich in BANNER_COLORS.items()
        ]

        def _picked(name) -> None:
            if not name:
                return
            rich = BANNER_COLORS.get(name)
            if not rich:
                return
            from code_puppy.config import set_banner_color
            from code_puppy.messaging import emit_success

            set_banner_color(banner, rich)
            emit_success(f"Set '{display}' banner color to {name}")
            self._populate(self.query_one("#filter", Input).value, select=banner)

        self.app.push_screen(
            FilterableListScreen(f"Color for {display}", choices), _picked
        )

    # ------------------------------------------------------------------ preview
    def _update_preview(self, selected: Optional[str]) -> None:
        self.query_one("#details", Static).update(self._build_preview(selected))

    def _build_preview(self, selected: Optional[str]) -> Text:
        colors = self._colors()
        t = Text()
        t.append("LIVE PREVIEW - Banner Colors\n\n", style="bold cyan")
        for key in self._keys:
            display, icon = BANNER_DISPLAY_INFO[key]
            color = colors.get(key, "blue")
            is_sel = key == selected
            t.append("\u25b6 " if is_sel else "  ", style="bold yellow")
            t.append(f" {display} ", style=f"bold white on {color}")
            if icon:
                t.append(f" {icon}")
            t.append("\n")
            sample = BANNER_SAMPLE_CONTENT.get(key, "")
            for line in sample.split("\n")[:2]:
                t.append(f"    {line}\n", style="dim")
            t.append("\n")
        return t
