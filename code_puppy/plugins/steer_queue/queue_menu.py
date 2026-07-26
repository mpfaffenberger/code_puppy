"""Full-screen queue manager for ``/queue``.

The application owns presentation state only. Queue mutations continue to flow
through :class:`PauseController`, keeping listeners and the bottom status bar in
sync with edits made here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional
from code_puppy.callbacks import on_prompt_toolkit_style

logger = logging.getLogger(__name__)

_PREVIEW_CELLS = 58


def _preview(text: str, width: int = _PREVIEW_CELLS) -> str:
    """Return a compact single-line preview for a queued prompt."""
    flat = " ".join(text.split())
    if len(flat) <= width:
        return flat
    return flat[: max(0, width - 1)] + "…"


@dataclass
class QueueMenuState:
    """Small, testable state adapter around ``PauseController``."""

    controller: object
    selected: int = 0
    editing: bool = False
    adding: bool = False
    delete_armed: Optional[int] = None
    notice: str = ""

    @property
    def items(self) -> List[str]:
        return self.controller.peek_pending_steer_queued()

    @property
    def selected_text(self) -> str:
        items = self.items
        if not items:
            return ""
        self.selected = min(max(self.selected, 0), len(items) - 1)
        return items[self.selected]

    def clamp_selection(self) -> None:
        self.selected = min(max(self.selected, 0), max(0, len(self.items) - 1))

    def move_selection(self, delta: int) -> None:
        if not self.items:
            self.selected = 0
            return
        self.selected = min(max(self.selected + delta, 0), len(self.items) - 1)
        self.delete_armed = None
        self.notice = ""

    def begin_add(self) -> None:
        self.editing = True
        self.adding = True
        self.delete_armed = None
        self.notice = "Adding prompt — Ctrl+S save · Esc cancel"

    def begin_edit(self) -> bool:
        if not self.items:
            self.notice = "Queue is empty — press A to add a prompt"
            return False
        self.editing = True
        self.adding = False
        self.delete_armed = None
        self.notice = "Editing prompt — Ctrl+S save · Esc cancel"
        return True

    def cancel_edit(self) -> None:
        self.editing = False
        self.adding = False
        self.notice = "Edit cancelled"

    def save(self, text: str) -> bool:
        normalized = text.strip()
        if not normalized:
            self.notice = "Prompt cannot be blank"
            return False

        items = self.items
        if self.adding:
            self.controller.request_steer(normalized, mode="queue")
            self.selected = len(items)
            self.notice = "Prompt added"
        elif self.selected < len(items):
            items[self.selected] = normalized
            self.controller.replace_pending_steer_queued(items)
            self.notice = "Prompt updated"
        else:
            self.notice = "That queue item no longer exists"
            return False

        self.editing = False
        self.adding = False
        self.delete_armed = None
        self.clamp_selection()
        return True

    def request_delete(self) -> bool:
        if not self.items:
            self.notice = "Queue is already empty"
            return False
        if self.delete_armed != self.selected:
            self.delete_armed = self.selected
            self.notice = "Press D again to delete this prompt"
            return False

        items = self.items
        del items[self.selected]
        self.controller.replace_pending_steer_queued(items)
        self.delete_armed = None
        self.clamp_selection()
        self.notice = "Prompt deleted"
        return True

    def reorder(self, delta: int) -> bool:
        items = self.items
        destination = self.selected + delta
        if not items or destination < 0 or destination >= len(items):
            return False
        items[self.selected], items[destination] = (
            items[destination],
            items[self.selected],
        )
        self.controller.replace_pending_steer_queued(items)
        self.selected = destination
        self.delete_armed = None
        self.notice = "Prompt moved"
        return True


class QueueMenuApp:
    """Persistent full-screen prompt queue manager."""

    def __init__(self, controller):
        from prompt_toolkit import Application
        from prompt_toolkit.buffer import Buffer
        from prompt_toolkit.filters import Condition
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
        from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
        from prompt_toolkit.layout.dimension import Dimension
        from prompt_toolkit.layout.processors import BeforeInput
        from prompt_toolkit.widgets import Frame

        self.state = QueueMenuState(controller)
        self._list_control = FormattedTextControl(
            self._render_list, focusable=True, show_cursor=False
        )
        self._editor_buffer = Buffer(multiline=True)
        self._editor_control = BufferControl(
            buffer=self._editor_buffer,
            input_processors=[BeforeInput(self._editor_prefix)],
            focusable=Condition(lambda: self.state.editing),
        )
        self._detail_frame = Frame(
            Window(
                self._editor_control,
                wrap_lines=True,
                always_hide_cursor=Condition(lambda: not self.state.editing),
            ),
            title=self._detail_title,
            style="class:tui.body",
        )

        body = VSplit(
            [
                Frame(
                    Window(
                        self._list_control,
                        wrap_lines=False,
                        width=Dimension(weight=2),
                    ),
                    title="Queued prompts",
                    style="class:tui.body",
                ),
                Window(width=1, char=" "),
                self._detail_frame,
            ],
            padding=0,
        )
        root = HSplit(
            [
                Window(
                    FormattedTextControl(self._render_header),
                    height=2,
                    style="class:tui.header",
                ),
                body,
                Window(
                    FormattedTextControl(self._render_notice),
                    height=1,
                    style="class:tui.warning",
                ),
                Window(
                    FormattedTextControl(self._render_footer),
                    height=2,
                    style="class:tui.help",
                ),
            ]
        )

        self._bindings = KeyBindings()
        self._register_bindings()
        self.application = Application(
            layout=Layout(root, focused_element=self._list_control),
            key_bindings=self._bindings,
            full_screen=True,
            mouse_support=True,
            style=on_prompt_toolkit_style(),
        )
        self._sync_editor()

    def _editor_prefix(self):
        return [("class:tui.label", "EDIT  " if self.state.editing else "")]

    def _detail_title(self) -> str:
        if self.state.adding:
            return "New prompt"
        if self.state.editing:
            return f"Edit prompt {self.state.selected + 1}"
        return "Prompt preview"

    def _render_header(self):
        count = len(self.state.items)
        return [
            ("class:tui.title", "  PROMPT QUEUE\n"),
            ("class:tui.header", f"  {count} item{'s' if count != 1 else ''} waiting"),
        ]

    def _render_list(self):
        items = self.state.items
        if not items:
            return [
                (
                    "class:tui.muted",
                    "\n  Queue is empty.\n\n  Press A to add a prompt.",
                )
            ]
        fragments = []
        for index, text in enumerate(items):
            style = (
                "class:tui.selected"
                if index == self.state.selected
                else "class:tui.body"
            )
            marker = "▶" if index == self.state.selected else " "
            fragments.extend(
                [
                    (style, f" {marker} "),
                    (f"{style} class:tui.muted", f"{index + 1:>2}  "),
                    (style, _preview(text)),
                    (style, "\n"),
                ]
            )
        return fragments

    def _render_notice(self):
        return [("class:tui.warning", f"  {self.state.notice}")]

    def _render_footer(self):
        if self.state.editing:
            return [
                ("class:tui.help", "  "),
                ("class:tui.help-key", "Ctrl+S"),
                ("class:tui.help", " save   "),
                ("class:tui.help-key", "Esc"),
                ("class:tui.help", " cancel   Multi-line editing enabled"),
            ]
        return [
            ("class:tui.help", "  "),
            ("class:tui.help-key", "↑↓/JK"),
            ("class:tui.help", " select   "),
            ("class:tui.help-key", "Enter/E"),
            ("class:tui.help", " edit   "),
            ("class:tui.help-key", "A"),
            ("class:tui.help", " add   "),
            ("class:tui.help-key", "D D"),
            ("class:tui.help", " delete\n  "),
            ("class:tui.help-key", "[ ]"),
            ("class:tui.help", " reorder   "),
            ("class:tui.help-key", "Q/Esc"),
            ("class:tui.help", " done"),
        ]

    def _sync_editor(self, text: Optional[str] = None) -> None:
        value = self.state.selected_text if text is None else text
        self._editor_buffer.set_document(
            self._editor_buffer.document.__class__(value, cursor_position=len(value)),
            bypass_readonly=True,
        )

    def _refresh(self) -> None:
        self.application.invalidate()

    def _focus_list(self) -> None:
        self.application.layout.focus(self._list_control)

    def _begin_add(self) -> None:
        self.state.begin_add()
        self._sync_editor("")
        self.application.layout.focus(self._editor_control)

    def _begin_edit(self) -> None:
        if self.state.begin_edit():
            self._sync_editor()
            self.application.layout.focus(self._editor_control)

    def _cancel_edit(self) -> None:
        self.state.cancel_edit()
        self._sync_editor()
        self._focus_list()

    def _save_edit(self) -> None:
        if self.state.save(self._editor_buffer.text):
            self._sync_editor()
            self._focus_list()

    def _move_selection(self, delta: int) -> None:
        self.state.move_selection(delta)
        self._sync_editor()

    def _register_bindings(self) -> None:
        kb = self._bindings

        @kb.add("up")
        @kb.add("k")
        def _up(event):
            if not self.state.editing:
                self._move_selection(-1)

        @kb.add("down")
        @kb.add("j")
        def _down(event):
            if not self.state.editing:
                self._move_selection(1)

        @kb.add("home")
        def _home(event):
            if not self.state.editing:
                self.state.selected = 0
                self._sync_editor()

        @kb.add("end")
        def _end(event):
            if not self.state.editing and self.state.items:
                self.state.selected = len(self.state.items) - 1
                self._sync_editor()

        @kb.add("a")
        def _add(event):
            if not self.state.editing:
                self._begin_add()

        @kb.add("e")
        @kb.add("enter")
        def _edit(event):
            if not self.state.editing:
                self._begin_edit()
            else:
                self._editor_buffer.insert_text("\n")

        @kb.add("d")
        def _delete(event):
            if not self.state.editing:
                deleted = self.state.request_delete()
                if deleted:
                    self._sync_editor()
                self._refresh()

        @kb.add("[")
        def _move_up(event):
            if not self.state.editing and self.state.reorder(-1):
                self._sync_editor()

        @kb.add("]")
        def _move_down(event):
            if not self.state.editing and self.state.reorder(1):
                self._sync_editor()

        @kb.add("c-s")
        def _save(event):
            if self.state.editing:
                self._save_edit()

        @kb.add("escape")
        def _escape(event):
            if self.state.editing:
                self._cancel_edit()
            else:
                event.app.exit()

        @kb.add("q")
        def _quit(event):
            if not self.state.editing:
                event.app.exit()

        @kb.add("c-c")
        def _ctrl_c(event):
            if self.state.editing:
                self._cancel_edit()
            else:
                event.app.exit()

    async def run(self) -> None:
        await self.application.run_async()


async def run_queue_menu() -> None:
    """Run the full-screen queue manager."""
    from code_puppy.messaging.pause_controller import get_pause_controller

    await QueueMenuApp(get_pause_controller()).run()


def open_queue_menu_blocking(timeout_s: float = 600.0) -> None:
    """Run the menu on a worker thread with an isolated event loop."""
    import asyncio
    import concurrent.futures

    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.submit(lambda: asyncio.run(run_queue_menu())).result(
                timeout=timeout_s
            )
    except Exception:
        logger.debug("queue menu failed", exc_info=True)


__all__ = [
    "QueueMenuApp",
    "QueueMenuState",
    "open_queue_menu_blocking",
    "run_queue_menu",
]
