"""Interactive TUI for configuring banner colors.

Similar to diff_menu.py but for customizing the banner background colors
for different tool outputs (THINKING, SHELL COMMAND, READ FILE, etc.).

Use /colors to launch the TUI and customize your banners!
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

# Banner display names with icons
BANNER_DISPLAY_INFO = {
    "thinking": ("THINKING", "⚡"),
    "agent_response": ("AGENT RESPONSE", ""),
    "shell_command": ("SHELL COMMAND", "🚀"),
    "read_file": ("READ FILE", "📂"),
    "edit_file": ("EDIT FILE", "✏️"),
    "grep": ("GREP", "📂"),
    "directory_listing": ("DIRECTORY LISTING", "📂"),
    "agent_reasoning": ("AGENT REASONING", ""),
    "invoke_agent": ("🤖 INVOKE AGENT", ""),
    "subagent_response": ("✓ AGENT RESPONSE", ""),
    "list_agents": ("LIST AGENTS", ""),
}

# Sample content to show after each banner
BANNER_SAMPLE_CONTENT = {
    "thinking": "Let me analyze this code structure and figure out the best approach...",
    "agent_response": "I've implemented the feature you requested. The changes include...",
    "shell_command": "$ npm run test -- --silent\n⏱ Timeout: 60s",
    "read_file": "/path/to/file.py (lines 1-50)",
    "edit_file": "MODIFY /path/to/file.py\n--- a/file.py\n+++ b/file.py",
    "grep": "/src for 'handleClick'\n📄 Button.tsx (3 matches)",
    "directory_listing": "/src (recursive=True)\n📁 components/\n   └── Button.tsx",
    "agent_reasoning": "Current reasoning:\nI need to refactor this function...",
    "invoke_agent": "code-reviewer (New session)\nSession: review-auth-abc123",
    "subagent_response": "code-reviewer\nThe code looks good overall...",
    "list_agents": "- code-puppy: Code Puppy 🐶\n- planning-agent: Planning Agent",
}

# Available background colors grouped by theme
BANNER_COLORS = {
    # Cool colors
    "blue": "blue",
    "dark blue": "dark_blue",
    "navy blue": "navy_blue",
    "deep sky blue": "deep_sky_blue4",
    "steel blue": "steel_blue",
    "dodger blue": "dodger_blue3",
    # Cyans & Teals
    "dark cyan": "dark_cyan",
    "cyan": "cyan4",
    "teal": "dark_turquoise",
    "aquamarine": "aquamarine1",
    # Greens
    "green": "green4",
    "dark green": "dark_green",
    "sea green": "dark_sea_green4",
    "spring green": "spring_green4",
    "chartreuse": "chartreuse4",
    # Purples & Magentas
    "purple": "purple",
    "dark magenta": "dark_magenta",
    "medium purple": "medium_purple4",
    "dark violet": "dark_violet",
    "plum": "plum4",
    "orchid": "dark_orchid",
    # Reds & Oranges
    "red": "red3",
    "dark red": "dark_red",
    "indian red": "indian_red",
    "orange red": "orange_red1",
    "orange": "dark_orange3",
    # Yellows & Golds
    "gold": "gold3",
    "dark goldenrod": "dark_goldenrod",
    "olive": "dark_olive_green3",
    # Grays
    "grey30": "grey30",
    "grey37": "grey37",
    "grey42": "grey42",
    "grey50": "grey50",
    "grey58": "grey58",
    "dark slate gray": "dark_slate_gray3",
    # Pink tones
    "hot pink": "hot_pink3",
    "deep pink": "deep_pink4",
    "pale violet red": "pale_violet_red1",
}


class ColorConfiguration:
    """Holds the current banner color configuration state."""

    def __init__(self):
        """Initialize configuration from current settings."""
        from code_puppy.config import get_all_banner_colors

        self.current_colors = get_all_banner_colors()
        self.original_colors = self.current_colors.copy()
        self.selected_banner_index = 0
        self.banner_keys = list(BANNER_DISPLAY_INFO.keys())

    def has_changes(self) -> bool:
        """Check if any changes have been made."""
        return self.current_colors != self.original_colors

    def get_current_banner_key(self) -> str:
        """Get the currently selected banner key."""
        return self.banner_keys[self.selected_banner_index]

    def get_current_banner_color(self) -> str:
        """Get the color of the currently selected banner."""
        return self.current_colors[self.get_current_banner_key()]

    def set_current_banner_color(self, color: str):
        """Set the color of the currently selected banner."""
        self.current_colors[self.get_current_banner_key()] = color

    def next_banner(self):
        """Cycle to the next banner."""
        self.selected_banner_index = (self.selected_banner_index + 1) % len(
            self.banner_keys
        )

    def prev_banner(self):
        """Cycle to the previous banner."""
        self.selected_banner_index = (self.selected_banner_index - 1) % len(
            self.banner_keys
        )


async def interactive_colors_picker() -> Optional[dict]:
    """Show an interactive full-screen terminal UI to configure banner colors.

    Returns:
        A dict with changes or None if cancelled
    """
    from code_puppy.tools.command_runner import set_awaiting_user_input

    config = ColorConfiguration()

    set_awaiting_user_input(True)

    # Enter alternate screen buffer once for entire session
    sys.stdout.write("\033[?1049h")  # Enter alternate buffer
    sys.stdout.write("\033[2J\033[H")  # Clear and home
    sys.stdout.flush()
    time.sleep(0.1)  # Minimal delay for state sync

    try:
        # Main menu loop
        while True:
            choices = []
            for key in config.banner_keys:
                display_name, icon = BANNER_DISPLAY_INFO[key]
                current_color = config.current_colors[key]
                choices.append(f"{display_name} [{current_color}]")

            # Add action items
            if config.has_changes():
                choices.append("─── Actions ───")
                choices.append("💾 Save & Exit")
                choices.append("🔄 Reset All to Defaults")
                choices.append("❌ Discard & Exit")
            else:
                choices.append("─── Actions ───")
                choices.append("🔄 Reset All to Defaults")
                choices.append("❌ Exit")

            def dummy_update(choice: str):
                pass

            def get_main_preview():
                return _get_preview_text_for_prompt_toolkit(config)

            try:
                selected = await _split_panel_selector(
                    "Banner Color Configuration",
                    choices,
                    dummy_update,
                    get_preview=get_main_preview,
                    config=config,
                )
            except KeyboardInterrupt:
                break

            # Handle selection
            if selected is None:
                break
            elif "Save & Exit" in selected:
                break
            elif "Reset All" in selected:
                from code_puppy.config import DEFAULT_BANNER_COLORS

                config.current_colors = DEFAULT_BANNER_COLORS.copy()
            elif "Discard" in selected or selected == "❌ Exit":
                config.current_colors = config.original_colors.copy()
                break
            elif "───" in selected:
                # Separator - do nothing
                pass
            else:
                # A banner was selected - show color picker
                # Find which banner was selected
                for i, key in enumerate(config.banner_keys):
                    display_name, _ = BANNER_DISPLAY_INFO[key]
                    if selected.startswith(display_name):
                        config.selected_banner_index = i
                        await _handle_color_menu(config)
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
        return config.current_colors

    return None


async def _split_panel_selector(
    title: str,
    choices: list[str],
    on_change: Callable[[str], None],
    get_preview: Callable[[], ANSI],
    config: Optional[ColorConfiguration] = None,
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

            if not choices:
                lines.append(("fg:ansiyellow", "No choices available"))
                lines.append(("", "\n"))
            else:
                for i, choice in enumerate(choices):
                    # Skip separator lines for selection highlighting
                    if "───" in choice:
                        lines.append(("fg:ansigray", f"  {choice}"))
                        lines.append(("", "\n"))
                    elif i == selected_index[0]:
                        lines.append(("fg:ansigreen", "▶ "))
                        lines.append(("fg:ansigreen bold", choice))
                        lines.append(("", "\n"))
                    else:
                        lines.append(("", "  "))
                        lines.append(("", choice))
                        lines.append(("", "\n"))

            lines.append(("", "\n"))
            lines.append(
                ("fg:ansicyan", "↑↓ Navigate  │  Enter Select  │  Ctrl-C Cancel")
            )
            return FormattedText(lines)
        except Exception as e:
            return FormattedText([("fg:ansired", f"Error: {e}")])

    def get_right_panel_text():
        """Generate the preview panel text."""
        try:
            preview = get_preview()
            return preview
        except Exception as e:
            return FormattedText([("fg:ansired", f"Preview error: {e}")])

    kb = KeyBindings()

    @kb.add("up")
    def move_up(event):
        if choices:
            # Skip separator lines
            new_idx = (selected_index[0] - 1) % len(choices)
            while "───" in choices[new_idx]:
                new_idx = (new_idx - 1) % len(choices)
            selected_index[0] = new_idx
            on_change(choices[selected_index[0]])
        event.app.invalidate()

    @kb.add("down")
    def move_down(event):
        if choices:
            # Skip separator lines
            new_idx = (selected_index[0] + 1) % len(choices)
            while "───" in choices[new_idx]:
                new_idx = (new_idx + 1) % len(choices)
            selected_index[0] = new_idx
            on_change(choices[selected_index[0]])
        event.app.invalidate()

    @kb.add("enter")
    def accept(event):
        if choices:
            result[0] = choices[selected_index[0]]
        else:
            result[0] = None
        event.app.exit()

    @kb.add("c-c")
    def cancel(event):
        result[0] = None
        event.app.exit()

    # Create split layout with left (selector) and right (preview) panels
    left_panel = Window(
        content=FormattedTextControl(lambda: get_left_panel_text()),
        width=45,
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
        full_screen=False,
        mouse_support=False,
        color_depth="DEPTH_24_BIT",
    )

    sys.stdout.flush()

    # Trigger initial update only if choices is not empty
    if choices:
        on_change(choices[selected_index[0]])

    # Clear the current buffer
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

    # Run application
    await app.run_async()

    if result[0] is None:
        raise KeyboardInterrupt()

    return result[0]


def _get_preview_text_for_prompt_toolkit(config: ColorConfiguration) -> ANSI:
    """Get preview as ANSI for embedding in selector with live colors.

    Returns ANSI-formatted text that prompt_toolkit can render with full colors.
    """
    # Build preview showing all banners with their current colors
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        force_terminal=True,
        width=70,
        legacy_windows=False,
        color_system="truecolor",
        no_color=False,
        force_interactive=True,
    )

    # Header
    console.print("[bold]═" * 60 + "[/bold]")
    console.print("[bold cyan] LIVE PREVIEW - Banner Colors[/bold cyan]")
    console.print("[bold]═" * 60 + "[/bold]")
    console.print()

    # Show each banner with its current color
    for key in config.banner_keys:
        display_name, icon = BANNER_DISPLAY_INFO[key]
        color = config.current_colors[key]
        sample = BANNER_SAMPLE_CONTENT[key]

        # Highlight the currently selected banner
        is_selected = key == config.get_current_banner_key()
        if is_selected:
            console.print("[bold yellow]▶[/bold yellow] ", end="")
        else:
            console.print("  ", end="")

        # Print the banner with its configured color
        icon_str = f" {icon}" if icon else ""
        banner_text = (
            f"[bold white on {color}] {display_name} [/bold white on {color}]{icon_str}"
        )
        console.print(banner_text)

        # Print sample content (dimmed)
        sample_lines = sample.split("\n")
        for line in sample_lines[:2]:  # Only show first 2 lines
            if is_selected:
                console.print(f"    [dim]{line}[/dim]")
            else:
                console.print(f"    [dim]{line}[/dim]")
        console.print()

    console.print("[bold]═" * 60 + "[/bold]")

    ansi_output = buffer.getvalue()
    return ANSI(ansi_output)


async def _handle_color_menu(config: ColorConfiguration) -> None:
    """Handle color selection for the current banner."""
    banner_key = config.get_current_banner_key()
    display_name, _ = BANNER_DISPLAY_INFO[banner_key]
    current_color = config.get_current_banner_color()
    title = f"Select color for {display_name}:"

    # Build choices with color names
    choices = []
    for name, color_value in BANNER_COLORS.items():
        marker = " ← current" if color_value == current_color else ""
        choices.append(f"{name}{marker}")

    # Store original color for potential cancellation
    original_color = current_color

    # Callback for live preview updates
    def update_preview(selected_choice: str):
        color_name = selected_choice.replace(" ← current", "").strip()
        selected_color = BANNER_COLORS.get(color_name, "blue")
        config.set_current_banner_color(selected_color)

    def get_preview_header():
        return _get_single_banner_preview(config)

    try:
        await _split_panel_selector(
            title,
            choices,
            update_preview,
            get_preview=get_preview_header,
            config=config,
        )
    except KeyboardInterrupt:
        # Restore original color on cancel
        config.set_current_banner_color(original_color)
    except Exception:
        pass  # Silent error handling


def _get_single_banner_preview(config: ColorConfiguration) -> ANSI:
    """Get preview for a single banner being edited."""
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        force_terminal=True,
        width=70,
        legacy_windows=False,
        color_system="truecolor",
        no_color=False,
        force_interactive=True,
    )

    banner_key = config.get_current_banner_key()
    display_name, icon = BANNER_DISPLAY_INFO[banner_key]
    color = config.get_current_banner_color()
    sample = BANNER_SAMPLE_CONTENT[banner_key]

    # Header
    console.print("[bold]═" * 60 + "[/bold]")
    console.print(f"[bold cyan] Editing: {display_name}[/bold cyan]")
    console.print(f" Current Color: [bold]{color}[/bold]")
    console.print("[bold]═" * 60 + "[/bold]")
    console.print()

    # Show the banner large
    icon_str = f" {icon}" if icon else ""
    banner_text = (
        f"[bold white on {color}] {display_name} [/bold white on {color}]{icon_str}"
    )
    console.print(banner_text)
    console.print()

    # Show sample content
    console.print("[dim]Sample output:[/dim]")
    for line in sample.split("\n"):
        console.print(f"[dim]{line}[/dim]")

    console.print()
    console.print("[bold]═" * 60 + "[/bold]")

    ansi_output = buffer.getvalue()
    return ANSI(ansi_output)
