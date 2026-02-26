"""Rendering functions for the ask_user_question TUI.

This module contains the panel rendering logic, separated from the main
TUI logic to keep files under 600 lines.
"""

from __future__ import annotations

import io
import shutil
from typing import TYPE_CHECKING

from prompt_toolkit.formatted_text import ANSI
from rich.console import Console
from rich.markup import escape as rich_escape

from .constants import (
    ARROW_DOWN,
    ARROW_LEFT,
    ARROW_RIGHT,
    ARROW_UP,
    AUTO_ADD_OTHER_OPTION,
    BORDER_DOUBLE,
    CHECK_MARK,
    CURSOR_POINTER,
    HELP_BORDER_WIDTH,
    MAX_READABLE_WIDTH,
    OTHER_OPTION_DESCRIPTION,
    OTHER_OPTION_LABEL,
    PANEL_CONTENT_PADDING,
    PIPE_SEPARATOR,
    RADIO_FILLED,
)
from .theme import get_rich_colors

if TYPE_CHECKING:
    from .terminal_ui import QuestionUIState
    from .theme import RichColors


def render_question_panel(
    state: QuestionUIState,
    colors: RichColors | None = None,
    available_width: int | None = None,
) -> ANSI:
    """Render the right panel with the current question.

    Args:
        state: The current UI state
        colors: Optional cached RichColors instance. If None, fetches from config.
    """
    if colors is None:
        colors = get_rich_colors()

    buffer = io.StringIO()
    # Use available panel width if provided, otherwise fall back to terminal width
    # Subtract padding to avoid overflow into frame borders
    if available_width is not None:
        terminal_width = min(available_width, MAX_READABLE_WIDTH)
    else:
        terminal_width = min(shutil.get_terminal_size().columns, MAX_READABLE_WIDTH)
    console = Console(
        file=buffer,
        force_terminal=True,
        width=terminal_width,
        legacy_windows=False,
        color_system="truecolor",
        no_color=False,
        force_interactive=True,
    )

    # Show help overlay if requested
    if state.show_help:
        return _render_help_overlay(console, buffer, colors)

    question = state.current_question
    q_num = state.current_question_index + 1
    total = len(state.questions)
    pad = PANEL_CONTENT_PADDING  # Left padding for visual alignment

    # Header
    console.print(
        f"{pad}[{colors.header}][{question.header}][/{colors.header}] "
        f"[{colors.progress}]({q_num}/{total})[/{colors.progress}]"
    )
    console.print()

    # Question text
    if question.multi_select:
        console.print(
            f"{pad}[bold]? {question.question}[/bold] [dim](select multiple)[/dim]"
        )
    else:
        console.print(f"{pad}[bold]? {question.question}[/bold]")
    console.print()

    # Render options
    for i, option in enumerate(question.options):
        _render_option(
            console,
            label=option.label,
            description=option.description,
            is_cursor=state.current_cursor == i,
            is_selected=state.is_option_selected(i),
            multi_select=question.multi_select,
            colors=colors,
            padding=pad,
        )

    # Render "Other" option if enabled
    if AUTO_ADD_OTHER_OPTION:
        other_idx = len(question.options)
        # Get the stored "Other" text for this question
        other_text = state.get_other_text_for_question(state.current_question_index)
        # Build the description - show stored text if available
        # Escape user input to prevent Rich markup injection
        if other_text:
            other_desc = f'"{rich_escape(other_text)}"'
        else:
            other_desc = OTHER_OPTION_DESCRIPTION
        _render_option(
            console,
            label=OTHER_OPTION_LABEL,
            description=other_desc,
            is_cursor=state.current_cursor == other_idx,
            is_selected=state.is_option_selected(other_idx),
            multi_select=question.multi_select,
            colors=colors,
            padding=pad,
        )

    # If entering "Other" text, show the input field
    if state.entering_other_text:
        console.print()
        console.print(
            f"{pad}[{colors.input_label}]Enter your custom option:[/{colors.input_label}]"
        )
        console.print(
            f"{pad}[{colors.input_text}]> {state.other_text_buffer}_[/{colors.input_text}]"
        )
        console.print()
        console.print(
            f"{pad}[{colors.input_hint}]Enter to confirm, Esc to cancel[/{colors.input_hint}]"
        )

    # Help text at bottom - build dynamically, filtering out None entries
    console.print()
    is_last = state.current_question_index == total - 1
    help_parts = [
        "Space Toggle" if question.multi_select else "Space Select",
        "Enter Next" if not is_last else None,
        f"{ARROW_LEFT}{ARROW_RIGHT} Questions" if total > 1 else None,
        "Ctrl+S Submit",
        "? Help",
    ]
    separator = f" {PIPE_SEPARATOR} "
    console.print(
        f"{pad}[{colors.description}]{separator.join(p for p in help_parts if p)}[/{colors.description}]"
    )

    # Show timeout warning if approaching timeout
    if state.should_show_timeout_warning():
        remaining = state.get_time_remaining()
        console.print()
        console.print(
            f"{pad}[{colors.timeout_warning}]⚠ Timeout in {remaining}s - press any key to continue[/{colors.timeout_warning}]"
        )

    return ANSI(buffer.getvalue())


# Help overlay shortcut data: (section_name, [(primary_key, alt_key_or_None, description), ...])
_HELP_SECTIONS: list[tuple[str, list[tuple[str, str | None, str]]]] = [
    (
        "Navigation:",
        [
            (ARROW_UP, "k", "Move up"),
            (ARROW_DOWN, "j", "Move down"),
            (ARROW_LEFT, "h", "Previous question"),
            (ARROW_RIGHT, "l", "Next question"),
            ("g", None, "Jump to first option"),
            ("G", None, "Jump to last option"),
        ],
    ),
    (
        "Selection:",
        [
            ("Space", None, "Select option (radio) / Toggle (checkbox)"),
            ("Enter", None, "Next question (select + advance)"),
            ("a", None, "Select all (multi-select)"),
            ("n", None, "Select none (multi-select)"),
            ("Ctrl+S", None, "Submit all answers"),
        ],
    ),
    (
        "Other:",
        [
            ("Tab", None, "Peek behind (toggle TUI visibility)"),
            ("?", None, "Toggle this help"),
            ("Esc", None, "Cancel"),
            ("Ctrl+C", None, "Cancel"),
        ],
    ),
]


def _render_help_overlay(
    console: Console, buffer: io.StringIO, colors: RichColors
) -> ANSI:
    """Render the help overlay using data-driven approach."""
    pad = PANEL_CONTENT_PADDING
    border = colors.help_border
    key_style = colors.help_key
    section_style = colors.help_section

    border_line = f"{pad}[{border}]{BORDER_DOUBLE * HELP_BORDER_WIDTH}[/{border}]"

    console.print(border_line)
    console.print(
        f"{pad}[{colors.help_title}]           KEYBOARD SHORTCUTS[/{colors.help_title}]"
    )
    console.print(border_line)
    console.print()

    for section_name, shortcuts in _HELP_SECTIONS:
        console.print(f"{pad}[{section_style}]{section_name}[/{section_style}]")
        for primary, alt, desc in shortcuts:
            if alt:
                console.print(
                    f"{pad}  [{key_style}]{primary}[/{key_style}] / "
                    f"[{key_style}]{alt}[/{key_style}]       {desc}"
                )
            else:
                console.print(
                    f"{pad}  [{key_style}]{primary}[/{key_style}]           {desc}"
                )
        console.print()

    console.print(border_line)
    console.print(
        f"{pad}[{colors.help_close}]Press [{key_style}]?[/{key_style}] to close this help[/{colors.help_close}]"
    )
    console.print(border_line)

    return ANSI(buffer.getvalue())


def _render_option(
    console: Console,
    *,
    label: str,
    description: str,
    is_cursor: bool,
    is_selected: bool,
    multi_select: bool,
    colors: RichColors,
    padding: str = "",
) -> None:
    """Render a single option line.

    Args:
        console: Rich console to render to
        label: Option label text
        description: Option description text
        is_cursor: Whether cursor is on this option
        is_selected: Whether this option is selected
        multi_select: Whether this is a multi-select question
        colors: RichColors instance (required to avoid repeated config lookups)
        padding: Left padding string to prepend to each line
    """
    # Escape label and description to prevent Rich markup injection
    label = rich_escape(label)
    description = rich_escape(description) if description else ""

    cursor_style = colors.cursor
    selected_style = colors.selected
    desc_style = colors.description

    # Build the prefix with checkbox or radio button
    if multi_select:
        # Checkbox style: [✓] or [ ]
        checkbox = f"[{CHECK_MARK}]" if is_selected else "[ ]"
        if is_cursor:
            prefix = f"[{cursor_style}]{CURSOR_POINTER} {checkbox}[/{cursor_style}]"
        else:
            prefix = f"  {checkbox}"
    else:
        # Radio button style: (●) or ( )
        radio = f"({RADIO_FILLED})" if is_selected else "( )"
        if is_cursor:
            prefix = f"[{cursor_style}]{CURSOR_POINTER} {radio}[/{cursor_style}]"
        else:
            prefix = f"  {radio}"

    # Build the label
    if is_cursor:
        label_styled = f"[{cursor_style}]{label}[/{cursor_style}]"
    elif is_selected:
        label_styled = f"[{selected_style}]{label}[/{selected_style}]"
    else:
        label_styled = label

    # Print option
    console.print(f"{padding}  {prefix} {label_styled}")

    # Print description if present
    if description:
        console.print(f"{padding}      [{desc_style}]{description}[/{desc_style}]")
    console.print()
