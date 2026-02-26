"""TUI loop and keyboard handlers for ask_user_question.

This module contains the main TUI application loop and all keyboard bindings.
Separated from terminal_ui.py to keep files under 600 lines.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from prompt_toolkit import Application
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.formatted_text import ANSI, FormattedText
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.layout import Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.output import create_output
from prompt_toolkit.output.color_depth import ColorDepth
from prompt_toolkit.widgets import Frame

from .constants import (
    ARROW_DOWN,
    ARROW_LEFT,
    ARROW_RIGHT,
    ARROW_UP,
    CHECK_MARK,
    CURSOR_TRIANGLE,
)
from .renderers import render_question_panel
from .theme import get_rich_colors, get_tui_colors

if TYPE_CHECKING:
    from .models import QuestionAnswer
    from .terminal_ui import QuestionUIState


def _wait_for_keypress() -> None:
    """Block until any key is pressed, reading directly from the terminal.

    On Unix: switches to raw mode so a single keypress returns immediately.
    On Windows: uses msvcrt.getch() which already reads a single key.
    Called inside run_in_terminal's cooked-mode context.
    """
    try:
        # Windows
        import msvcrt

        msvcrt.getch()
    except ImportError:
        # Unix / macOS
        import select
        import termios
        import tty

        fd = sys.__stdin__.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.__stdin__.read(1)
            # Arrow/F-keys send multi-byte escape sequences (e.g. \x1b[A).
            # Drain trailing bytes so they don't leak into prompt_toolkit.
            if ch == "\x1b":
                while select.select([sys.__stdin__], [], [], 0.01)[0]:
                    sys.__stdin__.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


@dataclass(slots=True)
class TUIResult:
    """Result holder for the TUI interaction."""

    cancelled: bool = False
    confirmed: bool = False


async def run_question_tui(
    state: QuestionUIState,
) -> tuple[list[QuestionAnswer], bool, bool]:
    """Run the main question TUI loop.

    Returns:
        Tuple of (answers, cancelled, timed_out)
    """
    result = TUIResult()
    timed_out = False
    kb = KeyBindings()

    # --- Factory for dual-mode handlers (vim keys that type in text mode) ---
    def make_dual_mode_handler(
        char: str, action: Callable[[], None]
    ) -> Callable[[KeyPressEvent], None]:
        """Create handler that types char in text mode, calls action otherwise."""

        def handler(event: KeyPressEvent) -> None:
            state.reset_activity_timer()
            if state.entering_other_text:
                state.other_text_buffer += char
            else:
                action()
            event.app.invalidate()

        return handler

    # --- Factory for arrow key navigation (don't type in text mode) ---
    def make_arrow_handler(
        action: Callable[[], None],
    ) -> Callable[[KeyPressEvent], None]:
        """Create handler that only fires when not in text input mode."""

        def handler(event: KeyPressEvent) -> None:
            state.reset_activity_timer()
            if not state.entering_other_text:
                action()
                event.app.invalidate()

        return handler

    kb.add("up")(make_arrow_handler(state.move_cursor_up))
    kb.add("down")(make_arrow_handler(state.move_cursor_down))
    kb.add("left")(make_arrow_handler(state.prev_question))
    kb.add("right")(make_arrow_handler(state.next_question))

    # --- Vim-style navigation (types letter in text mode) ---
    kb.add("k")(make_dual_mode_handler("k", state.move_cursor_up))
    kb.add("j")(make_dual_mode_handler("j", state.move_cursor_down))
    kb.add("h")(make_dual_mode_handler("h", state.prev_question))
    kb.add("l")(make_dual_mode_handler("l", state.next_question))
    kb.add("g")(make_dual_mode_handler("g", state.jump_to_first))
    kb.add("G")(make_dual_mode_handler("G", state.jump_to_last))

    # --- Selection controls (also dual-mode) ---
    def _toggle_help() -> None:
        state.show_help = not state.show_help

    kb.add("a")(make_dual_mode_handler("a", state.select_all_options))
    kb.add("n")(make_dual_mode_handler("n", state.select_no_options))
    kb.add("?")(make_dual_mode_handler("?", _toggle_help))

    @kb.add("space")
    def toggle_option(event: KeyPressEvent) -> None:
        """Toggle/select the current option.

        For multi-select: toggles the checkbox
        For single-select: selects the radio button (without advancing)
        """
        state.reset_activity_timer()
        if state.entering_other_text:
            state.other_text_buffer += " "
            event.app.invalidate()
            return

        # Check if current option is "Other"
        if state.is_other_option(state.current_cursor):
            state.enter_other_text_mode()
            event.app.invalidate()
            return

        if state.current_question.multi_select:
            # Toggle checkbox
            state.toggle_current_option()
        else:
            # Select radio button (doesn't advance)
            state.select_current_option()
        event.app.invalidate()

    @kb.add("enter")
    def advance_question(event: KeyPressEvent) -> None:
        """Select current option and advance, or submit if confirming selection.

        Behavior:
        - Selects the current option (for single-select) or enters Other mode
        - Advances to next question if not on last
        - On last question: only submits if cursor is on an already-selected option
          (i.e., user is confirming their choice by pressing Enter on it again)
        """
        state.reset_activity_timer()
        if state.entering_other_text:
            # Confirm the "Other" text using centralized method
            state.commit_other_text()
            event.app.invalidate()
            return

        # Check if current option is "Other"
        if state.is_other_option(state.current_cursor):
            state.enter_other_text_mode()
            event.app.invalidate()
            return

        is_last_question = state.current_question_index == len(state.questions) - 1
        cursor_is_on_selected = state.is_option_selected(state.current_cursor)

        # For single-select, select the current option when pressing Enter
        if not state.current_question.multi_select:
            state.select_current_option()

        # Advance to next question if not on the last one
        if not is_last_question:
            state.next_question()
            event.app.invalidate()
        else:
            # On the last question:
            # Only submit if cursor was already on the selected option (confirming)
            # This prevents accidental submission when browsing options
            if cursor_is_on_selected:
                result.confirmed = True
                event.app.exit()
            else:
                # Just selected a new option, update display but don't submit
                # User needs to press Enter again to confirm
                event.app.invalidate()

    @kb.add("c-s")
    def submit_all(event: KeyPressEvent) -> None:
        """Ctrl+S submits all answers immediately from any question."""
        state.reset_activity_timer()
        # If entering other text, save it first before submitting
        if state.entering_other_text:
            state.commit_other_text()
        result.confirmed = True
        event.app.exit()

    @kb.add("escape")
    def cancel(event: KeyPressEvent) -> None:
        state.reset_activity_timer()
        if state.entering_other_text:
            state.entering_other_text = False
            state.other_text_buffer = ""
            event.app.invalidate()
            return
        result.cancelled = True
        event.app.exit()

    @kb.add("c-c")
    def ctrl_c_cancel(event: KeyPressEvent) -> None:
        result.cancelled = True
        event.app.exit()

    @kb.add("tab")
    def toggle_peek(event: KeyPressEvent) -> None:
        """Peek behind the TUI to see terminal output.

        Uses prompt_toolkit's run_in_terminal to properly suspend rendering,
        exit alt screen, wait for a keypress, then restore everything with
        a full repaint. This prevents resize events from clobbering the
        main screen during peek and ensures borders render correctly on return.
        """
        state.reset_activity_timer()

        def _peek() -> None:
            sys.__stdout__.write(
                "\n  \033[2mPress any key to return to questions...\033[0m\n"
            )
            sys.__stdout__.flush()
            _wait_for_keypress()
            state.reset_activity_timer()

        run_in_terminal(_peek, in_executor=True)

    @kb.add("<any>")
    def handle_text_input(event: KeyPressEvent) -> None:
        state.reset_activity_timer()
        if state.entering_other_text:
            char = event.data
            if char and len(char) == 1 and ord(char) >= 32:
                state.other_text_buffer += char
                event.app.invalidate()

    @kb.add("backspace")
    def handle_backspace(event: KeyPressEvent) -> None:
        if state.entering_other_text and state.other_text_buffer:
            state.other_text_buffer = state.other_text_buffer[:-1]
            event.app.invalidate()

    # --- Panel rendering ---
    # Cache colors once per session to avoid repeated config lookups
    tui_colors = get_tui_colors()
    rich_colors = get_rich_colors()

    def get_left_panel_text() -> FormattedText:
        """Generate the left panel with question headers."""
        pad = "  "
        lines: list[tuple[str, str]] = [
            ("", pad),
            (tui_colors.header_bold, "Questions"),
            ("", "\n\n"),
        ]

        for i, question in enumerate(state.questions):
            is_current = i == state.current_question_index
            is_answered = state.is_question_answered(i)
            cursor = f"{CURSOR_TRIANGLE} " if is_current else "  "
            status = f"{CHECK_MARK} " if is_answered else "  "

            # Determine styles based on state
            cursor_style = (
                tui_colors.cursor_active if is_current else tui_colors.cursor_inactive
            )
            content_style = (
                tui_colors.selected_check
                if is_answered
                else tui_colors.cursor_active
                if is_current
                else tui_colors.text_dim
            )

            lines.append(("", pad))
            if is_answered:
                # Answered: cursor and status+header use different styles
                lines.append((cursor_style, cursor))
                lines.append((content_style, status + question.header))
            else:
                # Not answered: cursor+status+header all use same style
                lines.append((content_style, cursor + status + question.header))
            lines.append(("", "\n"))

        # Footer with keyboard shortcuts
        lines.extend(
            [
                ("", "\n"),
                ("", pad),
                (tui_colors.header_dim, f"{ARROW_LEFT}{ARROW_RIGHT} Switch question"),
                ("", "\n"),
                ("", pad),
                (tui_colors.header_dim, f"{ARROW_UP}{ARROW_DOWN} Navigate options"),
                ("", "\n"),
                ("", "\n"),
                ("", pad),
                (tui_colors.help_key, "Ctrl+S"),
                (tui_colors.header_dim, " Submit"),
                ("", "\n"),
                ("", pad),
                (tui_colors.help_key, "Tab"),
                (tui_colors.header_dim, " Peek behind"),
            ]
        )

        return FormattedText(lines)

    def get_right_panel_text() -> ANSI:
        """Generate the right panel with current question and options."""
        # Calculate available width: terminal minus left panel, minus frame borders (4 chars)
        term_width = shutil.get_terminal_size().columns
        available = term_width - left_panel_width - 4
        return render_question_panel(
            state, colors=rich_colors, available_width=available
        )

    # --- Layout ---
    # Calculate dynamic left panel width based on longest header
    left_panel_width = state.get_left_panel_width()

    left_panel = Window(
        content=FormattedTextControl(lambda: get_left_panel_text()),
        width=Dimension(preferred=left_panel_width, max=left_panel_width),
    )

    right_panel = Window(
        content=FormattedTextControl(lambda: get_right_panel_text()),
        wrap_lines=True,
        # Right panel takes remaining space
    )

    root_container = VSplit(
        [
            Frame(left_panel, title=""),
            Frame(right_panel, title=""),
        ]
    )

    layout = Layout(root_container)

    # Create output that writes to the real terminal, bypassing any stdout capture
    output = create_output(stdout=sys.__stdout__)

    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=True,
        mouse_support=False,
        color_depth=ColorDepth.DEPTH_24_BIT,
        output=output,
    )

    # Timeout checker background task
    async def timeout_checker() -> None:
        nonlocal timed_out
        while True:
            await asyncio.sleep(1)
            if state.is_timed_out():
                timed_out = True
                app.exit()
                return
            app.invalidate()

    timeout_task = asyncio.create_task(timeout_checker())
    app_exception: BaseException | None = None

    try:
        await app.run_async()
    except BaseException as e:
        app_exception = e
    finally:
        timeout_task.cancel()
        # Use asyncio.gather with return_exceptions to avoid race conditions
        await asyncio.gather(timeout_task, return_exceptions=True)

    # Re-raise any exception from app.run_async() after cleanup
    if app_exception is not None:
        raise app_exception

    if timed_out:
        return ([], False, True)

    if result.cancelled:
        return ([], True, False)

    return (state.build_answers(), False, False)
