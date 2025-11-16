"""Interactive nested menu for diff configuration.

Now using the fixed arrow_select_async with proper HTML escaping.
"""

import io
import sys
import time
from typing import Callable, Optional

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import ANSI, FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame
from rich.console import Console


class DiffConfiguration:
    """Holds the current diff configuration state."""

    def __init__(self):
        """Initialize configuration from current settings."""
        from code_puppy.config import (
            get_diff_addition_color,
            get_diff_deletion_color,
            get_diff_highlight_style,
        )

        self.current_style = get_diff_highlight_style()
        self.current_add_color = get_diff_addition_color()
        self.current_del_color = get_diff_deletion_color()
        self.original_style = self.current_style
        self.original_add_color = self.current_add_color
        self.original_del_color = self.current_del_color

    def has_changes(self) -> bool:
        """Check if any changes have been made."""
        return (
            self.current_style != self.original_style
            or self.current_add_color != self.original_add_color
            or self.current_del_color != self.original_del_color
        )


async def interactive_diff_picker() -> Optional[dict]:
    """Show an interactive full-screen TUI to configure diff settings.

    Returns:
        A dict with changes or None if cancelled
    """
    from code_puppy.tools.command_runner import set_awaiting_user_input

    config = DiffConfiguration()

    set_awaiting_user_input(True)

    # Enter alternate screen buffer once for entire session
    sys.stdout.write("\033[?1049h")  # Enter alternate buffer
    sys.stdout.write("\033[2J\033[H")  # Clear and home
    sys.stdout.flush()
    time.sleep(0.1)  # Minimal delay for state sync

    try:
        # Main menu loop
        while True:
            choices = [
                "Configure Style",
                "Configure Addition Color",
                "Configure Deletion Color",
            ]

            if config.has_changes():
                choices.append("Save & Exit")
            else:
                choices.append("Exit")

            # Dummy update function for main menu (config doesn't change on navigation)
            def dummy_update(choice: str):
                pass

            def get_main_preview():
                return _get_preview_text_for_prompt_toolkit(config)

            try:
                selected = await _split_panel_selector(
                    "Diff Configuration",
                    choices,
                    dummy_update,
                    get_preview=get_main_preview,
                )
            except KeyboardInterrupt:
                break

            # Handle selection
            if "Style" in selected:
                await _handle_style_menu(config)
            elif "Addition" in selected:
                await _handle_color_menu(config, "additions")
            elif "Deletion" in selected:
                await _handle_color_menu(config, "deletions")
            else:
                # Exit
                break

    except Exception:
        # Silent error - just exit cleanly
        return None
    finally:
        set_awaiting_user_input(False)
        # Exit alternate screen buffer once at end
        sys.stdout.write("\033[?1049l")  # Exit alternate buffer
        sys.stdout.flush()

    # Return changes if any
    if config.has_changes():
        return {
            "style": config.current_style,
            "add_color": config.current_add_color,
            "del_color": config.current_del_color,
        }

    return None


async def _handle_style_menu(config: DiffConfiguration) -> None:
    """Handle style selection."""
    from code_puppy.tools.common import arrow_select_async

    styles = ["text", "highlight"]
    descriptions = {
        "text": "Plain text diffs with simple colors",
        "highlight": "Full syntax highlighting with Pygments (beautiful!)",
    }

    choices = []
    for style in styles:
        marker = " (current)" if style == config.current_style else ""
        choices.append(f"{style.upper()} - {descriptions[style]}{marker}")

    try:
        selected = await arrow_select_async("Select diff style:", choices)

        # Update config instantly - no delay
        for style in styles:
            if style.upper() in selected:
                config.current_style = style
                break
    except KeyboardInterrupt:
        pass
    except Exception:
        pass  # Silent error handling


async def _split_panel_selector(
    title: str,
    choices: list[str],
    on_change: Callable[[str], None],
    get_preview: Callable[[], ANSI],
) -> Optional[str]:
    """Split-panel selector with menu on left and live preview on right."""
    selected_index = [0]
    result = [None]

    def get_left_panel_text():
        """Generate the selector menu text."""
        try:
            lines = []
            lines.append(("bold cyan", title))
            lines.append(("", "\n\n"))

            for i, choice in enumerate(choices):
                if i == selected_index[0]:
                    lines.append(("fg:ansigreen", "▶ "))
                    lines.append(("fg:ansigreen bold", choice))
                else:
                    lines.append(("", "  "))
                    lines.append(("", choice))
                lines.append(("", "\n"))

            lines.append(("", "\n"))
            lines.append(
                ("fg:ansicyan", "↑↓ Navigate  │  Enter Confirm  │  Ctrl-C Cancel")
            )
            return FormattedText(lines)
        except Exception as e:
            return FormattedText([("fg:ansired", f"Error: {e}")])

    def get_right_panel_text():
        """Generate the preview panel text."""
        try:
            preview = get_preview()
            # get_preview() now returns ANSI, which is already FormattedText-compatible
            return preview
        except Exception as e:
            return FormattedText([("fg:ansired", f"Preview error: {e}")])

    kb = KeyBindings()

    @kb.add("up")
    def move_up(event):
        selected_index[0] = (selected_index[0] - 1) % len(choices)
        on_change(choices[selected_index[0]])
        event.app.invalidate()

    @kb.add("down")
    def move_down(event):
        selected_index[0] = (selected_index[0] + 1) % len(choices)
        on_change(choices[selected_index[0]])
        event.app.invalidate()

    @kb.add("enter")
    def accept(event):
        result[0] = choices[selected_index[0]]
        event.app.exit()

    @kb.add("c-c")
    def cancel(event):
        result[0] = None
        event.app.exit()

    # Create split layout with left (selector) and right (preview) panels
    left_panel = Window(
        content=FormattedTextControl(lambda: get_left_panel_text()),
        width=50,
    )

    right_panel = Window(
        content=FormattedTextControl(lambda: get_right_panel_text()),
    )

    # Create vertical split (side-by-side panels)
    root_container = VSplit(
        [
            Frame(left_panel, title="Menu"),
            Frame(right_panel, title="Preview"),
        ]
    )

    layout = Layout(root_container)
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,  # Don't use full_screen to avoid buffer issues
        mouse_support=False,
    )

    sys.stdout.flush()
    sys.stdout.flush()

    # Trigger initial update
    on_change(choices[selected_index[0]])

    # Just clear the current buffer (don't switch buffers)
    sys.stdout.write("\033[2J\033[H")  # Clear screen within current buffer
    sys.stdout.flush()

    # Run application (stays in same alternate buffer)
    await app.run_async()

    if result[0] is None:
        raise KeyboardInterrupt()

    return result[0]


# Color palettes with nice names
ADDITION_COLORS = {
    "Green": "green",
    "Bright Green": "bright_green",
    "Cyan": "cyan",
    "Bright Cyan": "bright_cyan",
    "Blue": "blue",
    "Bright Blue": "bright_blue",
    "Lime": "#00ff00",
    "Spring Green": "#00ff7f",
    "Aqua": "#00ffff",
    "Chartreuse": "#7fff00",
    "Medium Spring Green": "#00fa9a",
    "Lime Green": "#32cd32",
    "Turquoise": "#40e0d0",
    "Bright Spring Green": "#00ff80",
    "Caribbean Green": "#00d4aa",
    "Dodger Blue": "#1e90ff",
    "Deep Sky Blue": "#00bfff",
    "Sky Blue": "#87ceeb",
    "Royal Blue": "#4169e1",
    "Azure": "#0080ff",
    "Spring": "#00ffaa",
}

DELETION_COLORS = {
    "Red": "red",
    "Bright Red": "bright_red",
    "Magenta": "magenta",
    "Bright Magenta": "bright_magenta",
    "Yellow": "yellow",
    "Bright Yellow": "bright_yellow",
    "Pure Red": "#ff0000",
    "Orange Red": "#ff4500",
    "Tomato": "#ff6347",
    "Orange": "#ffa500",
    "Deep Pink": "#ff1493",
    "Fuchsia": "#ff00ff",
    "Orchid": "#da70d6",
    "Electric Yellow": "#ffff00",
    "Vivid Magenta": "#ff00aa",
    "Safety Orange": "#ff7700",
    "Vivid Orange": "#ffaa00",
    "Dark Orange": "#ff8800",
    "Violet": "#ee82ee",
    "Neon Magenta": "#ff55ff",
    "Purple Magenta": "#cc00ff",
}


def _convert_rich_color_to_prompt_toolkit(color: str) -> str:
    """Convert Rich color names to prompt-toolkit compatible names."""
    # Hex colors pass through as-is
    if color.startswith("#"):
        return color
    # Map bright_ colors to ansi equivalents
    if color.startswith("bright_"):
        return "ansi" + color.replace("bright_", "")
    # Basic terminal colors
    if color.lower() in [
        "black",
        "red",
        "green",
        "yellow",
        "blue",
        "magenta",
        "cyan",
        "white",
        "gray",
        "grey",
    ]:
        return color.lower()
    # Default safe fallback for unknown colors
    return "white"


def _get_preview_text_for_prompt_toolkit(config: DiffConfiguration) -> ANSI:
    """Get preview as ANSI for embedding in selector with live colors.

    Returns ANSI-formatted text that prompt_toolkit can render with full colors.
    """
    from code_puppy.tools.common import format_diff_with_colors

    # Build header with current settings info using Rich markup
    header_parts = []
    header_parts.append("[bold]═" * 50 + "[/bold]")
    header_parts.append("[bold cyan] LIVE PREVIEW[/bold cyan]")
    header_parts.append("[bold]═" * 50 + "[/bold]")
    header_parts.append("")
    header_parts.append(f" Style: [bold]{config.current_style}[/bold]")

    if config.current_style == "text":
        header_parts.append(f" Additions: {config.current_add_color}")
        header_parts.append(f" Deletions: {config.current_del_color}")
    elif config.current_style == "highlight":
        header_parts.append(" Mode: Full syntax highlighting")
        header_parts.append(" Colors: Monokai theme")
        header_parts.append(" Backgrounds: Dark themed")

    header_parts.append("")
    header_parts.append("[bold] Example Diff:[/bold]")
    header_parts.append("")

    header_text = "\n".join(header_parts)

    # Create a sample diff that shows off the highlighting
    sample_diff = """--- a/example.py
+++ b/example.py
@@ -1,5 +1,7 @@
 def hello(name):
-    return "old"
+    msg = "new"
+    return msg
 
 def goodbye():
-    pass
+    print("bye!")
+    return None"""

    # Temporarily override config to use current preview settings
    from code_puppy.config import (
        get_diff_addition_color,
        get_diff_deletion_color,
        get_diff_highlight_style,
        set_diff_addition_color,
        set_diff_deletion_color,
        set_diff_highlight_style,
    )

    # Save original values
    original_style = get_diff_highlight_style()
    original_add_color = get_diff_addition_color()
    original_del_color = get_diff_deletion_color()

    try:
        # Temporarily set config to preview values
        set_diff_highlight_style(config.current_style)
        set_diff_addition_color(config.current_add_color)
        set_diff_deletion_color(config.current_del_color)

        # Get the formatted diff (either Rich Text or Rich markup string)
        formatted_diff = format_diff_with_colors(sample_diff)

        # Render everything with Rich Console to get ANSI output
        buffer = io.StringIO()
        console = Console(
            file=buffer,
            force_terminal=True,
            width=60,
            legacy_windows=False,
            color_system="truecolor",
        )

        # Print header
        console.print(header_text, end="\n")

        # Print diff (handles both Text objects and markup strings)
        console.print(formatted_diff, end="\n\n")

        # Print footer
        console.print("[bold]═" * 50 + "[/bold]", end="")

        ansi_output = buffer.getvalue()

    finally:
        # Restore original config values
        set_diff_highlight_style(original_style)
        set_diff_addition_color(original_add_color)
        set_diff_deletion_color(original_del_color)

    # Wrap in ANSI() so prompt_toolkit can render it
    return ANSI(ansi_output)


async def _handle_color_menu(config: DiffConfiguration, color_type: str) -> None:
    """Handle color selection with live preview updates."""
    # Text mode only (highlighted disabled)
    if color_type == "additions":
        color_dict = ADDITION_COLORS
        current = config.current_add_color
        title = "Select addition color:"
    else:
        color_dict = DELETION_COLORS
        current = config.current_del_color
        title = "Select deletion color:"

    # Build choices with nice names
    choices = []
    for name, color_value in color_dict.items():
        marker = " ← current" if color_value == current else ""
        choices.append(f"{name}{marker}")

    # Store original color for potential cancellation
    original_color = current

    # Callback for live preview updates
    def update_preview(selected_choice: str):
        # Extract color name and look up the actual color value
        color_name = selected_choice.replace(" ← current", "").strip()
        selected_color = color_dict.get(color_name, list(color_dict.values())[0])
        if color_type == "additions":
            config.current_add_color = selected_color
        else:
            config.current_del_color = selected_color

    # Function to get live preview header with colored diff
    def get_preview_header():
        return _get_preview_text_for_prompt_toolkit(config)

    try:
        # Use split panel selector with live preview
        await _split_panel_selector(
            title, choices, update_preview, get_preview=get_preview_header
        )
    except KeyboardInterrupt:
        # Restore original color on cancel
        if color_type == "additions":
            config.current_add_color = original_color
        else:
            config.current_del_color = original_color
    except Exception:
        pass  # Silent error handling
