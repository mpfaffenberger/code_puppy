"""Arrow-based selector component for custom theme builder.

This module provides the arrow_select_async function used for selecting
colors and style modifiers in the custom theme builder interface.
"""

import sys
from typing import Callable, List, Optional

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame


async def arrow_select_async(
    title: str, choices: List[str], current: str, on_change: Callable[[str], None]
) -> Optional[str]:
    """Arrow-based selector with live preview.

    This function creates a simple arrow-based selector interface where users
    can navigate through choices using up/down arrows and confirm with Enter.
    The currently selected value is highlighted and the original/current value
    is marked with "(current)" label.

    Args:
        title: Title for the selector
        choices: List of choices to select from
        current: Currently selected value (marked with "(current)")
        on_change: Callback function called when selection changes

    Returns:
        Selected choice or None if cancelled (Ctrl-C)

    Example:
        >>> from code_puppy.command_line.custom_theme_picker import arrow_select_async
        >>> import asyncio
        >>>
        >>> def on_change(choice):
        ...     print(f"Selected: {choice}")
        >>>
        >>> selected = asyncio.run(
        ...     arrow_select_async(
        ...         "Select Color",
        ...         ["red", "green", "blue"],
        ...         "green",
        ...         on_change
        ...     )
        ... )
    """
    selected_index = [0]
    result = [None]

    # Find current selection
    try:
        selected_index[0] = choices.index(current)
    except ValueError:
        selected_index[0] = 0

    def get_preview_text() -> FormattedText:
        """Generate the selector text with current selection highlighted."""
        lines = []
        lines.append(("bold cyan", title))
        lines.append(("", "\n\n"))

        for i, choice in enumerate(choices):
            is_current = choice == current
            is_selected = i == selected_index[0]

            if is_selected:
                lines.append(("fg:ansigreen", "▶ "))
                lines.append(("fg:ansigreen bold", choice))
            elif is_current:
                lines.append(("", "  "))
                lines.append(("fg:ansiyellow", f"{choice} (current)"))
            else:
                lines.append(("", "  "))
                lines.append(("", choice))
            lines.append(("", "\n"))

        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  ↑/↓ "))
        lines.append(("", "Navigate  "))
        lines.append(("fg:green", "Enter "))
        lines.append(("", "Confirm  "))
        lines.append(("fg:ansibrightblack", "Esc "))
        lines.append(("", "Cancel"))
        lines.append(("", "\n"))
        lines.append(("fg:ansibrightblack", "  Ctrl+C "))
        lines.append(("", "Exit"))

        return FormattedText(lines)

    # Key bindings
    kb = KeyBindings()

    @kb.add("up")
    def move_up(event):
        """Move selection up."""
        selected_index[0] = (selected_index[0] - 1) % len(choices)
        on_change(choices[selected_index[0]])
        event.app.invalidate()

    @kb.add("down")
    def move_down(event):
        """Move selection down."""
        selected_index[0] = (selected_index[0] + 1) % len(choices)
        on_change(choices[selected_index[0]])
        event.app.invalidate()

    @kb.add("enter")
    def accept(event):
        """Accept current selection."""
        result[0] = choices[selected_index[0]]
        event.app.exit()

    @kb.add("c-c")
    def cancel(event):
        """Cancel selection."""
        result[0] = None
        event.app.exit()

    @kb.add("escape")
    def cancel_esc(event):
        """Cancel selection on Escape."""
        result[0] = None
        event.app.exit()

    # Create UI
    preview_window = Window(
        content=FormattedTextControl(lambda: get_preview_text()), width=50
    )

    preview_frame = Frame(preview_window, title="Select")

    layout = Layout(preview_frame)
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )

    # Clear screen
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

    # Run application
    await app.run_async()

    if result[0] is None:
        raise KeyboardInterrupt()

    return result[0]
