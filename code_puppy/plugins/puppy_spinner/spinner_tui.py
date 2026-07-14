"""Textual ModalScreen for /spinner - a REAL live-preview picker.

The classic ``/spinner`` opens a full-screen prompt_toolkit ``Application``
(``picker.py``) whose animated preview would corrupt the Textual screen (the
same class of bug ``/theme`` and the other pickers dodge). Until now the TUI
just printed "use /spinner <name>" - graceful degradation, not parity.

This screen restores full parity: a left list + an *animated* right preview
that runs each spinner at its own configured speed, a speed dial (-/+ or
left/right), and ``i`` to write the starter ``spinners.json``. It reads/writes
the SAME data layer (``spinners.get_catalogue`` / ``get_active_spinner`` /
``set_active`` / ``write_template``) and reuses the classic picker's speed-grid
math (``_step_interval``) so the two UIs stay behaviourally identical.

UX:
  * left  -> spinner list (active marked ``*``), up/down to move
  * right -> live animated preview + metadata for the highlighted spinner
  * -/+ (or left/right) dial speed  ·  i init spinners.json
  * Enter apply (saves a dialed speed)  ·  Esc cancel
"""

from __future__ import annotations

import time
from typing import List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, OptionList, Static
from textual.widgets.option_list import Option

from . import spinners as sp

#: Preview repaint cadence. Pinned to the speed floor so even a spinner
#: dialed down to MIN_INTERVAL still previews at its true speed.
_REFRESH_INTERVAL_S = sp.MIN_INTERVAL


class SpinnerScreen(ModalScreen[None]):
    """Live-preview spinner picker. Dismisses with None (applies in place)."""

    CSS = """
    SpinnerScreen { align: center middle; }
    #dialog {
        width: 88%;
        height: 84%;
        border: round $accent;
        background: $panel;
        padding: 1 2;
    }
    #title { text-style: bold; color: $accent; }
    #subtitle { color: $text-muted; margin-bottom: 1; }
    #body { height: 1fr; }
    #left { width: 42%; }
    #items { height: 1fr; border: round $primary; }
    #preview {
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
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "apply", "Apply"),
        Binding("minus,left", "slower", "Slower"),
        Binding("plus,equal,right", "faster", "Faster"),
        Binding("i", "init_file", "Init spinners.json"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._entries: List[sp.Spinner] = list(sp.get_catalogue().values())
        self._active: str = sp.get_active_spinner().name
        # Speed the user dialed for the highlighted entry; None = its own speed.
        self._custom_interval: Optional[float] = None
        self._notice: str = ""
        self._started_at: float = time.monotonic()
        self._file_stamp = sp.user_file_stamp()

    # ------------------------------------------------------------------ layout
    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Choose a spinner", id="title")
            yield Label("", id="subtitle")
            with Horizontal(id="body"):
                with Vertical(id="left"):
                    yield OptionList(id="items")
                with VerticalScroll(id="preview"):
                    yield Static("", id="preview-text")
            with Horizontal(id="footer"):
                yield Label(
                    "\u2191/\u2193 move \u00b7 -/+ speed \u00b7 i init \u00b7 "
                    "Enter apply \u00b7 Esc cancel",
                    id="hint",
                )
                yield Button("Apply", id="apply", variant="primary")

    def on_mount(self) -> None:
        self._rebuild_list(select_name=self._active)
        self.query_one("#items", OptionList).focus()
        # Animate the preview + watch spinners.json for external edits.
        self.set_interval(_REFRESH_INTERVAL_S, self._tick)

    # ----------------------------------------------------------------- list
    def _rebuild_list(self, select_name: Optional[str] = None) -> None:
        items = self.query_one("#items", OptionList)
        items.clear_options()
        for spinner in self._entries:
            items.add_option(Option(self._row_label(spinner)))

        self.query_one("#subtitle", Label).update(
            f"{len(self._entries)} spinner(s) \u00b7 active: {self._active}"
        )

        target = 0
        if select_name is not None:
            target = next(
                (i for i, s in enumerate(self._entries) if s.name == select_name), 0
            )
        if self._entries:
            items.highlighted = target
        self._update_preview()

    def _row_label(self, spinner: sp.Spinner) -> Text:
        label = Text()
        marker = "*" if spinner.name == self._active else " "
        label.append(f"{marker} ", style="bold green" if marker == "*" else "dim")
        label.append(spinner.name)
        return label

    def _highlighted(self) -> Optional[sp.Spinner]:
        idx = self.query_one("#items", OptionList).highlighted
        if idx is None or idx >= len(self._entries):
            return None
        return self._entries[idx]

    # ----------------------------------------------------------------- preview
    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        # Moving resets the dialed speed: each entry previews at its own speed.
        self._custom_interval = None
        self._update_preview()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        # Enter on the focused OptionList fires this (not the screen-level
        # `enter` binding, which the widget swallows) -> apply the choice.
        event.stop()
        self.action_apply()

    def _tick(self) -> None:
        # Reload the catalogue if spinners.json changed underneath us (same
        # mtime signal the classic picker + tick loop use), then repaint.
        stamp = sp.user_file_stamp()
        if stamp != self._file_stamp:
            self._file_stamp = stamp
            current = self._highlighted()
            self._entries = list(sp.get_catalogue().values())
            self._rebuild_list(select_name=current.name if current else None)
            return
        self._update_preview()

    def _update_preview(self) -> None:
        self.query_one("#preview-text", Static).update(self._build_preview())

    def _build_preview(self) -> Text:
        t = Text()
        t.append("LIVE PREVIEW\n\n", style="dim cyan")
        spinner = self._highlighted()
        if spinner is None:
            t.append("No spinner selected.", style="yellow")
            return t

        effective = (
            self._custom_interval
            if self._custom_interval is not None
            else spinner.interval
        )
        elapsed = time.monotonic() - self._started_at
        frame = spinner.frames[int(elapsed / effective) % len(spinner.frames)]

        t.append(f"{spinner.name}\n\n", style="bold")
        if spinner.description:
            t.append(f"{spinner.description}\n\n", style="dim")
        t.append(f"  {frame}\n\n", style="bold")
        t.append("Source: ", style="bold")
        t.append(f"{spinner.source}\n")
        t.append("Frames: ", style="bold")
        t.append(f"{len(spinner.frames)}\n")
        t.append("Interval: ", style="bold")
        t.append(f"{effective:.2f}s")
        if self._custom_interval is not None:
            t.append("  (custom - Enter saves it)", style="yellow")
        t.append("\n\n")
        t.append("Custom spinners:\n", style="bold")
        t.append(f"  {sp.USER_SPINNERS_FILE}\n", style="dim")
        t.append("  (press i to write a starter file)\n", style="dim")
        if self._notice:
            t.append(f"\n{self._notice}\n", style="yellow")
        return t

    # ----------------------------------------------------------------- actions
    def _nudge_speed(self, delta: float) -> None:
        from .picker import _step_interval

        spinner = self._highlighted()
        if spinner is None:
            return
        current = (
            self._custom_interval
            if self._custom_interval is not None
            else spinner.interval
        )
        self._custom_interval = _step_interval(current, delta)
        self._update_preview()

    def action_slower(self) -> None:
        from .picker import _SPEED_STEP_S

        self._nudge_speed(+_SPEED_STEP_S)

    def action_faster(self) -> None:
        from .picker import _SPEED_STEP_S

        self._nudge_speed(-_SPEED_STEP_S)

    def action_init_file(self) -> None:
        try:
            created = sp.write_template()
            self._notice = (
                "Starter file written - edit it freely, changes apply live."
                if created
                else "spinners.json already exists - edit it directly."
            )
        except OSError as exc:
            self._notice = f"Could not write starter file: {exc}"
        self._update_preview()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_apply()

    def action_apply(self) -> None:
        from code_puppy.messaging import emit_error, emit_info

        spinner = self._highlighted()
        self.dismiss(None)
        if spinner is None:
            return
        try:
            applied = sp.set_active(spinner.name, self._custom_interval)
        except KeyError:
            emit_error(f"/spinner: unknown spinner '{spinner.name}'")
            return
        emit_info(f"Spinner set to '{applied.name}' (interval {applied.interval:.2f}s)")

    def action_cancel(self) -> None:
        self.dismiss(None)


def open_spinner(app) -> None:
    """register_screen opener: push the live-preview spinner picker (TUI only)."""
    app.push_screen(SpinnerScreen())


__all__ = ["SpinnerScreen", "open_spinner"]
