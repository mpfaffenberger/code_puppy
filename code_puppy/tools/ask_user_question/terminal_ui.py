"""Terminal UI for ask_user_question tool.

Uses prompt_toolkit for a split-panel TUI similar to the /colors command.
Left panel (20%): Question headers/tabs
Right panel (80%): Current question with options

Navigation:
- Left/Right: Switch between questions
- Up/Down: Navigate options within current question
- Enter: Select option (single-select) or confirm (multi-select)
- Space: Toggle option (multi-select only)
- Esc/Ctrl+C: Cancel
"""

from __future__ import annotations

import time

from .constants import (
    AUTO_ADD_OTHER_OPTION,
    DEFAULT_TIMEOUT_SECONDS,
    LEFT_PANEL_PADDING,
    MAX_LEFT_PANEL_WIDTH,
    MIN_LEFT_PANEL_WIDTH,
    OTHER_OPTION_LABEL,
    TIMEOUT_WARNING_SECONDS,
)
from .models import Question, QuestionAnswer


class CancelledException(Exception):
    """Raised when user cancels the interaction."""


class QuestionUIState:
    """Holds the current UI state for the question interaction."""

    def __init__(self, questions: list[Question]) -> None:
        """Initialize state with questions.

        Args:
            questions: List of validated Question objects
        """
        self.questions = questions
        self.current_question_index = 0
        # For each question, track: cursor position and selected options
        self.cursor_positions: list[int] = [0] * len(questions)
        # For multi-select, track selected option indices per question
        self.selected_options: list[set[int]] = [set() for _ in questions]
        # For single-select, track the selected option index per question (None = not selected)
        self.single_selections: list[int | None] = [None] * len(questions)
        # Store "Other" text per question
        self.other_texts: list[str | None] = [None] * len(questions)
        # Track if we're in "Other" text input mode
        self.entering_other_text = False
        self.other_text_buffer = ""
        # Track if help overlay is shown
        self.show_help = False
        # Timeout tracking (use monotonic to avoid clock drift/NTP issues)
        self.timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
        self.last_activity_time: float = time.monotonic()

    def reset_activity_timer(self) -> None:
        """Reset the activity timer (called on user input)."""
        self.last_activity_time = time.monotonic()

    def get_time_remaining(self) -> int:
        """Get seconds remaining before timeout."""
        elapsed = time.monotonic() - self.last_activity_time
        remaining = self.timeout_seconds - elapsed
        return max(0, int(remaining))

    def is_timed_out(self) -> bool:
        """Check if the interaction has timed out."""
        return self.get_time_remaining() <= 0

    def should_show_timeout_warning(self) -> bool:
        """Check if we should show the timeout warning."""
        remaining = self.get_time_remaining()
        return remaining <= TIMEOUT_WARNING_SECONDS and remaining > 0

    @property
    def current_question(self) -> Question:
        """Get the currently displayed question."""
        return self.questions[self.current_question_index]

    def get_left_panel_width(self) -> int:
        """Calculate the left panel width based on longest header.

        Returns:
            Width in characters, including padding for cursor and checkmark.
        """
        max_header_len = max(len(q.header) for q in self.questions)
        width = max_header_len + LEFT_PANEL_PADDING
        return max(MIN_LEFT_PANEL_WIDTH, min(width, MAX_LEFT_PANEL_WIDTH))

    def get_other_text_for_question(self, index: int) -> str | None:
        """Get the 'Other' text for a specific question.

        Args:
            index: Question index

        Returns:
            The stored other_text or None if not set.
        """
        return self.other_texts[index]

    def jump_to_first(self) -> None:
        """Jump cursor to first option."""
        self.current_cursor = 0

    def jump_to_last(self) -> None:
        """Jump cursor to last option."""
        self.current_cursor = self.total_options - 1

    @property
    def current_cursor(self) -> int:
        """Get cursor position for current question."""
        return self.cursor_positions[self.current_question_index]

    @current_cursor.setter
    def current_cursor(self, value: int) -> None:
        """Set cursor position for current question."""
        self.cursor_positions[self.current_question_index] = value

    @property
    def total_options(self) -> int:
        """Get total number of options including 'Other' if enabled."""
        count = len(self.current_question.options)
        if AUTO_ADD_OTHER_OPTION:
            count += 1
        return count

    def is_question_answered(self, index: int) -> bool:
        """Check if a question has at least one selection.

        For multi-select: True if any option is selected or Other text provided.
        For single-select: True if an option is selected.
        """
        question = self.questions[index]
        if question.multi_select:
            return (
                len(self.selected_options[index]) > 0
                or self.other_texts[index] is not None
            )
        return self.single_selections[index] is not None

    def is_other_option(self, index: int) -> bool:
        """Check if the given index is the 'Other' option."""
        if not AUTO_ADD_OTHER_OPTION:
            return False
        return index == len(self.current_question.options)

    def enter_other_text_mode(self) -> None:
        """Enter text input mode for the 'Other' option.

        This centralizes the logic for starting 'Other' text entry,
        avoiding duplication in the keyboard handlers.
        """
        self.entering_other_text = True
        self.other_text_buffer = self.other_texts[self.current_question_index] or ""

    def commit_other_text(self) -> None:
        """Save the other text buffer and mark the Other option as selected.

        This centralizes the logic for confirming an 'Other' text entry,
        avoiding duplication in the various keyboard handlers.
        """
        if not self.other_text_buffer.strip():
            # Don't save empty/whitespace-only text
            self.entering_other_text = False
            self.other_text_buffer = ""
            return

        self.other_texts[self.current_question_index] = self.other_text_buffer
        other_idx = len(self.current_question.options)
        self._select_option_at(self.current_question_index, other_idx)
        self.entering_other_text = False
        self.other_text_buffer = ""

    def _select_option_at(self, question_idx: int, option_idx: int) -> None:
        """Mark an option as selected for the given question.

        Handles both single-select and multi-select modes.
        """
        if self.questions[question_idx].multi_select:
            self.selected_options[question_idx].add(option_idx)
        else:
            self.single_selections[question_idx] = option_idx

    def select_all_options(self) -> None:
        """Select all regular options for the current question (multi-select only)."""
        if not self.current_question.multi_select:
            return
        for i in range(len(self.current_question.options)):
            self.selected_options[self.current_question_index].add(i)

    def select_no_options(self) -> None:
        """Clear all selections for the current question (multi-select only)."""
        if not self.current_question.multi_select:
            return
        self.selected_options[self.current_question_index].clear()
        self.other_texts[self.current_question_index] = None

    def move_cursor_up(self) -> None:
        """Move cursor up within current question."""
        if self.current_cursor > 0:
            self.current_cursor -= 1

    def move_cursor_down(self) -> None:
        """Move cursor down within current question."""
        if self.current_cursor < self.total_options - 1:
            self.current_cursor += 1

    def next_question(self) -> None:
        """Move to next question."""
        if self.current_question_index < len(self.questions) - 1:
            self.current_question_index += 1

    def prev_question(self) -> None:
        """Move to previous question."""
        if self.current_question_index > 0:
            self.current_question_index -= 1

    def toggle_current_option(self) -> None:
        """Toggle the current option for multi-select questions."""
        if not self.current_question.multi_select:
            return
        cursor = self.current_cursor
        selected = self.selected_options[self.current_question_index]
        if cursor in selected:
            selected.discard(cursor)
        else:
            selected.add(cursor)

    def select_current_option(self) -> None:
        """Select current option for single-select questions."""
        if self.current_question.multi_select:
            return
        self.single_selections[self.current_question_index] = self.current_cursor

    def is_option_selected(self, index: int) -> bool:
        """Check if an option is selected."""
        if self.current_question.multi_select:
            return index in self.selected_options[self.current_question_index]
        else:
            return self.single_selections[self.current_question_index] == index

    def _resolve_option_label(
        self, question: Question, question_idx: int, opt_idx: int
    ) -> tuple[str, str | None]:
        """Resolve the label and other_text for an option index.

        Args:
            question: The question being answered
            question_idx: Index of the question in self.questions
            opt_idx: Index of the selected option

        Returns:
            Tuple of (label, other_text) where other_text is set only for "Other" option
        """
        if AUTO_ADD_OTHER_OPTION and opt_idx == len(question.options):
            return OTHER_OPTION_LABEL, self.other_texts[question_idx]
        return question.options[opt_idx].label, None

    def build_answers(self) -> list[QuestionAnswer]:
        """Build the list of answers from current state."""
        answers = []
        for i, question in enumerate(self.questions):
            selected_labels: list[str] = []
            other_text: str | None = None

            if question.multi_select:
                # Multi-select: gather all selected option labels
                for opt_idx in sorted(self.selected_options[i]):
                    label, opt_other = self._resolve_option_label(question, i, opt_idx)
                    selected_labels.append(label)
                    if opt_other is not None:
                        other_text = opt_other
            else:
                # Single-select: get the selected option
                sel_idx = self.single_selections[i]
                if sel_idx is not None:
                    label, other_text = self._resolve_option_label(question, i, sel_idx)
                    selected_labels.append(label)

            answers.append(
                QuestionAnswer(
                    question_header=question.header,
                    selected_options=selected_labels,
                    other_text=other_text,
                )
            )
        return answers


async def interactive_question_picker(
    questions: list[Question],
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[list[QuestionAnswer], bool, bool]:
    """Show an interactive split-panel TUI for questions.

    Args:
        questions: List of validated Question objects
        timeout_seconds: Inactivity timeout in seconds

    Returns:
        Tuple of (answers, cancelled, timed_out) where:
        - answers: List of QuestionAnswer objects
        - cancelled: True if user cancelled
        - timed_out: True if interaction timed out

    Raises:
        CancelledException: If user cancels with Esc/Ctrl+C
    """
    # Import here to avoid circular dependency with command_runner
    from code_puppy.tools.command_runner import set_awaiting_user_input

    state = QuestionUIState(questions)
    state.timeout_seconds = timeout_seconds
    set_awaiting_user_input(True)

    try:
        from .tui_loop import run_question_tui

        # prompt_toolkit manages alt screen via full_screen=True
        return await run_question_tui(state)
    finally:
        set_awaiting_user_input(False)
