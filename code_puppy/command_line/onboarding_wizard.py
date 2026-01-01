"""Interactive TUI onboarding wizard for first-time Code Puppy users.

🐶 Quick 5-slide tutorial. ADHD-friendly!

Usage:
    from code_puppy.command_line.onboarding_wizard import (
        run_onboarding_wizard,
        reset_onboarding,
    )

    result = await run_onboarding_wizard()
    # result: "chatgpt", "claude", "completed", "skipped", or None
"""

import io
import os
import sys
import time
from typing import List, Optional, Tuple

from prompt_toolkit import Application
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame
from rich.console import Console

from code_puppy.config import CONFIG_DIR

from .onboarding_slides import (
    MODEL_OPTIONS,
    slide_done,
    slide_mcp,
    slide_models,
    slide_use_cases,
    slide_welcome,
)

# ============================================================================
# State Tracking
# ============================================================================

ONBOARDING_COMPLETE_FILE = os.path.join(CONFIG_DIR, "onboarding_complete")


def has_completed_onboarding() -> bool:
    """Check if the user has already completed onboarding."""
    return os.path.exists(ONBOARDING_COMPLETE_FILE)


def mark_onboarding_complete() -> None:
    """Mark onboarding as complete."""
    os.makedirs(os.path.dirname(ONBOARDING_COMPLETE_FILE), exist_ok=True)
    with open(ONBOARDING_COMPLETE_FILE, "w") as f:
        f.write("completed\n")


def should_show_onboarding() -> bool:
    """Determine if the onboarding wizard should be shown.

    Returns False if:
    - User has already completed onboarding
    - CODE_PUPPY_SKIP_TUTORIAL env var is set to '1' or 'true'
    """
    # Allow skipping tutorial via environment variable (useful for testing)
    skip_env = os.environ.get("CODE_PUPPY_SKIP_TUTORIAL", "").lower()
    if skip_env in ("1", "true", "yes"):
        return False
    return not has_completed_onboarding()


def reset_onboarding() -> None:
    """Reset onboarding state (for re-running with /tutorial)."""
    if os.path.exists(ONBOARDING_COMPLETE_FILE):
        os.remove(ONBOARDING_COMPLETE_FILE)


# ============================================================================
# Onboarding Wizard Class
# ============================================================================


class OnboardingWizard:
    """5-slide interactive tutorial.

    Slides:
        0: Welcome
        1: Model selection
        2: MCP servers
        3: Use cases (Planning vs Coding)
        4: Done!
    """

    TOTAL_SLIDES = 5

    def __init__(self):
        """Initialize wizard state."""
        self.current_slide = 0
        self.selected_option = 0
        self.trigger_oauth: Optional[str] = None
        self.model_choice: Optional[str] = None
        self.result: Optional[str] = None
        self._should_exit = False

    def get_progress_indicator(self) -> str:
        """Progress dots: ● ○ ○ ○ ○"""
        return " ".join(
            "●" if i == self.current_slide else "○" for i in range(self.TOTAL_SLIDES)
        )

    def get_slide_content(self) -> str:
        """Get content for current slide."""
        if self.current_slide == 0:
            return slide_welcome()
        elif self.current_slide == 1:
            options = self.get_options_for_slide()
            return slide_models(self.selected_option, options)
        elif self.current_slide == 2:
            return slide_mcp()
        elif self.current_slide == 3:
            return slide_use_cases()
        else:  # slide 4
            return slide_done(self.trigger_oauth)

    def get_options_for_slide(self) -> List[Tuple[str, str]]:
        """Get selectable options for current slide."""
        if self.current_slide == 1:  # Model selection
            return [(opt[0], opt[1]) for opt in MODEL_OPTIONS]
        return []

    def handle_option_select(self) -> None:
        """Handle option selection."""
        if self.current_slide == 1:  # Model selection
            options = self.get_options_for_slide()
            if 0 <= self.selected_option < len(options):
                choice_id = options[self.selected_option][0]
                self.model_choice = choice_id
                if choice_id == "chatgpt":
                    self.trigger_oauth = "chatgpt"
                elif choice_id == "claude":
                    self.trigger_oauth = "claude"

    def next_slide(self) -> bool:
        """Move to next slide."""
        if self.current_slide < self.TOTAL_SLIDES - 1:
            self.current_slide += 1
            self.selected_option = 0
            return True
        return False

    def prev_slide(self) -> bool:
        """Move to previous slide."""
        if self.current_slide > 0:
            self.current_slide -= 1
            self.selected_option = 0
            return True
        return False

    def next_option(self) -> None:
        """Move to next option."""
        options = self.get_options_for_slide()
        if options:
            self.selected_option = (self.selected_option + 1) % len(options)

    def prev_option(self) -> None:
        """Move to previous option."""
        options = self.get_options_for_slide()
        if options:
            self.selected_option = (self.selected_option - 1) % len(options)


# ============================================================================
# TUI Rendering
# ============================================================================


def _get_slide_panel_content(wizard: OnboardingWizard) -> ANSI:
    """Generate slide content for display."""
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

    # Progress indicator
    progress = wizard.get_progress_indicator()
    console.print(f"[dim]{progress}[/dim]")
    console.print(
        f"[dim]Slide {wizard.current_slide + 1} of {wizard.TOTAL_SLIDES}[/dim]\n"
    )

    # Slide content (includes nav footer)
    console.print(wizard.get_slide_content())

    return ANSI(buffer.getvalue())


# ============================================================================
# Main Entry Point
# ============================================================================


async def run_onboarding_wizard() -> Optional[str]:
    """Run the interactive tutorial.

    Returns:
        - "chatgpt" if user wants ChatGPT OAuth
        - "claude" if user wants Claude OAuth
        - "completed" if finished normally
        - "skipped" if user pressed ESC
        - None on error
    """
    from code_puppy.tools.command_runner import set_awaiting_user_input

    wizard = OnboardingWizard()
    set_awaiting_user_input(True)

    # Enter alternate screen buffer
    sys.stdout.write("\033[?1049h")  # Enter alternate buffer
    sys.stdout.write("\033[2J\033[H")  # Clear and home
    sys.stdout.flush()
    time.sleep(0.1)

    try:
        kb = KeyBindings()

        @kb.add("right")
        @kb.add("l")
        def next_slide(event):
            if wizard.current_slide == wizard.TOTAL_SLIDES - 1:
                wizard.result = "completed"
                wizard._should_exit = True
                event.app.exit()
            else:
                wizard.next_slide()
            event.app.invalidate()

        @kb.add("left")
        @kb.add("h")
        def prev_slide(event):
            wizard.prev_slide()
            event.app.invalidate()

        @kb.add("down")
        @kb.add("j")
        def next_option(event):
            wizard.next_option()
            event.app.invalidate()

        @kb.add("up")
        @kb.add("k")
        def prev_option(event):
            wizard.prev_option()
            event.app.invalidate()

        @kb.add("enter")
        def select_or_next(event):
            options = wizard.get_options_for_slide()
            if options:
                wizard.handle_option_select()

            if wizard.current_slide == wizard.TOTAL_SLIDES - 1:
                wizard.result = "completed"
                wizard._should_exit = True
                event.app.exit()
            else:
                wizard.next_slide()
            event.app.invalidate()

        @kb.add("escape")
        def skip_wizard(event):
            wizard.result = "skipped"
            wizard._should_exit = True
            event.app.exit()

        @kb.add("c-c")
        def cancel_wizard(event):
            wizard.result = "skipped"
            wizard._should_exit = True
            event.app.exit()

        slide_panel = Window(
            content=FormattedTextControl(lambda: _get_slide_panel_content(wizard))
        )

        root_container = Frame(slide_panel, title="🐶 Code Puppy Tutorial")
        layout = Layout(root_container)

        app = Application(
            layout=layout,
            key_bindings=kb,
            full_screen=False,
            mouse_support=False,
            color_depth="DEPTH_24_BIT",
        )

        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

        await app.run_async()

    except KeyboardInterrupt:
        wizard.result = "skipped"
    except Exception:
        wizard.result = None
    finally:
        set_awaiting_user_input(False)
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()

    # Clear exit message
    from code_puppy.messaging import emit_info

    if wizard.result == "skipped":
        emit_info("✓ Tutorial skipped")
    elif wizard.result == "completed":
        emit_info("✓ Tutorial completed! Welcome to Code Puppy! 🐶")
    else:
        emit_info("✓ Exited tutorial")

    if wizard.result in ("completed", "skipped"):
        mark_onboarding_complete()

    if wizard.trigger_oauth:
        return wizard.trigger_oauth

    return wizard.result


async def run_onboarding_if_needed() -> Optional[str]:
    """Run tutorial if user hasn't seen it yet."""
    if should_show_onboarding():
        return await run_onboarding_wizard()
    return None
