"""Termflow event loop for the ask_user_question TUI.

Split-panel layout (question headers left, current question right) painted
with the shared Rich-markup renderers, driven by a plain ``read_key`` loop.
Follows the headless-widget recipe: ``key_source`` / ``output`` / ``size`` /
``use_alt_screen`` are injectable so tests drive the widget with scripted
keys and a StringIO -- no tty, no prompt_toolkit.

Timeouts ride the resize poll: ``read_key(timeout=...)`` returns ``""``
every tick, which doubles as the inactivity-countdown heartbeat.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional, TextIO

from .constants import CLEAR_AND_HOME, ENTER_ALT_SCREEN, EXIT_ALT_SCREEN
from .renderers import render_header_panel, render_question_panel
from .theme import get_rich_colors

if TYPE_CHECKING:
    from .models import QuestionAnswer
    from .terminal_ui import QuestionUIState


@dataclass
class TUIResult:
    """Outcome flags accumulated while the loop runs."""

    confirmed: bool = False
    cancelled: bool = False
    timed_out: bool = False


class QuestionTUI:
    """The interactive question widget on termflow primitives."""

    def __init__(
        self,
        state: "QuestionUIState",
        *,
        key_source: Optional[Callable[[], str]] = None,
        output: Optional[TextIO] = None,
        size: Optional[Callable[[], tuple[int, int]]] = None,
        use_alt_screen: bool = True,
    ) -> None:
        import sys

        from termflow.tui.keys import read_key
        from termflow.tui.menu import RESIZE_POLL_S
        from termflow.tui.terminal import terminal_size

        self._state = state
        self._read_key = key_source or (lambda: read_key(timeout=RESIZE_POLL_S))
        self._output = output if output is not None else sys.__stdout__
        self._size = size or terminal_size
        self._use_alt_screen = use_alt_screen
        self._colors = get_rich_colors()
        self._result = TUIResult()
        self._last_size: tuple[int, int] | None = None
        self._last_remaining: int | None = None

    # -- painting ------------------------------------------------------------

    def _panel_lines(self, ansi: str) -> list[str]:
        return ansi.rstrip("\n").split("\n")

    def _paint(self) -> None:
        from termflow.tui.layout import collapsed, split_frame, truncate

        width, height = self._size()
        self._last_size = (width, height)
        self._last_remaining = self._state.get_time_remaining()

        left_width = self._state.get_left_panel_width()
        right_width = width - 1 if collapsed(width) else max(20, width - left_width - 3)
        right = self._panel_lines(
            render_question_panel(
                self._state, colors=self._colors, available_width=right_width
            )
        )
        left = self._panel_lines(
            render_header_panel(self._state, colors=self._colors, width=left_width)
        )
        body = split_frame(
            left,
            right,
            width=width,
            list_width=left_width,
            focus="right",
        )
        frame = [truncate(line, width - 1) for line in body[: max(1, height - 1)]]
        self._output.write(CLEAR_AND_HOME + "\r\n".join(frame))
        self._output.flush()

    # -- key handling --------------------------------------------------------

    def _handle_text_key(self, key: str) -> bool:
        """Keys while typing an 'Other' answer. True exits the loop."""
        from termflow.tui.keys import Key

        state = self._state
        if key == Key.ENTER:
            state.commit_other_text()
        elif key == Key.ESCAPE:
            state.entering_other_text = False
            state.other_text_buffer = ""
        elif key == Key.BACKSPACE:
            state.other_text_buffer = state.other_text_buffer[:-1]
        elif key == "ctrl-s":
            state.commit_other_text()
            self._result.confirmed = True
            return True
        elif key == "ctrl-c":
            self._result.cancelled = True
            return True
        elif len(key) == 1 and key.isprintable():
            state.other_text_buffer += key
        return False

    def _handle_enter(self) -> bool:
        """Select + advance; double-Enter on the last question submits."""
        state = self._state
        if state.is_other_option(state.current_cursor):
            state.enter_other_text_mode()
            return False
        is_last = state.current_question_index == len(state.questions) - 1
        cursor_on_selected = state.is_option_selected(state.current_cursor)
        if not state.current_question.multi_select:
            state.select_current_option()
        if not is_last:
            state.next_question()
        elif cursor_on_selected:
            self._result.confirmed = True
            return True
        return False

    def _handle_space(self) -> None:
        state = self._state
        if state.is_other_option(state.current_cursor):
            state.enter_other_text_mode()
        elif state.current_question.multi_select:
            state.toggle_current_option()
        else:
            state.select_current_option()

    def _handle_key(self, key: str) -> bool:
        """Dispatch one key. True exits the loop."""
        from termflow.tui.keys import Key

        state = self._state
        state.reset_activity_timer()

        if state.entering_other_text:
            return self._handle_text_key(key)
        if key == "ctrl-c" or key == Key.ESCAPE:
            self._result.cancelled = True
            return True
        if key == "ctrl-s":
            self._result.confirmed = True
            return True
        if state.show_help:
            # Any key closes the help overlay.
            state.show_help = False
            return False
        if key in (Key.UP, "k"):
            state.move_cursor_up()
        elif key in (Key.DOWN, "j"):
            state.move_cursor_down()
        elif key in (Key.LEFT, "h"):
            state.prev_question()
        elif key in (Key.RIGHT, "l"):
            state.next_question()
        elif key == "g":
            state.jump_to_first()
        elif key == "G":
            state.jump_to_last()
        elif key == "a":
            state.select_all_options()
        elif key == "n":
            state.select_no_options()
        elif key == "?":
            state.show_help = True
        elif key == " ":
            self._handle_space()
        elif key == Key.ENTER:
            return self._handle_enter()
        elif key == Key.TAB:
            self._peek()
        return False

    def _peek(self) -> None:
        """Drop out of the alt screen so the transcript shows through."""
        if not self._use_alt_screen:
            return
        from termflow.tui.keys import read_key

        self._output.write(EXIT_ALT_SCREEN)
        self._output.write(
            "\r\n  \033[2mPress any key to return to questions...\033[0m\r\n"
        )
        self._output.flush()
        read_key()  # block until any real key
        self._output.write(ENTER_ALT_SCREEN)
        self._output.flush()
        self._state.reset_activity_timer()

    # -- loop ----------------------------------------------------------------

    def _loop(self) -> None:
        self._paint()
        while True:
            key = self._read_key()
            if key == "":
                # Poll tick: timeout countdown + resize detection.
                if self._state.is_timed_out():
                    self._result.timed_out = True
                    return
                if self._size() != self._last_size:
                    self._paint()
                elif (
                    self._state.should_show_timeout_warning()
                    and self._state.get_time_remaining() != self._last_remaining
                ):
                    self._paint()
                continue
            if self._handle_key(key):
                return
            self._paint()

    def run(self) -> tuple[list["QuestionAnswer"], bool, bool]:
        """Run the widget. Returns (answers, cancelled, timed_out)."""
        if self._use_alt_screen:
            from termflow.tui.terminal import alt_screen, raw_mode

            with raw_mode(), alt_screen(self._output):
                self._loop()
        else:
            self._loop()

        if self._result.timed_out:
            return ([], False, True)
        if self._result.cancelled or not self._result.confirmed:
            return ([], True, False)
        return (self._state.build_answers(), False, False)


async def run_question_tui(
    state: "QuestionUIState",
) -> tuple[list["QuestionAnswer"], bool, bool]:
    """Async entry point: run the widget without blocking the event loop.

    Suspends the run UI for the duration -- the full-screen widget needs the
    scroll region reset AND stdin freed, or the listener eats keystrokes.
    """
    import asyncio

    from code_puppy.messaging.run_ui import suspended_run_ui

    with suspended_run_ui():
        return await asyncio.to_thread(QuestionTUI(state).run)
