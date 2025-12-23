"""Interactive TUI theme picker for Code Puppy.

Split-panel interface with theme list on left (35%) and live preview on right (65%).
Shows sample messages with actual theme colors for real-time feedback.
"""

import io
import sys
from typing import Optional

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import ANSI, FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from code_puppy.theming import (
    get_available_themes,
    get_current_theme,
    get_theme_by_name,
    set_current_theme,
)
from code_puppy.tools.command_runner import set_awaiting_user_input


async def interactive_theme_picker() -> Optional[str]:
    """Show interactive theme picker TUI.

    Returns:
        Theme name if user selected one, None if cancelled.
    """
    try:
        set_awaiting_user_input(True)

        # Get available themes
        available_themes = get_available_themes()
        if not available_themes:
            return None

        # Prepare choices list: themes + custom option
        choices = []
        for theme_name in available_themes:
            theme = get_theme_by_name(theme_name)
            if theme is None:
                continue  # Skip invalid themes
            current_theme = get_current_theme()
            marker = " ← current" if theme_name == current_theme.name else ""
            choices.append(f"{theme.display_name}{marker}")

        # Add custom theme option
        choices.append("✨ Custom Theme")

        selected_index = [0]
        result = [None]

        # Track original theme in case of cancel
        original_theme_name = get_current_theme().name

        def update_preview(selected_choice: str):
            """Update theme based on selection."""
            try:
                # Extract theme name from display text
                if selected_choice == "✨ Custom Theme":
                    # Keep current theme for custom mode
                    pass
                else:
                    # Remove any "← current" marker
                    theme_display_name = selected_choice.replace(
                        " ← current", ""
                    ).strip()

                    # Find the theme by display name
                    for theme_name in available_themes:
                        theme = get_theme_by_name(theme_name)
                        if theme and theme.display_name == theme_display_name:
                            set_current_theme(theme_name)
                            break
            except Exception:
                pass  # Silently ignore errors

        def get_left_panel_text():
            """Generate the selector menu text."""
            lines = []
            lines.append(("bold cyan", "[ THEME PICKER ]"))
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
                ("fg:ansicyan", "↑↓ Navigate  │  Enter Select  │  Ctrl+C Cancel")
            )
            return FormattedText(lines)

        def get_right_panel_text():
            """Generate the preview panel with live theme colors."""
            try:
                current_choice = choices[selected_index[0]]
                if current_choice == "✨ Custom Theme":
                    return get_custom_theme_preview()
                else:
                    return get_theme_preview()
            except Exception as e:
                return FormattedText([("fg:ansired", f"Preview error: {e}")])

        # Set up key bindings
        kb = KeyBindings()

        @kb.add("up")
        def move_up(event):
            selected_index[0] = (selected_index[0] - 1) % len(choices)
            selected_choice = choices[selected_index[0]]
            update_preview(selected_choice)
            event.app.invalidate()

        @kb.add("down")
        def move_down(event):
            selected_index[0] = (selected_index[0] + 1) % len(choices)
            selected_choice = choices[selected_index[0]]
            update_preview(selected_choice)
            event.app.invalidate()

        @kb.add("enter")
        def accept(event):
            selected_choice = choices[selected_index[0]]
            if selected_choice == "✨ Custom Theme":
                result[0] = "custom"
            else:
                # Extract theme display name
                theme_display_name = selected_choice.replace(" ← current", "").strip()
                # Find theme by display name
                for theme_name in available_themes:
                    theme = get_theme_by_name(theme_name)
                    if theme and theme.display_name == theme_display_name:
                        result[0] = theme_name
                        break
            event.app.exit()

        @kb.add("c-c")
        @kb.add("escape")
        def cancel(event):
            # Restore original theme
            set_current_theme(original_theme_name)
            result[0] = None
            event.app.exit()

        # Create split layout
        left_panel = Window(
            content=FormattedTextControl(lambda: get_left_panel_text()),
            width=35,  # 35% width for menu
        )

        right_panel = Window(
            content=FormattedTextControl(lambda: get_right_panel_text()),
        )

        root_container = VSplit(
            [
                Frame(left_panel, title="Themes"),
                Frame(right_panel, title="Live Preview"),
            ]
        )

        layout = Layout(root_container)

        app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=False,
            mouse_support=False,
            color_depth="DEPTH_24_BIT",
        )

        sys.stdout.flush()

        # Clear screen and run
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

        # Trigger initial update
        update_preview(choices[selected_index[0]])

        await app.run_async()

        return result[0]

    finally:
        set_awaiting_user_input(False)


def get_theme_preview() -> ANSI:
    """Generate live preview using current theme colors."""
    theme = get_current_theme()

    # Render with Rich Console to get actual theme colors
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        force_terminal=True,
        width=80,
        legacy_windows=False,
        color_system="truecolor",
        no_color=False,
        force_interactive=True,
    )

    # Use Rich components that will pick up theme colors

    # Header
    header_text = f"LIVE PREVIEW - Theme: {theme.display_name}"
    console.print(Rule(characters="═", style=theme.colors.header_style))
    title_text = f"[{theme.colors.panel_title_style}]LIVE PREVIEW - Theme: {theme.display_name}[/{theme.colors.panel_title_style}]"
    console.print(
        Panel(
            header_text, title=title_text, border_style=theme.colors.panel_border_style
        )
    )
    console.print(Rule(characters="═", style=theme.colors.header_style))

    # Message Levels
    console.print()
    console.print("MESSAGE LEVELS:", style=theme.colors.header_style)
    console.print(
        "ℹ Info: This is an informational message", style=theme.colors.info_style
    )
    console.print(
        "✓ Success: Operation completed successfully!", style=theme.colors.success_style
    )
    console.print(
        "⚠ Warning: Something needs your attention", style=theme.colors.warning_style
    )
    console.print("✗ Error: Something went wrong", style=theme.colors.error_style)
    console.print("• Debug: Verbose debugging output", style=theme.colors.debug_style)

    # Agent Output
    console.print()
    console.print("AGENT OUTPUT:", style=theme.colors.header_style)

    reasoning_title = f"[{theme.colors.reasoning_header_style}]AGENT REASONING[/{theme.colors.reasoning_header_style}]"
    reasoning_panel = Panel(
        "Analyzing the codebase structure...\n\nCurrent: I'm examining the theming system\nNext: Will render the preview with live colors",
        title=reasoning_title,
        border_style=theme.colors.panel_border_style,
    )
    console.print(reasoning_panel)

    response_title = f"[{theme.colors.response_header_style}]AGENT RESPONSE[/{theme.colors.response_header_style}]"
    response_panel = Panel(
        "Found 5 themes available for selection.\n\nThe theming system looks well-structured\nwith proper color integration throughout.",
        title=response_title,
        border_style=theme.colors.panel_border_style,
    )
    console.print(response_panel)

    # Tool Output
    console.print()
    console.print("TOOL OUTPUT:", style=theme.colors.header_style)
    console.print(
        "📂 /path/to/example.py (15.2 KB)", style=theme.colors.file_path_style
    )
    # Use Rich Text objects for line numbers to avoid markup issues
    line42_text = Text()
    line42_text.append("  42 │ ", style=theme.colors.line_number_style)
    line42_text.append("def example_function():", style="default")
    console.print(line42_text)

    line43_text = Text()
    line43_text.append("  43 │ ", style=theme.colors.line_number_style)
    line43_text.append("    return 'Hello World'", style="default")
    console.print(line43_text)

    # Grep Results
    console.print()
    console.print("GREP RESULTS:", style=theme.colors.header_style)
    console.print("📄 main.py (3 matches)", style=theme.colors.file_path_style)
    # Use Rich Text objects for line numbers
    lines = [
        "theme = get_current_theme()",
        "set_current_theme('dracula')",
        "theme.apply(styles)",
    ]
    for i, content in enumerate(lines, 15):
        line_text = Text()
        line_text.append(f"  {i} │ ", style=theme.colors.line_number_style)
        line_text.append(content, style="default")
        console.print(line_text)
    console.print("✓ Found 3 matches across 1 files", style=theme.colors.success_style)

    # Shell Command
    console.print()
    console.print("SHELL COMMAND:", style=theme.colors.header_style)
    # Use Rich Text for command
    cmd_text = Text()
    cmd_text.append("🚀 $ ", style=theme.colors.command_style)
    cmd_text.append("echo 'Hello, World!'", style="default")
    console.print(cmd_text)
    console.print("Hello, World!", style=theme.colors.info_style)

    # Spinner
    console.print()
    console.print("SPINNER:", style=theme.colors.header_style)
    console.print("⠋ Thinking...", style=theme.colors.spinner_text_style)

    # Status Panel
    console.print()
    console.print("STATUS PANEL:", style=theme.colors.header_style)
    table = Table(show_header=True, box=None)
    table.add_column("Key", style=theme.colors.panel_title_style)
    table.add_column("Value")
    table.add_row("Foo", "Bar")
    table.add_row("Baz", "Qux")
    status_title = (
        f"[{theme.colors.panel_title_style}]Status[/{theme.colors.panel_title_style}]"
    )
    panel = Panel(
        table,
        title=status_title,
        border_style=theme.colors.panel_border_style,
    )
    console.print(panel)

    console.print(Rule(characters="═", style=theme.colors.header_style))

    ansi_output = buffer.getvalue()
    return ANSI(ansi_output)


def get_custom_theme_preview() -> ANSI:
    """Generate preview for custom theme mode."""
    theme = get_current_theme()

    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=True, width=80)

    console.print(Rule(characters="═", style=theme.colors.header_style))
    editor_title = f"[{theme.colors.panel_title_style}]CUSTOM THEME EDITOR[/{theme.colors.panel_title_style}]"
    console.print(
        Panel(
            "CUSTOM THEME EDITOR",
            title=editor_title,
            border_style=theme.colors.panel_border_style,
        )
    )
    console.print(Rule(characters="═", style=theme.colors.header_style))
    console.print()
    console.print(
        "Select a category on the left to customize colors.",
        style=theme.colors.muted_style,
    )
    console.print(f"Current theme: {theme.display_name}", style=theme.colors.info_style)
    console.print(Rule(characters="═", style=theme.colors.header_style))

    ansi_output = buffer.getvalue()
    return ANSI(ansi_output)


def run_theme_menu() -> Optional[str]:
    """Synchronous wrapper for theme picker.

    Runs the async theme picker in a separate thread to avoid
    conflicts with any existing event loop.

    Returns:
        Theme name if user selected one, None if cancelled.
    """
    import asyncio
    import concurrent.futures

    try:
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(lambda: asyncio.run(interactive_theme_picker()))
            return future.result(timeout=300)  # 5 min timeout
    except KeyboardInterrupt:
        return None
    except concurrent.futures.TimeoutError:
        return None
    except Exception:
        return None
